"""A foglalási mag írási rétege: slot-állapot, hold, foglalás.

Minden itteni függvény a `db-hordozhatosag` skill mintáját követi: kapcsolat
`isolation_level=None` (autocommit) módban jön (lásd `migracio.kapcsolat_nyitas`),
minden írás explicit `BEGIN IMMEDIATE` / `COMMIT` / `ROLLBACK` blokkban fut, a
dupla foglalás elleni védelem kizárólag a `foglalas` tábla parciális UNIQUE
indexe (`ix_foglalas_slot_aktiv`, ADR-003) — nem alkalmazásszintű zár vagy
számláló. Minden művelet a végén eseményt ír az `esemenyek` táblába
(foglalasi-mag skill, "Eseménykibocsátás").

Kereszt-szervezeti konzisztencia: egyik függvény sem fogad el `szervezet_id`-t
paraméterként — mindig a hivatkozott sorból (itt: a `slot`-ból) olvassuk ki,
sosem a hívótól kapott, ellenőrizetlen értékből. Ez zárja ki azt a hibaosztályt,
amit a `tesztek/egyseg/test_alapsema.py` xfail tesztje dokumentál (A szervezet
egy sora B szervezet sorára hivatkozik): amíg egy repo-függvény a szülő sorból
származtatja a szervezet_id-t, nem a hívó adja meg külön, addig ez a hiba nem
keletkezhet *ezen az úton*. A varians tábla írási rétege (amikor megíródik)
ugyanezt a mintát kell kövesse ahhoz, hogy az a konkrét xfail teszt is zöldre
váltson — ez a modul csak a mintát mutatja meg, a varians-ra nem terjed ki.
"""

from __future__ import annotations

import json
import secrets
import sqlite3
from enum import Enum

from core.azonosito import new_uuid
from core.ido import most_iso

# A vasarlo_kulcs HMAC-jéhez tartozó pepper-verzió. Amíg nincs önálló
# adatvedelem/ pepper-rotációs modul (lásd CLAUDE.md, "Sérthetetlen
# invariánsok" 2. pont), ez egy dokumentált helyőrző — a hívó feladata,
# hogy a vasarlo_kulcs-ot ezzel a verzióval számítsa ki. Ha a rotáció
# megvalósul, ez a függvényszignatúra explicit kulcs_verzio paramétert kap.
CURRENT_CUSTOMER_KEY_VERSION = 1

# Foglalási kód ábécéje: nincs benne O/0 és I/1 — hangban vagy telefonon
# félreolvasható párok kizárva.
_CODE_ABC = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
_CODE_LENGTH = 8


class Result(Enum):
    """Minden írási művelet ezt adja vissza — sosem kivételt a normál
    versenyhelyzeti ágakra (foglalt slot, ismételt kérés, stb.)."""

    SUCCESS = "sikeres"
    PREEMPTED = "megeloztek"
    NO_ILYEN = "nincs_ilyen"
    ALREADY_CANCELLED = "mar_lemondva"


def _new_booking_code() -> str:
    return "".join(secrets.choice(_CODE_ABC) for _ in range(_CODE_LENGTH))


def _event_write(
    conn: sqlite3.Connection,
    org_id: str,
    tipus: str,
    entity_type: str,
    entity_id: str,
    useful_payload: dict,
) -> None:
    conn.execute(
        "INSERT INTO esemenyek "
        "(id, szervezet_id, tipus, entitas_tipus, entitas_id, idobelyeg, hasznos_teher) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            new_uuid(),
            org_id,
            tipus,
            entity_type,
            entity_id,
            most_iso(),
            json.dumps(useful_payload, ensure_ascii=False),
        ),
    )


def slot_free(conn: sqlite3.Connection, slot_id: str) -> bool:
    """Igaz, ha a slot létezik, nincs rajta MÉG ÉRVÉNYES hold (`lejar` a
    jelen időnél későbbi), és nincs aktív foglalás sem.

    Egy lejárt, de még nem takarított hold NEM számít blokkolónak — a
    takarítás (`lejart_holdok_takaritasa()`) csak a táblát tisztítja,
    magát a szabadságot nem ez dönti el, hanem a `lejar` mező.
    """
    if conn.execute("SELECT 1 FROM slot WHERE id = ?", (slot_id,)).fetchone() is None:
        return False
    has_valid_hold = conn.execute(
        "SELECT 1 FROM hold WHERE slot_id = ? AND lejar > ?", (slot_id, most_iso())
    ).fetchone()
    if has_valid_hold is not None:
        return False
    has_active_booking = conn.execute(
        "SELECT 1 FROM foglalas WHERE slot_id = ? AND allapot <> 'lemondva'", (slot_id,)
    ).fetchone()
    return has_active_booking is None


def hold_create(conn: sqlite3.Connection, slot_id: str, session_id: str, lejar: str) -> Result:
    """Puha zárat tesz egy slotra. Slotonként legfeljebb egy hold ülhet
    (`ix_hold_slot` UNIQUE index) — ha már van MÉG ÉRVÉNYES hold, vagy a
    slot már aktívan foglalt, `MEGELOZTEK`.

    Egy lejárt, de még nem takarított hold nem blokkolhatja az újat: a
    beszúrás előtt, ugyanebben a tranzakcióban töröljük a slot lejárt
    holdjait — így nem kell megvárni a `lejart_holdok_takaritasa()`
    külön ütemezett futását ahhoz, hogy a slot ténylegesen újra
    holdolható legyen."""
    conn.execute("BEGIN IMMEDIATE")
    try:
        row = conn.execute("SELECT szervezet_id FROM slot WHERE id = ?", (slot_id,)).fetchone()
        if row is None:
            conn.execute("ROLLBACK")
            return Result.NO_ILYEN
        (org_id,) = row

        has_active_booking = conn.execute(
            "SELECT 1 FROM foglalas WHERE slot_id = ? AND allapot <> 'lemondva'", (slot_id,)
        ).fetchone()
        if has_active_booking is not None:
            conn.execute("ROLLBACK")
            return Result.PREEMPTED

        most = most_iso()
        conn.execute("DELETE FROM hold WHERE slot_id = ? AND lejar <= ?", (slot_id, most))

        hold_id = new_uuid()
        cur = conn.execute(
            "INSERT INTO hold (id, szervezet_id, slot_id, session_id, letrejott, lejar) "
            "VALUES (?, ?, ?, ?, ?, ?) "
            "ON CONFLICT DO NOTHING",
            (hold_id, org_id, slot_id, session_id, most, lejar),
        )
        if cur.rowcount == 0:
            conn.execute("ROLLBACK")
            return Result.PREEMPTED

        _event_write(
            conn,
            org_id,
            "hold_letrejott",
            "hold",
            hold_id,
            {"slot_id": slot_id, "session_id": session_id},
        )
    except Exception:
        conn.execute("ROLLBACK")
        raise
    else:
        conn.execute("COMMIT")
        return Result.SUCCESS


def hold_list(conn: sqlite3.Connection, *, slot_id: str, session_id: str) -> str | None:
    """Az adott slotra, adott session által tartott hold id-je, vagy
    `None`, ha nincs ilyen — pl. amikor a hívónak (verseny-demó,
    `mag/api/verseny.py`) a saját maga szerezte holdot kell utólag
    felszabadítania, és csak a slot/session párost ismeri."""
    row = conn.execute(
        "SELECT id FROM hold WHERE slot_id = ? AND session_id = ?", (slot_id, session_id)
    ).fetchone()
    return row[0] if row else None


def hold_release(conn: sqlite3.Connection, hold_id: str) -> Result:
    """Egy hold explicit felszabadítása (pl. a vásárló megszakította a
    beszélgetést, mielőtt a hold lejárt volna)."""
    conn.execute("BEGIN IMMEDIATE")
    try:
        row = conn.execute(
            "SELECT szervezet_id, slot_id FROM hold WHERE id = ?", (hold_id,)
        ).fetchone()
        if row is None:
            conn.execute("ROLLBACK")
            return Result.NO_ILYEN
        org_id, slot_id = row

        conn.execute("DELETE FROM hold WHERE id = ?", (hold_id,))
        _event_write(conn, org_id, "hold_felszabadult", "hold", hold_id, {"slot_id": slot_id})
    except Exception:
        conn.execute("ROLLBACK")
        raise
    else:
        conn.execute("COMMIT")
        return Result.SUCCESS


def lejart_holds_cleanup(conn: sqlite3.Connection, most: str) -> list[str]:
    """A `most` (ISO-8601 UTC) időpontnál nem később lejáró holdokat törli.

    Egyetlen tranzakcióban fut, minden törölt holdhoz `hold_lejart` eseményt
    ír (foglalasi-mag skill eseménykatalógusa). Visszaadja a törölt hold-ok
    id-jét.
    """
    conn.execute("BEGIN IMMEDIATE")
    try:
        lejartak = conn.execute(
            "SELECT id, szervezet_id, slot_id FROM hold WHERE lejar <= ?", (most,)
        ).fetchall()
        for hold_id, org_id, slot_id in lejartak:
            _event_write(conn, org_id, "hold_lejart", "hold", hold_id, {"slot_id": slot_id})
        if lejartak:
            conn.execute("DELETE FROM hold WHERE lejar <= ?", (most,))
    except Exception:
        conn.execute("ROLLBACK")
        raise
    else:
        conn.execute("COMMIT")
        return [row[0] for row in lejartak]


def booking_create(
    conn: sqlite3.Connection,
    slot_id: str,
    customer_key: str,
    idempotency_key: str,
    session_id: str,
) -> Result:
    """Foglalást hoz létre. A dupla foglalás elleni EGYETLEN védelem a
    `foglalas` tábla parciális UNIQUE indexe (ADR-003): itt nincs előzetes
    `slot_szabad()`-ellenőrzés, mert az verseny esetén réstelen (TOCTOU)
    lenne — az `INSERT ... ON CONFLICT DO NOTHING` a bizonyíték, nem az,
    hogy előtte "üresnek látszott".

    Ha az `idempotencia_kulcs` már szerepel egy foglaláson (bármilyen
    állapotban), ez megismételt kérés — nem hiba, `SIKERES`-t ad vissza
    új sor létrehozása nélkül.
    """
    conn.execute("BEGIN IMMEDIATE")
    try:
        row = conn.execute("SELECT szervezet_id FROM slot WHERE id = ?", (slot_id,)).fetchone()
        if row is None:
            conn.execute("ROLLBACK")
            return Result.NO_ILYEN
        (org_id,) = row

        booking_id = new_uuid()
        booking_code = _new_booking_code()
        cur = conn.execute(
            "INSERT INTO foglalas "
            "(id, szervezet_id, slot_id, vasarlo_kulcs, kulcs_verzio, "
            "idempotencia_kulcs, foglalasi_kod, allapot, letrehozva) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, 'aktiv', ?) "
            "ON CONFLICT DO NOTHING",
            (
                booking_id,
                org_id,
                slot_id,
                customer_key,
                CURRENT_CUSTOMER_KEY_VERSION,
                idempotency_key,
                booking_code,
                most_iso(),
            ),
        )
        if cur.rowcount == 0:
            # Kétféle ok lehet: (a) ugyanezzel az idempotencia_kulccsal már
            # létrejött egy foglalás — megismételt kérés, ez nem hiba; vagy
            # (b) a slotra időközben más nyert (parciális index ütközés) —
            # valaki megelőzött. A foglalasi_kod ütközése elméletileg
            # lehetséges, de a _KOD_ABC méretével (33^8) gyakorlatilag
            # elhanyagolható, nem kezeljük külön ágként.
            repeated = conn.execute(
                "SELECT 1 FROM foglalas WHERE idempotencia_kulcs = ?", (idempotency_key,)
            ).fetchone()
            conn.execute("ROLLBACK")
            return Result.SUCCESS if repeated is not None else Result.PREEMPTED

        # A slotra ülő hold (ha volt) feleslegessé vált — nincs kettős
        # könyvelés (docs/domain.md, "Hold").
        conn.execute("DELETE FROM hold WHERE slot_id = ?", (slot_id,))

        _event_write(
            conn,
            org_id,
            "foglalas_letrejott",
            "foglalas",
            booking_id,
            {"slot_id": slot_id, "session_id": session_id, "foglalasi_kod": booking_code},
        )
    except Exception:
        conn.execute("ROLLBACK")
        raise
    else:
        conn.execute("COMMIT")
        return Result.SUCCESS


def booking_lemond(conn: sqlite3.Connection, booking_code: str) -> Result:
    """Lemond egy foglalást a foglalási kódja alapján (a számsor nem
    hitelesítő, lásd blueprint 8. szakasz). A slot ettől a pillanattól
    újra foglalható — nincs külön "foglalási ablak" (ADR-008)."""
    conn.execute("BEGIN IMMEDIATE")
    try:
        row = conn.execute(
            "SELECT id, szervezet_id, slot_id, allapot FROM foglalas WHERE foglalasi_kod = ?",
            (booking_code,),
        ).fetchone()
        if row is None:
            conn.execute("ROLLBACK")
            return Result.NO_ILYEN
        booking_id, org_id, slot_id, status = row
        if status == "lemondva":
            conn.execute("ROLLBACK")
            return Result.ALREADY_CANCELLED

        conn.execute("UPDATE foglalas SET allapot = 'lemondva' WHERE id = ?", (booking_id,))
        _event_write(
            conn, org_id, "foglalas_lemondva", "foglalas", booking_id, {"slot_id": slot_id}
        )
        _event_write(
            conn,
            org_id,
            "slot_felszabadult",
            "slot",
            slot_id,
            {"foglalas_id": booking_id},
        )
    except Exception:
        conn.execute("ROLLBACK")
        raise
    else:
        conn.execute("COMMIT")
        return Result.SUCCESS


def free_slots_search(
    conn: sqlite3.Connection,
    *,
    org_id: str,
    shop_id: str | None = None,
    service_id: str | None = None,
) -> list[tuple[str, str, str]]:
    """Szabad — sem MÉG ÉRVÉNYES hold, sem aktív foglalás nélküli —
    slotokat listáz, kezdet szerint rendezve — `(slot_id, kezdet, veg)`
    hármasokként.

    Egy lejárt, de még nem takarított hold NEM zárja ki a slotot (lásd
    `slot_szabad` azonos indoklása).

    Ez NEM az ajánlatpontozó (ADR-006) — puszta, rendezetlen szűrés,
    pontozás/rangsorolás nélkül. A pontozó egy külön, ennél nagyobb
    komponens, ami még nem íródott meg; ez a függvény addig is használható
    egyenes listázásra (pl. a CLI `keres` parancsához).
    """
    rows = conn.execute(
        "SELECT slot.id, slot.kezdet, slot.veg "
        "FROM slot JOIN muszak ON muszak.id = slot.muszak_id "
        "WHERE muszak.szervezet_id = ? "
        "AND (? IS NULL OR muszak.bolt_id = ?) "
        "AND (? IS NULL OR muszak.szolgaltatas_id = ?) "
        "AND NOT EXISTS (SELECT 1 FROM hold WHERE hold.slot_id = slot.id AND hold.lejar > ?) "
        "AND NOT EXISTS ("
        "  SELECT 1 FROM foglalas "
        "  WHERE foglalas.slot_id = slot.id AND foglalas.allapot <> 'lemondva'"
        ") "
        "ORDER BY slot.kezdet",
        (org_id, shop_id, shop_id, service_id, service_id, most_iso()),
    ).fetchall()
    return [(row[0], row[1], row[2]) for row in rows]


def slot_statuses_list(conn: sqlite3.Connection, *, shift_id: str) -> list[dict]:
    """Egy műszak slotjai, kezdet szerint rendezve, mindegyikhez az
    aktuális állapottal ('szabad' | 'holdolt' | 'foglalt') — a naptárnézet
    (`felulet/admin/`) ezzel színez. Egy lejárt, de még nem takarított
    hold NEM számít blokkolónak, ugyanúgy, mint `slot_szabad()`-ban."""
    rows = conn.execute(
        "SELECT slot.id, slot.kezdet, slot.veg, "
        "  (SELECT 1 FROM foglalas WHERE foglalas.slot_id = slot.id "
        "     AND foglalas.allapot <> 'lemondva') AS van_foglalas, "
        "  (SELECT 1 FROM hold WHERE hold.slot_id = slot.id AND hold.lejar > ?) AS van_hold, "
        "  (SELECT foglalasi_kod FROM foglalas WHERE foglalas.slot_id = slot.id "
        "     AND foglalas.allapot <> 'lemondva') AS foglalasi_kod "
        "FROM slot WHERE slot.muszak_id = ? ORDER BY slot.kezdet",
        (most_iso(), shift_id),
    ).fetchall()
    result = []
    for slot_id, start, end, has_booking, has_hold, booking_code in rows:
        if has_booking:
            status = "foglalt"
        elif has_hold:
            status = "holdolt"
        else:
            status = "szabad"
        result.append(
            {
                "slot_id": slot_id,
                "kezdet": start,
                "veg": end,
                "allapot": status,
                "foglalasi_kod": booking_code,
            }
        )
    return result


def bookings_list(
    conn: sqlite3.Connection, *, org_id: str, shop_id: str | None = None
) -> list[dict]:
    """Aktív és lemondott foglalások listája (admin felület, `felulet/admin/`),
    a slot időpontjával és — bolt-szűréshez — a műszak boltjával
    kiegészítve. A `vasarlo_kulcs` szándékosan NEM kerül a visszaadott
    dict-be: az admin felületnek a beosztáshoz nincs rá szüksége, és
    CLAUDE.md 2. invariánsa szerint amúgy is csak HMAC-hash, nyers
    azonosító sosem — de a felesleges expozíció itt is elkerülendő."""
    rows = conn.execute(
        "SELECT f.id, f.foglalasi_kod, f.allapot, f.letrehozva, "
        "s.kezdet, s.veg, m.bolt_id "
        "FROM foglalas f "
        "JOIN slot s ON s.id = f.slot_id "
        "JOIN muszak m ON m.id = s.muszak_id "
        "WHERE f.szervezet_id = ? "
        "AND (? IS NULL OR m.bolt_id = ?) "
        "ORDER BY s.kezdet",
        (org_id, shop_id, shop_id),
    ).fetchall()
    return [
        {
            "foglalas_id": row[0],
            "foglalasi_kod": row[1],
            "allapot": row[2],
            "letrehozva": row[3],
            "slot_kezdet": row[4],
            "slot_veg": row[5],
            "bolt_id": row[6],
        }
        for row in rows
    ]


def booking_query_idempotency_by(conn: sqlite3.Connection, idempotency_key: str) -> dict | None:
    """Egy korábban létrehozott foglalás alapadatai — pl. a CLI `foglal`
    parancsának, hogy a `foglalasi_kod`-ot vissza tudja adni idempotens
    ismétlés esetén is (amikor `foglalas_letrehoz` nem hoz létre új sort)."""
    row = conn.execute(
        "SELECT id, slot_id, foglalasi_kod, allapot FROM foglalas WHERE idempotencia_kulcs = ?",
        (idempotency_key,),
    ).fetchone()
    if row is None:
        return None
    return {"id": row[0], "slot_id": row[1], "foglalasi_kod": row[2], "allapot": row[3]}

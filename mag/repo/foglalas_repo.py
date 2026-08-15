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

from mag.azonosito import uj_uuid
from mag.ido import most_iso

# A vasarlo_kulcs HMAC-jéhez tartozó pepper-verzió. Amíg nincs önálló
# adatvedelem/ pepper-rotációs modul (lásd CLAUDE.md, "Sérthetetlen
# invariánsok" 2. pont), ez egy dokumentált helyőrző — a hívó feladata,
# hogy a vasarlo_kulcs-ot ezzel a verzióval számítsa ki. Ha a rotáció
# megvalósul, ez a függvényszignatúra explicit kulcs_verzio paramétert kap.
AKTUALIS_VASARLO_KULCS_VERZIO = 1

# Foglalási kód ábécéje: nincs benne O/0 és I/1 — hangban vagy telefonon
# félreolvasható párok kizárva.
_KOD_ABC = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
_KOD_HOSSZ = 8


class Eredmeny(Enum):
    """Minden írási művelet ezt adja vissza — sosem kivételt a normál
    versenyhelyzeti ágakra (foglalt slot, ismételt kérés, stb.)."""

    SIKERES = "sikeres"
    MEGELOZTEK = "megeloztek"
    NINCS_ILYEN = "nincs_ilyen"
    MAR_LEMONDVA = "mar_lemondva"


def _uj_foglalasi_kod() -> str:
    return "".join(secrets.choice(_KOD_ABC) for _ in range(_KOD_HOSSZ))


def _esemeny_ir(
    conn: sqlite3.Connection,
    szervezet_id: str,
    tipus: str,
    entitas_tipus: str,
    entitas_id: str,
    hasznos_teher: dict,
) -> None:
    conn.execute(
        "INSERT INTO esemenyek "
        "(id, szervezet_id, tipus, entitas_tipus, entitas_id, idobelyeg, hasznos_teher) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            uj_uuid(),
            szervezet_id,
            tipus,
            entitas_tipus,
            entitas_id,
            most_iso(),
            json.dumps(hasznos_teher, ensure_ascii=False),
        ),
    )


def slot_szabad(conn: sqlite3.Connection, slot_id: str) -> bool:
    """Igaz, ha a slot létezik, és nincs rajta sem hold, sem aktív foglalás.

    Nem néz hold-TTL-t: egy lejárt, de még nem takarított hold is foglaltnak
    számít itt — a takarítás a `lejart_holdok_takaritasa()` dolga, külön
    ütemezve, nem ennek a függvénynek olvasáskor.
    """
    if conn.execute("SELECT 1 FROM slot WHERE id = ?", (slot_id,)).fetchone() is None:
        return False
    if conn.execute("SELECT 1 FROM hold WHERE slot_id = ?", (slot_id,)).fetchone() is not None:
        return False
    van_aktiv_foglalas = conn.execute(
        "SELECT 1 FROM foglalas WHERE slot_id = ? AND allapot <> 'lemondva'", (slot_id,)
    ).fetchone()
    return van_aktiv_foglalas is None


def hold_letrehoz(conn: sqlite3.Connection, slot_id: str, session_id: str, lejar: str) -> Eredmeny:
    """Puha zárat tesz egy slotra. Slotonként legfeljebb egy hold ülhet
    (`ix_hold_slot` UNIQUE index) — ha már van, vagy a slot már aktívan
    foglalt, `MEGELOZTEK`."""
    conn.execute("BEGIN IMMEDIATE")
    try:
        sor = conn.execute("SELECT szervezet_id FROM slot WHERE id = ?", (slot_id,)).fetchone()
        if sor is None:
            conn.execute("ROLLBACK")
            return Eredmeny.NINCS_ILYEN
        (szervezet_id,) = sor

        van_aktiv_foglalas = conn.execute(
            "SELECT 1 FROM foglalas WHERE slot_id = ? AND allapot <> 'lemondva'", (slot_id,)
        ).fetchone()
        if van_aktiv_foglalas is not None:
            conn.execute("ROLLBACK")
            return Eredmeny.MEGELOZTEK

        hold_id = uj_uuid()
        cur = conn.execute(
            "INSERT INTO hold (id, szervezet_id, slot_id, session_id, letrejott, lejar) "
            "VALUES (?, ?, ?, ?, ?, ?) "
            "ON CONFLICT DO NOTHING",
            (hold_id, szervezet_id, slot_id, session_id, most_iso(), lejar),
        )
        if cur.rowcount == 0:
            conn.execute("ROLLBACK")
            return Eredmeny.MEGELOZTEK

        _esemeny_ir(
            conn,
            szervezet_id,
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
        return Eredmeny.SIKERES


def hold_felszabadit(conn: sqlite3.Connection, hold_id: str) -> Eredmeny:
    """Egy hold explicit felszabadítása (pl. a vásárló megszakította a
    beszélgetést, mielőtt a hold lejárt volna)."""
    conn.execute("BEGIN IMMEDIATE")
    try:
        sor = conn.execute(
            "SELECT szervezet_id, slot_id FROM hold WHERE id = ?", (hold_id,)
        ).fetchone()
        if sor is None:
            conn.execute("ROLLBACK")
            return Eredmeny.NINCS_ILYEN
        szervezet_id, slot_id = sor

        conn.execute("DELETE FROM hold WHERE id = ?", (hold_id,))
        _esemeny_ir(conn, szervezet_id, "hold_felszabadult", "hold", hold_id, {"slot_id": slot_id})
    except Exception:
        conn.execute("ROLLBACK")
        raise
    else:
        conn.execute("COMMIT")
        return Eredmeny.SIKERES


def lejart_holdok_takaritasa(conn: sqlite3.Connection, most: str) -> list[str]:
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
        for hold_id, szervezet_id, slot_id in lejartak:
            _esemeny_ir(conn, szervezet_id, "hold_lejart", "hold", hold_id, {"slot_id": slot_id})
        if lejartak:
            conn.execute("DELETE FROM hold WHERE lejar <= ?", (most,))
    except Exception:
        conn.execute("ROLLBACK")
        raise
    else:
        conn.execute("COMMIT")
        return [sor[0] for sor in lejartak]


def foglalas_letrehoz(
    conn: sqlite3.Connection,
    slot_id: str,
    vasarlo_kulcs: str,
    idempotencia_kulcs: str,
    session_id: str,
) -> Eredmeny:
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
        sor = conn.execute("SELECT szervezet_id FROM slot WHERE id = ?", (slot_id,)).fetchone()
        if sor is None:
            conn.execute("ROLLBACK")
            return Eredmeny.NINCS_ILYEN
        (szervezet_id,) = sor

        foglalas_id = uj_uuid()
        foglalasi_kod = _uj_foglalasi_kod()
        cur = conn.execute(
            "INSERT INTO foglalas "
            "(id, szervezet_id, slot_id, vasarlo_kulcs, kulcs_verzio, "
            "idempotencia_kulcs, foglalasi_kod, allapot, letrehozva) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, 'aktiv', ?) "
            "ON CONFLICT DO NOTHING",
            (
                foglalas_id,
                szervezet_id,
                slot_id,
                vasarlo_kulcs,
                AKTUALIS_VASARLO_KULCS_VERZIO,
                idempotencia_kulcs,
                foglalasi_kod,
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
            ismetelt = conn.execute(
                "SELECT 1 FROM foglalas WHERE idempotencia_kulcs = ?", (idempotencia_kulcs,)
            ).fetchone()
            conn.execute("ROLLBACK")
            return Eredmeny.SIKERES if ismetelt is not None else Eredmeny.MEGELOZTEK

        # A slotra ülő hold (ha volt) feleslegessé vált — nincs kettős
        # könyvelés (docs/domain.md, "Hold").
        conn.execute("DELETE FROM hold WHERE slot_id = ?", (slot_id,))

        _esemeny_ir(
            conn,
            szervezet_id,
            "foglalas_letrejott",
            "foglalas",
            foglalas_id,
            {"slot_id": slot_id, "session_id": session_id, "foglalasi_kod": foglalasi_kod},
        )
    except Exception:
        conn.execute("ROLLBACK")
        raise
    else:
        conn.execute("COMMIT")
        return Eredmeny.SIKERES


def foglalas_lemond(conn: sqlite3.Connection, foglalasi_kod: str) -> Eredmeny:
    """Lemond egy foglalást a foglalási kódja alapján (a számsor nem
    hitelesítő, lásd blueprint 8. szakasz). A slot ettől a pillanattól
    újra foglalható — nincs külön "foglalási ablak" (ADR-008)."""
    conn.execute("BEGIN IMMEDIATE")
    try:
        sor = conn.execute(
            "SELECT id, szervezet_id, slot_id, allapot FROM foglalas WHERE foglalasi_kod = ?",
            (foglalasi_kod,),
        ).fetchone()
        if sor is None:
            conn.execute("ROLLBACK")
            return Eredmeny.NINCS_ILYEN
        foglalas_id, szervezet_id, slot_id, allapot = sor
        if allapot == "lemondva":
            conn.execute("ROLLBACK")
            return Eredmeny.MAR_LEMONDVA

        conn.execute("UPDATE foglalas SET allapot = 'lemondva' WHERE id = ?", (foglalas_id,))
        _esemeny_ir(
            conn, szervezet_id, "foglalas_lemondva", "foglalas", foglalas_id, {"slot_id": slot_id}
        )
        _esemeny_ir(
            conn,
            szervezet_id,
            "slot_felszabadult",
            "slot",
            slot_id,
            {"foglalas_id": foglalas_id},
        )
    except Exception:
        conn.execute("ROLLBACK")
        raise
    else:
        conn.execute("COMMIT")
        return Eredmeny.SIKERES


def szabad_slotok_keresese(
    conn: sqlite3.Connection,
    *,
    szervezet_id: str,
    bolt_id: str | None = None,
    szolgaltatas_id: str | None = None,
) -> list[tuple[str, str, str]]:
    """Szabad (sem hold, sem aktív foglalás nélküli) slotokat listáz,
    kezdet szerint rendezve — `(slot_id, kezdet, veg)` hármasokként.

    Ez NEM az ajánlatpontozó (ADR-006) — puszta, rendezetlen szűrés,
    pontozás/rangsorolás nélkül. A pontozó egy külön, ennél nagyobb
    komponens, ami még nem íródott meg; ez a függvény addig is használható
    egyenes listázásra (pl. a CLI `keres` parancsához).
    """
    sorok = conn.execute(
        "SELECT slot.id, slot.kezdet, slot.veg "
        "FROM slot JOIN muszak ON muszak.id = slot.muszak_id "
        "WHERE muszak.szervezet_id = ? "
        "AND (? IS NULL OR muszak.bolt_id = ?) "
        "AND (? IS NULL OR muszak.szolgaltatas_id = ?) "
        "AND NOT EXISTS (SELECT 1 FROM hold WHERE hold.slot_id = slot.id) "
        "AND NOT EXISTS ("
        "  SELECT 1 FROM foglalas "
        "  WHERE foglalas.slot_id = slot.id AND foglalas.allapot <> 'lemondva'"
        ") "
        "ORDER BY slot.kezdet",
        (szervezet_id, bolt_id, bolt_id, szolgaltatas_id, szolgaltatas_id),
    ).fetchall()
    return [(sor[0], sor[1], sor[2]) for sor in sorok]


def foglalas_lekerdezes_idempotencia_szerint(
    conn: sqlite3.Connection, idempotencia_kulcs: str
) -> dict | None:
    """Egy korábban létrehozott foglalás alapadatai — pl. a CLI `foglal`
    parancsának, hogy a `foglalasi_kod`-ot vissza tudja adni idempotens
    ismétlés esetén is (amikor `foglalas_letrehoz` nem hoz létre új sort)."""
    sor = conn.execute(
        "SELECT id, slot_id, foglalasi_kod, allapot FROM foglalas WHERE idempotencia_kulcs = ?",
        (idempotencia_kulcs,),
    ).fetchone()
    if sor is None:
        return None
    return {"id": sor[0], "slot_id": sor[1], "foglalasi_kod": sor[2], "allapot": sor[3]}

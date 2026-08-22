"""A `muszak`, `muszak_blokk`, `slot` táblák írási/olvasási rétege.

Ez a modul köti össze a `mag/slot/` tiszta generáló logikáját (`Muszak`,
`Blokk`, `Slot` dataclass-ok) a ténylegesen SQL-t tartalmazó táblákkal — a
generátor maga nem ismeri a `sqlite3` modult (CLAUDE.md, 5. invariáns).
"""

from __future__ import annotations

import json
import sqlite3

from core.azonosito import new_uuid
from core.ido import most_iso
from core.modell.shift import Block, Shift, Slot


def shift_create(
    conn: sqlite3.Connection,
    *,
    org_id: str,
    shop_id: str,
    counter_id: str,
    employee_id: str,
    service_id: str,
    start: str,
    end: str,
    duration_minute: int,
    buffer_after_minute: int,
    min_grid_minute: int,
    bookable_ratio: float,
    block_rule: dict,
    id_: str | None = None,
) -> str:
    shift_id = id_ or new_uuid()
    conn.execute(
        "INSERT INTO muszak "
        "(id, szervezet_id, bolt_id, pult_id, alkalmazott_id, szolgaltatas_id, "
        "kezdet, veg, idotartam_perc, puffer_utana_perc, min_racs_perc, "
        "foglalhato_arany, blokk_szabaly, allapot, letrehozva) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'aktiv', ?)",
        (
            shift_id,
            org_id,
            shop_id,
            counter_id,
            employee_id,
            service_id,
            start,
            end,
            duration_minute,
            buffer_after_minute,
            min_grid_minute,
            bookable_ratio,
            json.dumps(block_rule, ensure_ascii=False),
            most_iso(),
        ),
    )
    return shift_id


def shift_load(conn: sqlite3.Connection, shift_id: str) -> Shift | None:
    row = conn.execute(
        "SELECT id, szervezet_id, kezdet, veg, idotartam_perc, puffer_utana_perc, "
        "min_racs_perc, foglalhato_arany, blokk_szabaly FROM muszak WHERE id = ?",
        (shift_id,),
    ).fetchone()
    if row is None:
        return None
    (
        mid,
        org_id,
        start,
        end,
        duration_minute,
        buffer_after_minute,
        min_grid_minute,
        bookable_ratio,
        block_rule_json,
    ) = row
    return Shift(
        id=mid,
        org_id=org_id,
        start=start,
        end=end,
        duration_minute=duration_minute,
        buffer_after_minute=buffer_after_minute,
        min_grid_minute=min_grid_minute,
        bookable_ratio=bookable_ratio,
        block_rule=json.loads(block_rule_json),
    )


def shift_alapadatai(conn: sqlite3.Connection, *, shift_id: str) -> dict | None:
    """A `muszak_betoltese`-nél bővebb, nyers sor — a törzsadat-kapcsoló
    oszlopokkal (`bolt_id`, `pult_id`, `alkalmazott_id`, `szolgaltatas_id`)
    is, amiket a `Muszak` dataclass szándékosan nem tartalmaz (a
    slotgenerátor tiszta számítás, nem kell neki a törzsadat-kapocs).
    Ez a lekérdezés a sablon-mentéshez kell (`mag/api/adminszolgaltatas.py`),
    ahol pont ezekre a kapcsoló oszlopokra van szükség."""
    row = conn.execute(
        "SELECT szervezet_id, bolt_id, pult_id, alkalmazott_id, szolgaltatas_id, kezdet, veg, "
        "idotartam_perc, puffer_utana_perc, min_racs_perc, foglalhato_arany, blokk_szabaly "
        "FROM muszak WHERE id = ?",
        (shift_id,),
    ).fetchone()
    if row is None:
        return None
    (
        org_id,
        shop_id,
        counter_id,
        employee_id,
        service_id,
        start,
        end,
        duration_minute,
        buffer_after_minute,
        min_grid_minute,
        bookable_ratio,
        block_rule_json,
    ) = row
    return {
        "szervezet_id": org_id,
        "bolt_id": shop_id,
        "pult_id": counter_id,
        "alkalmazott_id": employee_id,
        "szolgaltatas_id": service_id,
        "kezdet": start,
        "veg": end,
        "idotartam_perc": duration_minute,
        "puffer_utana_perc": buffer_after_minute,
        "min_racs_perc": min_grid_minute,
        "foglalhato_arany": bookable_ratio,
        "blokk_szabaly": json.loads(block_rule_json),
    }


def blocks_slots_save(
    conn: sqlite3.Connection,
    *,
    shift_id: str,
    org_id: str,
    blocks: list[Block],
    slots: list[Slot],
) -> None:
    """Egyetlen `BEGIN IMMEDIATE` tranzakcióban menti a generált
    blokkokat és slotokat — vagy mindkettő teljesen bekerül, vagy semmi."""
    conn.execute("BEGIN IMMEDIATE")
    try:
        for b in blocks:
            conn.execute(
                "INSERT INTO muszak_blokk "
                "(id, szervezet_id, muszak_id, tipus, kezdet, veg, rogzitett, "
                "beszamit_kvotaba, letrehozva) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    new_uuid(),
                    org_id,
                    shift_id,
                    b.tipus,
                    b.start,
                    b.end,
                    int(b.fixed),
                    int(b.counts_toward_into_quota),
                    most_iso(),
                ),
            )
        for s in slots:
            conn.execute(
                "INSERT INTO slot (id, szervezet_id, muszak_id, kezdet, veg, letrehozva) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (new_uuid(), org_id, shift_id, s.start, s.end, most_iso()),
            )
    except Exception:
        conn.execute("ROLLBACK")
        raise
    else:
        conn.execute("COMMIT")


def shifts_list(
    conn: sqlite3.Connection,
    *,
    org_id: str,
    shop_id: str | None = None,
    date_tol: str | None = None,
    date_ig: str | None = None,
) -> list[dict]:
    """Műszakok listája egy időablakban (naptárnézethez, `felulet/admin/`),
    bolt/pult/alkalmazott/szolgáltatás névvel kiegészítve — a felület nem
    kap nyers azonosítót mutatni valót, olvasható nevet kap.

    `datum_tol`/`datum_ig` a `muszak.kezdet` oszlopra szűr (ISO-8601 UTC
    időbélyeg-előtag egyezés is elég, pl. csak a dátumrész). A slotszámot
    is visszaadja (aloszekvenciás lekérdezéssel), hogy a naptárnézet
    üresen generált (kivetel_nap miatt kihagyott) műszakot is meg tudjon
    különböztetni."""
    rows = conn.execute(
        "SELECT m.id, m.bolt_id, b.nev, m.pult_id, p.nev, m.alkalmazott_id, a.nev, "
        "m.szolgaltatas_id, sz.nev, m.kezdet, m.veg, m.allapot, "
        "(SELECT COUNT(*) FROM slot WHERE slot.muszak_id = m.id) AS slot_szam "
        "FROM muszak m "
        "JOIN bolt b ON b.id = m.bolt_id "
        "JOIN pult p ON p.id = m.pult_id "
        "JOIN alkalmazott a ON a.id = m.alkalmazott_id "
        "JOIN szolgaltatas sz ON sz.id = m.szolgaltatas_id "
        "WHERE m.szervezet_id = ? "
        "AND (? IS NULL OR m.bolt_id = ?) "
        "AND (? IS NULL OR m.kezdet >= ?) "
        "AND (? IS NULL OR m.kezdet < ?) "
        "ORDER BY m.kezdet",
        (org_id, shop_id, shop_id, date_tol, date_tol, date_ig, date_ig),
    ).fetchall()
    return [
        {
            "muszak_id": row[0],
            "bolt_id": row[1],
            "bolt_nev": row[2],
            "pult_id": row[3],
            "pult_nev": row[4],
            "alkalmazott_id": row[5],
            "alkalmazott_nev": row[6],
            "szolgaltatas_id": row[7],
            "szolgaltatas_nev": row[8],
            "kezdet": row[9],
            "veg": row[10],
            "allapot": row[11],
            "slot_szam": row[12],
        }
        for row in rows
    ]


def blocks_list(conn: sqlite3.Connection, *, shift_id: str) -> list[dict]:
    """Egy műszak blokkjai (szünet/ebéd/szabad sáv), kezdet szerint
    rendezve — a naptárnézet ezekkel rajzolja ki a slotok közti réseket."""
    rows = conn.execute(
        "SELECT tipus, kezdet, veg, rogzitett, beszamit_kvotaba "
        "FROM muszak_blokk WHERE muszak_id = ? ORDER BY kezdet",
        (shift_id,),
    ).fetchall()
    return [
        {
            "tipus": row[0],
            "kezdet": row[1],
            "veg": row[2],
            "rogzitett": bool(row[3]),
            "beszamit_kvotaba": bool(row[4]),
        }
        for row in rows
    ]


def exception_days_list(
    conn: sqlite3.Connection, *, org_id: str, shop_id: str | None = None
) -> frozenset[str]:
    """A szervezet-szintű (`bolt_id IS NULL`) és a megadott bolt szintű
    kivételnapok dátumainak uniója, `YYYY-MM-DD` szövegként."""
    rows = conn.execute(
        "SELECT datum FROM kivetel_nap WHERE szervezet_id = ? AND (bolt_id IS NULL OR bolt_id = ?)",
        (org_id, shop_id),
    ).fetchall()
    return frozenset(row[0] for row in rows)


def slot_range(conn: sqlite3.Connection, *, org_id: str) -> dict | None:
    """Melyik időszakra és MELYIK BOLTOKRA van egyáltalán generált slot
    ebben a szervezetben — `{"elso_nap": "2026-12-21", "utolso_nap":
    "2026-12-27", "boltok": ["Törpilla"]}`, vagy `None`, ha nincs egy
    slot sem.

    Ez nem ütemezési logika, hanem **tájékozódás**: a felületnek tudnia
    kell, hol keressen. A `ui/vasarlo.py` ebből tölti ki a nap-választó
    alapértékét és az indító sort ("A demóadat ... hetére szól, beosztás
    a Törpilla boltban van") — enélkül a vásárlói felület a mai naptól,
    tetszőleges boltban keresne, a demóadat pedig egy fix, távoli hétre
    és EGYETLEN boltra szól, tehát minden keresés üresen térne vissza.
    Az üres találat ilyenkor helyes viselkedés, csak épp
    megkülönböztethetetlen a hibától — ezt a megkülönböztetést adja ez a
    függvény.

    A `slot.kezdet` ISO-8601 UTC szöveg, ezért a `MIN`/`MAX` szöveges
    összehasonlítása helyes rendezést ad (fix hosszú, nullákkal feltöltött
    alak) — nincs szükség dátum-függvényre, ami motoronként eltérne
    (db-hordozhatosag skill)."""
    row = conn.execute(
        "SELECT MIN(kezdet), MAX(kezdet) FROM slot WHERE szervezet_id = ?",
        (org_id,),
    ).fetchone()
    if row is None or row[0] is None:
        return None
    boltok = conn.execute(
        "SELECT DISTINCT b.nev FROM slot s "
        "JOIN muszak m ON m.id = s.muszak_id "
        "JOIN bolt b ON b.id = m.bolt_id "
        "WHERE s.szervezet_id = ? ORDER BY b.nev",
        (org_id,),
    ).fetchall()
    return {
        "elso_nap": row[0][:10],
        "utolso_nap": row[1][:10],
        "boltok": [sor[0] for sor in boltok],
    }

"""A `muszak`, `muszak_blokk`, `slot` táblák írási/olvasási rétege.

Ez a modul köti össze a `mag/slot/` tiszta generáló logikáját (`Muszak`,
`Blokk`, `Slot` dataclass-ok) a ténylegesen SQL-t tartalmazó táblákkal — a
generátor maga nem ismeri a `sqlite3` modult (CLAUDE.md, 5. invariáns).
"""

from __future__ import annotations

import json
import sqlite3

from mag.azonosito import uj_uuid
from mag.ido import most_iso
from mag.modell.muszak import Blokk, Muszak, Slot


def muszak_letrehoz(
    conn: sqlite3.Connection,
    *,
    szervezet_id: str,
    bolt_id: str,
    pult_id: str,
    alkalmazott_id: str,
    szolgaltatas_id: str,
    kezdet: str,
    veg: str,
    idotartam_perc: int,
    puffer_utana_perc: int,
    min_racs_perc: int,
    foglalhato_arany: float,
    blokk_szabaly: dict,
    id_: str | None = None,
) -> str:
    muszak_id = id_ or uj_uuid()
    conn.execute(
        "INSERT INTO muszak "
        "(id, szervezet_id, bolt_id, pult_id, alkalmazott_id, szolgaltatas_id, "
        "kezdet, veg, idotartam_perc, puffer_utana_perc, min_racs_perc, "
        "foglalhato_arany, blokk_szabaly, allapot, letrehozva) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'aktiv', ?)",
        (
            muszak_id,
            szervezet_id,
            bolt_id,
            pult_id,
            alkalmazott_id,
            szolgaltatas_id,
            kezdet,
            veg,
            idotartam_perc,
            puffer_utana_perc,
            min_racs_perc,
            foglalhato_arany,
            json.dumps(blokk_szabaly, ensure_ascii=False),
            most_iso(),
        ),
    )
    return muszak_id


def muszak_betoltese(conn: sqlite3.Connection, muszak_id: str) -> Muszak | None:
    sor = conn.execute(
        "SELECT id, szervezet_id, kezdet, veg, idotartam_perc, puffer_utana_perc, "
        "min_racs_perc, foglalhato_arany, blokk_szabaly FROM muszak WHERE id = ?",
        (muszak_id,),
    ).fetchone()
    if sor is None:
        return None
    (
        mid,
        szervezet_id,
        kezdet,
        veg,
        idotartam_perc,
        puffer_utana_perc,
        min_racs_perc,
        foglalhato_arany,
        blokk_szabaly_json,
    ) = sor
    return Muszak(
        id=mid,
        szervezet_id=szervezet_id,
        kezdet=kezdet,
        veg=veg,
        idotartam_perc=idotartam_perc,
        puffer_utana_perc=puffer_utana_perc,
        min_racs_perc=min_racs_perc,
        foglalhato_arany=foglalhato_arany,
        blokk_szabaly=json.loads(blokk_szabaly_json),
    )


def blokkok_slotok_mentese(
    conn: sqlite3.Connection,
    *,
    muszak_id: str,
    szervezet_id: str,
    blokkok: list[Blokk],
    slotok: list[Slot],
) -> None:
    """Egyetlen `BEGIN IMMEDIATE` tranzakcióban menti a generált
    blokkokat és slotokat — vagy mindkettő teljesen bekerül, vagy semmi."""
    conn.execute("BEGIN IMMEDIATE")
    try:
        for b in blokkok:
            conn.execute(
                "INSERT INTO muszak_blokk "
                "(id, szervezet_id, muszak_id, tipus, kezdet, veg, rogzitett, "
                "beszamit_kvotaba, letrehozva) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    uj_uuid(),
                    szervezet_id,
                    muszak_id,
                    b.tipus,
                    b.kezdet,
                    b.veg,
                    int(b.rogzitett),
                    int(b.beszamit_kvotaba),
                    most_iso(),
                ),
            )
        for s in slotok:
            conn.execute(
                "INSERT INTO slot (id, szervezet_id, muszak_id, kezdet, veg, letrehozva) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (uj_uuid(), szervezet_id, muszak_id, s.kezdet, s.veg, most_iso()),
            )
    except Exception:
        conn.execute("ROLLBACK")
        raise
    else:
        conn.execute("COMMIT")


def muszakok_lekerdezese(
    conn: sqlite3.Connection,
    *,
    szervezet_id: str,
    bolt_id: str | None = None,
    datum_tol: str | None = None,
    datum_ig: str | None = None,
) -> list[dict]:
    """Műszakok listája egy időablakban (naptárnézethez, `felulet/admin/`),
    bolt/pult/alkalmazott/szolgáltatás névvel kiegészítve — a felület nem
    kap nyers azonosítót mutatni valót, olvasható nevet kap.

    `datum_tol`/`datum_ig` a `muszak.kezdet` oszlopra szűr (ISO-8601 UTC
    időbélyeg-előtag egyezés is elég, pl. csak a dátumrész). A slotszámot
    is visszaadja (aloszekvenciás lekérdezéssel), hogy a naptárnézet
    üresen generált (kivetel_nap miatt kihagyott) műszakot is meg tudjon
    különböztetni."""
    sorok = conn.execute(
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
        (szervezet_id, bolt_id, bolt_id, datum_tol, datum_tol, datum_ig, datum_ig),
    ).fetchall()
    return [
        {
            "muszak_id": sor[0],
            "bolt_id": sor[1],
            "bolt_nev": sor[2],
            "pult_id": sor[3],
            "pult_nev": sor[4],
            "alkalmazott_id": sor[5],
            "alkalmazott_nev": sor[6],
            "szolgaltatas_id": sor[7],
            "szolgaltatas_nev": sor[8],
            "kezdet": sor[9],
            "veg": sor[10],
            "allapot": sor[11],
            "slot_szam": sor[12],
        }
        for sor in sorok
    ]


def blokkok_lekerdezese(conn: sqlite3.Connection, *, muszak_id: str) -> list[dict]:
    """Egy műszak blokkjai (szünet/ebéd/szabad sáv), kezdet szerint
    rendezve — a naptárnézet ezekkel rajzolja ki a slotok közti réseket."""
    sorok = conn.execute(
        "SELECT tipus, kezdet, veg, rogzitett, beszamit_kvotaba "
        "FROM muszak_blokk WHERE muszak_id = ? ORDER BY kezdet",
        (muszak_id,),
    ).fetchall()
    return [
        {
            "tipus": sor[0],
            "kezdet": sor[1],
            "veg": sor[2],
            "rogzitett": bool(sor[3]),
            "beszamit_kvotaba": bool(sor[4]),
        }
        for sor in sorok
    ]


def kivetel_napok_lekerdezese(
    conn: sqlite3.Connection, *, szervezet_id: str, bolt_id: str | None = None
) -> frozenset[str]:
    """A szervezet-szintű (`bolt_id IS NULL`) és a megadott bolt szintű
    kivételnapok dátumainak uniója, `YYYY-MM-DD` szövegként."""
    sorok = conn.execute(
        "SELECT datum FROM kivetel_nap WHERE szervezet_id = ? AND (bolt_id IS NULL OR bolt_id = ?)",
        (szervezet_id, bolt_id),
    ).fetchall()
    return frozenset(sor[0] for sor in sorok)

"""A `muszak_sablon` tábla írási/olvasási rétege (migraciok/0003).

Egy sablon egy elmentett, dátumtól független műszak-recept: pult,
alkalmazott, szolgáltatás, napi óra-időablak, snapshot-mezők és
blokkszabály. Az alkalmazás (konkrét napra/hétre való ráhelyezés) a
`mag/api/adminszolgaltatas.py` dolga — ez a modul csak CRUD-szerű
lekérdezés, ugyanúgy, ahogy a `torzsadat_repo.py` sem versenyhelyzeti út.
"""

from __future__ import annotations

import json
import sqlite3

from mag.azonosito import uj_uuid
from mag.ido import most_iso


def sablon_letrehoz(
    conn: sqlite3.Connection,
    *,
    szervezet_id: str,
    nev: str,
    bolt_id: str,
    pult_id: str,
    alkalmazott_id: str,
    szolgaltatas_id: str,
    kezdet_ora: int,
    veg_ora: int,
    idotartam_perc: int,
    puffer_utana_perc: int,
    min_racs_perc: int,
    foglalhato_arany: float,
    blokk_szabaly: dict,
    id_: str | None = None,
) -> str:
    sablon_id = id_ or uj_uuid()
    conn.execute(
        "INSERT INTO muszak_sablon "
        "(id, szervezet_id, nev, bolt_id, pult_id, alkalmazott_id, szolgaltatas_id, "
        "kezdet_ora, veg_ora, idotartam_perc, puffer_utana_perc, min_racs_perc, "
        "foglalhato_arany, blokk_szabaly, letrehozva) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            sablon_id,
            szervezet_id,
            nev,
            bolt_id,
            pult_id,
            alkalmazott_id,
            szolgaltatas_id,
            kezdet_ora,
            veg_ora,
            idotartam_perc,
            puffer_utana_perc,
            min_racs_perc,
            foglalhato_arany,
            json.dumps(blokk_szabaly, ensure_ascii=False),
            most_iso(),
        ),
    )
    return sablon_id


def sablon_betoltese(conn: sqlite3.Connection, *, sablon_id: str) -> dict | None:
    sor = conn.execute(
        "SELECT id, szervezet_id, nev, bolt_id, pult_id, alkalmazott_id, szolgaltatas_id, "
        "kezdet_ora, veg_ora, idotartam_perc, puffer_utana_perc, min_racs_perc, "
        "foglalhato_arany, blokk_szabaly "
        "FROM muszak_sablon WHERE id = ?",
        (sablon_id,),
    ).fetchone()
    if sor is None:
        return None
    return _sorbol_dict(sor)


def sablonok_lekerdezese(
    conn: sqlite3.Connection, *, szervezet_id: str, bolt_id: str | None = None
) -> list[dict]:
    """Sablonok listája (admin felület, sablon-választó), névre rendezve."""
    sorok = conn.execute(
        "SELECT id, szervezet_id, nev, bolt_id, pult_id, alkalmazott_id, szolgaltatas_id, "
        "kezdet_ora, veg_ora, idotartam_perc, puffer_utana_perc, min_racs_perc, "
        "foglalhato_arany, blokk_szabaly "
        "FROM muszak_sablon WHERE szervezet_id = ? AND (? IS NULL OR bolt_id = ?) ORDER BY nev",
        (szervezet_id, bolt_id, bolt_id),
    ).fetchall()
    return [_sorbol_dict(sor) for sor in sorok]


def _sorbol_dict(sor) -> dict:
    (
        sablon_id,
        szervezet_id,
        nev,
        bolt_id,
        pult_id,
        alkalmazott_id,
        szolgaltatas_id,
        kezdet_ora,
        veg_ora,
        idotartam_perc,
        puffer_utana_perc,
        min_racs_perc,
        foglalhato_arany,
        blokk_szabaly_json,
    ) = sor
    return {
        "id": sablon_id,
        "szervezet_id": szervezet_id,
        "nev": nev,
        "bolt_id": bolt_id,
        "pult_id": pult_id,
        "alkalmazott_id": alkalmazott_id,
        "szolgaltatas_id": szolgaltatas_id,
        "kezdet_ora": kezdet_ora,
        "veg_ora": veg_ora,
        "idotartam_perc": idotartam_perc,
        "puffer_utana_perc": puffer_utana_perc,
        "min_racs_perc": min_racs_perc,
        "foglalhato_arany": foglalhato_arany,
        "blokk_szabaly": json.loads(blokk_szabaly_json),
    }

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

from core.azonosito import new_uuid
from core.ido import most_iso


def template_create(
    conn: sqlite3.Connection,
    *,
    org_id: str,
    name: str,
    shop_id: str,
    counter_id: str,
    employee_id: str,
    service_id: str,
    start_hour: int,
    end_hour: int,
    duration_minute: int,
    buffer_after_minute: int,
    min_grid_minute: int,
    bookable_ratio: float,
    block_rule: dict,
    id_: str | None = None,
) -> str:
    template_id = id_ or new_uuid()
    conn.execute(
        "INSERT INTO muszak_sablon "
        "(id, szervezet_id, nev, bolt_id, pult_id, alkalmazott_id, szolgaltatas_id, "
        "kezdet_ora, veg_ora, idotartam_perc, puffer_utana_perc, min_racs_perc, "
        "foglalhato_arany, blokk_szabaly, letrehozva) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            template_id,
            org_id,
            name,
            shop_id,
            counter_id,
            employee_id,
            service_id,
            start_hour,
            end_hour,
            duration_minute,
            buffer_after_minute,
            min_grid_minute,
            bookable_ratio,
            json.dumps(block_rule, ensure_ascii=False),
            most_iso(),
        ),
    )
    return template_id


def template_load(conn: sqlite3.Connection, *, template_id: str) -> dict | None:
    row = conn.execute(
        "SELECT id, szervezet_id, nev, bolt_id, pult_id, alkalmazott_id, szolgaltatas_id, "
        "kezdet_ora, veg_ora, idotartam_perc, puffer_utana_perc, min_racs_perc, "
        "foglalhato_arany, blokk_szabaly "
        "FROM muszak_sablon WHERE id = ?",
        (template_id,),
    ).fetchone()
    if row is None:
        return None
    return _from_row_dict(row)


def templates_list(
    conn: sqlite3.Connection, *, org_id: str, shop_id: str | None = None
) -> list[dict]:
    """Sablonok listája (admin felület, sablon-választó), névre rendezve."""
    rows = conn.execute(
        "SELECT id, szervezet_id, nev, bolt_id, pult_id, alkalmazott_id, szolgaltatas_id, "
        "kezdet_ora, veg_ora, idotartam_perc, puffer_utana_perc, min_racs_perc, "
        "foglalhato_arany, blokk_szabaly "
        "FROM muszak_sablon WHERE szervezet_id = ? AND (? IS NULL OR bolt_id = ?) ORDER BY nev",
        (org_id, shop_id, shop_id),
    ).fetchall()
    return [_from_row_dict(row) for row in rows]


def _from_row_dict(row) -> dict:
    (
        template_id,
        org_id,
        name,
        shop_id,
        counter_id,
        employee_id,
        service_id,
        start_hour,
        end_hour,
        duration_minute,
        buffer_after_minute,
        min_grid_minute,
        bookable_ratio,
        block_rule_json,
    ) = row
    return {
        "id": template_id,
        "szervezet_id": org_id,
        "nev": name,
        "bolt_id": shop_id,
        "pult_id": counter_id,
        "alkalmazott_id": employee_id,
        "szolgaltatas_id": service_id,
        "kezdet_ora": start_hour,
        "veg_ora": end_hour,
        "idotartam_perc": duration_minute,
        "puffer_utana_perc": buffer_after_minute,
        "min_racs_perc": min_grid_minute,
        "foglalhato_arany": bookable_ratio,
        "blokk_szabaly": json.loads(block_rule_json),
    }

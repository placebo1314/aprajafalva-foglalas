"""A törzsadat-táblák (szervezet, bolt, pult, alkalmazott, szolgaltatas,
kivetel_nap) írási rétege. Lásd migraciok/0001_alapsema.sql.

Egyszerű, egysoros beszúró függvények — ezeket a `seed/betolt.py` és
egy jövőbeli admin-felület repo-rétege használja. Nincs bennük
konkurenciakezelés, mert a törzsadat írása nem versenyhelyzeti út
(szemben a `foglalas_repo.py`-val).
"""

from __future__ import annotations

import sqlite3

from mag.azonosito import uj_uuid
from mag.ido import most_iso


def szervezet_letrehoz(
    conn: sqlite3.Connection, *, nev: str, idozona: str, id_: str | None = None
) -> str:
    szervezet_id = id_ or uj_uuid()
    conn.execute(
        "INSERT INTO szervezet (id, nev, idozona, letrehozva) VALUES (?, ?, ?, ?)",
        (szervezet_id, nev, idozona, most_iso()),
    )
    return szervezet_id


def bolt_letrehoz(
    conn: sqlite3.Connection, *, szervezet_id: str, nev: str, id_: str | None = None
) -> str:
    bolt_id = id_ or uj_uuid()
    conn.execute(
        "INSERT INTO bolt (id, szervezet_id, nev, letrehozva) VALUES (?, ?, ?, ?)",
        (bolt_id, szervezet_id, nev, most_iso()),
    )
    return bolt_id


def pult_letrehoz(
    conn: sqlite3.Connection,
    *,
    szervezet_id: str,
    bolt_id: str,
    nev: str,
    id_: str | None = None,
) -> str:
    pult_id = id_ or uj_uuid()
    conn.execute(
        "INSERT INTO pult (id, szervezet_id, bolt_id, nev, letrehozva) VALUES (?, ?, ?, ?, ?)",
        (pult_id, szervezet_id, bolt_id, nev, most_iso()),
    )
    return pult_id


def alkalmazott_letrehoz(
    conn: sqlite3.Connection,
    *,
    szervezet_id: str,
    bolt_id: str,
    nev: str,
    id_: str | None = None,
) -> str:
    alkalmazott_id = id_ or uj_uuid()
    conn.execute(
        "INSERT INTO alkalmazott (id, szervezet_id, bolt_id, nev, letrehozva) "
        "VALUES (?, ?, ?, ?, ?)",
        (alkalmazott_id, szervezet_id, bolt_id, nev, most_iso()),
    )
    return alkalmazott_id


def szolgaltatas_letrehoz(
    conn: sqlite3.Connection,
    *,
    szervezet_id: str,
    bolt_id: str,
    nev: str,
    alap_idotartam_perc: int,
    id_: str | None = None,
) -> str:
    szolgaltatas_id = id_ or uj_uuid()
    conn.execute(
        "INSERT INTO szolgaltatas "
        "(id, szervezet_id, bolt_id, nev, alap_idotartam_perc, letrehozva) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (szolgaltatas_id, szervezet_id, bolt_id, nev, alap_idotartam_perc, most_iso()),
    )
    return szolgaltatas_id


def boltok_lekerdezese(conn: sqlite3.Connection, *, szervezet_id: str) -> list[dict]:
    """Egy szervezet boltjai, névre rendezve — az admin felület (`felulet/admin/`)
    bolt-választójának való listázás."""
    sorok = conn.execute(
        "SELECT id, nev FROM bolt WHERE szervezet_id = ? ORDER BY nev", (szervezet_id,)
    ).fetchall()
    return [{"id": sor[0], "nev": sor[1]} for sor in sorok]


def pultok_lekerdezese(conn: sqlite3.Connection, *, bolt_id: str) -> list[dict]:
    """Egy bolt pultjai, névre rendezve."""
    sorok = conn.execute(
        "SELECT id, nev FROM pult WHERE bolt_id = ? ORDER BY nev", (bolt_id,)
    ).fetchall()
    return [{"id": sor[0], "nev": sor[1]} for sor in sorok]


def alkalmazottak_lekerdezese(conn: sqlite3.Connection, *, bolt_id: str) -> list[dict]:
    """Egy bolt alkalmazottai, névre rendezve."""
    sorok = conn.execute(
        "SELECT id, nev FROM alkalmazott WHERE bolt_id = ? ORDER BY nev", (bolt_id,)
    ).fetchall()
    return [{"id": sor[0], "nev": sor[1]} for sor in sorok]


def szolgaltatasok_lekerdezese(conn: sqlite3.Connection, *, bolt_id: str) -> list[dict]:
    """Egy bolt szolgáltatásai, névre rendezve."""
    sorok = conn.execute(
        "SELECT id, nev, alap_idotartam_perc FROM szolgaltatas WHERE bolt_id = ? ORDER BY nev",
        (bolt_id,),
    ).fetchall()
    return [{"id": sor[0], "nev": sor[1], "alap_idotartam_perc": sor[2]} for sor in sorok]


def kivetel_nap_letrehoz(
    conn: sqlite3.Connection,
    *,
    szervezet_id: str,
    bolt_id: str | None,
    datum: str,
    indok: str,
    id_: str | None = None,
) -> str:
    kivetel_id = id_ or uj_uuid()
    conn.execute(
        "INSERT INTO kivetel_nap (id, szervezet_id, bolt_id, datum, indok, letrehozva) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (kivetel_id, szervezet_id, bolt_id, datum, indok, most_iso()),
    )
    return kivetel_id

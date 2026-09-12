"""A törzsadat-táblák (szervezet, bolt, pult, alkalmazott, szolgaltatas,
kivetel_nap) írási rétege. Lásd migraciok/0001_alapsema.sql.

Egyszerű, egysoros beszúró függvények — ezeket a `seed/betolt.py` és
egy jövőbeli admin-felület repo-rétege használja. Nincs bennük
konkurenciakezelés, mert a törzsadat írása nem versenyhelyzeti út
(szemben a `foglalas_repo.py`-val).
"""

from __future__ import annotations

import sqlite3

from core.azonosito import new_uuid
from core.ido import most_iso


def org_create(
    conn: sqlite3.Connection, *, name: str, timezone: str, id_: str | None = None
) -> str:
    org_id = id_ or new_uuid()
    conn.execute(
        "INSERT INTO szervezet (id, nev, idozona, letrehozva) VALUES (?, ?, ?, ?)",
        (org_id, name, timezone, most_iso()),
    )
    return org_id


def org_load(conn: sqlite3.Connection, org_id: str) -> dict | None:
    """Egy szervezet alapadatai — az ajánlatpontozónak (`core/api/ajanlatpontozo.py`)
    kell hozzá az `idozona`, hogy a `napszak` (délelőtt/délután/este) a
    helyi óra szerint értelmezhető legyen."""
    row = conn.execute("SELECT id, nev, idozona FROM szervezet WHERE id = ?", (org_id,)).fetchone()
    if row is None:
        return None
    return {"id": row[0], "nev": row[1], "idozona": row[2]}


def shop_create(conn: sqlite3.Connection, *, org_id: str, name: str, id_: str | None = None) -> str:
    shop_id = id_ or new_uuid()
    conn.execute(
        "INSERT INTO bolt (id, szervezet_id, nev, letrehozva) VALUES (?, ?, ?, ?)",
        (shop_id, org_id, name, most_iso()),
    )
    return shop_id


def counter_create(
    conn: sqlite3.Connection,
    *,
    org_id: str,
    shop_id: str,
    name: str,
    id_: str | None = None,
) -> str:
    counter_id = id_ or new_uuid()
    conn.execute(
        "INSERT INTO pult (id, szervezet_id, bolt_id, nev, letrehozva) VALUES (?, ?, ?, ?, ?)",
        (counter_id, org_id, shop_id, name, most_iso()),
    )
    return counter_id


def employee_create(
    conn: sqlite3.Connection,
    *,
    org_id: str,
    shop_id: str,
    name: str,
    id_: str | None = None,
) -> str:
    employee_id = id_ or new_uuid()
    conn.execute(
        "INSERT INTO alkalmazott (id, szervezet_id, bolt_id, nev, letrehozva) "
        "VALUES (?, ?, ?, ?, ?)",
        (employee_id, org_id, shop_id, name, most_iso()),
    )
    return employee_id


def service_create(
    conn: sqlite3.Connection,
    *,
    org_id: str,
    shop_id: str,
    name: str,
    alap_duration_minute: int,
    id_: str | None = None,
) -> str:
    service_id = id_ or new_uuid()
    conn.execute(
        "INSERT INTO szolgaltatas "
        "(id, szervezet_id, bolt_id, nev, alap_idotartam_perc, letrehozva) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (service_id, org_id, shop_id, name, alap_duration_minute, most_iso()),
    )
    return service_id


def orgs_list(conn: sqlite3.Connection) -> list[dict]:
    """Az összes szervezet, névre rendezve — az admin felület
    (`felulet/admin/`) induláskori szervezet-választójának."""
    rows = conn.execute("SELECT id, nev FROM szervezet ORDER BY nev").fetchall()
    return [{"id": row[0], "nev": row[1]} for row in rows]


def shops_list(conn: sqlite3.Connection, *, org_id: str) -> list[dict]:
    """Egy szervezet boltjai, névre rendezve — az admin felület (`felulet/admin/`)
    bolt-választójának való listázás."""
    rows = conn.execute(
        "SELECT id, nev FROM bolt WHERE szervezet_id = ? ORDER BY nev", (org_id,)
    ).fetchall()
    return [{"id": row[0], "nev": row[1]} for row in rows]


def shop_load(conn: sqlite3.Connection, shop_id: str) -> dict | None:
    """Egy bolt részletei, a `megjelenes` mezővel együtt — a `bolt_info`
    eszköznek kell (docs/blueprint.md 10. szakasz, "Bolti tudás"). A
    `shops_list()` szándékosan nem tartalmazza ezt: az a legördülő-
    listázásnak elég, ez a részletes lekérdezés (ugyanaz a minta, mint
    `orgs_list()` vs. `org_load()`)."""
    row = conn.execute("SELECT id, nev, megjelenes FROM bolt WHERE id = ?", (shop_id,)).fetchone()
    if row is None:
        return None
    return {"id": row[0], "nev": row[1], "megjelenes": row[2]}


def counters_list(conn: sqlite3.Connection, *, shop_id: str) -> list[dict]:
    """Egy bolt pultjai, névre rendezve."""
    rows = conn.execute(
        "SELECT id, nev FROM pult WHERE bolt_id = ? ORDER BY nev", (shop_id,)
    ).fetchall()
    return [{"id": row[0], "nev": row[1]} for row in rows]


def employees_list(conn: sqlite3.Connection, *, shop_id: str) -> list[dict]:
    """Egy bolt alkalmazottai, névre rendezve."""
    rows = conn.execute(
        "SELECT id, nev FROM alkalmazott WHERE bolt_id = ? ORDER BY nev", (shop_id,)
    ).fetchall()
    return [{"id": row[0], "nev": row[1]} for row in rows]


def services_list(conn: sqlite3.Connection, *, shop_id: str) -> list[dict]:
    """Egy bolt szolgáltatásai, névre rendezve. A `termekleiras`/`ar`
    (docs/blueprint.md 10. szakasz, "Bolti tudás") üres string, ha nincs
    megadva — ez a `bolt_info` eszköznek jelzi, hogy nincs tényleges
    válasz, nem NULL-ellenőrzést igényel."""
    rows = conn.execute(
        "SELECT id, nev, alap_idotartam_perc, termekleiras, ar, koznyelvi_nevek "
        "FROM szolgaltatas WHERE bolt_id = ? ORDER BY nev",
        (shop_id,),
    ).fetchall()
    return [
        {
            "id": row[0],
            "nev": row[1],
            "alap_idotartam_perc": row[2],
            "termekleiras": row[3],
            "ar": row[4],
            # KÖZNYELVI NEVEK: ahogy a VÁSÁRLÓ hívja (0005. migráció).
            # Listaként adjuk vissza, nem nyers stringként — a tárolási
            # alak (vesszős lista) a séma dolga, a hívóé a lista.
            "koznyelvi_nevek": _koznyelvi_lista(row[5]),
        }
        for row in rows
    ]


def _koznyelvi_lista(nyers: str | None) -> list[str]:
    """A vesszővel tárolt köznyelvi nevek listája, üresek nélkül."""
    return [resz.strip() for resz in (nyers or "").split(",") if resz.strip()]


def exception_day_create(
    conn: sqlite3.Connection,
    *,
    org_id: str,
    shop_id: str | None,
    date: str,
    reason: str,
    id_: str | None = None,
) -> str:
    exception_id = id_ or new_uuid()
    conn.execute(
        "INSERT INTO kivetel_nap (id, szervezet_id, bolt_id, datum, indok, letrehozva) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (exception_id, org_id, shop_id, date, reason, most_iso()),
    )
    return exception_id


def exception_days_in_detail_list(
    conn: sqlite3.Connection, *, org_id: str, shop_id: str | None = None
) -> list[dict]:
    """A `kivetel_napok_lekerdezese` (muszak_repo.py) csak a dátumok
    halmazát adja (a generátornak csak az kell) — ez itt a teljes sort
    adja vissza (id, indok is), az admin felület listázásához."""
    rows = conn.execute(
        "SELECT id, bolt_id, datum, indok FROM kivetel_nap "
        "WHERE szervezet_id = ? AND (bolt_id IS NULL OR bolt_id = ?) ORDER BY datum",
        (org_id, shop_id),
    ).fetchall()
    return [{"id": row[0], "bolt_id": row[1], "datum": row[2], "indok": row[3]} for row in rows]


# --- szerkesztés (nev, ill. szolgaltatasnal alap_idotartam_perc is) ------
#
# Csak a leíró mezőket engedjük szerkeszteni — az FK-kapcsolatok (bolt_id,
# szervezet_id) átírása kaszkádoló következményekkel járna (meglévő
# műszakok/sablonok mutatnának "áthelyezett" sorra), ez explicit döntést
# és valószínűleg ADR-t igényelne, nem ide tartozik.


def shop_update(conn: sqlite3.Connection, *, shop_id: str, name: str) -> None:
    conn.execute("UPDATE bolt SET nev = ? WHERE id = ?", (name, shop_id))


def shop_description_update(conn: sqlite3.Connection, *, shop_id: str, megjelenes: str) -> None:
    """A "Bolti tudás" mező (docs/blueprint.md 10. szakasz) — külön
    függvény a névátnevezéstől (`shop_update`), mert az admin felületen
    is külön mező, külön mentés-gomb: a leírás szerkesztése nem igényel
    egyidejű névváltoztatást."""
    conn.execute("UPDATE bolt SET megjelenes = ? WHERE id = ?", (megjelenes, shop_id))


def counter_update(conn: sqlite3.Connection, *, counter_id: str, name: str) -> None:
    conn.execute("UPDATE pult SET nev = ? WHERE id = ?", (name, counter_id))


def employee_update(conn: sqlite3.Connection, *, employee_id: str, name: str) -> None:
    conn.execute("UPDATE alkalmazott SET nev = ? WHERE id = ?", (name, employee_id))


def service_update(
    conn: sqlite3.Connection, *, service_id: str, name: str, alap_duration_minute: int
) -> None:
    conn.execute(
        "UPDATE szolgaltatas SET nev = ?, alap_idotartam_perc = ? WHERE id = ?",
        (name, alap_duration_minute, service_id),
    )


def service_koznyelvi_update(
    conn: sqlite3.Connection, *, service_id: str, nevek: list[str]
) -> None:
    """A köznyelvi nevek (0005. migráció) — ahogy a VÁSÁRLÓ hívja a
    szolgáltatást. Külön függvény, mert külön szerkesztői döntés: a
    boltnak nem kell hozzányúlnia a leíráshoz ahhoz, hogy felvegyen egy
    új szinonimát."""
    conn.execute(
        "UPDATE szolgaltatas SET koznyelvi_nevek = ? WHERE id = ?",
        (", ".join(nev.strip() for nev in nevek if nev.strip()), service_id),
    )


def service_description_update(
    conn: sqlite3.Connection, *, service_id: str, termekleiras: str, ar: str
) -> None:
    """A "Bolti tudás" mezők (docs/blueprint.md 10. szakasz) — külön
    függvény a `service_update`-től, ugyanazért, mint a bolt leírásánál:
    a leírás/ár szerkesztése nem igényel egyidejű név-/időtartam-
    változtatást."""
    conn.execute(
        "UPDATE szolgaltatas SET termekleiras = ?, ar = ? WHERE id = ?",
        (termekleiras, ar, service_id),
    )

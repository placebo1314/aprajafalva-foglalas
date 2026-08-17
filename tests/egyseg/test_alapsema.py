"""Egységtesztek a 0001_alapsema migrációra.

Minden teszt saját, ideiglenes SQLite fájlon fut (`tmp_path` pytest
fixture), tiszta állapotból indul, és a migrációt előbb lefuttatja.
"""

from __future__ import annotations

import sqlite3
import uuid

import pytest

from core.repo import migracio

_MOST = "2026-08-15T10:00:00Z"


def _uuid() -> str:
    return uuid.uuid4().hex


@pytest.fixture
def db_path(tmp_path) -> str:
    return str(tmp_path / "teszt.db")


@pytest.fixture
def conn(db_path):
    conn = migracio.conn_nyitas(db_path)
    migracio.migral(conn)
    yield conn
    conn.close()


def _org_insert(conn: sqlite3.Connection) -> str:
    org_id = _uuid()
    conn.execute(
        "INSERT INTO szervezet (id, nev, idozona, letrehozva) VALUES (?, ?, ?, ?)",
        (org_id, "Aprajafalva", "Europe/Budapest", _MOST),
    )
    return org_id


def _shop_insert(conn: sqlite3.Connection, org_id: str, name: str = "Bolt") -> str:
    shop_id = _uuid()
    conn.execute(
        "INSERT INTO bolt (id, szervezet_id, nev, letrehozva) VALUES (?, ?, ?, ?)",
        (shop_id, org_id, name, _MOST),
    )
    return shop_id


def _service_insert(conn: sqlite3.Connection, org_id: str, shop_id: str) -> str:
    service_id = _uuid()
    conn.execute(
        "INSERT INTO szolgaltatas "
        "(id, szervezet_id, bolt_id, nev, alap_idotartam_perc, letrehozva) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (service_id, org_id, shop_id, "kis petárda", 5, _MOST),
    )
    return service_id


def test_migration_up_creates_week_master_data_tablat(conn):
    tablak = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    elvart = {
        "szervezet",
        "bolt",
        "pult",
        "alkalmazott",
        "szolgaltatas",
        "varians",
        "kivetel_nap",
    }
    assert elvart <= tablak


def test_rollback_fully_restore(db_path):
    conn = migracio.conn_nyitas(db_path)
    ran = migracio.migral(conn)
    rolled_back = migracio.rollback(conn)

    # A visszagörgetés fordított sorrendben pontosan a lefuttatott
    # migrációkat görgeti vissza — nem kötjük konkrét migrációszámhoz,
    # mert az újakkal bővülni fog.
    assert rolled_back == list(reversed(ran))

    tablak = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    conn.close()

    # A sema_verzio a migrációs rendszer saját nyilvántartása, nem
    # migrációból jön (lásd mag/repo/migracio.py), ezért down után is
    # megmarad — de üresen, hiszen minden migráció sora törlődött.
    assert tablak == {"sema_verzio"}


def test_fk_constraint_rejects_nonexistent_reference(conn):
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO bolt (id, szervezet_id, nev, letrehozva) VALUES (?, ?, ?, ?)",
            (_uuid(), _uuid(), "Bolt egy nemlétező szervezetben", _MOST),
        )


def test_variant_duration_feluliras_not_fillable_ki(conn):
    org_id = _org_insert(conn)
    shop_id = _shop_insert(conn, org_id)
    service_id = _service_insert(conn, org_id, shop_id)

    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO varians "
            "(id, szervezet_id, szolgaltatas_id, nev, idotartam_feluliras, letrehozva) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (_uuid(), org_id, service_id, "piros", 10, _MOST),
        )

    # NULL viszont megengedett — ez a normál, elvárt eset.
    conn.execute(
        "INSERT INTO varians "
        "(id, szervezet_id, szolgaltatas_id, nev, idotartam_feluliras, letrehozva) "
        "VALUES (?, ?, ?, ?, NULL, ?)",
        (_uuid(), org_id, service_id, "piros", _MOST),
    )


@pytest.mark.xfail(
    reason=(
        "A kereszt-szervezeti hivatkozást a séma önmagában nem szűri ki. "
        "A mag/repo/ írási függvényeinek kell majd ellenőrizniük, hogy egy "
        "beszúrt/módosított sor szervezet_id-je megegyezik a hivatkozott "
        "sorok szervezet_id-jével — ez még nem íródott meg."
    ),
    strict=True,
)
def test_cross_org_reference_ma_not_bukik_el(conn):
    """A séma nem köti össze DB-szinten a `varians.szervezet_id`-t a
    hivatkozott `szolgaltatas.szervezet_id`-vel — ezt a
    migraciok/0001_alapsema.sql fejléc-kommentje is jelzi. Ez a teszt azt
    az elvárt viselkedést írja le, hogy A szervezet egy variánsa nem
    hivatkozhatna B szervezet szolgáltatására; ma ez sikeresen beszúrható,
    ezért a teszt xfail — amint a mag/repo/ írási rétege ezt kikényszeríti,
    a teszt átfordul, és a `strict=True` miatt ez hibaként jelzi, hogy az
    xfail jelölést el kell távolítani.
    """
    org = _org_insert(conn)
    b_org = _org_insert(conn)

    b_shop = _shop_insert(conn, b_org, "B bolt")
    b_service = _service_insert(conn, b_org, b_shop)

    # A varians A szervezet szervezet_id-jét kapja, de B szervezet
    # szolgáltatására hivatkozik — üzletileg értelmetlen kombináció.
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO varians "
            "(id, szervezet_id, szolgaltatas_id, nev, letrehozva) "
            "VALUES (?, ?, ?, ?, ?)",
            (_uuid(), org, b_service, "kereszt-szervezeti", _MOST),
        )

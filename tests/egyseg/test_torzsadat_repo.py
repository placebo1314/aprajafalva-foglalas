"""Egységtesztek a mag/repo/torzsadat_repo.py olvasó (listázó) függvényeire.

Az író függvényeket (`*_letrehoz`) a `test_seed.py` már közvetetten fedi —
itt kifejezetten az admin felület (`felulet/admin/`) és a demo-verseny
(`mag/api/verseny.py`) kiszolgálására írt lekérdezéseket teszteljük: üres
eredmény, egy elem, több elem (névre rendezve), és a bolt/szervezet
szerinti szűrés.
"""

from __future__ import annotations

import uuid

import pytest

from core.repo import migracio, torzsadat_repo

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


@pytest.fixture
def org(conn) -> str:
    return torzsadat_repo.org_create(conn, name="Aprajafalva", timezone="UTC")


@pytest.fixture
def shop(conn, org) -> str:
    return torzsadat_repo.shop_create(conn, org_id=org, name="Ügyifogyi")


# --- szervezetek_lekerdezese -----------------------------------------------


def test_orgs_list_empty(conn):
    assert torzsadat_repo.orgs_list(conn) == []


def test_orgs_list_one_elem(conn, org):
    result = torzsadat_repo.orgs_list(conn)
    assert result == [{"id": org, "nev": "Aprajafalva"}]


def test_orgs_list_multiple_elem_name_rendezve(conn):
    torzsadat_repo.org_create(conn, name="Zebra Kft", timezone="UTC")
    torzsadat_repo.org_create(conn, name="Aprajafalva", timezone="UTC")
    names = [s["nev"] for s in torzsadat_repo.orgs_list(conn)]
    assert names == ["Aprajafalva", "Zebra Kft"]


# --- boltok_lekerdezese ------------------------------------------------


def test_shops_list_empty(conn, org):
    assert torzsadat_repo.shops_list(conn, org_id=org) == []


def test_shops_list_one_elem(conn, org, shop):
    result = torzsadat_repo.shops_list(conn, org_id=org)
    assert result == [{"id": shop, "nev": "Ügyifogyi"}]


def test_shops_list_multiple_elem_name_rendezve(conn, org):
    torzsadat_repo.shop_create(conn, org_id=org, name="Törpilla")
    torzsadat_repo.shop_create(conn, org_id=org, name="Szundi")
    names = [b["nev"] for b in torzsadat_repo.shops_list(conn, org_id=org)]
    assert names == ["Szundi", "Törpilla"]


def test_shops_list_filter_org_by(conn, org, shop):
    other_org = torzsadat_repo.org_create(conn, name="Másik", timezone="UTC")
    torzsadat_repo.shop_create(conn, org_id=other_org, name="Idegen bolt")
    result = torzsadat_repo.shops_list(conn, org_id=org)
    assert result == [{"id": shop, "nev": "Ügyifogyi"}]


def test_shop_load_ures_megjelenes_alapertelmezetten(conn, shop):
    assert torzsadat_repo.shop_load(conn, shop) == {
        "id": shop,
        "nev": "Ügyifogyi",
        "megjelenes": "",
    }


def test_shop_load_szerkesztett_megjelenes(conn, shop):
    conn.execute("UPDATE bolt SET megjelenes = ? WHERE id = ?", ("kék tábla", shop))
    assert torzsadat_repo.shop_load(conn, shop) == {
        "id": shop,
        "nev": "Ügyifogyi",
        "megjelenes": "kék tábla",
    }


def test_shop_load_nemletezo_none(conn):
    assert torzsadat_repo.shop_load(conn, "nemletezo") is None


def test_shop_description_update(conn, shop):
    torzsadat_repo.shop_description_update(conn, shop_id=shop, megjelenes="sárga tető")
    assert torzsadat_repo.shop_load(conn, shop)["megjelenes"] == "sárga tető"


def test_service_description_update(conn, org, shop):
    service_id = torzsadat_repo.service_create(
        conn, org_id=org, shop_id=shop, name="petárda", alap_duration_minute=5
    )
    torzsadat_repo.service_description_update(
        conn, service_id=service_id, termekleiras="durranó", ar="100 arany"
    )
    result = torzsadat_repo.services_list(conn, shop_id=shop)
    assert result == [
        {
            "id": service_id,
            "nev": "petárda",
            "alap_idotartam_perc": 5,
            "termekleiras": "durranó",
            "ar": "100 arany",
        }
    ]


# --- pultok_lekerdezese --------------------------------------------------


def test_counters_list_empty(conn, shop):
    assert torzsadat_repo.counters_list(conn, shop_id=shop) == []


def test_counters_list_multiple_elem_and_filter_shop_by(conn, org, shop):
    p1 = torzsadat_repo.counter_create(conn, org_id=org, shop_id=shop, name="Pult B")
    p2 = torzsadat_repo.counter_create(conn, org_id=org, shop_id=shop, name="Pult A")
    other_shop = torzsadat_repo.shop_create(conn, org_id=org, name="Másik bolt")
    torzsadat_repo.counter_create(conn, org_id=org, shop_id=other_shop, name="Idegen")

    result = torzsadat_repo.counters_list(conn, shop_id=shop)
    assert result == [{"id": p2, "nev": "Pult A"}, {"id": p1, "nev": "Pult B"}]


# --- alkalmazottak_lekerdezese ------------------------------------------


def test_employees_list_empty(conn, shop):
    assert torzsadat_repo.employees_list(conn, shop_id=shop) == []


def test_employees_list_multiple_elem_and_filter_shop_by(conn, org, shop):
    a1 = torzsadat_repo.employee_create(conn, org_id=org, shop_id=shop, name="Durranó")
    other_shop = torzsadat_repo.shop_create(conn, org_id=org, name="Másik bolt")
    torzsadat_repo.employee_create(conn, org_id=org, shop_id=other_shop, name="Idegen")

    result = torzsadat_repo.employees_list(conn, shop_id=shop)
    assert result == [{"id": a1, "nev": "Durranó"}]


# --- szolgaltatasok_lekerdezese ------------------------------------------


def test_services_list_empty(conn, shop):
    assert torzsadat_repo.services_list(conn, shop_id=shop) == []


def test_services_list_one_elem_alap_with_duration(conn, org, shop):
    sz_id = torzsadat_repo.service_create(
        conn, org_id=org, shop_id=shop, name="petárda", alap_duration_minute=5
    )
    result = torzsadat_repo.services_list(conn, shop_id=shop)
    assert result == [
        {
            "id": sz_id,
            "nev": "petárda",
            "alap_idotartam_perc": 5,
            "termekleiras": "",
            "ar": "",
        }
    ]


def test_services_list_filter_shop_by(conn, org, shop):
    torzsadat_repo.service_create(
        conn, org_id=org, shop_id=shop, name="petárda", alap_duration_minute=5
    )
    other_shop = torzsadat_repo.shop_create(conn, org_id=org, name="Másik bolt")
    torzsadat_repo.service_create(
        conn, org_id=org, shop_id=other_shop, name="idegen", alap_duration_minute=10
    )

    result = torzsadat_repo.services_list(conn, shop_id=shop)
    assert [s["nev"] for s in result] == ["petárda"]


# --- szerkesztés ----------------------------------------------------------


def test_shop_update_renames_name(conn, org, shop):
    torzsadat_repo.shop_update(conn, shop_id=shop, name="Új név")
    result = torzsadat_repo.shops_list(conn, org_id=org)
    assert result == [{"id": shop, "nev": "Új név"}]


def test_counter_update_renames_name(conn, org, shop):
    counter_id = torzsadat_repo.counter_create(conn, org_id=org, shop_id=shop, name="A")
    torzsadat_repo.counter_update(conn, counter_id=counter_id, name="B")
    result = torzsadat_repo.counters_list(conn, shop_id=shop)
    assert result == [{"id": counter_id, "nev": "B"}]


def test_employee_update_renames_name(conn, org, shop):
    employee_id = torzsadat_repo.employee_create(conn, org_id=org, shop_id=shop, name="Régi")
    torzsadat_repo.employee_update(conn, employee_id=employee_id, name="Új")
    result = torzsadat_repo.employees_list(conn, shop_id=shop)
    assert result == [{"id": employee_id, "nev": "Új"}]


def test_service_update_renames_name_and_duration(conn, org, shop):
    service_id = torzsadat_repo.service_create(
        conn, org_id=org, shop_id=shop, name="Régi", alap_duration_minute=5
    )
    torzsadat_repo.service_update(conn, service_id=service_id, name="Új", alap_duration_minute=20)
    result = torzsadat_repo.services_list(conn, shop_id=shop)
    assert result == [
        {
            "id": service_id,
            "nev": "Új",
            "alap_idotartam_perc": 20,
            "termekleiras": "",
            "ar": "",
        }
    ]


# --- kivetel_napok_reszletesen_lekerdezese --------------------------------


def test_exception_days_in_detail_list_empty(conn, org):
    assert torzsadat_repo.exception_days_in_detail_list(conn, org_id=org) == []


def test_exception_days_in_detail_list_org_and_shop_level(conn, org, shop):
    org_level = torzsadat_repo.exception_day_create(
        conn, org_id=org, shop_id=None, date="2026-12-25", reason="karácsony"
    )
    shop_level = torzsadat_repo.exception_day_create(
        conn, org_id=org, shop_id=shop, date="2026-08-20", reason="felújítás"
    )
    other_shop = torzsadat_repo.shop_create(conn, org_id=org, name="Másik")
    torzsadat_repo.exception_day_create(
        conn, org_id=org, shop_id=other_shop, date="2026-09-01", reason="idegen"
    )

    result = torzsadat_repo.exception_days_in_detail_list(conn, org_id=org, shop_id=shop)
    id_k = {e["id"] for e in result}
    assert id_k == {org_level, shop_level}  # a másik bolt kivétele nem jön be
    dates = sorted(e["datum"] for e in result)
    assert dates == ["2026-08-20", "2026-12-25"]

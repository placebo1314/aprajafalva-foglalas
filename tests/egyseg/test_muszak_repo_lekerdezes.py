"""Egységtesztek a mag/repo/muszak_repo.py olvasó (listázó) függvényeire:
`muszakok_lekerdezese` és `blokkok_lekerdezese`.

Az író/generáló oldalt (`muszak_letrehoz`, `blokkok_slotok_mentese`,
`kivetel_napok_lekerdezese`) a `test_seed.py` és a `test_muszak_slot.py`
már közvetetten fedi — itt az admin felület (`felulet/admin/`) naptár-
nézetéhez írt lekérdezéseket teszteljük.
"""

from __future__ import annotations

import pytest

from core.modell.shift import Block, Slot
from core.repo import migracio, muszak_repo, torzsadat_repo

_MOST = "2026-08-15T10:00:00Z"


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
def master(conn) -> dict[str, str]:
    org_id = torzsadat_repo.org_create(conn, name="Aprajafalva", timezone="UTC")
    shop_id = torzsadat_repo.shop_create(conn, org_id=org_id, name="Ügyifogyi")
    counter_id = torzsadat_repo.counter_create(conn, org_id=org_id, shop_id=shop_id, name="Pult 1")
    employee_id = torzsadat_repo.employee_create(
        conn, org_id=org_id, shop_id=shop_id, name="Durranó"
    )
    service_id = torzsadat_repo.service_create(
        conn,
        org_id=org_id,
        shop_id=shop_id,
        name="petárda",
        alap_duration_minute=10,
    )
    return {
        "szervezet_id": org_id,
        "bolt_id": shop_id,
        "pult_id": counter_id,
        "alkalmazott_id": employee_id,
        "szolgaltatas_id": service_id,
    }


def _shift(conn, master, start: str, end: str) -> str:
    return muszak_repo.shift_create(
        conn,
        org_id=master["szervezet_id"],
        shop_id=master["bolt_id"],
        counter_id=master["pult_id"],
        employee_id=master["alkalmazott_id"],
        service_id=master["szolgaltatas_id"],
        start=start,
        end=end,
        duration_minute=10,
        buffer_after_minute=0,
        min_grid_minute=10,
        bookable_ratio=1.0,
        block_rule={"szunetek": []},
    )


# --- muszakok_lekerdezese -------------------------------------------------


def test_shifts_list_empty(conn, master):
    result = muszak_repo.shifts_list(conn, org_id=master["szervezet_id"])
    assert result == []


def test_shifts_list_one_elem_nevekkel(conn, master):
    shift_id = _shift(conn, master, "2026-08-18T08:00:00Z", "2026-08-18T09:00:00Z")
    result = muszak_repo.shifts_list(conn, org_id=master["szervezet_id"])
    assert len(result) == 1
    row = result[0]
    assert row["muszak_id"] == shift_id
    assert row["bolt_nev"] == "Ügyifogyi"
    assert row["pult_nev"] == "Pult 1"
    assert row["alkalmazott_nev"] == "Durranó"
    assert row["szolgaltatas_nev"] == "petárda"
    assert row["slot_szam"] == 0  # nincs slot mentve, csak a muszak sor


def test_shifts_list_multiple_elem_start_by_rendezve(conn, master):
    later = _shift(conn, master, "2026-08-19T08:00:00Z", "2026-08-19T09:00:00Z")
    earlier = _shift(conn, master, "2026-08-18T08:00:00Z", "2026-08-18T09:00:00Z")
    result = muszak_repo.shifts_list(conn, org_id=master["szervezet_id"])
    assert [e["muszak_id"] for e in result] == [earlier, later]


def test_shifts_list_date_window_filter(conn, master):
    _shift(conn, master, "2026-08-17T08:00:00Z", "2026-08-17T09:00:00Z")
    bent = _shift(conn, master, "2026-08-18T08:00:00Z", "2026-08-18T09:00:00Z")
    _shift(conn, master, "2026-08-25T08:00:00Z", "2026-08-25T09:00:00Z")

    result = muszak_repo.shifts_list(
        conn,
        org_id=master["szervezet_id"],
        date_tol="2026-08-18T00:00:00Z",
        date_ig="2026-08-19T00:00:00Z",
    )
    assert [e["muszak_id"] for e in result] == [bent]


def test_shifts_list_shop_by_filter(conn, master):
    own = _shift(conn, master, "2026-08-18T08:00:00Z", "2026-08-18T09:00:00Z")
    other_shop = torzsadat_repo.shop_create(conn, org_id=master["szervezet_id"], name="Törpilla")
    other_counter = torzsadat_repo.counter_create(
        conn, org_id=master["szervezet_id"], shop_id=other_shop, name="Törpilla pult"
    )
    other_employee = torzsadat_repo.employee_create(
        conn, org_id=master["szervezet_id"], shop_id=other_shop, name="Törpilla"
    )
    other_service = torzsadat_repo.service_create(
        conn,
        org_id=master["szervezet_id"],
        shop_id=other_shop,
        name="boldogság",
        alap_duration_minute=15,
    )
    muszak_repo.shift_create(
        conn,
        org_id=master["szervezet_id"],
        shop_id=other_shop,
        counter_id=other_counter,
        employee_id=other_employee,
        service_id=other_service,
        start="2026-08-18T08:00:00Z",
        end="2026-08-18T09:00:00Z",
        duration_minute=10,
        buffer_after_minute=0,
        min_grid_minute=10,
        bookable_ratio=1.0,
        block_rule={"szunetek": []},
    )

    result = muszak_repo.shifts_list(conn, org_id=master["szervezet_id"], shop_id=master["bolt_id"])
    assert [e["muszak_id"] for e in result] == [own]


def test_shifts_list_slot_count_saved_slots_tukrozi(conn, master):
    shift_id = _shift(conn, master, "2026-08-18T08:00:00Z", "2026-08-18T09:00:00Z")
    slots = [Slot("2026-08-18T08:00:00Z", "2026-08-18T08:10:00Z")]
    muszak_repo.blocks_slots_save(
        conn,
        shift_id=shift_id,
        org_id=master["szervezet_id"],
        blocks=[],
        slots=slots,
    )
    result = muszak_repo.shifts_list(conn, org_id=master["szervezet_id"])
    assert result[0]["slot_szam"] == 1


# --- blokkok_lekerdezese --------------------------------------------------


def test_blocks_list_empty(conn, master):
    shift_id = _shift(conn, master, "2026-08-18T08:00:00Z", "2026-08-18T09:00:00Z")
    assert muszak_repo.blocks_list(conn, shift_id=shift_id) == []


def test_blocks_list_multiple_elem_start_by_rendezve(conn, master):
    shift_id = _shift(conn, master, "2026-08-18T08:00:00Z", "2026-08-18T09:00:00Z")
    blocks = [
        Block("szunet", "2026-08-18T08:30:00Z", "2026-08-18T08:40:00Z", True, True),
        Block("szunet", "2026-08-18T08:00:00Z", "2026-08-18T08:10:00Z", True, True),
    ]
    muszak_repo.blocks_slots_save(
        conn,
        shift_id=shift_id,
        org_id=master["szervezet_id"],
        blocks=blocks,
        slots=[],
    )
    result = muszak_repo.blocks_list(conn, shift_id=shift_id)
    assert [b["kezdet"] for b in result] == ["2026-08-18T08:00:00Z", "2026-08-18T08:30:00Z"]
    assert result[0]["tipus"] == "szunet"
    assert result[0]["rogzitett"] is True
    assert result[0]["beszamit_kvotaba"] is True


def test_blocks_list_filter_shift_by(conn, master):
    shift_1 = _shift(conn, master, "2026-08-18T08:00:00Z", "2026-08-18T09:00:00Z")
    shift_2 = _shift(conn, master, "2026-08-19T08:00:00Z", "2026-08-19T09:00:00Z")
    muszak_repo.blocks_slots_save(
        conn,
        shift_id=shift_2,
        org_id=master["szervezet_id"],
        blocks=[Block("szabad_sav", "2026-08-19T08:50:00Z", "2026-08-19T09:00:00Z", True, False)],
        slots=[],
    )
    assert muszak_repo.blocks_list(conn, shift_id=shift_1) == []
    assert len(muszak_repo.blocks_list(conn, shift_id=shift_2)) == 1

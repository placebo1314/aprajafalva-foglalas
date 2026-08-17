"""Egységtesztek a mag/api/cli.py parancsokra.

A parancsfüggvényeket közvetlenül hívja (nem subprocess-ként) — ezek
tiszta `argv → kilépőkód` függvények, `sys.exit`/subprocess nélkül
tesztelhetők.
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta

import pytest

from core.api import cli
from core.repo import foglalas_repo, migracio, muszak_repo, torzsadat_repo


@pytest.fixture
def db_path(tmp_path) -> str:
    return str(tmp_path / "cli.db")


@pytest.fixture
def base_data(db_path) -> dict:
    """Migrál, és felvesz egy minimális törzsadatot + egy 1 órás,
    szünet nélküli műszakot — elég egy CLI-teszthez, seed nélkül."""
    conn = migracio.conn_nyitas(db_path)
    try:
        migracio.migral(conn)
        org_id = torzsadat_repo.org_create(conn, name="Aprajafalva", timezone="Europe/Budapest")
        shop_id = torzsadat_repo.shop_create(conn, org_id=org_id, name="Törpilla")
        counter_id = torzsadat_repo.counter_create(
            conn, org_id=org_id, shop_id=shop_id, name="Pult 1"
        )
        employee_id = torzsadat_repo.employee_create(
            conn, org_id=org_id, shop_id=shop_id, name="Hulk Hugan"
        )
        service_id = torzsadat_repo.service_create(
            conn,
            org_id=org_id,
            shop_id=shop_id,
            name="boldogság",
            alap_duration_minute=15,
        )
        shift_id = muszak_repo.shift_create(
            conn,
            org_id=org_id,
            shop_id=shop_id,
            counter_id=counter_id,
            employee_id=employee_id,
            service_id=service_id,
            start="2027-01-05T08:00:00Z",
            end="2027-01-05T09:00:00Z",
            duration_minute=15,
            buffer_after_minute=0,
            min_grid_minute=15,
            bookable_ratio=1.0,
            block_rule={"szunetek": []},
        )
    finally:
        conn.close()
    return {
        "szervezet_id": org_id,
        "bolt_id": shop_id,
        "szolgaltatas_id": service_id,
        "muszak_id": shift_id,
    }


def test_migral_new_on_database(db_path):
    code = cli._migral([db_path])
    assert code == 0
    conn = sqlite3.connect(db_path)
    tablak = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    conn.close()
    assert "muszak" in tablak


def test_slots_generate_and_saves(db_path, base_data):
    code = cli._slots([db_path, base_data["muszak_id"]])
    assert code == 0
    conn = sqlite3.connect(db_path)
    slot_count = conn.execute(
        "SELECT COUNT(*) FROM slot WHERE muszak_id = ?", (base_data["muszak_id"],)
    ).fetchone()[0]
    conn.close()
    assert slot_count == 4  # 60 perc / 15 perc, szünet nélkül


def test_slots_no_ilyen_shift(db_path, base_data):
    code = cli._slots([db_path, "0" * 32])
    assert code == 1


def test_search_empty_free_slot_without(db_path, base_data):
    code = cli._search([db_path, base_data["szervezet_id"]])
    assert code == 0  # "nincs szabad időpont" is sikeres futás, nem hiba


def test_search_finds_free_slot(db_path, base_data, capsys):
    cli._slots([db_path, base_data["muszak_id"]])
    capsys.readouterr()  # az eddigi kimenet eldobása

    code = cli._search([db_path, base_data["szervezet_id"], "--bolt", base_data["bolt_id"]])

    assert code == 0
    output = capsys.readouterr().out
    assert output.count("\n") == 4  # 4 slot, soronként egy


def test_foglal_and_lemond_process(db_path, base_data, capsys):
    cli._slots([db_path, base_data["muszak_id"]])
    conn = sqlite3.connect(db_path)
    slot_id = conn.execute(
        "SELECT id FROM slot WHERE muszak_id = ? ORDER BY kezdet LIMIT 1",
        (base_data["muszak_id"],),
    ).fetchone()[0]
    conn.close()
    capsys.readouterr()

    foglal_code = cli._foglal([db_path, slot_id, "a" * 64, "idem-1", "session-1"])
    assert foglal_code == 0
    output = capsys.readouterr().out
    assert "sikeres" in output
    assert "Foglalási kód:" in output

    conn = sqlite3.connect(db_path)
    booking_code = conn.execute(
        "SELECT foglalasi_kod FROM foglalas WHERE idempotencia_kulcs = 'idem-1'"
    ).fetchone()[0]
    conn.close()

    lemond_code = cli._lemond([db_path, booking_code])
    assert lemond_code == 0

    ujra_lemond_code = cli._lemond([db_path, booking_code])
    assert ujra_lemond_code == 1  # már lemondva — nem SIKERES


def test_foglal_second_attempt_preempted(db_path, base_data, capsys):
    cli._slots([db_path, base_data["muszak_id"]])
    conn = sqlite3.connect(db_path)
    slot_id = conn.execute(
        "SELECT id FROM slot WHERE muszak_id = ? ORDER BY kezdet LIMIT 1",
        (base_data["muszak_id"],),
    ).fetchone()[0]
    conn.close()

    cli._foglal([db_path, slot_id, "a" * 64, "idem-1", "session-1"])
    capsys.readouterr()
    second_code = cli._foglal([db_path, slot_id, "b" * 64, "idem-2", "session-2"])

    assert second_code == 1
    assert "megeloztek" in capsys.readouterr().out


def test_holds_cleanup(db_path, base_data, capsys):
    cli._slots([db_path, base_data["muszak_id"]])
    conn = migracio.conn_nyitas(db_path)
    slot_id = conn.execute(
        "SELECT id FROM slot WHERE muszak_id = ? LIMIT 1", (base_data["muszak_id"],)
    ).fetchone()[0]
    # A lejar > letrejott CHECK a valódi rendszerórát nézi (most_iso()),
    # ezért a hold létrehozásakor a jövőben kell lennie — a "takarítás"
    # pillanatát viszont ennél is későbbre, 2099-re állítjuk, hogy már
    # lejártnak számítson.
    near_jovo = (datetime.now(UTC) + timedelta(minutes=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
    foglalas_repo.hold_create(conn, slot_id, "session-1", near_jovo)
    conn.close()
    capsys.readouterr()

    code = cli._holds_cleanup([db_path, "2099-01-01T00:00:00Z"])

    assert code == 0
    assert "Törölve: 1" in capsys.readouterr().out


def test_command_nelkuli_call_sugot_write_ki(capsys):
    import sys

    known = list(sys.argv)
    try:
        sys.argv = ["mag.api.cli"]
        code = cli._fo()
    finally:
        sys.argv = known

    assert code == 1
    assert "Parancssori felület" in capsys.readouterr().out

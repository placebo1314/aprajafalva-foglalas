"""Egységtesztek a 0002_muszak_slot migrációra.

Minden teszt saját, ideiglenes SQLite fájlon fut (`tmp_path` pytest
fixture), tiszta állapotból indul, és az ÖSSZES migrációt lefuttatja
(`migracio.migral` mindig a teljes, még le nem futott sort végrehajtja —
ma 0001, 0002, 0003).
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


def _master_data_insert(conn: sqlite3.Connection) -> dict[str, str]:
    """Teljes láncot szúr be: szervezet → bolt → pult/alkalmazott/szolgaltatas."""
    org_id = _uuid()
    conn.execute(
        "INSERT INTO szervezet (id, nev, idozona, letrehozva) VALUES (?, ?, ?, ?)",
        (org_id, "Aprajafalva", "Europe/Budapest", _MOST),
    )
    shop_id = _uuid()
    conn.execute(
        "INSERT INTO bolt (id, szervezet_id, nev, letrehozva) VALUES (?, ?, ?, ?)",
        (shop_id, org_id, "Törpilla boltja", _MOST),
    )
    counter_id = _uuid()
    conn.execute(
        "INSERT INTO pult (id, szervezet_id, bolt_id, nev, letrehozva) VALUES (?, ?, ?, ?, ?)",
        (counter_id, org_id, shop_id, "Pult 1", _MOST),
    )
    employee_id = _uuid()
    conn.execute(
        "INSERT INTO alkalmazott (id, szervezet_id, bolt_id, nev, letrehozva) "
        "VALUES (?, ?, ?, ?, ?)",
        (employee_id, org_id, shop_id, "Törpilla", _MOST),
    )
    service_id = _uuid()
    conn.execute(
        "INSERT INTO szolgaltatas "
        "(id, szervezet_id, bolt_id, nev, alap_idotartam_perc, letrehozva) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (service_id, org_id, shop_id, "kis petárda", 30, _MOST),
    )
    return {
        "szervezet_id": org_id,
        "bolt_id": shop_id,
        "pult_id": counter_id,
        "alkalmazott_id": employee_id,
        "szolgaltatas_id": service_id,
    }


def _shift_insert(conn: sqlite3.Connection, master: dict[str, str]) -> str:
    shift_id = _uuid()
    conn.execute(
        "INSERT INTO muszak "
        "(id, szervezet_id, bolt_id, pult_id, alkalmazott_id, szolgaltatas_id, "
        "kezdet, veg, idotartam_perc, puffer_utana_perc, min_racs_perc, "
        "foglalhato_arany, blokk_szabaly, allapot, letrehozva) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            shift_id,
            master["szervezet_id"],
            master["bolt_id"],
            master["pult_id"],
            master["alkalmazott_id"],
            master["szolgaltatas_id"],
            "2026-08-18T08:00:00Z",
            "2026-08-18T16:00:00Z",
            30,
            0,
            5,
            0.8,
            '{"strategia": "FixBlokk"}',
            "aktiv",
            _MOST,
        ),
    )
    return shift_id


def _slot_insert(
    conn: sqlite3.Connection,
    master: dict[str, str],
    shift_id: str,
    start: str = "2026-08-18T08:00:00Z",
    end: str = "2026-08-18T08:30:00Z",
) -> str:
    slot_id = _uuid()
    conn.execute(
        "INSERT INTO slot (id, szervezet_id, muszak_id, kezdet, veg, letrehozva) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (slot_id, master["szervezet_id"], shift_id, start, end, _MOST),
    )
    return slot_id


def _booking_insert(
    conn: sqlite3.Connection,
    master: dict[str, str],
    slot_id: str,
    status: str = "aktiv",
    idempotency_key: str | None = None,
    booking_code: str | None = None,
) -> str:
    booking_id = _uuid()
    conn.execute(
        "INSERT INTO foglalas "
        "(id, szervezet_id, slot_id, vasarlo_kulcs, kulcs_verzio, "
        "idempotencia_kulcs, foglalasi_kod, allapot, letrehozva) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            booking_id,
            master["szervezet_id"],
            slot_id,
            "a" * 64,
            1,
            idempotency_key or _uuid(),
            booking_code or _uuid()[:8],
            status,
            _MOST,
        ),
    )
    return booking_id


def test_migration_up_creates_new_tablakat(conn):
    tablak = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    elvart = {"muszak", "muszak_blokk", "slot", "foglalas", "hold", "esemenyek"}
    assert elvart <= tablak


def test_rollback_fully_restore(db_path):
    conn = migracio.conn_nyitas(db_path)
    migracio.migral(conn)
    rolled_back = migracio.rollback(conn)
    assert rolled_back == ["0005", "0004", "0003", "0002", "0001"]

    tablak = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    conn.close()
    assert tablak == {"sema_verzio"}


def test_one_for_slot_only_one_active_booking_lehet(conn):
    master = _master_data_insert(conn)
    shift_id = _shift_insert(conn, master)
    slot_id = _slot_insert(conn, master, shift_id)

    _booking_insert(conn, master, slot_id)

    with pytest.raises(sqlite3.IntegrityError):
        _booking_insert(conn, master, slot_id)


def test_lemondas_after_same_for_slot_ujra_bookable(conn):
    master = _master_data_insert(conn)
    shift_id = _shift_insert(conn, master)
    slot_id = _slot_insert(conn, master, shift_id)

    first_booking_id = _booking_insert(conn, master, slot_id)
    conn.execute("UPDATE foglalas SET allapot = 'lemondva' WHERE id = ?", (first_booking_id,))

    # Most, hogy az egyetlen aktív foglalás lemondva, ugyanarra a slotra
    # újra be kell tudni szúrni — a parciális index csak az aktívakat védi.
    second_booking_id = _booking_insert(conn, master, slot_id)
    assert second_booking_id != first_booking_id


def test_hold_per_slot_egyedi(conn):
    master = _master_data_insert(conn)
    shift_id = _shift_insert(conn, master)
    slot_id = _slot_insert(conn, master, shift_id)

    conn.execute(
        "INSERT INTO hold (id, szervezet_id, slot_id, session_id, letrejott, lejar) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (_uuid(), master["szervezet_id"], slot_id, "session-1", _MOST, "2026-08-15T10:03:00Z"),
    )

    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO hold (id, szervezet_id, slot_id, session_id, letrejott, lejar) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (_uuid(), master["szervezet_id"], slot_id, "session-2", _MOST, "2026-08-15T10:03:00Z"),
        )


def test_idempotency_key_egyedi(conn):
    master = _master_data_insert(conn)
    shift_id = _shift_insert(conn, master)
    slot_1 = _slot_insert(conn, master, shift_id, "2026-08-18T08:00:00Z", "2026-08-18T08:30:00Z")
    slot_2 = _slot_insert(conn, master, shift_id, "2026-08-18T08:30:00Z", "2026-08-18T09:00:00Z")

    common_key = _uuid()
    _booking_insert(conn, master, slot_1, idempotency_key=common_key)

    with pytest.raises(sqlite3.IntegrityError):
        _booking_insert(conn, master, slot_2, idempotency_key=common_key)


def test_booking_code_egyedi(conn):
    master = _master_data_insert(conn)
    shift_id = _shift_insert(conn, master)
    slot_1 = _slot_insert(conn, master, shift_id, "2026-08-18T08:00:00Z", "2026-08-18T08:30:00Z")
    slot_2 = _slot_insert(conn, master, shift_id, "2026-08-18T08:30:00Z", "2026-08-18T09:00:00Z")

    common_code = "ABC12345"
    _booking_insert(conn, master, slot_1, booking_code=common_code)

    with pytest.raises(sqlite3.IntegrityError):
        _booking_insert(conn, master, slot_2, booking_code=common_code)


def test_fk_rejects_slot_insert_nonexistent_for_shift(conn):
    master = _master_data_insert(conn)

    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO slot (id, szervezet_id, muszak_id, kezdet, veg, letrehozva) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                _uuid(),
                master["szervezet_id"],
                _uuid(),  # nem létező muszak_id
                "2026-08-18T08:00:00Z",
                "2026-08-18T08:30:00Z",
                _MOST,
            ),
        )


def test_fk_rejects_booking_insert_nonexistent_for_slot(conn):
    master = _master_data_insert(conn)

    with pytest.raises(sqlite3.IntegrityError):
        _booking_insert(conn, master, _uuid())  # nem létező slot_id


def test_fk_rejects_hold_insert_nonexistent_for_slot(conn):
    master = _master_data_insert(conn)

    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO hold (id, szervezet_id, slot_id, session_id, letrejott, lejar) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                _uuid(),
                master["szervezet_id"],
                _uuid(),  # nem létező slot_id
                "session-1",
                _MOST,
                "2026-08-15T10:03:00Z",
            ),
        )


def test_shift_block_type_invalid_erteket_reject(conn):
    master = _master_data_insert(conn)
    shift_id = _shift_insert(conn, master)

    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO muszak_blokk "
            "(id, szervezet_id, muszak_id, tipus, kezdet, veg, rogzitett, "
            "beszamit_kvotaba, letrehozva) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                _uuid(),
                master["szervezet_id"],
                shift_id,
                "ebedszunet",  # nem szerepel a {szunet, ebed, szabad_sav} halmazban
                "2026-08-18T12:00:00Z",
                "2026-08-18T12:15:00Z",
                1,
                1,
                _MOST,
            ),
        )

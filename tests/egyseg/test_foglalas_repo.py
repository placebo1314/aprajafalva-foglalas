"""Egységtesztek a mag/repo/foglalas_repo.py írási rétegére.

Nem konkurenciateszt — egyetlen kapcsolatból, szekvenciálisan hívja a
függvényeket, a versenyhelyzeti (párhuzamos írás) eseteket a
`konkurencia-teszto` agent tesztjei fedik (tesztek/konkurencia/).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from core.repo import foglalas_repo, migracio, torzsadat_repo
from core.repo.foglalas_repo import Result

_MOST = "2026-08-15T10:00:00Z"


def _uuid() -> str:
    return uuid.uuid4().hex


def _jovoben(minute: int = 5) -> str:
    """Valódi 'most'-hoz képest a jövőben lévő ISO-8601 időpont — a hold
    lejar > letrejott CHECK-je a tényleges rendszerórát (most_iso())
    használja, nem a fix _MOST teszt-konstanst."""
    return (datetime.now(UTC) + timedelta(minutes=minute)).strftime("%Y-%m-%dT%H:%M:%SZ")


@pytest.fixture
def db_path(tmp_path) -> str:
    return str(tmp_path / "teszt.db")


@pytest.fixture
def conn(db_path):
    conn = migracio.conn_nyitas(db_path)
    migracio.migral(conn)
    yield conn
    conn.close()


def _master_data_insert(conn) -> dict[str, str]:
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


def _shift_insert(conn, master: dict[str, str]) -> str:
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
    conn,
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


@pytest.fixture
def slot(conn) -> str:
    master = _master_data_insert(conn)
    shift_id = _shift_insert(conn, master)
    return _slot_insert(conn, master, shift_id)


def _lejart_hold_insert(conn, slot_id: str, session_id: str = "session-lejart") -> None:
    """Egy MÁR LEJÁRT holdot szúr be közvetlenül — a `hold_letrehoz` a
    `lejar > letrejott` CHECK miatt nem tudna ilyet létrehozni (a
    `letrejott` mindig a valódi 'most'). Mindkét időpont biztonságosan a
    múltban van a valódi rendszerórához képest."""
    (org_id,) = conn.execute("SELECT szervezet_id FROM slot WHERE id = ?", (slot_id,)).fetchone()
    conn.execute(
        "INSERT INTO hold (id, szervezet_id, slot_id, session_id, letrejott, lejar) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (
            _uuid(),
            org_id,
            slot_id,
            session_id,
            "2020-01-01T00:00:00Z",
            "2020-01-01T00:00:01Z",
        ),
    )


# --- slot_szabad ---------------------------------------------------------


def test_slot_free_true_new_on_slot(conn, slot):
    assert foglalas_repo.slot_free(conn, slot) is True


def test_slot_free_false_nonexistent_for_slot(conn):
    assert foglalas_repo.slot_free(conn, _uuid()) is False


def test_slot_free_false_if_has_hold(conn, slot):
    foglalas_repo.hold_create(conn, slot, "session-1", _jovoben())
    assert foglalas_repo.slot_free(conn, slot) is False


def test_slot_free_true_lejart_hold_after_cleanup_without_is(conn, slot):
    """Egy lejárt, de még nem takarított hold nem blokkolhat — a
    takarítás (lejart_holdok_takaritasa) csak a táblát tisztítja, a
    szabadságot a lejar mező dönti el."""
    _lejart_hold_insert(conn, slot)
    assert foglalas_repo.slot_free(conn, slot) is True


def test_slot_free_false_if_has_active_booking(conn, slot):
    foglalas_repo.booking_create(conn, slot, "a" * 64, _uuid(), "session-1")
    assert foglalas_repo.slot_free(conn, slot) is False


def test_slot_free_true_cancelled_booking_after(conn, slot):
    foglalas_repo.booking_create(conn, slot, "a" * 64, _uuid(), "session-1")
    code = conn.execute("SELECT foglalasi_kod FROM foglalas WHERE slot_id = ?", (slot,)).fetchone()[
        0
    ]
    foglalas_repo.booking_lemond(conn, code)
    assert foglalas_repo.slot_free(conn, slot) is True


# --- hold ------------------------------------------------------------------


def test_hold_create_success(conn, slot):
    result = foglalas_repo.hold_create(conn, slot, "session-1", _jovoben())
    assert result is Result.SUCCESS
    rows = conn.execute("SELECT slot_id, session_id FROM hold").fetchall()
    assert rows == [(slot, "session-1")]


def test_hold_create_no_ilyen_for_slot(conn):
    result = foglalas_repo.hold_create(conn, _uuid(), "session-1", _jovoben())
    assert result is Result.NO_ILYEN


def test_hold_create_preempted_other_hold_miatt(conn, slot):
    foglalas_repo.hold_create(conn, slot, "session-1", _jovoben())
    result = foglalas_repo.hold_create(conn, slot, "session-2", _jovoben())
    assert result is Result.PREEMPTED
    assert conn.execute("SELECT COUNT(*) FROM hold").fetchone()[0] == 1


def test_hold_create_success_lejart_hold_after(conn, slot):
    """A lejárt hold nem blokkolja az újat: a hold_letrehoz a beszúrás
    előtt, ugyanabban a tranzakcióban törli a slot lejárt holdjait."""
    _lejart_hold_insert(conn, slot)

    result = foglalas_repo.hold_create(conn, slot, "session-uj", _jovoben())

    assert result is Result.SUCCESS
    rows = conn.execute("SELECT session_id FROM hold WHERE slot_id = ?", (slot,)).fetchall()
    assert rows == [("session-uj",)]  # a lejárt sor eltűnt, csak az új maradt


def test_hold_create_preempted_active_booking_miatt(conn, slot):
    foglalas_repo.booking_create(conn, slot, "a" * 64, _uuid(), "session-1")
    result = foglalas_repo.hold_create(conn, slot, "session-2", _jovoben())
    assert result is Result.PREEMPTED
    assert conn.execute("SELECT COUNT(*) FROM hold").fetchone()[0] == 0


def test_hold_release_success(conn, slot):
    foglalas_repo.hold_create(conn, slot, "session-1", _jovoben())
    hold_id = conn.execute("SELECT id FROM hold WHERE slot_id = ?", (slot,)).fetchone()[0]

    result = foglalas_repo.hold_release(conn, hold_id)
    assert result is Result.SUCCESS
    assert conn.execute("SELECT COUNT(*) FROM hold").fetchone()[0] == 0
    # A felszabadított slot újra foglalható.
    assert foglalas_repo.slot_free(conn, slot) is True


def test_hold_release_no_ilyen(conn):
    result = foglalas_repo.hold_release(conn, _uuid())
    assert result is Result.NO_ILYEN


def test_lejart_holds_cleanup_only_lejarottakat_deletes(conn):
    master = _master_data_insert(conn)
    shift_id = _shift_insert(conn, master)
    expiring_slot = _slot_insert(
        conn, master, shift_id, "2026-08-18T08:00:00Z", "2026-08-18T08:30:00Z"
    )
    elo_slot = _slot_insert(conn, master, shift_id, "2026-08-18T08:30:00Z", "2026-08-18T09:00:00Z")

    soon_expiring = _jovoben(1)
    sokaig_elo = _jovoben(60)
    foglalas_repo.hold_create(conn, expiring_slot, "session-1", soon_expiring)
    foglalas_repo.hold_create(conn, elo_slot, "session-2", sokaig_elo)

    # A "most" a két lejárat közé esik: az első már lejárt, a második nem.
    kozepso_time = (
        datetime.strptime(soon_expiring, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
        + timedelta(seconds=30)
    ).strftime("%Y-%m-%dT%H:%M:%SZ")

    deleted_id_k = foglalas_repo.lejart_holds_cleanup(conn, kozepso_time)

    remains = {row[0] for row in conn.execute("SELECT slot_id FROM hold")}
    assert remains == {elo_slot}
    assert len(deleted_id_k) == 1

    events = {
        row[0] for row in conn.execute("SELECT tipus FROM esemenyek WHERE tipus = 'hold_lejart'")
    }
    assert events == {"hold_lejart"}


def test_lejart_holds_cleanup_empty_if_no_lejart(conn, slot):
    foglalas_repo.hold_create(conn, slot, "session-1", _jovoben(60))
    deleted = foglalas_repo.lejart_holds_cleanup(conn, _MOST)
    assert deleted == []
    assert conn.execute("SELECT COUNT(*) FROM hold").fetchone()[0] == 1


# --- foglalas_letrehoz -------------------------------------------------


def test_booking_create_success_and_deletes_hold(conn, slot):
    foglalas_repo.hold_create(conn, slot, "session-1", _jovoben())

    result = foglalas_repo.booking_create(conn, slot, "a" * 64, _uuid(), "session-1")

    assert result is Result.SUCCESS
    assert conn.execute("SELECT COUNT(*) FROM foglalas").fetchone()[0] == 1
    # Nincs kettős könyvelés: a hold eltűnik, amint valódi foglalás lesz.
    assert conn.execute("SELECT COUNT(*) FROM hold").fetchone()[0] == 0


def test_booking_create_no_ilyen_for_slot(conn):
    result = foglalas_repo.booking_create(conn, _uuid(), "a" * 64, _uuid(), "session-1")
    assert result is Result.NO_ILYEN


def test_booking_create_preempted_second_active_for_booking(conn, slot):
    first = foglalas_repo.booking_create(conn, slot, "a" * 64, _uuid(), "session-1")
    assert first is Result.SUCCESS

    second = foglalas_repo.booking_create(conn, slot, "b" * 64, _uuid(), "session-2")
    assert second is Result.PREEMPTED
    assert conn.execute("SELECT COUNT(*) FROM foglalas").fetchone()[0] == 1


def test_booking_create_idempotent_repetition_not_hoz_create_new_sort(conn, slot):
    key = _uuid()
    first = foglalas_repo.booking_create(conn, slot, "a" * 64, key, "session-1")
    second = foglalas_repo.booking_create(conn, slot, "a" * 64, key, "session-1")

    assert first is Result.SUCCESS
    assert second is Result.SUCCESS
    assert conn.execute("SELECT COUNT(*) FROM foglalas").fetchone()[0] == 1


def test_booking_create_event_write(conn, slot):
    foglalas_repo.booking_create(conn, slot, "a" * 64, _uuid(), "session-1")
    events = [
        row[0]
        for row in conn.execute("SELECT tipus FROM esemenyek WHERE entitas_tipus = 'foglalas'")
    ]
    assert events == ["foglalas_letrejott"]


# --- foglalas_lemond -----------------------------------------------------


def test_booking_lemond_success(conn, slot):
    foglalas_repo.booking_create(conn, slot, "a" * 64, _uuid(), "session-1")
    code = conn.execute("SELECT foglalasi_kod FROM foglalas WHERE slot_id = ?", (slot,)).fetchone()[
        0
    ]

    result = foglalas_repo.booking_lemond(conn, code)

    assert result is Result.SUCCESS
    status = conn.execute("SELECT allapot FROM foglalas WHERE slot_id = ?", (slot,)).fetchone()[0]
    assert status == "lemondva"


def test_booking_lemond_no_ilyen_for_code(conn):
    result = foglalas_repo.booking_lemond(conn, "NEMLETEZO")
    assert result is Result.NO_ILYEN


def test_booking_lemond_already_cancelled(conn, slot):
    foglalas_repo.booking_create(conn, slot, "a" * 64, _uuid(), "session-1")
    code = conn.execute("SELECT foglalasi_kod FROM foglalas WHERE slot_id = ?", (slot,)).fetchone()[
        0
    ]
    foglalas_repo.booking_lemond(conn, code)

    result = foglalas_repo.booking_lemond(conn, code)
    assert result is Result.ALREADY_CANCELLED


def test_booking_lemond_events_write(conn, slot):
    foglalas_repo.booking_create(conn, slot, "a" * 64, _uuid(), "session-1")
    code = conn.execute("SELECT foglalasi_kod FROM foglalas WHERE slot_id = ?", (slot,)).fetchone()[
        0
    ]
    foglalas_repo.booking_lemond(conn, code)

    types = [
        row[0]
        for row in conn.execute(
            "SELECT tipus FROM esemenyek WHERE tipus IN ('foglalas_lemondva', 'slot_felszabadult')"
        )
    ]
    assert set(types) == {"foglalas_lemondva", "slot_felszabadult"}


# --- booking_move ---------------------------------------------------


def test_booking_move_success_old_cancelled_new_active(conn):
    master = _master_data_insert(conn)
    shift_id = _shift_insert(conn, master)
    old_slot = _slot_insert(conn, master, shift_id)
    new_slot = _slot_insert(
        conn, master, shift_id, start="2026-08-18T09:00:00Z", end="2026-08-18T09:30:00Z"
    )
    foglalas_repo.booking_create(conn, old_slot, "a" * 64, _uuid(), "session-1")
    code = conn.execute(
        "SELECT foglalasi_kod FROM foglalas WHERE slot_id = ?", (old_slot,)
    ).fetchone()[0]

    result = foglalas_repo.booking_move(conn, code, new_slot, _uuid())

    assert result is Result.SUCCESS
    old_status = conn.execute(
        "SELECT allapot FROM foglalas WHERE slot_id = ?", (old_slot,)
    ).fetchone()[0]
    assert old_status == "lemondva"
    new_row = conn.execute(
        "SELECT allapot, foglalasi_kod FROM foglalas WHERE slot_id = ?", (new_slot,)
    ).fetchone()
    assert new_row[0] == "aktiv"
    assert new_row[1] != code


def test_booking_move_no_ilyen_for_code(conn, slot):
    result = foglalas_repo.booking_move(conn, "NEMLETEZO", slot, _uuid())
    assert result is Result.NO_ILYEN


def test_booking_move_already_cancelled(conn):
    master = _master_data_insert(conn)
    shift_id = _shift_insert(conn, master)
    old_slot = _slot_insert(conn, master, shift_id)
    new_slot = _slot_insert(
        conn, master, shift_id, start="2026-08-18T09:00:00Z", end="2026-08-18T09:30:00Z"
    )
    foglalas_repo.booking_create(conn, old_slot, "a" * 64, _uuid(), "session-1")
    code = conn.execute(
        "SELECT foglalasi_kod FROM foglalas WHERE slot_id = ?", (old_slot,)
    ).fetchone()[0]
    foglalas_repo.booking_lemond(conn, code)

    result = foglalas_repo.booking_move(conn, code, new_slot, _uuid())
    assert result is Result.ALREADY_CANCELLED


def test_booking_move_preempted_old_unchanged(conn):
    """Ha az új slotra időközben más nyert, a régi foglalás VÁLTOZATLAN
    marad — az áthelyezés teljes egészében visszagördül, nem félkész."""
    master = _master_data_insert(conn)
    shift_id = _shift_insert(conn, master)
    old_slot = _slot_insert(conn, master, shift_id)
    new_slot = _slot_insert(
        conn, master, shift_id, start="2026-08-18T09:00:00Z", end="2026-08-18T09:30:00Z"
    )
    foglalas_repo.booking_create(conn, old_slot, "a" * 64, _uuid(), "session-1")
    code = conn.execute(
        "SELECT foglalasi_kod FROM foglalas WHERE slot_id = ?", (old_slot,)
    ).fetchone()[0]
    # Valaki más már ül az új sloton.
    foglalas_repo.booking_create(conn, new_slot, "b" * 64, _uuid(), "session-2")

    result = foglalas_repo.booking_move(conn, code, new_slot, _uuid())

    assert result is Result.PREEMPTED
    old_status = conn.execute(
        "SELECT allapot FROM foglalas WHERE slot_id = ?", (old_slot,)
    ).fetchone()[0]
    assert old_status == "aktiv"


def test_booking_move_idempotent_repetition_not_hoz_create_new_sort(conn):
    master = _master_data_insert(conn)
    shift_id = _shift_insert(conn, master)
    old_slot = _slot_insert(conn, master, shift_id)
    new_slot = _slot_insert(
        conn, master, shift_id, start="2026-08-18T09:00:00Z", end="2026-08-18T09:30:00Z"
    )
    foglalas_repo.booking_create(conn, old_slot, "a" * 64, _uuid(), "session-1")
    code = conn.execute(
        "SELECT foglalasi_kod FROM foglalas WHERE slot_id = ?", (old_slot,)
    ).fetchone()[0]
    move_idempotency_key = _uuid()

    first = foglalas_repo.booking_move(conn, code, new_slot, move_idempotency_key)
    second = foglalas_repo.booking_move(conn, code, new_slot, move_idempotency_key)

    assert first is Result.SUCCESS
    assert second is Result.SUCCESS
    count = conn.execute(
        "SELECT COUNT(*) FROM foglalas WHERE slot_id = ? AND allapot = 'aktiv'", (new_slot,)
    ).fetchone()[0]
    assert count == 1


def test_booking_move_deletes_hold_on_new_slot(conn):
    master = _master_data_insert(conn)
    shift_id = _shift_insert(conn, master)
    old_slot = _slot_insert(conn, master, shift_id)
    new_slot = _slot_insert(
        conn, master, shift_id, start="2026-08-18T09:00:00Z", end="2026-08-18T09:30:00Z"
    )
    foglalas_repo.booking_create(conn, old_slot, "a" * 64, _uuid(), "session-1")
    code = conn.execute(
        "SELECT foglalasi_kod FROM foglalas WHERE slot_id = ?", (old_slot,)
    ).fetchone()[0]
    foglalas_repo.hold_create(conn, new_slot, "session-1", _jovoben())

    foglalas_repo.booking_move(conn, code, new_slot, _uuid())

    remaining_hold = conn.execute("SELECT 1 FROM hold WHERE slot_id = ?", (new_slot,)).fetchone()
    assert remaining_hold is None


def test_booking_move_events_write(conn):
    master = _master_data_insert(conn)
    shift_id = _shift_insert(conn, master)
    old_slot = _slot_insert(conn, master, shift_id)
    new_slot = _slot_insert(
        conn, master, shift_id, start="2026-08-18T09:00:00Z", end="2026-08-18T09:30:00Z"
    )
    foglalas_repo.booking_create(conn, old_slot, "a" * 64, _uuid(), "session-1")
    code = conn.execute(
        "SELECT foglalasi_kod FROM foglalas WHERE slot_id = ?", (old_slot,)
    ).fetchone()[0]

    foglalas_repo.booking_move(conn, code, new_slot, _uuid())

    types = [
        row[0]
        for row in conn.execute("SELECT tipus FROM esemenyek WHERE tipus = 'foglalas_athelyezve'")
    ]
    assert types == ["foglalas_athelyezve"]


# --- szabad_slotok_keresese -------------------------------------------


def test_free_slots_search_finds_new_slot(conn, slot):
    master = conn.execute("SELECT szervezet_id FROM slot WHERE id = ?", (slot,)).fetchone()
    (org_id,) = master
    matches = foglalas_repo.free_slots_search(conn, org_id=org_id)
    assert slot in [t[0] for t in matches]


def test_free_slots_search_excludes_valid_hold(conn, slot):
    (org_id,) = conn.execute("SELECT szervezet_id FROM slot WHERE id = ?", (slot,)).fetchone()
    foglalas_repo.hold_create(conn, slot, "session-1", _jovoben())
    matches = foglalas_repo.free_slots_search(conn, org_id=org_id)
    assert slot not in [t[0] for t in matches]


def test_free_slots_search_not_locks_ki_lejart_hold_cleanup_without(conn, slot):
    """A kért javítás lényege: lejárt hold után a slot újra megjelenik a
    keresésben, takarítás (lejart_holdok_takaritasa) nélkül is."""
    (org_id,) = conn.execute("SELECT szervezet_id FROM slot WHERE id = ?", (slot,)).fetchone()
    _lejart_hold_insert(conn, slot)

    # A hold sora még mindig ott van — nem takarítottunk.
    has_hold = conn.execute("SELECT 1 FROM hold WHERE slot_id = ?", (slot,)).fetchone()
    assert has_hold is not None

    matches = foglalas_repo.free_slots_search(conn, org_id=org_id)
    assert slot in [t[0] for t in matches]


def test_free_slots_search_excludes_active_booking(conn, slot):
    (org_id,) = conn.execute("SELECT szervezet_id FROM slot WHERE id = ?", (slot,)).fetchone()
    foglalas_repo.booking_create(conn, slot, "a" * 64, _uuid(), "session-1")
    matches = foglalas_repo.free_slots_search(conn, org_id=org_id)
    assert slot not in [t[0] for t in matches]


def test_free_slots_search_empty_if_single_free_slot_no(conn):
    master = _master_data_insert(conn)
    shift_id = _shift_insert(conn, master)
    slot_1 = _slot_insert(conn, master, shift_id, "2026-08-18T08:00:00Z", "2026-08-18T08:30:00Z")
    slot_2 = _slot_insert(conn, master, shift_id, "2026-08-18T08:30:00Z", "2026-08-18T09:00:00Z")
    foglalas_repo.booking_create(conn, slot_1, "a" * 64, _uuid(), "session-1")
    foglalas_repo.hold_create(conn, slot_2, "session-2", _jovoben())

    matches = foglalas_repo.free_slots_search(conn, org_id=master["szervezet_id"])
    assert matches == []


def test_free_slots_search_empty_if_no_single_slot_nor_in_org(conn):
    org_id = torzsadat_repo.org_create(conn, name="Üres", timezone="UTC")
    matches = foglalas_repo.free_slots_search(conn, org_id=org_id)
    assert matches == []


def test_free_slots_search_pontosan_one_marad(conn):
    master = _master_data_insert(conn)
    shift_id = _shift_insert(conn, master)
    slot_1 = _slot_insert(conn, master, shift_id, "2026-08-18T08:00:00Z", "2026-08-18T08:30:00Z")
    last_free = _slot_insert(conn, master, shift_id, "2026-08-18T08:30:00Z", "2026-08-18T09:00:00Z")
    foglalas_repo.booking_create(conn, slot_1, "a" * 64, _uuid(), "session-1")

    matches = foglalas_repo.free_slots_search(conn, org_id=master["szervezet_id"])
    assert [t[0] for t in matches] == [last_free]


# --- hold_lekerdezese ------------------------------------------------------


def test_hold_list_no_ilyen(conn, slot):
    assert foglalas_repo.hold_list(conn, slot_id=slot, session_id="session-x") is None


def test_hold_list_finds_own_hold(conn, slot):
    foglalas_repo.hold_create(conn, slot, "session-1", _jovoben())
    hold_id = conn.execute("SELECT id FROM hold WHERE slot_id = ?", (slot,)).fetchone()[0]
    assert foglalas_repo.hold_list(conn, slot_id=slot, session_id="session-1") == hold_id


def test_hold_list_not_finds_other_session_hold(conn, slot):
    foglalas_repo.hold_create(conn, slot, "session-1", _jovoben())
    assert foglalas_repo.hold_list(conn, slot_id=slot, session_id="session-2") is None


# --- slot_allapotok_lekerdezese --------------------------------------------


def test_slot_statuses_list_empty_for_shift(conn):
    master = _master_data_insert(conn)
    shift_id = _shift_insert(conn, master)
    assert foglalas_repo.slot_statuses_list(conn, shift_id=shift_id) == []


def test_slot_statuses_list_free(conn, slot):
    (shift_id,) = conn.execute("SELECT muszak_id FROM slot WHERE id = ?", (slot,)).fetchone()
    result = foglalas_repo.slot_statuses_list(conn, shift_id=shift_id)
    assert result == [
        {
            "slot_id": slot,
            "kezdet": "2026-08-18T08:00:00Z",
            "veg": "2026-08-18T08:30:00Z",
            "allapot": "szabad",
            "foglalasi_kod": None,
        }
    ]


def test_slot_statuses_list_held(conn, slot):
    (shift_id,) = conn.execute("SELECT muszak_id FROM slot WHERE id = ?", (slot,)).fetchone()
    foglalas_repo.hold_create(conn, slot, "session-1", _jovoben())
    result = foglalas_repo.slot_statuses_list(conn, shift_id=shift_id)
    assert result[0]["allapot"] == "holdolt"
    assert result[0]["foglalasi_kod"] is None


def test_slot_statuses_list_booked(conn, slot):
    (shift_id,) = conn.execute("SELECT muszak_id FROM slot WHERE id = ?", (slot,)).fetchone()
    foglalas_repo.booking_create(conn, slot, "a" * 64, _uuid(), "session-1")
    code = conn.execute("SELECT foglalasi_kod FROM foglalas WHERE slot_id = ?", (slot,)).fetchone()[
        0
    ]

    result = foglalas_repo.slot_statuses_list(conn, shift_id=shift_id)
    assert result[0]["allapot"] == "foglalt"
    assert result[0]["foglalasi_kod"] == code


def test_slot_statuses_list_lejart_hold_free_counts(conn, slot):
    """Ugyanaz az invariáns, mint `slot_szabad`-nál: egy lejárt, de még
    nem takarított hold NEM zárja ki a slotot 'szabad'-ként."""
    (shift_id,) = conn.execute("SELECT muszak_id FROM slot WHERE id = ?", (slot,)).fetchone()
    _lejart_hold_insert(conn, slot)
    result = foglalas_repo.slot_statuses_list(conn, shift_id=shift_id)
    assert result[0]["allapot"] == "szabad"


def test_slot_statuses_list_cancelled_booking_after_free(conn, slot):
    (shift_id,) = conn.execute("SELECT muszak_id FROM slot WHERE id = ?", (slot,)).fetchone()
    foglalas_repo.booking_create(conn, slot, "a" * 64, _uuid(), "session-1")
    code = conn.execute("SELECT foglalasi_kod FROM foglalas WHERE slot_id = ?", (slot,)).fetchone()[
        0
    ]
    foglalas_repo.booking_lemond(conn, code)

    result = foglalas_repo.slot_statuses_list(conn, shift_id=shift_id)
    assert result[0]["allapot"] == "szabad"
    assert result[0]["foglalasi_kod"] is None


def test_slot_statuses_list_multiple_slot_start_by_rendezve(conn):
    master = _master_data_insert(conn)
    shift_id = _shift_insert(conn, master)
    later = _slot_insert(conn, master, shift_id, "2026-08-18T08:30:00Z", "2026-08-18T09:00:00Z")
    earlier = _slot_insert(conn, master, shift_id, "2026-08-18T08:00:00Z", "2026-08-18T08:30:00Z")
    result = foglalas_repo.slot_statuses_list(conn, shift_id=shift_id)
    assert [e["slot_id"] for e in result] == [earlier, later]


# --- foglalasok_lekerdezese -------------------------------------------


def test_bookings_list_empty(conn, slot):
    (org_id,) = conn.execute("SELECT szervezet_id FROM slot WHERE id = ?", (slot,)).fetchone()
    assert foglalas_repo.bookings_list(conn, org_id=org_id) == []


def test_bookings_list_one_elem(conn, slot):
    (org_id,) = conn.execute("SELECT szervezet_id FROM slot WHERE id = ?", (slot,)).fetchone()
    foglalas_repo.booking_create(conn, slot, "a" * 64, _uuid(), "session-1")
    code = conn.execute("SELECT foglalasi_kod FROM foglalas WHERE slot_id = ?", (slot,)).fetchone()[
        0
    ]

    result = foglalas_repo.bookings_list(conn, org_id=org_id)
    assert len(result) == 1
    assert result[0]["foglalasi_kod"] == code
    assert result[0]["allapot"] == "aktiv"
    assert result[0]["slot_kezdet"] == "2026-08-18T08:00:00Z"
    assert "vasarlo_kulcs" not in result[0]


def test_bookings_list_contains_cancelled_is(conn, slot):
    (org_id,) = conn.execute("SELECT szervezet_id FROM slot WHERE id = ?", (slot,)).fetchone()
    foglalas_repo.booking_create(conn, slot, "a" * 64, _uuid(), "session-1")
    code = conn.execute("SELECT foglalasi_kod FROM foglalas WHERE slot_id = ?", (slot,)).fetchone()[
        0
    ]
    foglalas_repo.booking_lemond(conn, code)

    result = foglalas_repo.bookings_list(conn, org_id=org_id)
    assert len(result) == 1
    assert result[0]["allapot"] == "lemondva"


def test_bookings_list_filter_shop_by(conn):
    """Két bolt UGYANABBAN a szervezetben — a bolt_id szűrés valódi
    hatását teszteli, nem a szervezet_id-ét (ami önmagában is
    elválasztaná őket)."""
    master = _master_data_insert(conn)
    shift_id = _shift_insert(conn, master)
    own_slot = _slot_insert(conn, master, shift_id)
    foglalas_repo.booking_create(conn, own_slot, "a" * 64, _uuid(), "session-1")

    other_shop_id = torzsadat_repo.shop_create(
        conn, org_id=master["szervezet_id"], name="Másik bolt"
    )
    other_counter_id = torzsadat_repo.counter_create(
        conn, org_id=master["szervezet_id"], shop_id=other_shop_id, name="Másik pult"
    )
    other_employee_id = torzsadat_repo.employee_create(
        conn, org_id=master["szervezet_id"], shop_id=other_shop_id, name="Másik"
    )
    other_service_id = torzsadat_repo.service_create(
        conn,
        org_id=master["szervezet_id"],
        shop_id=other_shop_id,
        name="másik szolgáltatás",
        alap_duration_minute=15,
    )
    other_shift_master = {
        **master,
        "bolt_id": other_shop_id,
        "pult_id": other_counter_id,
        "alkalmazott_id": other_employee_id,
        "szolgaltatas_id": other_service_id,
    }
    other_shift = _shift_insert(conn, other_shift_master)
    other_slot = _slot_insert(conn, other_shift_master, other_shift)
    foglalas_repo.booking_create(conn, other_slot, "b" * 64, _uuid(), "session-2")

    result = foglalas_repo.bookings_list(
        conn, org_id=master["szervezet_id"], shop_id=master["bolt_id"]
    )
    assert len(result) == 1
    assert result[0]["bolt_id"] == master["bolt_id"]

    all = foglalas_repo.bookings_list(conn, org_id=master["szervezet_id"])
    assert len(all) == 2

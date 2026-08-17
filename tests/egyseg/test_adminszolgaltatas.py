"""Egységtesztek a mag/api/adminszolgaltatas.py szolgáltatásrétegére.

A Tkinter felületet (`felulet/admin/app.py`) nem teszteljük — ez a fájl
csak a mag/api/ oldalt, ami tiszta Python, GUI nélkül hívható.
"""

from __future__ import annotations

import pytest

from core.api import adminszolgaltatas as api
from core.repo import migracio, torzsadat_repo


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


def _felvitel(conn, master, start: str, end: str) -> dict:
    return api.shift_felvitel(
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


# --- muszak_felvitel — normál eset ----------------------------------------


def test_shift_felvitel_success(conn, master):
    result = _felvitel(conn, master, "2026-08-18T08:00:00Z", "2026-08-18T09:00:00Z")
    assert result["hiba"] is None
    assert result["kihagyva"] is False
    assert result["slot_szam"] == 6
    assert result["muszak_id"] is not None


# --- muszak_felvitel — fordított / nulla hosszú időablak: ÉRTELMES elutasítás ---


def test_shift_felvitel_reversed_time_window_reject_exception_without(conn, master):
    result = _felvitel(conn, master, "2026-08-18T09:00:00Z", "2026-08-18T08:00:00Z")
    assert result["hiba"] is not None
    assert result["muszak_id"] is None
    assert result["slot_szam"] == 0
    # A DB-be nem került be a hibás sor.
    assert conn.execute("SELECT COUNT(*) FROM muszak").fetchone()[0] == 0


def test_shift_felvitel_zero_long_time_window_reject_exception_without(conn, master):
    result = _felvitel(conn, master, "2026-08-18T08:00:00Z", "2026-08-18T08:00:00Z")
    assert result["hiba"] is not None
    assert conn.execute("SELECT COUNT(*) FROM muszak").fetchone()[0] == 0


# --- muszak_felvitel — kivétel nap ------------------------------------


def test_shift_felvitel_exception_on_day_zero_slot(conn, master):
    torzsadat_repo.exception_day_create(
        conn,
        org_id=master["szervezet_id"],
        shop_id=None,
        date="2026-08-18",
        reason="teszt ünnep",
    )
    result = _felvitel(conn, master, "2026-08-18T08:00:00Z", "2026-08-18T09:00:00Z")
    assert result["hiba"] is None
    assert result["kihagyva"] is True
    assert result["kihagyas_oka"] == "2026-08-18"
    assert result["slot_szam"] == 0
    # A műszak SOR létrejön (ez mutatja meg a kihagyást), csak slot/blokk nem.
    assert conn.execute("SELECT COUNT(*) FROM muszak").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM slot").fetchone()[0] == 0


# --- muszak_reszletei / het_muszakjai — üres eredmények -------------------


def test_week_shifts_empty_new_in_org(conn, master):
    result = api.week_shifts(conn, org_id=master["szervezet_id"], week_start_date="2026-08-17")
    assert result == []


def test_shift_details_empty_new_for_shift(conn, master):
    _felvitel(conn, master, "2026-08-18T08:00:00Z", "2026-08-18T08:00:00Z")  # elutasítva
    week = api.week_shifts(conn, org_id=master["szervezet_id"], week_start_date="2026-08-17")
    assert week == []  # az elutasított felvitel nem hozott létre műszakot


# =====================================================================
# Műszak-sablonok (muszak_sablon, migraciok/0003)
# =====================================================================


def test_shift_template_save_success(conn, master):
    felvitel = _felvitel(conn, master, "2026-08-18T08:00:00Z", "2026-08-18T16:00:00Z")
    result = api.shift_template_save(conn, shift_id=felvitel["muszak_id"], name="Alap napi")
    assert result["hiba"] is None
    assert result["sablon_id"] is not None

    templates = api.shift_templates(conn, org_id=master["szervezet_id"])
    assert len(templates) == 1
    assert templates[0]["nev"] == "Alap napi"
    assert templates[0]["kezdet_ora"] == 8
    assert templates[0]["veg_ora"] == 16
    assert templates[0]["pult_id"] == master["pult_id"]
    assert templates[0]["alkalmazott_id"] == master["alkalmazott_id"]
    assert templates[0]["szolgaltatas_id"] == master["szolgaltatas_id"]


def test_shift_template_save_not_existing_for_shift(conn, master):
    result = api.shift_template_save(conn, shift_id="nincs-ilyen", name="X")
    assert result["hiba"] is not None
    assert result["sablon_id"] is None


def test_shift_template_save_ejfelen_spanning_rejected(conn, master):
    felvitel = _felvitel(conn, master, "2026-08-18T22:00:00Z", "2026-08-19T02:00:00Z")
    result = api.shift_template_save(conn, shift_id=felvitel["muszak_id"], name="X")
    assert result["hiba"] is not None
    assert result["sablon_id"] is None


def test_shift_template_save_not_kerek_hour_rejected(conn, master):
    felvitel = _felvitel(conn, master, "2026-08-18T08:15:00Z", "2026-08-18T16:00:00Z")
    result = api.shift_template_save(conn, shift_id=felvitel["muszak_id"], name="X")
    assert result["hiba"] is not None
    assert result["sablon_id"] is None


def _template_save(conn, master, start="2026-08-18T08:00:00Z", end="2026-08-18T16:00:00Z") -> str:
    felvitel = _felvitel(conn, master, start, end)
    result = api.shift_template_save(conn, shift_id=felvitel["muszak_id"], name="Alap napi")
    return result["sablon_id"]


def test_shift_template_apply_for_day(conn, master):
    template_id = _template_save(conn, master)
    result = api.shift_template_apply_for_day(conn, template_id=template_id, date="2026-08-25")
    assert result["hiba"] is None
    assert result["kihagyva"] is False
    assert result["slot_szam"] == 48  # 8 óra, 10 perces slot


def test_shift_template_apply_for_day_not_existing_for_template(conn):
    result = api.shift_template_apply_for_day(conn, template_id="nincs-ilyen", date="2026-08-25")
    assert result["hiba"] is not None


def test_shift_template_apply_for_day_exception_on_day_skipped(conn, master):
    template_id = _template_save(conn, master)
    torzsadat_repo.exception_day_create(
        conn,
        org_id=master["szervezet_id"],
        shop_id=None,
        date="2026-08-25",
        reason="teszt ünnep",
    )
    result = api.shift_template_apply_for_day(conn, template_id=template_id, date="2026-08-25")
    assert result["hiba"] is None
    assert result["kihagyva"] is True
    assert result["slot_szam"] == 0


def test_shift_template_apply_for_week_week_shift_hoz_create(conn, master):
    template_id = _template_save(conn, master)
    results = api.shift_template_apply_for_week(
        conn, template_id=template_id, week_start_date="2026-09-07"
    )
    assert len(results) == 7
    assert all(e["hiba"] is None for e in results)
    assert all(e["slot_szam"] == 48 for e in results)

    week = api.week_shifts(conn, org_id=master["szervezet_id"], week_start_date="2026-09-07")
    assert len(week) == 7


def test_shift_template_apply_for_week_exception_day_skips(conn, master):
    template_id = _template_save(conn, master)
    torzsadat_repo.exception_day_create(
        conn,
        org_id=master["szervezet_id"],
        shop_id=None,
        date="2026-09-09",  # a 2026-09-07-i hét szerdája
        reason="teszt ünnep",
    )
    results = api.shift_template_apply_for_week(
        conn, template_id=template_id, week_start_date="2026-09-07"
    )
    skipped = [e for e in results if e["kihagyva"]]
    assert len(skipped) == 1

    week = api.week_shifts(conn, org_id=master["szervezet_id"], week_start_date="2026-09-07")
    assert len(week) == 7  # a muszak SOR a kivétel napon is létrejön
    generated_slot_counts = sorted(m["slot_szam"] for m in week)
    assert generated_slot_counts[0] == 0  # a kivétel napi műszaknak nincs slotja
    assert generated_slot_counts[-1] == 48


# --- het_masolasa -------------------------------------------------------


def test_week_copy_copies_shifts_other_for_week(conn, master):
    _felvitel(conn, master, "2026-08-17T08:00:00Z", "2026-08-17T16:00:00Z")  # hétfő
    _felvitel(conn, master, "2026-08-19T08:00:00Z", "2026-08-19T16:00:00Z")  # szerda

    results = api.week_copy(
        conn,
        org_id=master["szervezet_id"],
        source_week_start="2026-08-17",
        target_week_start="2026-09-07",
    )
    assert len(results) == 2
    assert all(e["hiba"] is None and e["kihagyva"] is False for e in results)

    target_week = api.week_shifts(conn, org_id=master["szervezet_id"], week_start_date="2026-09-07")
    target_dates = sorted(m["kezdet"][:10] for m in target_week)
    assert target_dates == ["2026-09-07", "2026-09-09"]  # ugyanaz a hétfő/szerda mintázat


def test_week_copy_empty_source_week_empty_result(conn, master):
    results = api.week_copy(
        conn,
        org_id=master["szervezet_id"],
        source_week_start="2026-08-17",
        target_week_start="2026-09-07",
    )
    assert results == []


def test_week_copy_exception_day_skips_target_in_week(conn, master):
    _felvitel(conn, master, "2026-08-17T08:00:00Z", "2026-08-17T16:00:00Z")  # hétfő
    torzsadat_repo.exception_day_create(
        conn,
        org_id=master["szervezet_id"],
        shop_id=None,
        date="2026-09-07",  # a cél hét hétfője
        reason="teszt ünnep",
    )

    results = api.week_copy(
        conn,
        org_id=master["szervezet_id"],
        source_week_start="2026-08-17",
        target_week_start="2026-09-07",
    )
    assert len(results) == 1
    assert results[0]["kihagyva"] is True
    assert results[0]["slot_szam"] == 0


# =====================================================================
# Törzsadat-szerkesztés (bolt, pult, alkalmazott, szolgáltatás, kivétel nap)
# =====================================================================


def test_shop_add_success(conn, master):
    result = api.shop_add(conn, org_id=master["szervezet_id"], name="Törpilla")
    assert result["hiba"] is None
    assert result["bolt_id"] is not None
    names = [b["nev"] for b in api.shops(conn, org_id=master["szervezet_id"])]
    assert "Törpilla" in names


def test_shop_add_empty_name_sensible_rejection(conn, master):
    result = api.shop_add(conn, org_id=master["szervezet_id"], name="   ")
    assert result["hiba"] is not None
    assert result["bolt_id"] is None
    assert api.shops(conn, org_id=master["szervezet_id"]) == [
        {"id": master["bolt_id"], "nev": "Ügyifogyi"}
    ]


def test_shop_update_success(conn, master):
    result = api.shop_update(conn, shop_id=master["bolt_id"], name="Új név")
    assert result["hiba"] is None
    names = [b["nev"] for b in api.shops(conn, org_id=master["szervezet_id"])]
    assert names == ["Új név"]


def test_shop_update_empty_name_sensible_rejection(conn, master):
    result = api.shop_update(conn, shop_id=master["bolt_id"], name="")
    assert result["hiba"] is not None
    names = [b["nev"] for b in api.shops(conn, org_id=master["szervezet_id"])]
    assert names == ["Ügyifogyi"]  # változatlan


def test_counter_add_and_update(conn, master):
    add = api.counter_add(
        conn, org_id=master["szervezet_id"], shop_id=master["bolt_id"], name="Pult A"
    )
    assert add["hiba"] is None
    update = api.counter_update(conn, counter_id=add["pult_id"], name="Pult B")
    assert update["hiba"] is None
    names = [p["nev"] for p in api.counters(conn, shop_id=master["bolt_id"])]
    # a torzs fixture már felvett egy "Pult 1"-et — az átnevezett újnak
    # kell szerepelnie, "Pult A" néven viszont már nem.
    assert "Pult B" in names
    assert "Pult A" not in names


def test_counter_add_empty_name_sensible_rejection(conn, master):
    result = api.counter_add(
        conn, org_id=master["szervezet_id"], shop_id=master["bolt_id"], name=""
    )
    assert result["hiba"] is not None
    assert result["pult_id"] is None


def test_employee_add_and_update(conn, master):
    add = api.employee_add(
        conn, org_id=master["szervezet_id"], shop_id=master["bolt_id"], name="Régi"
    )
    assert add["hiba"] is None
    update = api.employee_update(conn, employee_id=add["alkalmazott_id"], name="Új")
    assert update["hiba"] is None
    names = [a["nev"] for a in api.employees(conn, shop_id=master["bolt_id"])]
    assert "Új" in names
    assert "Régi" not in names


def test_service_add_and_update(conn, master):
    add = api.service_add(
        conn,
        org_id=master["szervezet_id"],
        shop_id=master["bolt_id"],
        name="Régi",
        alap_duration_minute=5,
    )
    assert add["hiba"] is None
    update = api.service_update(
        conn,
        service_id=add["szolgaltatas_id"],
        name="Új",
        alap_duration_minute=30,
    )
    assert update["hiba"] is None
    result = {s["nev"]: s for s in api.services(conn, shop_id=master["bolt_id"])}
    assert "Régi" not in result
    assert result["Új"]["alap_idotartam_perc"] == 30


def test_service_add_not_positive_for_duration_sensible_rejection(conn, master):
    result = api.service_add(
        conn,
        org_id=master["szervezet_id"],
        shop_id=master["bolt_id"],
        name="Valami",
        alap_duration_minute=0,
    )
    assert result["hiba"] is not None
    assert result["szolgaltatas_id"] is None


def test_exception_day_add_success(conn, master):
    result = api.exception_day_add(
        conn,
        org_id=master["szervezet_id"],
        shop_id=None,
        date="2026-12-25",
        reason="karácsony",
    )
    assert result["hiba"] is None
    assert result["kivetel_id"] is not None
    list = api.exception_days(conn, org_id=master["szervezet_id"])
    assert [k["datum"] for k in list] == ["2026-12-25"]


def test_exception_day_add_invalid_for_date_sensible_rejection(conn, master):
    result = api.exception_day_add(
        conn,
        org_id=master["szervezet_id"],
        shop_id=None,
        date="nem-datum",
        reason="karácsony",
    )
    assert result["hiba"] is not None
    assert result["kivetel_id"] is None
    assert api.exception_days(conn, org_id=master["szervezet_id"]) == []


def test_exception_day_add_empty_for_reason_sensible_rejection(conn, master):
    result = api.exception_day_add(
        conn, org_id=master["szervezet_id"], shop_id=None, date="2026-12-25", reason=""
    )
    assert result["hiba"] is not None
    assert result["kivetel_id"] is None


def test_exception_day_add_and_shift_felvitel_skips(conn, master):
    """Integrációs pillanatkép: az admin által felvitt kivétel nap
    ugyanúgy kihagyatja a generátort, mint a seed-elt kivétel nap."""
    api.exception_day_add(
        conn,
        org_id=master["szervezet_id"],
        shop_id=None,
        date="2026-08-18",
        reason="admin által felvett ünnep",
    )
    result = _felvitel(conn, master, "2026-08-18T08:00:00Z", "2026-08-18T09:00:00Z")
    assert result["kihagyva"] is True
    assert result["kihagyas_oka"] == "2026-08-18"


# =====================================================================
# Ütközéslista (mag/szabalyok/kenyszerek.py-ra épülve)
# =====================================================================


def test_conflict_list_empty_new_in_org(conn, master):
    assert api.conflict_list(conn, org_id=master["szervezet_id"]) == []


def test_conflict_list_constraint_violation_signals_break_nelkuli_long_for_shift(conn, master):
    _felvitel(conn, master, "2026-08-18T08:00:00Z", "2026-08-18T16:00:00Z")  # 8 óra, szünet nélkül

    problems = api.conflict_list(conn, org_id=master["szervezet_id"])
    szabalyok = {p["szabaly"] for p in problems}
    assert "munkajogi_minimum" in szabalyok
    assert "minimum_osszes_szunet" in szabalyok
    assert all(p["tipus"] == "kenyszer_sertes" for p in problems)


def test_conflict_list_not_signals_nothing_short_for_shift_if_break_threshold_zero(conn, master):
    """1 órás műszak a 6 órás munkajogi küszöb ALATT — a
    `min_osszes_szunet_perc` a kenyszerek.ellenoriz()-ben FELTÉTEL
    NÉLKÜLI minimum (nem csak a hosszú műszakokra vonatkozik), ezért
    ehhez a teszthez explicit 0-ra állítjuk, hogy kizárólag a munkajogi
    küszöb hatását nézzük."""
    _felvitel(conn, master, "2026-08-18T08:00:00Z", "2026-08-18T09:00:00Z")
    assert api.conflict_list(conn, org_id=master["szervezet_id"], min_all_break_minute=0) == []


def test_conflict_list_overlapping_shifts_same_on_counter(conn, master):
    _felvitel(conn, master, "2026-08-18T08:00:00Z", "2026-08-18T10:00:00Z")
    _felvitel(conn, master, "2026-08-18T09:00:00Z", "2026-08-18T11:00:00Z")  # átfedi az elsőt

    problems = api.conflict_list(conn, org_id=master["szervezet_id"])
    overlaps = [p for p in problems if p["tipus"] == "atfedes"]
    assert len(overlaps) == 1
    assert overlaps[0]["szabaly"] == "atfedo_muszak"


def test_conflict_list_not_overlapping_shifts_different_counters(conn, master):
    other_counter = torzsadat_repo.counter_create(
        conn, org_id=master["szervezet_id"], shop_id=master["bolt_id"], name="Másik pult"
    )
    _felvitel(conn, master, "2026-08-18T08:00:00Z", "2026-08-18T10:00:00Z")
    api.shift_felvitel(
        conn,
        org_id=master["szervezet_id"],
        shop_id=master["bolt_id"],
        counter_id=other_counter,
        employee_id=master["alkalmazott_id"],
        service_id=master["szolgaltatas_id"],
        start="2026-08-18T09:00:00Z",  # időben átfedi az elsőt, DE másik pulton
        end="2026-08-18T11:00:00Z",
        duration_minute=10,
        buffer_after_minute=0,
        min_grid_minute=10,
        bookable_ratio=1.0,
        block_rule={"szunetek": []},
    )

    problems = api.conflict_list(conn, org_id=master["szervezet_id"])
    overlaps = [p for p in problems if p["tipus"] == "atfedes"]
    assert overlaps == []


def test_conflict_list_egymast_touching_shifts_not_overlap(conn, master):
    """Az egyik vége pont a másik kezdete — ez nem átfedés, csak
    egymáshoz illeszkedés."""
    _felvitel(conn, master, "2026-08-18T08:00:00Z", "2026-08-18T09:00:00Z")
    _felvitel(conn, master, "2026-08-18T09:00:00Z", "2026-08-18T10:00:00Z")

    problems = api.conflict_list(conn, org_id=master["szervezet_id"])
    assert [p for p in problems if p["tipus"] == "atfedes"] == []


def test_conflict_list_zero_slot_not_exception_on_day_signalled(conn, master):
    """5 perces ablak 10 perces slottal — nulla slot generálódik, DE
    nincs kivétel nap, tehát ez valódi probléma."""
    result = _felvitel(conn, master, "2026-08-18T08:00:00Z", "2026-08-18T08:05:00Z")
    assert result["slot_szam"] == 0

    problems = api.conflict_list(conn, org_id=master["szervezet_id"])
    zero_slots = [p for p in problems if p["tipus"] == "nulla_slot"]
    assert len(zero_slots) == 1


def test_conflict_list_exception_on_day_nothing_not_signals(conn, master):
    """A kivétel napi nulla slot ÉS az üres blokklista miatti kényszer-
    sértés is HAMIS pozitív lenne — egyik se kerülhet az ütközéslistába."""
    torzsadat_repo.exception_day_create(
        conn,
        org_id=master["szervezet_id"],
        shop_id=None,
        date="2026-08-18",
        reason="ünnep",
    )
    result = _felvitel(conn, master, "2026-08-18T08:00:00Z", "2026-08-18T16:00:00Z")
    assert result["kihagyva"] is True

    assert api.conflict_list(conn, org_id=master["szervezet_id"]) == []


def test_conflict_list_shop_by_filterable(conn, master):
    other_shop = torzsadat_repo.shop_create(conn, org_id=master["szervezet_id"], name="Másik bolt")
    other_counter = torzsadat_repo.counter_create(
        conn, org_id=master["szervezet_id"], shop_id=other_shop, name="Másik pult"
    )
    other_employee = torzsadat_repo.employee_create(
        conn, org_id=master["szervezet_id"], shop_id=other_shop, name="Másik"
    )
    other_service = torzsadat_repo.service_create(
        conn,
        org_id=master["szervezet_id"],
        shop_id=other_shop,
        name="másik",
        alap_duration_minute=10,
    )
    api.shift_felvitel(
        conn,
        org_id=master["szervezet_id"],
        shop_id=other_shop,
        counter_id=other_counter,
        employee_id=other_employee,
        service_id=other_service,
        start="2026-08-18T08:00:00Z",
        end="2026-08-18T16:00:00Z",
        duration_minute=10,
        buffer_after_minute=0,
        min_grid_minute=10,
        bookable_ratio=1.0,
        block_rule={"szunetek": []},
    )

    own_shop_problems = api.conflict_list(
        conn, org_id=master["szervezet_id"], shop_id=master["bolt_id"]
    )
    assert own_shop_problems == []  # a másik bolt problémája nem jön be

    all = api.conflict_list(conn, org_id=master["szervezet_id"])
    assert len(all) > 0

"""Egységtesztek a mag/szabalyok/kenyszerek.py kemény kényszereire."""

from __future__ import annotations

from core.modell.shift import Block, Shift
from core.szabalyok import kenyszerek as k


def _shift(start: str = "2026-08-18T08:00:00Z", end: str = "2026-08-18T16:00:00Z") -> Shift:
    return Shift(
        id="m",
        org_id="sz",
        start=start,
        end=end,
        duration_minute=30,
        buffer_after_minute=0,
        min_grid_minute=10,
        bookable_ratio=1.0,
        block_rule={},
    )


def test_no_violation_if_all_rendben():
    shift = _shift()  # 8 órás műszak
    blocks = [Block("szunet", "2026-08-18T12:00:00Z", "2026-08-18T12:20:00Z", True, True)]
    violations = k.check(shift, blocks, min_all_break_minute=15, max_continuous_work_minute=300)
    assert violations == []


def test_block_on_shift_tul_violation():
    shift = _shift()
    blocks = [Block("szunet", "2026-08-18T07:50:00Z", "2026-08-18T12:20:00Z", True, True)]
    violations = k.check(shift, blocks, min_all_break_minute=5, max_continuous_work_minute=600)
    assert [s.rule for s in violations] == ["blokk_muszakon_belul"]


def test_min_all_break_violation():
    shift = _shift()
    blocks = [Block("szunet", "2026-08-18T12:00:00Z", "2026-08-18T12:05:00Z", True, True)]
    violations = k.check(shift, blocks, min_all_break_minute=20, max_continuous_work_minute=600)
    assert "minimum_osszes_szunet" in [s.rule for s in violations]


def test_max_continuous_work_violation():
    shift = _shift()  # 8 óra, egyetlen szünet a közepén
    blocks = [Block("szunet", "2026-08-18T12:00:00Z", "2026-08-18T12:20:00Z", True, True)]
    # a szünet előtti szakasz 4 óra (240 perc) — ha a küszöb ez alatt van, sértés
    violations = k.check(shift, blocks, min_all_break_minute=15, max_continuous_work_minute=180)
    szabalyok = [s.rule for s in violations]
    assert szabalyok.count("maximum_folyamatos_munka") == 2  # szünet előtt ÉS után is túllépi


def test_labor_law_min_6_hour_under_not_required():
    shift = _shift(end="2026-08-18T13:00:00Z")  # 5 órás műszak, nincs szünet
    violations = k.check(shift, [], min_all_break_minute=0, max_continuous_work_minute=600)
    assert "munkajogi_minimum" not in [s.rule for s in violations]


def test_labor_law_min_6_hour_above_required_and_violatable():
    shift = _shift()  # 8 óra
    blocks = [Block("szunet", "2026-08-18T12:00:00Z", "2026-08-18T12:10:00Z", True, True)]
    violations = k.check(shift, blocks, min_all_break_minute=5, max_continuous_work_minute=600)
    assert "munkajogi_minimum" in [s.rule for s in violations]  # 10 perc < 20 perces minimum


def test_labor_law_min_20_minute_break_satisfies():
    shift = _shift()  # 8 óra
    blocks = [Block("szunet", "2026-08-18T12:00:00Z", "2026-08-18T12:20:00Z", True, True)]
    violations = k.check(shift, blocks, min_all_break_minute=15, max_continuous_work_minute=600)
    assert "munkajogi_minimum" not in [s.rule for s in violations]

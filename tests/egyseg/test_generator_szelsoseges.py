"""Szélsőséges esetek a slotgenerátorra (mag/slot/generator.py).

A `test_blokk_generator.py` már fedi a normál Törpilla-ábrákat, a DST-t
és a kivetel_nap ágat (`test_kivetel_napon_nem_general_semmit`) — ez a
fájl kifejezetten a határeseteket célozza: első/utolsó slot, éjfélen
átnyúló műszak, és a nulla hosszú / fordított időablak, ami NEM dobhat
kivételt (a `Muszak` dataclass maga nem validál, a DB-szintű
`CHECK (veg > kezdet)` csak a `mag/repo/`-n át írt sorokra vonatkozik —
ez a teszt a tiszta generátor-függvényt közvetlenül hívja, `mag/repo/`
nélkül).
"""

from __future__ import annotations

from core.modell.shift import Shift
from core.slot import generator
from core.slot.blokk import FixedBlock

_STRATEGIA = FixedBlock()


def _shift(
    start: str,
    end: str,
    duration_minute: int = 10,
    buffer_after_minute: int = 0,
    min_grid_minute: int = 10,
    bookable_ratio: float = 1.0,
    block_rule: dict | None = None,
) -> Shift:
    return Shift(
        id="m",
        org_id="sz",
        start=start,
        end=end,
        duration_minute=duration_minute,
        buffer_after_minute=buffer_after_minute,
        min_grid_minute=min_grid_minute,
        bookable_ratio=bookable_ratio,
        block_rule=block_rule or {"szunetek": []},
    )


# --- első és utolsó slot -------------------------------------------------


def test_first_slot_pontosan_shift_at_start_kezdodik():
    shift = _shift("2026-08-18T08:00:00Z", "2026-08-18T09:00:00Z")
    result = generator.generate(shift, _STRATEGIA)
    assert result.slots[0].start == shift.start


def test_last_slot_not_nyulik_tul_shift_at_end():
    shift = _shift("2026-08-18T08:00:00Z", "2026-08-18T09:00:00Z")
    result = generator.generate(shift, _STRATEGIA)
    assert result.slots[-1].end <= shift.end


def test_last_slot_not_generate_if_not_ferne_ki_pontosan():
    """55 perces műszak, 10 perces slot, 0 puffer → 5 slot fér ki
    (50 perc), az 55. percig nincs hatodik — nem csonka slotot generál."""
    shift = _shift("2026-08-18T08:00:00Z", "2026-08-18T08:55:00Z")
    result = generator.generate(shift, _STRATEGIA)
    assert len(result.slots) == 5
    assert result.slots[-1].end == "2026-08-18T08:50:00Z"


# --- éjfélen átnyúló műszak ------------------------------------------------


def test_ejfelen_spanning_shift_correct_slot_count():
    """22:00–02:00 (+1 nap), 10 perces slot → 4 óra = 24 slot. A kezdet/
    veg teljes ISO-8601 időbélyeg, nem csak óra:perc, ezért az éjfél
    átlépése a generátornak nem külön eset — normál dátumaritmetika."""
    shift = _shift("2026-08-18T22:00:00Z", "2026-08-19T02:00:00Z")
    result = generator.generate(shift, _STRATEGIA)
    assert len(result.slots) == 24
    assert result.slots[0].start == "2026-08-18T22:00:00Z"
    assert result.slots[-1].end == "2026-08-19T02:00:00Z"


def test_ejfelen_spanning_shift_with_break_not_lognak_across_at_boundary():
    shift = _shift(
        "2026-08-18T23:30:00Z",
        "2026-08-19T01:00:00Z",
        block_rule={"szunetek": [{"tipus": "szunet", "hossz_perc": 10, "mintazat": "oranta"}]},
    )
    result = generator.generate(shift, _STRATEGIA)
    for blokk in result.blocks:
        assert shift.start <= blokk.start
        assert blokk.end <= shift.end


# --- nulla hosszú / fordított időablak ------------------------------------


def test_zero_long_time_window_empty_result_not_exception():
    shift = _shift("2026-08-18T08:00:00Z", "2026-08-18T08:00:00Z")
    result = generator.generate(shift, _STRATEGIA)
    assert result.skipped is False
    assert result.slots == []
    assert result.blocks == []


def test_reversed_time_window_empty_result_not_exception():
    shift = _shift("2026-08-18T09:00:00Z", "2026-08-18T08:00:00Z")
    result = generator.generate(shift, _STRATEGIA)
    assert result.skipped is False
    assert result.slots == []
    assert result.blocks == []


def test_reversed_time_window_with_break_is_empty_not_exception():
    """A szünet-generálás is ciklikus (while True: ... break) — fordított
    ablakon az első iterációban ki kell lépnie, nem szabad végtelen
    ciklusba futnia."""
    shift = _shift(
        "2026-08-18T09:00:00Z",
        "2026-08-18T08:00:00Z",
        block_rule={"szunetek": [{"tipus": "szunet", "hossz_perc": 10, "mintazat": "oranta"}]},
    )
    result = generator.generate(shift, _STRATEGIA)
    assert result.slots == []
    assert result.blocks == []


def test_very_short_time_window_if_one_slot_worth_nor_fer_ki():
    """5 perces ablak, 10 perces slot — nem fér ki egy slot sem, de ez
    nem kivétel, csak üres eredmény."""
    shift = _shift("2026-08-18T08:00:00Z", "2026-08-18T08:05:00Z")
    result = generator.generate(shift, _STRATEGIA)
    assert result.slots == []

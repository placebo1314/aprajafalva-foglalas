"""Egységtesztek a mag/slot/blokk.py + mag/slot/generator.py párra.

Az első teszteset a roadmap „Az első tíz lépés" 7. pontja szerint: „az
egyórás Törpilla-ábra" — a Törpilla bolt három pultjának egy órája.
Emellett DST-teszt (tavaszi és őszi óraátállás, Europe/Budapest) és a
kivetel_nap / szabad sáv ágak.
"""

from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from core.modell.shift import Shift
from core.slot import generator
from core.slot._idomatek import minute_difference
from core.slot.blokk import FixedBlock

_STRATEGIA = FixedBlock()


def _shift(
    duration_minute: int,
    buffer_after_minute: int,
    min_grid_minute: int,
    block_rule: dict,
    bookable_ratio: float = 1.0,
    start: str = "2026-08-18T08:00:00Z",
    end: str = "2026-08-18T09:00:00Z",
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
        block_rule=block_rule,
    )


# --- Törpilla-pultok, egy óra ------------------------------------------


def test_gipszjakab_three_slot_three_break_block():
    """GipszJakab: 10 perc vásárlás, 10 perc szünet minden vásárlás után —
    egy órába pontosan 3 ciklus fér (10+10)×3 = 60 perc."""
    shift = _shift(
        duration_minute=10,
        buffer_after_minute=0,
        min_grid_minute=10,
        block_rule={
            "szunetek": [{"tipus": "szunet", "hossz_perc": 10, "mintazat": "minden_slot_utan"}]
        },
    )

    result = generator.generate(shift, _STRATEGIA)

    assert len(result.slots) == 3
    assert all(s.length_minute() == 10 for s in result.slots)
    assert len(result.blocks) == 3
    assert all(b.tipus == "szunet" and b.length_minute() == 10 for b in result.blocks)
    _no_overlap(result)
    _total_minutes_matches_with_shift(shift, result)


def test_torpilla_two_slot_15_minute_break():
    """Törpilla: legfeljebb 2 vásárló óránként (20 perces szolgáltatás),
    15 perces szünet óránként egyszer."""
    shift = _shift(
        duration_minute=20,
        buffer_after_minute=0,
        min_grid_minute=20,
        block_rule={"szunetek": [{"tipus": "szunet", "hossz_perc": 15, "mintazat": "oranta"}]},
    )

    result = generator.generate(shift, _STRATEGIA)

    assert len(result.slots) == 2
    assert all(s.length_minute() == 20 for s in result.slots)
    assert len(result.blocks) == 1
    assert result.blocks[0].tipus == "szunet"
    assert result.blocks[0].length_minute() == 15
    _no_overlap(result)


def test_hulk_hugan_four_slot_break_without():
    """Hulk Hugan: 15 percenként foglalható, szünet nélkül — egy órába
    pontosan 4 slot fér."""
    shift = _shift(
        duration_minute=15,
        buffer_after_minute=0,
        min_grid_minute=15,
        block_rule={"szunetek": []},
    )

    result = generator.generate(shift, _STRATEGIA)

    assert len(result.slots) == 4
    assert all(s.length_minute() == 15 for s in result.slots)
    assert result.blocks == []
    _total_minutes_matches_with_shift(shift, result)


# --- Szabad sáv és kivétel nap ------------------------------------------


def test_free_band_shift_to_end_aligned():
    shift = _shift(
        duration_minute=15,
        buffer_after_minute=0,
        min_grid_minute=15,
        block_rule={"szunetek": []},
        bookable_ratio=0.75,
    )

    result = generator.generate(shift, _STRATEGIA)

    assert len(result.blocks) == 1
    free_band = result.blocks[0]
    assert free_band.tipus == "szabad_sav"
    assert free_band.end == shift.end
    assert free_band.length_minute() == 15  # 60 perc 25%-a
    assert len(result.slots) == 3  # a maradék 45 percbe 3×15 perc fér
    _no_overlap(result)


def test_free_band_and_break_pattern_not_fedi_egymast():
    """Regresszióteszt: ha egyszerre van szünetmintázat ÉS foglalhato_arany
    < 1.0, a szünetciklusok nem lóghatnak bele a szabad sávba — a szünet
    elsőbbrendű, a szabad sáv az adott órában lerövidül vagy elmarad
    (lásd mag/slot/blokk.py, FixBlokk._szabad_sav)."""
    shift = _shift(
        duration_minute=10,
        buffer_after_minute=0,
        min_grid_minute=10,
        block_rule={
            "szunetek": [{"tipus": "szunet", "hossz_perc": 10, "mintazat": "minden_slot_utan"}]
        },
        bookable_ratio=0.8,
        start="2026-08-18T08:00:00Z",
        end="2026-08-18T16:00:00Z",
    )

    result = generator.generate(shift, _STRATEGIA)

    free_band = [b for b in result.blocks if b.tipus == "szabad_sav"]
    assert len(free_band) > 0
    break_blocks = [b for b in result.blocks if b.tipus == "szunet"]
    for szunet in break_blocks:
        for band in free_band:
            overlaps = szunet.start < band.end and szunet.end > band.start
            assert not overlaps, f"szünet és szabad sáv átfedésben: {szunet} / {band}"
    _no_overlap(result)


def test_free_band_hourly_elosztva_eight_hour_in_shift():
    """8 órás műszak, szünet nélkül, foglalhato_arany=0.8 -> legalább 4
    szabad sáv blokk, óránként egyenletesen elosztva — nem egyetlen blokk
    a műszak végén (ADR-011: "elnyeli a csúszást", ami csak akkor igaz,
    ha a szabad idő a nap egészében jelen van)."""
    shift = _shift(
        duration_minute=15,
        buffer_after_minute=0,
        min_grid_minute=15,
        block_rule={"szunetek": []},
        bookable_ratio=0.8,
        start="2026-08-18T08:00:00Z",
        end="2026-08-18T16:00:00Z",
    )

    result = generator.generate(shift, _STRATEGIA)

    free_band = sorted((b for b in result.blocks if b.tipus == "szabad_sav"), key=lambda b: b.start)
    assert len(free_band) >= 4

    # "Egyenletesen elosztva": a blokkok között nincs 2 óránál nagyobb rés,
    # tehát nem torlódnak egyetlen szakaszba.
    boundaries = [shift.start, *[b.start for b in free_band], shift.end]
    gaps = [minute_difference(boundaries[i], boundaries[i + 1]) for i in range(len(boundaries) - 1)]
    assert all(gap <= 120 for gap in gaps), f"nem egyenletes eloszlás: {gaps}"
    _no_overlap(result)


def test_bookable_ratio_one_eseten_no_free_band():
    shift = _shift(15, 0, 15, {"szunetek": []}, bookable_ratio=1.0)
    result = generator.generate(shift, _STRATEGIA)
    assert not any(b.tipus == "szabad_sav" for b in result.blocks)


def test_exception_on_day_not_generate_nothing():
    shift = _shift(
        15,
        0,
        15,
        {"szunetek": []},
        start="2026-12-25T08:00:00Z",
        end="2026-12-25T09:00:00Z",
    )

    result = generator.generate(shift, _STRATEGIA, exception_days=frozenset({"2026-12-25"}))

    assert result.skipped is True
    assert result.skip_oka == "2026-12-25"
    assert result.slots == []
    assert result.blocks == []


def test_not_exception_on_day_generates():
    shift = _shift(
        15,
        0,
        15,
        {"szunetek": []},
        start="2026-12-26T08:00:00Z",
        end="2026-12-26T09:00:00Z",
    )

    result = generator.generate(shift, _STRATEGIA, exception_days=frozenset({"2026-12-25"}))

    assert result.skipped is False
    assert len(result.slots) == 4


# --- DST: 2027-03-28 (óraátállítás tavasszal) és 2027-10-31 (ősszel) ----


def test_dst_tavaszi_transition_total_minutes_matches():
    _dst_test("2027-03-28")


def test_dst_oszi_transition_total_minutes_matches():
    _dst_test("2027-10-31")


def _dst_test(date: str) -> None:
    """Egy 08:00–16:00 helyi idejű (Europe/Budapest) 8 órás műszak — a
    generált slotok összperce pontosan egyezzen a műszak tényleges UTC
    hosszával, ne legyen duplikált vagy hiányzó slot, függetlenül attól,
    hogy a nap CET-ben vagy CEST-ben van."""
    zone = ZoneInfo("Europe/Budapest")
    year, month, day = (int(part) for part in date.split("-"))
    start_local = datetime(year, month, day, 8, 0, tzinfo=zone)
    end_local = datetime(year, month, day, 16, 0, tzinfo=zone)
    start_utc = start_local.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    end_utc = end_local.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

    shift = _shift(
        duration_minute=15,
        buffer_after_minute=0,
        min_grid_minute=15,
        block_rule={"szunetek": []},
        start=start_utc,
        end=end_utc,
    )

    result = generator.generate(shift, _STRATEGIA)

    actual_length = minute_difference(start_utc, end_utc)
    assert actual_length == 480  # 8 óra, DST-től függetlenül (UTC-ben mérve)

    total_minutes = sum(s.length_minute() for s in result.slots)
    assert total_minutes == actual_length

    starts = [s.start for s in result.slots]
    assert len(starts) == len(set(starts)), "duplikált slot"
    assert len(result.slots) == 32  # 480 / 15


# --- segédek --------------------------------------------------------------


def _no_overlap(result) -> None:
    """Sem a slotok, sem a slotok és a blokkok nem fedhetik egymást."""
    periods = [(s.start, s.end) for s in result.slots] + [(b.start, b.end) for b in result.blocks]
    periods.sort()
    for previous, next in zip(periods, periods[1:], strict=False):
        assert previous[1] <= next[0], f"átfedés: {previous} és {next}"


def _total_minutes_matches_with_shift(shift: Shift, result) -> None:
    slot_minute = sum(s.length_minute() for s in result.slots)
    block_minute = sum(b.length_minute() for b in result.blocks)
    assert slot_minute + block_minute == minute_difference(shift.start, shift.end)

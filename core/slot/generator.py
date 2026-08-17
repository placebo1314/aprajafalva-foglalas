"""A slotgenerátor.

Sorrend: előbb a blokkok (`BlokkStrategia.general()`), aztán a slotok a
maradék időbe — soha nem generál slotot blokkba (foglalasi-mag skill,
roadmap „Az első tíz lépés" 7. pont: „Első teszteset: az egyórás Törpilla-
ábra.").

A műszak snapshot-mezőit használja (`idotartam_perc`, `puffer_utana_perc`,
`min_racs_perc`) — a törzsadatot nem nézi, azok már befagyasztva vannak a
`Muszak` objektumban (docs/domain.md, "Snapshot"). Kivétel-napra
(`kivetel_nap`) nem generál semmit.

Nincs benne SQL — tiszta számítás (CLAUDE.md, 5. invariáns). A perzisztálás
a `mag/repo/muszak_repo.py` dolga.
"""

from __future__ import annotations

from dataclasses import dataclass

from core.modell.shift import Block, Shift, Slot
from core.slot._idomatek import add_minute, minute_difference
from core.slot.blokk import BlockStrategy


@dataclass(frozen=True)
class GenerationResult:
    skipped: bool
    skip_oka: str | None
    blocks: list[Block]
    slots: list[Slot]


def generate(
    shift: Shift,
    strategia: BlockStrategy,
    exception_days: frozenset[str] = frozenset(),
) -> GenerationResult:
    """Egyetlen műszakra generálja a blokkokat és a slotokat.

    `kivetel_napok`: `YYYY-MM-DD` dátumok halmaza (lásd
    `mag/repo/muszak_repo.py::kivetel_napok_lekerdezese`). Ha a műszak
    kezdetének dátuma benne van, nem generál semmit — a bolt aznap zárva
    (blueprint 9. szakasz: „enélkül a slotgenerátor karácsonyra is
    generál").
    """
    date = shift.start[:10]
    if date in exception_days:
        return GenerationResult(skipped=True, skip_oka=date, blocks=[], slots=[])

    blocks = strategia.generate(shift)
    free_segments = _free_segments(shift, blocks)
    slots: list[Slot] = []
    for segment_start, segment_end in free_segments:
        slots.extend(_slots_into_segment(shift, segment_start, segment_end))
    return GenerationResult(skipped=False, skip_oka=None, blocks=blocks, slots=slots)


def _free_segments(shift: Shift, blocks: list[Block]) -> list[tuple[str, str]]:
    """A műszak időablakából a blokkok (feltételezve: nem fedik egymást,
    kezdet szerint rendezve) kivágása után maradó szabad szakaszok."""
    segments: list[tuple[str, str]] = []
    cursor = shift.start
    for b in blocks:
        if b.start > cursor:
            segments.append((cursor, b.start))
        if b.end > cursor:
            cursor = b.end
    if cursor < shift.end:
        segments.append((cursor, shift.end))
    return segments


def _grid_rounding(moment: str, reference_pont: str, grid_minute: int) -> str:
    """`idopont`-ot felfelé kerekíti a `viszonyitasi_pont`-tól számított
    `racs_perc` méretű rácsra — így egy blokk után induló szabad szakasz
    is mindig "kerek" időponton kezdi a slotgenerálást."""
    if grid_minute <= 0:
        return moment
    elapsed = minute_difference(reference_pont, moment)
    maradek = elapsed % grid_minute
    if maradek == 0:
        return moment
    return add_minute(moment, grid_minute - maradek)


def _slots_into_segment(shift: Shift, start: str, end: str) -> list[Slot]:
    cadence = shift.duration_minute + shift.buffer_after_minute
    slots: list[Slot] = []
    cursor = _grid_rounding(start, shift.start, shift.min_grid_minute)
    while True:
        slot_end = add_minute(cursor, shift.duration_minute)
        if slot_end > end:
            break
        slots.append(Slot(cursor, slot_end))
        cursor = add_minute(cursor, cadence)
    return slots

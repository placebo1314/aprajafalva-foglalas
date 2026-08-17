"""Kemény kényszerek ellenőrzése a műszakblokkokra — a `BlokkStrategia`-n
KÍVÜL, önálló függvényben.

Blueprint 4. szakasz: "A kemény kényszerek ellenőrzése a stratégián kívül
van — a munkajogi minimumot nem az implementáció dönti el." Ezek
megsértése elutasítás, nem preferencia — szemben a puha preferenciákkal
(időzítés, egyenletes elosztás), amik nem ide, hanem egy jövőbeli
költségfüggvénybe tartoznak.
"""

from __future__ import annotations

from dataclasses import dataclass

from core.modell.shift import Block, Shift
from core.slot._idomatek import minute_difference

# Munkajogi minimum: 6 óra fölötti műszakban legalább egy 20 perces (vagy
# hosszabb) szünet/ebéd kötelező. Védett kategória — nincs paraméter, ami
# kikapcsolná (blueprint 4. szakasz, CLAUDE.md szellemében). A pontos érték
# a roadmap.md "Nyitott kérdések" szerint még nem végleges, de amíg nincs
# felülvizsgálva ADR-rel, ez a kötelező érték.
LABOR_LAW_THRESHOLD_MINUTE = 6 * 60
LABOR_LAW_MIN_BREAK_MINUTE = 20

_BREAK_LIKE_TYPES = ("szunet", "ebed")


@dataclass(frozen=True)
class ConstraintViolation:
    rule: str
    message: str


def check(
    shift: Shift,
    blocks: list[Block],
    *,
    min_all_break_minute: int,
    max_continuous_work_minute: int,
) -> list[ConstraintViolation]:
    """A négy kemény kényszert ellenőrzi, a sértéseket listaként adja
    vissza — sosem dob kivételt, a hívó (pl. a generátor vagy egy
    admin-felület) dönti el, mit kezd velük (elutasítás, magyarázó motor
    bemenete).

    `min_osszes_szunet_perc` és `max_folyamatos_munka_perc` bolt-/
    profilfüggő paraméterek: nincs bennük egyetlen "helyes" érték, ezért a
    hívó adja meg őket — csak a munkajogi minimum hardkódolt, mert az
    védett kategória.
    """
    return [
        *_block_on_shift_within(shift, blocks),
        *_all_break(blocks, min_all_break_minute),
        *_max_continuous_work(shift, blocks, max_continuous_work_minute),
        *_labor_law_min(shift, blocks),
    ]


def _block_on_shift_within(shift: Shift, blocks: list[Block]) -> list[ConstraintViolation]:
    return [
        ConstraintViolation(
            "blokk_muszakon_belul",
            f"A blokk ({b.tipus}, {b.start}–{b.end}) kilóg a műszak "
            f"({shift.start}–{shift.end}) időablakából.",
        )
        for b in blocks
        if b.start < shift.start or b.end > shift.end
    ]


def _all_break(blocks: list[Block], threshold: int) -> list[ConstraintViolation]:
    total = sum(b.length_minute() for b in blocks if b.tipus in _BREAK_LIKE_TYPES)
    if total < threshold:
        return [
            ConstraintViolation(
                "minimum_osszes_szunet",
                f"A műszak összes szünetideje {total} perc, a minimum {threshold} perc lenne.",
            )
        ]
    return []


def _max_continuous_work(
    shift: Shift, blocks: list[Block], threshold: int
) -> list[ConstraintViolation]:
    """A leghosszabb megszakítás nélküli munkaszakaszt nézi: a műszak
    eleje/vége és a szünet-jellegű blokkok közötti réseket. A szabad sáv
    NEM munkamegszakítás — az alkalmazott ott is szolgálatban van, csak
    nincs előre beosztva rá foglalás (blueprint 4. szakasz)."""
    boundaries = [shift.start]
    for b in sorted(blocks, key=lambda b: b.start):
        if b.tipus in _BREAK_LIKE_TYPES:
            boundaries.append(b.start)
            boundaries.append(b.end)
    boundaries.append(shift.end)

    violations = []
    for i in range(0, len(boundaries), 2):
        segment_length = minute_difference(boundaries[i], boundaries[i + 1])
        if segment_length > threshold:
            violations.append(
                ConstraintViolation(
                    "maximum_folyamatos_munka",
                    f"{segment_length} perces megszakítás nélküli szakasz "
                    f"({boundaries[i]}–{boundaries[i + 1]}), a maximum "
                    f"{threshold} perc lenne.",
                )
            )
    return violations


def _labor_law_min(shift: Shift, blocks: list[Block]) -> list[ConstraintViolation]:
    shift_length = minute_difference(shift.start, shift.end)
    if shift_length <= LABOR_LAW_THRESHOLD_MINUTE:
        return []
    has_enough_long = any(
        b.tipus in _BREAK_LIKE_TYPES and b.length_minute() >= LABOR_LAW_MIN_BREAK_MINUTE
        for b in blocks
    )
    if has_enough_long:
        return []
    return [
        ConstraintViolation(
            "munkajogi_minimum",
            f"{shift_length} perces műszakhoz ({LABOR_LAW_THRESHOLD_MINUTE} perc fölött) "
            f"legalább egy {LABOR_LAW_MIN_BREAK_MINUTE} perces szünet kötelező, "
            "de egyik blokk sem éri el ezt a hosszt.",
        )
    ]

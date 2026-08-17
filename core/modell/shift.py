"""Tiszta, DB-független adatmodellek a műszakhoz, blokkhoz és slothoz.

Ezek a dataclass-ek NEM tábla-tükrök: csak azokat a mezőket tartalmazzák,
amikre a `mag/slot/` és a `mag/szabalyok/` generáló/ellenőrző logikájának
ténylegesen szüksége van. A perzisztálás (SQL) a `mag/repo/`-ban történik —
ez a modul nem importál `sqlite3`-at, és nem ismeri a kapcsolatot
(CLAUDE.md, 5. invariáns: "Minden SQL a mag/repo/-ban van").

Minden időpont ISO-8601 UTC szöveg, ugyanúgy, ahogy a táblákban is
(CLAUDE.md, 4. invariáns) — itt sem alakul lokális idővé.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Shift:
    """A generáláshoz szükséges műszak-mezők — a snapshot eredménye
    (docs/domain.md, "Snapshot")."""

    id: str
    org_id: str
    start: str  # ISO-8601 UTC
    end: str  # ISO-8601 UTC
    duration_minute: int
    buffer_after_minute: int
    min_grid_minute: int
    bookable_ratio: float
    block_rule: dict = field(default_factory=dict)


@dataclass(frozen=True)
class Block:
    """Egy `muszak_blokk` sor jövőbeli tartalma — még id és letrehozva
    nélkül, azokat a perzisztáló repo-függvény adja hozzá."""

    tipus: str  # 'szunet' | 'ebed' | 'szabad_sav'
    start: str
    end: str
    fixed: bool
    counts_toward_into_quota: bool

    def length_minute(self) -> int:
        from core.slot._idomatek import minute_difference

        return minute_difference(self.start, self.end)


@dataclass(frozen=True)
class Slot:
    """Egy `slot` sor jövőbeli tartalma — id és letrehozva nélkül."""

    start: str
    end: str

    def length_minute(self) -> int:
        from core.slot._idomatek import minute_difference

        return minute_difference(self.start, self.end)

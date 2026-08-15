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
class Muszak:
    """A generáláshoz szükséges műszak-mezők — a snapshot eredménye
    (docs/domain.md, "Snapshot")."""

    id: str
    szervezet_id: str
    kezdet: str  # ISO-8601 UTC
    veg: str  # ISO-8601 UTC
    idotartam_perc: int
    puffer_utana_perc: int
    min_racs_perc: int
    foglalhato_arany: float
    blokk_szabaly: dict = field(default_factory=dict)


@dataclass(frozen=True)
class Blokk:
    """Egy `muszak_blokk` sor jövőbeli tartalma — még id és letrehozva
    nélkül, azokat a perzisztáló repo-függvény adja hozzá."""

    tipus: str  # 'szunet' | 'ebed' | 'szabad_sav'
    kezdet: str
    veg: str
    rogzitett: bool
    beszamit_kvotaba: bool

    def hossz_perc(self) -> int:
        from mag.slot._idomatek import perc_kulonbseg

        return perc_kulonbseg(self.kezdet, self.veg)


@dataclass(frozen=True)
class Slot:
    """Egy `slot` sor jövőbeli tartalma — id és letrehozva nélkül."""

    kezdet: str
    veg: str

    def hossz_perc(self) -> int:
        from mag.slot._idomatek import perc_kulonbseg

        return perc_kulonbseg(self.kezdet, self.veg)

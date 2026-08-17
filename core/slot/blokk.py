"""Műszakblokk-generálási stratégiák (blueprint 4. szakasz, ADR-009).

v1-ben kizárólag a `FixBlokk` stratégia aktív: generál, nem mozgat,
ütközésnél elutasít. A `BlokkStrategia` Protocol azért létezik, hogy a
`MohoAthelyezo` és a `KoltsegAlapu` stratégia később, sémamódosítás nélkül
bekapcsolható legyen (ADR-009 kiváltó feltétele).

A kemény kényszerek (munkajogi minimum, stb.) ellenőrzése SZÁNDÉKOSAN nincs
itt — az a `mag/szabalyok/kenyszerek.py` dolga, a stratégián kívül
(blueprint 4. szakasz).
"""

from __future__ import annotations

from typing import Protocol

from core.modell.shift import Block, Shift
from core.slot._idomatek import add_minute, minute_difference


class BlockStrategy(Protocol):
    def generate(self, shift: Shift) -> list[Block]: ...


class FixedBlock:
    """Generál, nem mozgat, ütközésnél elutasít (v1, ADR-009).

    A `muszak.blokk_szabaly` JSON-ból olvassa a szünet-mintázatot:

        {"szunetek": [
            {"tipus": "szunet"|"ebed", "hossz_perc": int,
             "mintazat": "minden_slot_utan" | "oranta"}
        ]}

    Üres/hiányzó `szunetek` = nincs generált szünet (pl. Hulk Hugan, "szünet
    nélkül"). A szabad sávot a `muszak.foglalhato_arany`-ból generálja —
    NEM egyetlen blokként a műszak végén, hanem óránként arányosan
    elosztva (ADR-011: "elnyeli a csúszást" — ez csak akkor igaz, ha a
    szabad idő a nap egészében jelen van, nem csak a végén).

    A szünet-mintázat ELSŐBBRENDŰ: ha egy adott órában a szünet miatt nem
    marad elég hely a névleges szabad sávnak, a szabad sáv abban az órában
    lerövidül vagy elmarad — a szünet sosem mozdul el, sosem rövidül meg
    emiatt.
    """

    def generate(self, shift: Shift) -> list[Block]:
        break_blocks: list[Block] = []
        for rule in shift.block_rule.get("szunetek", []):
            break_blocks.extend(self._break_generation(shift, rule))

        free_band_blocks = self._free_band(shift, break_blocks)
        return sorted(break_blocks + free_band_blocks, key=lambda b: b.start)

    def _break_generation(self, shift: Shift, rule: dict) -> list[Block]:
        mintazat = rule["mintazat"]
        if mintazat == "minden_slot_utan":
            return self._all_slot_after(shift, rule)
        if mintazat == "oranta":
            return self._hourly(shift, rule)
        raise ValueError(f"Ismeretlen szünetmintázat: {mintazat!r}")

    def _all_slot_after(self, shift: Shift, rule: dict) -> list[Block]:
        """Ciklus: (szolgáltatás-idő) + (szünet), amíg belefér a műszakba."""
        tipus = rule["tipus"]
        length = rule["hossz_perc"]
        cadence = shift.duration_minute + shift.buffer_after_minute
        blocks = []
        start = shift.start
        while True:
            service_end = add_minute(start, cadence)
            break_end = add_minute(service_end, length)
            if break_end > shift.end:
                break
            blocks.append(Block(tipus, service_end, break_end, True, True))
            start = break_end
        return blocks

    def _hourly(self, shift: Shift, rule: dict) -> list[Block]:
        """Óránként egy blokk: annyi szolgáltatás után, amennyi a szünet
        előtt még belefér a névleges (műszakkezdettől számított) órába."""
        tipus = rule["tipus"]
        length = rule["hossz_perc"]
        cadence = shift.duration_minute + shift.buffer_after_minute
        blocks = []
        hour_start = shift.start
        while hour_start < shift.end:
            available_all = 60 - length
            service_count = max(available_all // cadence, 0)
            break_start = add_minute(hour_start, service_count * cadence)
            break_end = add_minute(break_start, length)
            if break_end > shift.end:
                break
            blocks.append(Block(tipus, break_start, break_end, True, True))
            hour_start = add_minute(hour_start, 60)
        return blocks

    def _free_band(self, shift: Shift, break_blocks: list[Block]) -> list[Block]:
        """Óránként egy szabad sáv blokk: a névleges óra
        `(1 - foglalhato_arany)` hányada, az óra szünettel nem foglalt
        részének a VÉGÉHEZ illesztve. Ha egy órában a szünet miatt nincs
        elég hely, a blokk lerövidül a rendelkezésre álló résznyire, vagy
        — ha nincs szabad rész — teljesen elmarad abban az órában."""
        if shift.bookable_ratio >= 1.0:
            return []

        blocks: list[Block] = []
        hour_start = shift.start
        while hour_start < shift.end:
            hour_end = min(add_minute(hour_start, 60), shift.end)
            hour_length = minute_difference(hour_start, hour_end)
            target_length = round(hour_length * (1 - shift.bookable_ratio))

            if target_length > 0:
                gaps = self._free_parts(hour_start, hour_end, break_blocks)
                if gaps:
                    gap_start, gap_end = gaps[-1]
                    length = min(target_length, minute_difference(gap_start, gap_end))
                    if length > 0:
                        block_start = add_minute(gap_end, -length)
                        blocks.append(Block("szabad_sav", block_start, gap_end, True, False))

            hour_start = add_minute(hour_start, 60)
        return blocks

    @staticmethod
    def _free_parts(
        hour_start: str, hour_end: str, break_blocks: list[Block]
    ) -> list[tuple[str, str]]:
        """Az `[ora_kezdet, ora_veg)` ablakból a rá eső szünetblokkok
        kivágása után maradó szabad részek, kezdet szerint rendezve."""
        affected = sorted(
            (max(b.start, hour_start), min(b.end, hour_end))
            for b in break_blocks
            if b.start < hour_end and b.end > hour_start
        )
        gaps: list[tuple[str, str]] = []
        cursor = hour_start
        for k, v in affected:
            if k > cursor:
                gaps.append((cursor, k))
            cursor = max(cursor, v)
        if cursor < hour_end:
            gaps.append((cursor, hour_end))
        return gaps

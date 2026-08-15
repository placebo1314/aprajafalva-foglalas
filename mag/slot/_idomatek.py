"""Belső idő-aritmetika a mag/slot/ generáláshoz.

Csak percre kerekített, UTC-alapú aritmetika — a slot- és blokk-időpontok
mindig ISO-8601 UTC szövegek (CLAUDE.md 4. invariáns). A percre kerekítés
biztonságos: a slotgenerátor a `min_racs_perc` rács miatt sosem tör fel
percnél finomabb egységet.

Vezető aláhúzás: ez modulon belüli segédlet, a `mag/slot/` API-ja a
`blokk.py` és a `generator.py` publikus függvényein keresztül érhető el.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta


def parse(idopont: str) -> datetime:
    return datetime.fromisoformat(idopont)


def formaz(idopont: datetime) -> str:
    return idopont.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def perc_kulonbseg(kezdet: str, veg: str) -> int:
    """`veg - kezdet` percben, lefelé kerekítve."""
    delta = parse(veg) - parse(kezdet)
    return int(delta.total_seconds() // 60)


def hozzaad_perc(idopont: str, perc: int) -> str:
    return formaz(parse(idopont) + timedelta(minutes=perc))

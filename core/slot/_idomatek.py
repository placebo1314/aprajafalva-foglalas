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


def parse(moment: str) -> datetime:
    return datetime.fromisoformat(moment)


def formaz(moment: datetime) -> str:
    return moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def minute_difference(start: str, end: str) -> int:
    """`veg - kezdet` percben, lefelé kerekítve."""
    delta = parse(end) - parse(start)
    return int(delta.total_seconds() // 60)


def add_minute(moment: str, minute: int) -> str:
    return formaz(parse(moment) + timedelta(minutes=minute))

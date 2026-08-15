"""Idő-segédfüggvény.

Minden idő UTC-ben, ISO-8601 szövegként tárolódik (CLAUDE.md 4. invariáns).
Ez az egyetlen hely, ahol ez a formázás történik, hogy a migrációk
`LIKE '____-__-__T__:__:__Z'` CHECK-jei és a ténylegesen beírt érték
biztosan egyezzenek — nem duplikáljuk modulonként.
"""

from __future__ import annotations

from datetime import UTC, datetime


def most_iso() -> str:
    """A jelenlegi UTC időpont ISO-8601 szövegként, pl. '2026-08-15T10:00:00Z'."""
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

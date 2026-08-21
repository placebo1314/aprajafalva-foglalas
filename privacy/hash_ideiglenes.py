"""Ideiglenes vásárlóazonosító-hashelés, amíg a végleges HMAC+pepper
megoldás (`adatvedelem` skill, CLAUDE.md 2. invariáns) nincs megírva.

**EZ NEM A VÉGLEGES MEGOLDÁS.** Nincs pepper, nincs kulcsverzió-rotáció,
sima SHA-256 — ugyanaz a dokumentált hézag, mint amit `core/api/cli.py`
a `foglal` parancsnál előír ("a hashelés a privacy/ modul feladata lesz;
amíg az nincs megírva, a hívó felelőssége előre kiszámítani"). Ez a
modul csak azért létezik itt, a `privacy/` alatt, hogy a nyers
azonosító sehol máshol (pl. `ui/vasarlo.py`) ne jelenjen meg kódban —
a hashelés, még ideiglenes formában is, kizárólag ennek a modulnak a
felelőssége (CLAUDE.md, modulhatár-tábla)."""

from __future__ import annotations

import hashlib


def ideiglenes_hash(nyers_azonosito: str) -> str:
    """64 hex karakter — ugyanaz a formátum, amit a végleges
    `hash_azonosito()` is adna majd (`core/repo/foglalas_repo.py`
    `vasarlo_kulcs` oszlopa erre a hosszra van CHECK-kényszerítve)."""
    return hashlib.sha256(nyers_azonosito.encode("utf-8")).hexdigest()

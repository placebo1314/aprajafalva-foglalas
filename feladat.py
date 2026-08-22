#!/usr/bin/env python3
"""Feladatfuttató. Platformfüggetlen, make nélkül.

python feladat.py teszt
python feladat.py teszt-mindketto
python feladat.py golden [--json UTVONAL]
python feladat.py migracio "<leiras>"
python feladat.py seed
python feladat.py lint

A `golden` a determinisztikus értelmezőt futtatja (`tests/golden/futtato.py`)
— nem indít Ollamát, nem hív modellt. Modell-összehasonlításhoz lásd az
eldobható `spike/golden_futtato.py --ertelmezo llm --modell NEV`-et.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

GYOKER = Path(__file__).parent


def fut(parancs: list[str], kornyezet: dict | None = None) -> int:
    # PYTHONUTF8=1: a kimenet magyar ékezetes karaktereket (ő, ű) tartalmaz,
    # amit Windowson az örökölt konzol-kódlap (cp1252) nem tud kódolni —
    # UTF-8 módban ez a probléma platformfüggetlenül nem áll fenn.
    korny = {**os.environ, "PYTHONUTF8": "1", **(kornyezet or {})}
    print(f"$ {' '.join(parancs)}")
    return subprocess.run(parancs, cwd=GYOKER, env=korny).returncode


def teszt(_: list[str]) -> int:
    return fut([sys.executable, "-m", "pytest", "tests/", "-q"])


def teszt_mindketto(_: list[str]) -> int:
    for motor in ("sqlite", "postgres"):
        print(f"\n=== {motor} ===")
        if motor == "postgres":
            print(
                "FIGYELEM: ma nincs Postgres-adapter (lásd ADR-004, 'Ellenőrzés') — "
                "ez az ág ténylegesen ugyanazt a SQLite-ot futtatja, nem bizonyít "
                "semmit Postgresen."
            )
        if kod := fut([sys.executable, "-m", "pytest", "tests/", "-q"], {"ADATTAR": motor}):
            return kod
    return 0


def golden(argv: list[str]) -> int:
    return fut([sys.executable, "-m", "tests.golden.futtato", *argv])


def migracio(argv: list[str]) -> int:
    if not argv:
        print('Használat: python feladat.py migracio "<leiras>"')
        return 1
    return fut([sys.executable, "-m", "tools.uj_migracio", argv[0]])


def seed(_: list[str]) -> int:
    return fut([sys.executable, "-m", "seed.betolt"])


def lint(_: list[str]) -> int:
    for parancs in (
        [sys.executable, "-m", "ruff", "format", "--check", "."],
        [sys.executable, "-m", "ruff", "check", "."],
    ):
        if kod := fut(parancs):
            return kod
    return 0


FELADATOK = {
    "teszt": teszt,
    "teszt-mindketto": teszt_mindketto,
    "golden": golden,
    "migracio": migracio,
    "seed": seed,
    "lint": lint,
}

if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in FELADATOK:
        print(__doc__)
        sys.exit(1)
    sys.exit(FELADATOK[sys.argv[1]](sys.argv[2:]))

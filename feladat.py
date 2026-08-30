#!/usr/bin/env python3
"""Feladatfuttató. Platformfüggetlen, make nélkül.

python feladat.py teszt
python feladat.py teszt-mindketto
python feladat.py golden [--json UTVONAL]
python feladat.py migracio "<leiras>"
python feladat.py seed [--ujra]
python feladat.py vegigjatszas [--db UTVONAL] [--robusztus] [--mod szoveges|beszelheto|mindketto]
python feladat.py naplo [--utolso N] [--golden SOR]
python feladat.py riport [--utolso N] [--ki UTVONAL] [--megnyit]
python feladat.py lint

A `golden` a determinisztikus értelmezőt futtatja (`tests/golden/futtato.py`)
— nem indít Ollamát, nem hív modellt. A modell-összehasonlítás ugyanennek a
parancsnak a `--ertelmezo llm|kaszkad|forditott` kapcsolójával megy.

Két halmaz van (`--halmaz nyelvi|robusztus`):

- `nyelvi` (alapértelmezett) — nyelvi megértés, EGY helyes válasz esetenként.
- `robusztus` — mi történik, amikor NEM az történik, amire számítunk: üres
  bemenet, zaj, idegen nyelv, ellentmondás, hatókörön kívüli kérés,
  prompt injection, érzelem, abszurd kérés, kéretlen személyes adat, és
  **ASR-hibák** (félrehallott szám és név, egybefolyt szavak, hiányzó
  szóvég, ékezet nélküli alak, hallucinált zárómondat — külön mérési
  bontásban). Itt nem pontosságot mérünk elsősorban, hanem NÉGY
  biztonsági számot (kivétel / hatókörön kívüli válasz / kitalált tény /
  instabil ismétlés), mindet 0-s kemény küszöbbel.

A `vegigjatszas` a vásárlói felületet hajtja végig Tkinter-eseményhurok
nélkül (`tools/vegigjatszas.py`) — önellenőrzés, mielőtt kézzel leülnél elé.
A `--mod` a kimeneti módot választja: `szoveges` (mai viselkedés),
`beszelheto` (felolvasásra) vagy `mindketto` (ugyanaz kétszer).

A `naplo` a próba-naplót (`naplo/probak.jsonl`) összesíti
(`tools/naplo_elemzo.py`): fordulószám, réteg-megoszlás, VÁLASZIDŐ-
ELOSZLÁS (p50/p95/átlag/max) a kétpontos elváráshoz mérve PLUSZ a
tendencia (ADR-022), bizonyosság-eloszlás, leggyakoribb hibaminták. A
`--golden <sor>` egy naplósorból golden teszteset-vázat ír, a `varhato`
mezőt ÜRESEN hagyva — a helyes választ embernek kell beírnia.

A `riport` ugyanebből a naplóból EGY FORDULÓT mutat meg teljes
mélységben (`tools/beszelgetes_riport.py`): egyetlen, offline
megnyitható HTML fájl, fordulónként összecsukható blokkal — bemenet és
normalizált alak egymás mellett, a döntő réteg színkóddal, a teljes
prompt, a nyers modellválasz, a dátumfeloldás (modell vs. parser), a
lépésenkénti idő, és a kimenő válasz MINDKÉT módban. A `naplo`
összesít, ez elmélyed: az egyik megmondja, hogy baj van, a másik azt,
hogy mi.
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


def seed(argv: list[str]) -> int:
    return fut([sys.executable, "-m", "seed.betolt", *argv])


def vegigjatszas(argv: list[str]) -> int:
    return fut([sys.executable, "-m", "tools.vegigjatszas", *argv])


def naplo(argv: list[str]) -> int:
    return fut([sys.executable, "-m", "tools.naplo_elemzo", *argv])


def riport(argv: list[str]) -> int:
    return fut([sys.executable, "-m", "tools.beszelgetes_riport", *argv])


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
    "vegigjatszas": vegigjatszas,
    "naplo": naplo,
    "riport": riport,
    "lint": lint,
}

if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in FELADATOK:
        print(__doc__)
        sys.exit(1)
    sys.exit(FELADATOK[sys.argv[1]](sys.argv[2:]))

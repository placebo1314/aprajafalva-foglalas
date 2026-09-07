#!/usr/bin/env python3
"""Feladatfuttató. Platformfüggetlen, make nélkül.

python feladat.py teszt
python feladat.py teszt-mindketto
python feladat.py golden [--json UTVONAL]
python feladat.py migracio "<leiras>"
python feladat.py seed [--ujra]
python feladat.py vegigjatszas [--db UTVONAL] [--robusztus] [--mod szoveges|beszelheto|mindketto]
python feladat.py naplo [--utolso N] [--golden SOR] [--fajl UTVONAL] [--archival]
python feladat.py riport [--utolso N] [--ki UTVONAL] [--fajl UTVONAL] [--megnyit]
python feladat.py utvonal [--session ELEJE] [--fajl UTVONAL] [--szoveg] [--utolso N]
python feladat.py hangproba [--mondat "..."] [--csak-diagnozis]
python feladat.py lint

A `golden` a determinisztikus értelmezőt futtatja (`tests/golden/futtato.py`)
— nem indít Ollamát, nem hív modellt. A modell-összehasonlítás ugyanennek a
parancsnak a `--ertelmezo llm|kaszkad|forditott` kapcsolójával megy.

Három halmaz van (`--halmaz nyelvi|robusztus|beszedhelyzetek`):

- `nyelvi` (alapértelmezett) — nyelvi megértés, EGY helyes válasz esetenként.
- `robusztus` — mi történik, amikor NEM az történik, amire számítunk: üres
  bemenet, zaj, idegen nyelv, ellentmondás, hatókörön kívüli kérés,
  prompt injection, érzelem, abszurd kérés, kéretlen személyes adat, és
  **ASR-hibák** (félrehallott szám és név, egybefolyt szavak, hiányzó
  szóvég, ékezet nélküli alak, hallucinált zárómondat — külön mérési
  bontásban). Itt nem pontosságot mérünk elsősorban, hanem NÉGY
  biztonsági számot (kivétel / hatókörön kívüli válasz / kitalált tény /
  instabil ismétlés), mindet 0-s kemény küszöbbel.
- `beszedhelyzetek` — nem az számít, HOGYAN mondja, hanem MILYEN
  HELYZETBEN: nem magának foglal („az anyámnak kellene"), feltételesen
  tervez („ha esik, akkor szerdán"), összehasonlít („melyik boltban van
  hamarabb hely?"), korábbi foglalásra hivatkozik azonosítás nélkül,
  több időpontot kér egyszerre, elköszön, meggondolja magát,
  közbekérdez foglalás közben, vagy szokatlan igét használ
  („bejelentkeznék", „lestoppolnék"). A várt viselkedés itt sokszor a
  VISSZAKÉRDEZÉS vagy az udvarias elhárítás, nem a tökéletes megoldás.

A `vegigjatszas` a vásárlói felületet hajtja végig Tkinter-eseményhurok
nélkül (`tools/vegigjatszas.py`) — önellenőrzés, mielőtt kézzel leülnél elé.
Négy menetet jár be: a saját próbákat, a foglalást GOMBOKKAL, a
foglalást VÉGIG ÍRÁSBAN (ez utóbbi fogta meg 2026-08-31-én, hogy az
„igen, foglald le" mondatból új keresés lett), és a modális indítási
ellenőrzést valódi Tk-ablakkal — azt egységteszt nem tudja megfogni,
mert gombnyomást vár.
A `--mod` a kimeneti módot választja: `szoveges` (mai viselkedés),
`beszelheto` (felolvasásra) vagy `mindketto` (ugyanaz kétszer).

A `naplo` a próba-naplót (`naplo/probak.jsonl`) összesíti
(`tools/naplo_elemzo.py`): fordulószám, réteg-megoszlás, VÁLASZIDŐ-
ELOSZLÁS (p50/p95/átlag/max) a kétpontos elváráshoz mérve PLUSZ a
tendencia (ADR-022), bizonyosság-eloszlás, leggyakoribb hibaminták. A
`--golden <sor>` egy naplósorból golden teszteset-vázat ír, a `varhato`
mezőt ÜRESEN hagyva — a helyes választ embernek kell beírnia. Az
`--archival` a jelenlegi naplót dátumozott néven félreteszi
(`naplo/probak-20260831-195812.jsonl`) és üres naplóval indul újra: ez
jelöli ki a mérési határt két próbasorozat közé, hogy az előző futás
számai ne mosódjanak össze az újakkal. Az archivált naplót a `--fajl`
kapcsoló olvassa vissza — a `naplo` és a `riport` egyaránt.

A `riport` ugyanebből a naplóból EGY FORDULÓT mutat meg teljes
mélységben (`tools/beszelgetes_riport.py`): egyetlen, offline
megnyitható HTML fájl, fordulónként összecsukható blokkal — bemenet és
normalizált alak egymás mellett, a döntő réteg színkóddal, a teljes
prompt, a nyers modellválasz, a dátumfeloldás (modell vs. parser), a
lépésenkénti idő, és a kimenő válasz MINDKÉT módban. A `naplo`
összesít, ez elmélyed: az egyik megmondja, hogy baj van, a másik azt,
hogy mi. A `--fajl` itt is archív naplót nyit meg, és a riport fejléce
kiírja, melyikből készült.

Az `utvonal` EGY BESZÉLGETÉS útvonalát mutatja lépésről lépésre
(`tools/utvonal.py`), Előző/Következő gombokkal — és fordulónként azt
is, MIÉRT oda ment tovább: elkapta-e a kapuőr, mit adott a modell és
mit a dátumparser, melyik nyert, mely mezők jöttek honnan, hova lépett
az állapotgép. A `naplo` összesít, a `riport` egy fordulót bont ki
mélységében, ez pedig a BESZÉLGETÉST teszi az elemzés egységévé. A
`--szoveg` ablak nélkül, konzolra írja ugyanezt.

A `hangproba` egyetlen mondatot szintetizál és lejátszik
(`tools/hangproba.py`) — és ha nem megy, MEGMONDJA, miért: nincs Piper,
nincs magyar hangmodell, vagy nincs lejátszó program. Három hiány,
három teendő. Eddig a felolvasás csendben maradt el, mert TTS soha nem
volt bekötve (a beszélhető mód a SZÖVEGET formázza felolvasásra,
ADR-023); a csend és a „nincs telepítve" ugyanúgy nézett ki.
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


def utvonal(argv: list[str]) -> int:
    return fut([sys.executable, "-m", "tools.utvonal", *argv])


def hangproba(argv: list[str]) -> int:
    return fut([sys.executable, "-m", "tools.hangproba", *argv])


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
    "utvonal": utvonal,
    "hangproba": hangproba,
    "lint": lint,
}

if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in FELADATOK:
        print(__doc__)
        sys.exit(1)
    sys.exit(FELADATOK[sys.argv[1]](sys.argv[2:]))

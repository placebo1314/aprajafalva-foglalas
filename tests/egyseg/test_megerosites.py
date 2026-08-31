"""ÍRÁSBELI IGEN/NEM a megerősítés-kérdésre (`assistant/megerosites.py`
és az orchestrator rövidzárja).

**Mért hibából született** (2026-08-31, `python feladat.py vegigjatszas`
`qwen3.5:9b`-vel ÉS tartalékágon egyaránt): a szöveges úton a foglalás
a harmadik lépésnél szakadt meg. A keresés jó volt, a sorszámos
választás jó („a másodikat kérem" → megerősítés-kérés), de az „igen,
foglald le" mondatból ÚJ KERESÉS lett, és a folyamatban lévő
megerősítés — a kiválasztott időponttal együtt — eltűnt a képernyőről.

Két dolgot bizonyítanak az itteni tesztek:

1. a felismerés **szűk**: csak azt fogadja el igenlésnek, ami tényleg
   az, és nem nyeli el a mondatba csomagolt ÚJ kéréseket;
2. a rövidzár **csak megerősítésre várva** szólal meg — máshol az
   „igen" önmagában semmit nem jelent.
"""

from __future__ import annotations

import pytest

from assistant.megerosites import IGEN, NEM, megerosito_valasz


@pytest.mark.parametrize(
    "mondat",
    [
        "igen",
        "Igen!",
        "igen, foglald le",
        "foglald le",
        "foglald le kérlek",
        "rendben",
        "rendben, köszönöm",
        "persze",
        "jó lesz",
        "ok",
        "mehet",
    ],
)
def test_igenles(mondat):
    assert megerosito_valasz(mondat) == IGEN


@pytest.mark.parametrize(
    "mondat",
    ["nem", "nem kell", "mégse", "mégsem", "mégse kell", "inkább ne", "hagyjuk", "nem, köszönöm"],
)
def test_tagadas(mondat):
    assert megerosito_valasz(mondat) == NEM


@pytest.mark.parametrize(
    "mondat",
    [
        # ÚJ KÉRÉS igenléssel csomagolva — ezt az értelmezőnek kell
        # látnia, nem szabad megerősítésként elnyelni.
        "igen, de inkább szerdán lenne jó",
        "nem, inkább a Szundihoz mennék",
        "igen és mennyibe kerül?",
        # BIZONYTALANSÁG — se nem igen, se nem nem. A kérdés maradjon
        # nyitva; egy „talán"-ból foglalni a legdrágább félreértés.
        "talán",
        "hát nem tudom",
        "lehet",
        # Üres és zajos bemenet.
        "",
        "   ",
        "asdf",
    ],
)
def test_nem_ismerjuk_fel(mondat):
    assert megerosito_valasz(mondat) is None


def test_a_tagadas_nem_nyeli_el_a_meggondolast():
    """A „mégsem kell, elnézést" TELJES visszavonás (l. a
    beszédhelyzetek halmaz `meggondolas` rétegét) — de ha épp
    megerősítésre várunk, akkor ELSŐSORBAN erre a kérdésre válasz. A két
    olvasat ugyanoda vezet: nem foglalunk."""
    assert megerosito_valasz("mégse kell") == NEM

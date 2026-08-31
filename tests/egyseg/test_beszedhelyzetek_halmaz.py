"""A BESZÉDHELYZETEK halmaz szerkezeti ellenőrzése
(`tests/golden/beszedhelyzetek.yaml`).

**Nem pontosságot mér** — azt `python feladat.py golden --halmaz
beszedhelyzetek` méri, modellel. Ez a fájl azt őrzi, hogy a halmaz
maga ép maradjon: betölthető, minden esetnek van rétege és küszöbe, és
a „nem árt" felsorolások csak létező eszközneveket tartalmaznak.

Miért érdemes: egy elgépelt cimke vagy egy hiányzó küszöb NÉMÁN
gyengítené a mérést — a réteg egyszerűen kimaradna a küszöb-
ellenőrzésből, és a jelentés zöld lenne.
"""

from __future__ import annotations

from tests.golden.futtato import BESZEDHELYZETEK_UTVONAL, HALMAZOK, betolt

MINIMUM_ESET = 20


def _halmaz():
    return betolt(BESZEDHELYZETEK_UTVONAL)


def test_a_halmaz_betoltheto_es_eleg_nagy():
    _, esetek = _halmaz()

    assert len(esetek) >= MINIMUM_ESET


def test_a_halmaz_szerepel_a_valaszthato_halmazok_kozott():
    """A `--halmaz` kapcsoló nélkül a fájl csak egy yaml a lemezen."""
    assert HALMAZOK["beszedhelyzetek"] == BESZEDHELYZETEK_UTVONAL


def test_minden_retegnek_van_kuszobe():
    meta, esetek = _halmaz()
    kuszobok = meta["kuszobok"]

    retegek = {eset.reteg for eset in esetek}

    assert retegek <= set(kuszobok), f"küszöb nélküli réteg: {retegek - set(kuszobok)}"
    assert set(kuszobok) <= retegek, (
        f"nem létező réteghez tartozó küszöb: {set(kuszobok) - retegek}"
    )


def test_minden_eset_mond_valamit_a_varhato_viselkedesrol():
    """Vagy EGY helyes válasz (`eszkoz`), vagy a nem ártó viselkedések
    listája (`elfogadhato_eszkozok`) — a kettő közül pontosan az egyik.
    Egy `varhato: {}` eset mindig sikerülne, és semmit nem mérne."""
    _, esetek = _halmaz()

    for eset in esetek:
        van_eszkoz = "eszkoz" in eset.varhato
        van_lista = bool(eset.elfogadhato_eszkozok)
        assert van_eszkoz != van_lista, f"{eset.id}: pontosan az egyik kell"


def test_a_beszedhelyzetek_nem_ismetlik_a_nyelvi_halmaz_mondatait():
    """A halmaz azt méri, MILYEN HELYZETBEN beszél a vásárló, nem azt,
    hogyan — ha ugyanazokat a mondatokat tartalmazná, csak megduplázná
    a nyelvi halmazt, és a súlyát tolná el a mérésben."""
    _, beszed = _halmaz()
    _, nyelvi = betolt(HALMAZOK["nyelvi"])

    nyelvi_mondatok = {mondat for eset in nyelvi for mondat in eset.fordulok}
    atfedes = {mondat for eset in beszed for mondat in eset.fordulok if mondat in nyelvi_mondatok}

    assert not atfedes, f"átfedő mondat: {atfedes}"


def test_a_tobbfordulos_eseteket_a_cimke_is_jeloli():
    """A `tobbfordulos` címke a jelentésben külön bontásként jelenik meg
    — ha lemarad, a többfordulós esetek némán beleolvadnak az
    egyfordulósok közé."""
    _, esetek = _halmaz()

    for eset in esetek:
        if eset.tobbfordulos:
            assert "tobbfordulos" in eset.cimkek, f"{eset.id}: hiányzó `tobbfordulos` címke"

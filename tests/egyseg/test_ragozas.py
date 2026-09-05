"""A ragozás (`assistant/valasz/ragozas.py`, ADR-032).

A bolt- és szolgáltatásnevek az ADATBÁZISBÓL jönnek, a mondat a
sablonból — a kettő között ragozni kell. Ez a modul közelítés, nem
morfológiai elemző; a tesztek azt rögzítik, MEDDIG jó.
"""

from __future__ import annotations

import pytest

from assistant.valasz import ragozas


@pytest.mark.parametrize(
    ("nev", "varhato"),
    [
        ("Szundi", "Szundiba"),
        ("Ügyifogyi", "Ügyifogyiba"),
        ("Törpilla", "Törpillába"),
        # Tisztán elülső hangrendű név: elülső rag.
        ("Csengettyű", "Csengettyűbe"),
        # Tővégi nyúlás e-re is.
        ("Fenyve", "Fenyvébe"),
    ],
)
def test_hova_rag(nev, varhato):
    assert ragozas.hova(nev) == varhato


@pytest.mark.parametrize(
    ("szo", "varhato"),
    [
        ("altató", "altatóért"),
        ("petárda", "petárdáért"),
        ("boldogság", "boldogságért"),
    ],
)
def test_ert_rag_invarians(szo, varhato):
    """A `-ért` a magyar néhány invariáns ragjának egyike: nem
    illeszkedik hangrendhez."""
    assert ragozas.ert(szo) == varhato


@pytest.mark.parametrize(
    ("szo", "varhato"), [("Szundi", "a"), ("Ügyifogyi", "az"), ("Törpilla", "a"), ("Altató", "az")]
)
def test_nevelo(szo, varhato):
    assert ragozas.nevelo(szo) == varhato


def test_vegyes_hangrend_a_hatso_ragot_kapja():
    """DOKUMENTÁLT KORLÁT: a vegyes hangrendű neveket a leggyakoribb
    szabály szerint kezeljük (van benne hátsó magánhangzó → hátsó rag).
    A mai három boltnévre helyes; egy jövőbeli névnél már nem biztos."""
    assert ragozas.hova("Ügyifogyi") == "Ügyifogyiba"

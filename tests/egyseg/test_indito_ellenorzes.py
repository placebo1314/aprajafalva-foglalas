"""AZ INDÍTÁSI ELLENŐRZÉS — „fut-e egyáltalán a modell?"
(`assistant/interpreter/llm_based.py::modell_allapot`,
`assistant/valasz/__init__.py::indito_ellenorzes_szoveg`).

**Miért van erre külön tesztfájl.** Ez a rendszer legdrágább
félreértése: a tartalék ág csendben átveszi a fordulót (helyes
viselkedés), a válaszok értelmesek maradnak, és a próbálgató egy egész
beszélgetést végigcsinál abban a hitben, hogy a modellt méri. Háromszor
fordult elő, mindháromszor csak utólag derült ki. Az ellenőrzés akkor ér
valamit, ha a HÁROM okot meg is különbözteti — mindhármat máshogy kell
javítani.

A hálózat itt mockolt: ez a fájl sosem indít valódi Ollama-hívást
(ugyanaz a szabály, mint a `test_llm_based.py`-ban).
"""

from __future__ import annotations

import io
import json
import urllib.error
from unittest.mock import patch

from assistant.interpreter.llm_based import (
    HIANY_NINCS_LETOLTVE,
    HIANY_NINCS_MODELL,
    HIANY_NINCS_SZOLGALTATAS,
    modell_allapot,
)
from assistant.valasz import indito_ellenorzes_szoveg


class _HamisValasz(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def _tags(*nevek: str):
    return _HamisValasz(json.dumps({"models": [{"name": nev} for nev in nevek]}).encode("utf-8"))


# -- a három ok --------------------------------------------------------


def test_nincs_konfiguralt_modell(monkeypatch):
    monkeypatch.delenv("APRAJAFALVA_LLM_MODELL", raising=False)

    allapot = modell_allapot()

    assert allapot.hiany == HIANY_NINCS_MODELL
    assert allapot.rendben is False
    assert allapot.modell is None


def test_a_szolgaltatas_nem_valaszol(monkeypatch):
    monkeypatch.setenv("APRAJAFALVA_LLM_MODELL", "qwen3.5:9b")

    with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("nincs kapcsolat")):
        allapot = modell_allapot()

    assert allapot.hiany == HIANY_NINCS_SZOLGALTATAS
    assert allapot.modell == "qwen3.5:9b", "a modellnevet tudjuk, csak a szolgáltatás hallgat"


def test_a_modell_nincs_letoltve(monkeypatch):
    monkeypatch.setenv("APRAJAFALVA_LLM_MODELL", "nincs-ilyen:9b")

    with patch("urllib.request.urlopen", return_value=_tags("qwen3.5:9b", "llama3.1:8b")):
        allapot = modell_allapot()

    assert allapot.hiany == HIANY_NINCS_LETOLTVE
    assert "qwen3.5:9b" in allapot.reszlet, "a részlet megmondja, mi VAN — abból lehet választani"


def test_minden_rendben(monkeypatch):
    monkeypatch.setenv("APRAJAFALVA_LLM_MODELL", "qwen3.5:9b")

    with patch("urllib.request.urlopen", return_value=_tags("qwen3.5:9b")):
        allapot = modell_allapot()

    assert allapot.rendben is True
    assert allapot.hiany is None


def test_a_latest_utotag_nem_buktatja_el_az_inditast(monkeypatch):
    """Az Ollama a `:latest` utótagot hol kiírja, hol nem — a két alak
    UGYANAZ a modell. Egy indítást nem szabad elbuktatni egy
    névkonvención."""
    monkeypatch.setenv("APRAJAFALVA_LLM_MODELL", "phi3.5")

    with patch("urllib.request.urlopen", return_value=_tags("phi3.5:latest")):
        assert modell_allapot().rendben is True


def test_ures_modell_lista_nem_bukik_el(monkeypatch):
    """Ha a szolgáltatás válaszol, de üres listát ad (friss telepítés,
    vagy egy másik API-alak), NE mondjuk azt, hogy „nincs letöltve" —
    azt onnan nem tudjuk. A hallgatás itt kevesebb kárt okoz, mint egy
    magabiztos téves diagnózis."""
    monkeypatch.setenv("APRAJAFALVA_LLM_MODELL", "qwen3.5:9b")

    with patch("urllib.request.urlopen", return_value=_HamisValasz(b'{"models": []}')):
        assert modell_allapot().rendben is True


# -- a modális ablak szövege -------------------------------------------


def test_rendben_allapotra_nincs_szoveg():
    assert indito_ellenorzes_szoveg(None) is None


def test_mindharom_ok_kulon_teendot_mond():
    """A három üzenet három KÜLÖN teendőt tartalmaz. Ha egy összevont
    „nem működik" mondat lenne, a próbálgató nem tudná, mit tegyen — az
    ellenőrzés pont attól ér valamit, hogy ezt megmondja."""
    teendok = {}
    for hiany in (HIANY_NINCS_MODELL, HIANY_NINCS_SZOLGALTATAS, HIANY_NINCS_LETOLTVE):
        cim, uzenet, folytat, kilep = indito_ellenorzes_szoveg(hiany, "qwen3.5:9b")
        assert cim
        assert "Teendő:" in uzenet
        assert folytat and kilep
        teendok[hiany] = uzenet

    assert len({*teendok.values()}) == 3, "a három ok nem mondhatja ugyanazt"
    assert "APRAJAFALVA_LLM_MODELL" in teendok[HIANY_NINCS_MODELL]
    assert "ollama serve" in teendok[HIANY_NINCS_SZOLGALTATAS]
    assert "ollama pull qwen3.5:9b" in teendok[HIANY_NINCS_LETOLTVE]


def test_a_szoveg_kimondja_hogy_nem_a_modellt_mernenk():
    """Ez az egy mondat a lényeg: nem az a baj, hogy „valami hiányzik",
    hanem hogy a mérés MÁST mérne, mint amit az ember hisz."""
    for hiany in (HIANY_NINCS_MODELL, HIANY_NINCS_SZOLGALTATAS, HIANY_NINCS_LETOLTVE):
        _, uzenet, _, _ = indito_ellenorzes_szoveg(hiany, "qwen3.5:9b")
        assert "TARTALÉK" in uzenet


def test_ismeretlen_hiany_nem_dob_kivetelt():
    """Egy jövőbeli, még nem ismert ok ne buktassa el az INDÍTÁST — a
    felület ilyenkor egyszerűen elindul (a sárga sáv és a napló
    továbbra is jelez)."""
    assert indito_ellenorzes_szoveg("valami_uj_ok", "qwen3.5:9b") is None

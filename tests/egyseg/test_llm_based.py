"""Egységtesztek az LLM-alapú értelmezőre (`assistant/interpreter/
llm_based.py`) — Ollama-hívás nélkül, `urllib.request.urlopen` mockolva.
Ez a fájl SOSEM indít valódi modellhívást (CLAUDE.md-höz igazodó
munkamenet-szabály: "ne futtass modellt" a fejlesztés közben — ez a
teszt sem tér el ettől)."""

from __future__ import annotations

import io
import json
from unittest.mock import patch

import pytest

from assistant.interpreter import ErtelmezesKontextus
from assistant.interpreter.llm_based import LLMErtelmezo, LLMSzolgaltato

_MOST = "2026-08-17T09:00:00Z"


class _HamisValasz(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def _ollama_valasz(tartalom: dict) -> _HamisValasz:
    return _HamisValasz(json.dumps({"message": {"content": json.dumps(tartalom)}}).encode())


# --- LLMSzolgaltato: konfigból jön a modellnév -----------------------


def test_llmszolgaltato_explicit_modellel():
    szolg = LLMSzolgaltato(modell="qwen3.5:4b")
    assert szolg.modell == "qwen3.5:4b"


def test_llmszolgaltato_kornyezeti_valtozobol(monkeypatch):
    monkeypatch.setenv("APRAJAFALVA_LLM_MODELL", "teszt-modell")
    szolg = LLMSzolgaltato()
    assert szolg.modell == "teszt-modell"


def test_llmszolgaltato_modell_nelkul_hiba(monkeypatch):
    monkeypatch.delenv("APRAJAFALVA_LLM_MODELL", raising=False)
    with pytest.raises(ValueError, match="modell"):
        LLMSzolgaltato()


# --- LLMErtelmezo.ertelmez ---------------------------------------------


def test_ertelmez_sikeres_valaszt_ad_vissza():
    ertelmezo = LLMErtelmezo(LLMSzolgaltato(modell="teszt-modell"))
    kimenet = {
        "eszkoz": "szabad_idopontok",
        "parameterek": {
            "bolt_id": "ugyifogyi",
            "datum_tol": "2026-08-18T00:00:00Z",
            "datum_ig": "2026-08-18T23:59:59Z",
            "napszak": "barmikor",
        },
    }
    with patch("urllib.request.urlopen", return_value=_ollama_valasz(kimenet)):
        eredmeny = ertelmezo.ertelmez(
            "petárdázni szeretnék kedden", most=_MOST, kontextus=ErtelmezesKontextus()
        )
    assert eredmeny == kimenet
    assert ertelmezo.utolso_hiba is None


def test_ertelmez_think_explicit_false():
    """A `think` mező mindig explicit False — l. modul docstring: kihagyva
    a modell kontrollálatlan gondolkodásba futhat."""
    ertelmezo = LLMErtelmezo(LLMSzolgaltato(modell="teszt-modell"))
    elkuldott = {}

    def hamis_urlopen(req, timeout=None):
        elkuldott["payload"] = json.loads(req.data)
        return _ollama_valasz({"eszkoz": "nincs", "parameterek": {}})

    with patch("urllib.request.urlopen", side_effect=hamis_urlopen):
        ertelmezo.ertelmez("bármi", most=_MOST, kontextus=ErtelmezesKontextus())

    assert elkuldott["payload"]["think"] is False
    assert elkuldott["payload"]["options"]["temperature"] == 0
    assert elkuldott["payload"]["model"] == "teszt-modell"


def test_ertelmez_ollama_nem_elerheto_nincs_kivetel(monkeypatch):
    """Ha az Ollama nem fut, NEM dob kivételt — 'nincs'-et ad vissza, és
    az utolso_hiba mezőn jelzi a hibát (a kaszkad.py ezt használja)."""
    import urllib.error

    ertelmezo = LLMErtelmezo(LLMSzolgaltato(modell="teszt-modell"))
    with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("connection refused")):
        eredmeny = ertelmezo.ertelmez("bármi", most=_MOST, kontextus=ErtelmezesKontextus())

    assert eredmeny == {"eszkoz": "nincs", "parameterek": {}}
    assert ertelmezo.utolso_hiba is not None
    assert "Ollama" in ertelmezo.utolso_hiba


def test_ertelmez_ervenytelen_json_nincs_kivetel():
    ertelmezo = LLMErtelmezo(LLMSzolgaltato(modell="teszt-modell"))
    hamis_valasz = _HamisValasz(json.dumps({"message": {"content": "nem json"}}).encode())
    with patch("urllib.request.urlopen", return_value=hamis_valasz):
        eredmeny = ertelmezo.ertelmez("bármi", most=_MOST, kontextus=ErtelmezesKontextus())

    assert eredmeny == {"eszkoz": "nincs", "parameterek": {}}
    assert ertelmezo.utolso_hiba is not None


def test_ertelmez_hianyzo_parameterek_kulcsot_ures_dict_kent_potolja():
    ertelmezo = LLMErtelmezo(LLMSzolgaltato(modell="teszt-modell"))
    with patch("urllib.request.urlopen", return_value=_ollama_valasz({"eszkoz": "nincs"})):
        eredmeny = ertelmezo.ertelmez("bármi", most=_MOST, kontextus=ErtelmezesKontextus())
    assert eredmeny == {"eszkoz": "nincs", "parameterek": {}}


def test_ertelmez_uj_hivas_torli_az_elozo_hibat():
    """Az `utolso_hiba` fordulónként újraértékelődik — egy korábbi hiba
    nem "ragad be" egy következő, sikeres híváson."""
    ertelmezo = LLMErtelmezo(LLMSzolgaltato(modell="teszt-modell"))
    with patch("urllib.request.urlopen", side_effect=OSError("nincs kapcsolat")):
        ertelmezo.ertelmez("bármi", most=_MOST, kontextus=ErtelmezesKontextus())
    assert ertelmezo.utolso_hiba is not None

    with patch(
        "urllib.request.urlopen",
        return_value=_ollama_valasz({"eszkoz": "nincs", "parameterek": {}}),
    ):
        ertelmezo.ertelmez("bármi", most=_MOST, kontextus=ErtelmezesKontextus())
    assert ertelmezo.utolso_hiba is None

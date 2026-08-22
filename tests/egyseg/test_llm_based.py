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
from assistant.interpreter.llm_based import (
    LLMErtelmezo,
    LLMSzolgaltato,
    _mezo_bizonyossag,
    bizonyossag_szamol,
)

_MOST = "2026-08-17T09:00:00Z"


def _ertelmezes(eredmeny: dict) -> dict:
    """Csak az `eszkoz` + `parameterek` rész — a `bizonyossag`-nak saját,
    dedikált tesztjei vannak lent, hogy az "mit ismert fel" tesztek
    egyetlen dologról szóljanak."""
    return {k: v for k, v in eredmeny.items() if k != "bizonyossag"}


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
    assert _ertelmezes(eredmeny) == kimenet
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

    assert _ertelmezes(eredmeny) == {"eszkoz": "nincs", "parameterek": {}}
    assert ertelmezo.utolso_hiba is not None
    assert "Ollama" in ertelmezo.utolso_hiba


def test_ertelmez_ervenytelen_json_nincs_kivetel():
    ertelmezo = LLMErtelmezo(LLMSzolgaltato(modell="teszt-modell"))
    hamis_valasz = _HamisValasz(json.dumps({"message": {"content": "nem json"}}).encode())
    with patch("urllib.request.urlopen", return_value=hamis_valasz):
        eredmeny = ertelmezo.ertelmez("bármi", most=_MOST, kontextus=ErtelmezesKontextus())

    assert _ertelmezes(eredmeny) == {"eszkoz": "nincs", "parameterek": {}}
    assert ertelmezo.utolso_hiba is not None


def test_ertelmez_hianyzo_parameterek_kulcsot_ures_dict_kent_potolja():
    ertelmezo = LLMErtelmezo(LLMSzolgaltato(modell="teszt-modell"))
    with patch("urllib.request.urlopen", return_value=_ollama_valasz({"eszkoz": "nincs"})):
        eredmeny = ertelmezo.ertelmez("bármi", most=_MOST, kontextus=ErtelmezesKontextus())
    assert _ertelmezes(eredmeny) == {"eszkoz": "nincs", "parameterek": {}}


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


# --- bizonyosság a logprobokból (nem a modell önbevallásából) --------


def _tokenek(*parok: tuple[str, float]) -> list[dict]:
    """`(token, logprob)` párokból logprob-lista, ahogy az Ollama adja."""
    return [{"token": t, "logprob": lp} for t, lp in parok]


def test_mezo_bizonyossag_biztos_ertek_egyhez_kozel():
    logprobs = _tokenek(
        ('{"', -0.01), ("eszkoz", -0.01), ('": "', -0.01), ("nincs", -0.001), ('"}', -0.01)
    )
    assert _mezo_bizonyossag(logprobs, "eszkoz") > 0.99


def test_mezo_bizonyossag_bizonytalan_ertek_alacsony():
    logprobs = _tokenek(
        ('{"', -0.01), ("eszkoz", -0.01), ('": "', -0.01), ("nincs", -2.3), ('"}', -0.01)
    )
    ertek = _mezo_bizonyossag(logprobs, "eszkoz")
    assert 0.05 < ertek < 0.5


def test_mezo_bizonyossag_hianyzo_mezore_none():
    logprobs = _tokenek(('{"', -0.01), ("eszkoz", -0.01), ('": "', -0.01), ("nincs", -0.01))
    assert _mezo_bizonyossag(logprobs, "bolt_id") is None


def test_mezo_bizonyossag_logprobok_nelkul_none():
    """Ha a szolgáltató nem ad logprobot, az "nem tudom megmondani"
    (None), NEM "biztosan rossz" (0.0)."""
    assert _mezo_bizonyossag([], "eszkoz") is None


def test_mezo_bizonyossag_a_hosszu_erteket_nem_bunteti():
    """A mértani közép miatt egy több tokenre bomló érték NEM lesz
    automatikusan bizonytalanabb, mint egy egy tokenes — a szorzat ezt
    korábban elrontotta (0,0001 nagyságrendű, használhatatlan számok)."""
    rovid = _tokenek(
        ('{"', -0.01), ("eszkoz", -0.01), ('": "', -0.01), ("nincs", -0.05), ('"}', -0.01)
    )
    hosszu = _tokenek(
        ('{"', -0.01),
        ("eszkoz", -0.01),
        ('": "', -0.01),
        ("vissza", -0.05),
        ("kerdez", -0.05),
        ('"}', -0.01),
    )
    assert abs(_mezo_bizonyossag(rovid, "eszkoz") - _mezo_bizonyossag(hosszu, "eszkoz")) < 0.05


def test_bizonyossag_szamol_csak_a_jelenlevo_mezokre_ad_szamot():
    logprobs = _tokenek(
        ('{"', -0.01),
        ("eszkoz", -0.01),
        ('": "', -0.01),
        ("nincs", -0.01),
        ('", "parameterek": {}}', -0.01),
    )
    b = bizonyossag_szamol(logprobs, {"eszkoz": "nincs", "parameterek": {}})
    assert b["eszkoz"] is not None
    assert b["bolt_id"] is None
    assert b["datum"] is None


def test_ertelmez_bizonyossagot_ad_a_valaszban():
    ertelmezo = LLMErtelmezo(LLMSzolgaltato(modell="teszt-modell"))
    kimenet = {"eszkoz": "nincs", "parameterek": {}}
    nyers = json.dumps(
        {
            "message": {"content": json.dumps(kimenet)},
            "logprobs": [
                {"token": '{"eszkoz": "', "logprob": -0.01},
                {"token": "nincs", "logprob": -0.02},
                {"token": '", "parameterek": {}}', "logprob": -0.01},
            ],
        }
    ).encode()
    with patch("urllib.request.urlopen", return_value=_HamisValasz(nyers)):
        eredmeny = ertelmezo.ertelmez("bármi", most=_MOST, kontextus=ErtelmezesKontextus())

    assert eredmeny["eszkoz"] == "nincs"
    assert eredmeny["bizonyossag"]["eszkoz"] is not None


def test_ertelmez_logprob_nelkuli_valasznal_ures_bizonyossag():
    ertelmezo = LLMErtelmezo(LLMSzolgaltato(modell="teszt-modell"))
    with patch(
        "urllib.request.urlopen",
        return_value=_ollama_valasz({"eszkoz": "nincs", "parameterek": {}}),
    ):
        eredmeny = ertelmezo.ertelmez("bármi", most=_MOST, kontextus=ErtelmezesKontextus())
    assert all(ertek is None for ertek in eredmeny["bizonyossag"].values())

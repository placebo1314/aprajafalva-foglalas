"""Egységtesztek `assistant/interpreter/__init__.py::
alapertelmezett_ertelmezo()`-ra — ez a belépési pont, amit `ui/vasarlo.py`
használ (CLAUDE.md, "Modulhatárok": a ui/ nem hívhat LLM-et közvetlenül).
Nincs Ollama-hívás egyik tesztben sem — az `LLMErtelmezo` konstruktora
önmagában nem érinti a hálózatot, csak az `.ertelmez()` hívása."""

from __future__ import annotations

from assistant.interpreter import alapertelmezett_ertelmezo
from assistant.interpreter.kaszkad import KaszkadErtelmezo
from assistant.interpreter.llm_based import LLMErtelmezo
from assistant.interpreter.rule_based import SzabalyAlapuErtelmezo


def test_alapertelmezett_ertelmezo_kaszkadot_ad(monkeypatch):
    monkeypatch.delenv("APRAJAFALVA_LLM_MODELL", raising=False)
    ertelmezo = alapertelmezett_ertelmezo()
    assert isinstance(ertelmezo, KaszkadErtelmezo)
    assert isinstance(ertelmezo.szabaly, SzabalyAlapuErtelmezo)


def test_alapertelmezett_ertelmezo_modell_nelkul_llm_none():
    """Ha nincs konfigurált modell, a kaszkád `llm=None`-nal épül fel —
    SOHA nem próbál Ollamát hívni (assistant/interpreter/kaszkad.py)."""
    import os

    korabbi = os.environ.pop("APRAJAFALVA_LLM_MODELL", None)
    try:
        ertelmezo = alapertelmezett_ertelmezo()
        assert ertelmezo.llm is None
    finally:
        if korabbi is not None:
            os.environ["APRAJAFALVA_LLM_MODELL"] = korabbi


def test_alapertelmezett_ertelmezo_konfiguralt_modellel_llm_epul(monkeypatch):
    monkeypatch.setenv("APRAJAFALVA_LLM_MODELL", "teszt-modell")
    ertelmezo = alapertelmezett_ertelmezo()
    assert isinstance(ertelmezo.llm, LLMErtelmezo)
    assert ertelmezo.llm.szolgaltato.modell == "teszt-modell"

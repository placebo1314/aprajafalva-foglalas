"""Egységtesztek a vásárlói felület (`ui/vasarlo.py`) mögötti, Tkinter
nélküli tiszta függvényre — a Tkinter-widgeteket nem teszteljük (ugyanaz a
minta, mint `ui/admin/app.py`-nál: "Tkinter-teszt nincs").

A magyar mondatokat összeállító logika (`nyugtazo_szoveg`,
`tenyvalasz_szoveg`, hibaüzenetek stb.) átköltözött az `assistant/valasz/`
modulba — azt `tests/egyseg/test_valasz.py` teszteli. Itt csak az marad,
ami ténylegesen ehhez a felülethez kötött formázás (időpont-címke a
koppintós gombokhoz) és a próba-napló, nem magyar mondat."""

from __future__ import annotations

import json

import ui.vasarlo as vasarlo_modul
from ui.vasarlo import _idopont_cimke, _proba_naplo_ir


def test_idopont_cimke_formazas():
    cimke = _idopont_cimke("2026-08-18T08:00:00Z", "2026-08-18T08:30:00Z")
    assert cimke == "2026-08-18 08:00–08:30 (UTC)"


# --- _proba_naplo_ir -------------------------------------------------


def test_proba_naplo_ir_egy_sort_ir_a_varazott_mezokkel(tmp_path, monkeypatch):
    naplo_utvonal = tmp_path / "naplo" / "probak.jsonl"
    monkeypatch.setattr(vasarlo_modul, "_PROBA_NAPLO_UTVONAL", naplo_utvonal)

    _proba_naplo_ir(
        "petárdázni szeretnék kedden",
        {"eszkoz": "szabad_idopontok", "parameterek": {"bolt_id": "ugyifogyi"}},
        "szabaly",
    )

    sorok = naplo_utvonal.read_text(encoding="utf-8").splitlines()
    assert len(sorok) == 1
    sor = json.loads(sorok[0])
    assert sor["bemenet"] == "petárdázni szeretnék kedden"
    assert sor["eszkoz"] == "szabad_idopontok"
    assert sor["parameterek"] == {"bolt_id": "ugyifogyi"}
    assert sor["reteg"] == "szabaly"
    assert "idobelyeg" in sor


def test_proba_naplo_ir_konyvtart_letrehozza_ha_hianyzik(tmp_path, monkeypatch):
    naplo_utvonal = tmp_path / "meg-nem-letezo" / "probak.jsonl"
    monkeypatch.setattr(vasarlo_modul, "_PROBA_NAPLO_UTVONAL", naplo_utvonal)
    assert not naplo_utvonal.parent.exists()

    _proba_naplo_ir("bármi", {"eszkoz": "nincs", "parameterek": {}}, "szabaly")

    assert naplo_utvonal.exists()


def test_proba_naplo_ir_tobbszori_hivas_fuzi_nem_felulirja(tmp_path, monkeypatch):
    naplo_utvonal = tmp_path / "naplo" / "probak.jsonl"
    monkeypatch.setattr(vasarlo_modul, "_PROBA_NAPLO_UTVONAL", naplo_utvonal)

    _proba_naplo_ir("első", {"eszkoz": "nincs", "parameterek": {}}, "szabaly")
    _proba_naplo_ir("második", {"eszkoz": "nincs", "parameterek": {}}, "szabaly")

    sorok = naplo_utvonal.read_text(encoding="utf-8").splitlines()
    assert len(sorok) == 2
    assert json.loads(sorok[0])["bemenet"] == "első"
    assert json.loads(sorok[1])["bemenet"] == "második"


def test_proba_naplo_ir_hianyzo_ertelmezesnel_ures_mezoket_ir(tmp_path, monkeypatch):
    """`ertelmezes=None` (pl. ha az orchestrator még nem hívta az
    értelmezőt) nem dobhat kivételt — a napló ilyenkor is íródjon,
    üres eszköz/paraméterek mezővel."""
    naplo_utvonal = tmp_path / "probak.jsonl"
    monkeypatch.setattr(vasarlo_modul, "_PROBA_NAPLO_UTVONAL", naplo_utvonal)

    _proba_naplo_ir("bármi", None, None)

    sor = json.loads(naplo_utvonal.read_text(encoding="utf-8").splitlines()[0])
    assert sor["eszkoz"] is None
    assert sor["parameterek"] is None
    assert sor["reteg"] is None

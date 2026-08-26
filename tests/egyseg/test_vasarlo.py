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
from ui.vasarlo import (
    _idopont_cimke,
    _proba_naplo_ir,
    horgony_most,
    proba_naplo_olvas,
    proba_naplo_szoveg,
)

_IDOSZAK = {"elso_nap": "2026-12-21", "utolso_nap": "2026-12-27", "boltok": ["Törpilla"]}


def test_idopont_cimke_formazas():
    cimke = _idopont_cimke("2026-08-18T08:00:00Z", "2026-08-18T08:30:00Z")
    assert cimke == "2026-08-18 08:00–08:30 (UTC)"


# --- horgony_most: a felület a beosztáshoz igazodik ------------------


def test_horgony_a_beosztas_elso_napjara_esik_ha_a_mai_nap_kivul_van():
    """A demóadat távoli hete: a "ma" a beosztás első napja legyen,
    hogy a "holnap"/"kedden" ne üres keresésre fusson."""
    assert horgony_most(_IDOSZAK, "2026-08-22T14:30:00Z") == "2026-12-21T00:00:00Z"


def test_horgony_a_valodi_idot_hagyja_ha_a_mai_nap_a_beosztasban_van():
    """Ha a beosztás a mai napot is lefedi, semmit nem tolunk el — az
    eltolás kizárólag a demóadat távoli hetének problémáját oldja meg."""
    assert horgony_most(_IDOSZAK, "2026-12-23T09:00:00Z") == "2026-12-23T09:00:00Z"


def test_horgony_beosztas_nelkul_a_valodi_idot_adja():
    assert horgony_most(None, "2026-08-22T14:30:00Z") == "2026-08-22T14:30:00Z"


def test_horgony_a_nap_elejere_all_nem_a_valodi_orara():
    """Este próbálgatva a valódi óra megtartása azt jelentené, hogy a
    "ma" a bolt zárása UTÁN kezdődik — üres válasz, pontosan az a hiba,
    amit a horgony megszüntetni hivatott."""
    assert horgony_most(_IDOSZAK, "2026-08-22T19:45:12Z") == "2026-12-21T00:00:00Z"


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


def test_proba_naplo_ir_a_teljes_fordulot_rogziti(tmp_path, monkeypatch):
    """Mind a nyolc mező — tesztelés közben mindegyikre külön kérdés
    merül fel (l. `_proba_naplo_ir` docstring)."""
    naplo_utvonal = tmp_path / "probak.jsonl"
    monkeypatch.setattr(vasarlo_modul, "_PROBA_NAPLO_UTVONAL", naplo_utvonal)

    _proba_naplo_ir(
        "Möggyek-ë hónap a petárdáshó?",
        {
            "eszkoz": "szabad_idopontok",
            "parameterek": {"bolt_id": "ugyifogyi"},
            "bizonyossag": {"eszkoz": 0.91, "bolt_id": 0.88},
        },
        "llm",
        normalizalt="Möggyek-ë holnap a petárdáshó?",
        valasz_tipus="ajanlat",
    )

    sor = json.loads(naplo_utvonal.read_text(encoding="utf-8").splitlines()[0])
    assert sor["normalizalt"] == "Möggyek-ë holnap a petárdáshó?"
    assert sor["reteg"] == "llm"
    assert sor["bizonyossag"] == {"eszkoz": 0.91, "bolt_id": 0.88}
    assert sor["valasz_tipus"] == "ajanlat"


# --- napló megnyitása --------------------------------------------------


def test_proba_naplo_olvas_hianyzo_fajlnal_ures(tmp_path, monkeypatch):
    monkeypatch.setattr(vasarlo_modul, "_PROBA_NAPLO_UTVONAL", tmp_path / "nincs.jsonl")
    assert proba_naplo_olvas() == []


def test_proba_naplo_olvas_serult_sort_atugrik(tmp_path, monkeypatch):
    """Egy félbeszakadt korábbi futás ne akadályozza meg a napló
    megnyitását."""
    naplo_utvonal = tmp_path / "probak.jsonl"
    naplo_utvonal.write_text('{"bemenet": "jó"}\nnem-json\n\n', encoding="utf-8")
    monkeypatch.setattr(vasarlo_modul, "_PROBA_NAPLO_UTVONAL", naplo_utvonal)

    sorok = proba_naplo_olvas()

    assert len(sorok) == 1
    assert sorok[0]["bemenet"] == "jó"


def test_proba_naplo_olvas_utolso_n_sort_ad(tmp_path, monkeypatch):
    naplo_utvonal = tmp_path / "probak.jsonl"
    monkeypatch.setattr(vasarlo_modul, "_PROBA_NAPLO_UTVONAL", naplo_utvonal)
    for i in range(5):
        _proba_naplo_ir(f"{i}", {"eszkoz": "nincs", "parameterek": {}}, "szabaly")

    sorok = proba_naplo_olvas(utolso=2)

    assert [s["bemenet"] for s in sorok] == ["3", "4"]


def test_proba_naplo_szoveg_ures_naplonal_utbaigazit():
    assert "Még nincs" in proba_naplo_szoveg([])


def test_proba_naplo_szoveg_minden_mezot_megmutat():
    szoveg = proba_naplo_szoveg(
        [
            {
                "idobelyeg": "2026-08-22T10:00:00Z",
                "bemenet": "petárda holnap",
                "normalizalt": "petárda holnap",
                "reteg": "llm",
                "eszkoz": "szabad_idopontok",
                "parameterek": {"bolt_id": "ugyifogyi"},
                "bizonyossag": {"eszkoz": 0.9},
                "valasz_tipus": "ajanlat",
            }
        ]
    )
    for reszlet in ("petárda holnap", "llm", "szabad_idopontok", "ugyifogyi", "ajanlat"):
        assert reszlet in szoveg


# --- beszélgetés-előzmény (ADR-019) -----------------------------------
#
# A felület vezeti, mert csak ő ismeri a ténylegesen kimondott magyar
# mondatokat. A Tkinter-widgeteket itt sem teszteljük — az
# `_elozmenyhez_ad` tiszta listakezelés, ez tesztelhető önmagában.


class _ElozmenyGazda:
    """A `VasarloApp` előzmény-kezelő részének minimális mása — a
    metódus maga a valódi (`VasarloApp._elozmenyhez_ad`), csak a Tkinter
    örökség nélkül."""

    _elozmenyhez_ad = vasarlo_modul.VasarloApp._elozmenyhez_ad

    def __init__(self):
        self.szo_elozmenyek: list[tuple[str, str]] = []


def test_elozmeny_gyujti_a_ket_oldalt():
    gazda = _ElozmenyGazda()

    gazda._elozmenyhez_ad("vasarlo", "Törpillához mennék")
    gazda._elozmenyhez_ad("rendszer", "Nincs szabad időpont.")

    assert gazda.szo_elozmenyek == [
        ("vasarlo", "Törpillához mennék"),
        ("rendszer", "Nincs szabad időpont."),
    ]


def test_elozmeny_a_legutobbi_sorokra_vagodik():
    """A prompt hossza latencia — a régi fordulók kiesnek."""
    gazda = _ElozmenyGazda()
    for i in range(30):
        gazda._elozmenyhez_ad("vasarlo", f"{i}")

    assert len(gazda.szo_elozmenyek) == vasarlo_modul._ELOZMENY_SOROK
    assert gazda.szo_elozmenyek[-1] == ("vasarlo", "29")


# --- kimeneti mód: a rendszer-mondatok pufferelése (M6) --------------


class _ModGazda:
    """A `VasarloApp` mód-kezelő metódusai Tkinter nélkül — ugyanaz a
    minta, mint az `_ElozmenyGazda`-nál: a metódusokat az osztályról
    kölcsönözzük, a widgeteket nem építjük fel."""

    _mod = vasarlo_modul.VasarloApp._mod
    _rendszer_mondat = vasarlo_modul.VasarloApp._rendszer_mondat
    _rendszer_flush = vasarlo_modul.VasarloApp._rendszer_flush

    def __init__(self, mod: str):
        self._beallitott_mod = mod
        self._rendszer_puffer: list[str] = []
        self.kiirt: list[str] = []
        # A `_mod()` a `kimeneti_mod` Tkinter-változót olvassa — itt egy
        # ugyanolyan `get()`-tel rendelkező kis objektum áll a helyén.
        self.kimeneti_mod = type("Valto", (), {"get": lambda _s: mod})()

    def _naplo_ir(self, _ki_be: str, szoveg: str) -> None:
        self.kiirt.append(szoveg)


def test_szoveges_modban_minden_mondat_azonnal_kimegy():
    """Regressziós védőháló: a szöveges út viselkedése nem változott —
    három rendszer-mondat három sor."""
    gazda = _ModGazda(vasarlo_modul.valasz_szoveg.MOD_SZOVEGES)
    gazda._rendszer_mondat("Egy pillanat.", kulon_megszolalas=True)
    gazda._rendszer_mondat("Találtam időpontot.")
    gazda._rendszer_mondat("Melyik jó?")
    gazda._rendszer_flush()

    assert gazda.kiirt == ["Egy pillanat.", "Találtam időpontot.", "Melyik jó?"]


def test_beszelheto_modban_egy_fordulo_egy_megszolalas():
    """A tartalmi mondatok EGY megszólalássá állnak össze, a nyugtázó
    viszont külön marad — az a kétlépcsős válasz első lépcsője
    (blueprint 7.)."""
    gazda = _ModGazda(vasarlo_modul.valasz_szoveg.MOD_BESZELHETO)
    gazda._rendszer_mondat("Egy pillanat, nézem.", kulon_megszolalas=True)
    gazda._rendszer_mondat("Nincs szabad időpont.")
    gazda._rendszer_mondat("A héten másik napon van. Megnézzem?")
    gazda._rendszer_flush()

    assert gazda.kiirt == [
        "Egy pillanat, nézem.",
        "A héten másik napon van. Megnézzem?",
    ]


def test_beszelheto_puffer_nem_csordul_at_a_kovetkezo_fordulora():
    """Flush nélkül a bennmaradt mondat a KÖVETKEZŐ forduló elejére
    csúszna, és a vásárló egy már megválaszolt kérdésre kapna feleletet
    — ezért zárul a válaszkezelés `finally`-vel."""
    gazda = _ModGazda(vasarlo_modul.valasz_szoveg.MOD_BESZELHETO)
    gazda._rendszer_mondat("Melyik boltba szeretnél menni?")
    gazda._rendszer_flush()
    gazda._rendszer_flush()

    assert gazda.kiirt == ["Melyik boltba szeretnél menni?"]
    assert gazda._rendszer_puffer == []

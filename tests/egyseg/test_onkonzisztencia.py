"""Egységtesztek az önkonzisztencia-ellenőrzésre
(`assistant/interpreter/onkonzisztencia.py`, ADR-021, blueprint 10.).

Modell nélkül tesztelhető: a burkolt értelmező itt egy szkriptelt hamis
objektum, ami futásonként ELŐRE MEGADOTT választ ad. Így a három
kimenetel (3/3, 2/3, mind más) determinisztikusan előállítható — ami
egy valódi modellel épp nem menne, hiszen ott a lényeg a
kiszámíthatatlanság.
"""

from __future__ import annotations

from assistant.interpreter import ErtelmezesKontextus
from assistant.interpreter.llm_based import Mintavetel
from assistant.interpreter.onkonzisztencia import (
    ALAP_FUTASOK,
    BIZONYOSSAG_SZORZO_KETTO_HARMADNAL,
    OnkonzisztensErtelmezo,
    bekapcsolva,
    eszkozhivas_kulcsa,
)

_MOST = "2026-08-17T09:00:00Z"


class _SzkripteltErtelmezo:
    """Futásonként más választ ad, a megadott lista szerint."""

    TAMOGAT_MINTAVETELT = True

    def __init__(self, valaszok: list[dict]):
        self.valaszok = valaszok
        self.hivasok = 0
        self.kapott_mintavetelek: list[Mintavetel | None] = []
        self.utolso_reteg = "llm"
        self.utolso_normalizalt = "normalizált"

    def ertelmez(self, mondat, *, most, kontextus, mintavetel=None):
        self.kapott_mintavetelek.append(mintavetel)
        valasz = self.valaszok[self.hivasok % len(self.valaszok)]
        self.hivasok += 1
        return valasz


class _DeterminisztikusErtelmezo:
    """Nincs `TAMOGAT_MINTAVETELT` — a burkoló egyszer futtatja."""

    def __init__(self):
        self.hivasok = 0

    def ertelmez(self, mondat, *, most, kontextus):
        self.hivasok += 1
        return {"eszkoz": "nincs", "parameterek": {}, "bizonyossag": {"eszkoz": 1.0}}


def _ertelmez(burkolo, mondat="Petárdázni szeretnék kedden."):
    # A szekvenciális futtatás azért kell, hogy a szkriptelt válaszok
    # SORRENDJE kiszámítható legyen — párhuzamosan a szálak
    # ütemezésétől függene, melyik hívás melyik választ kapja.
    return burkolo.ertelmez(mondat, most=_MOST, kontextus=ErtelmezesKontextus())


_KERESES = {
    "eszkoz": "szabad_idopontok",
    "parameterek": {"bolt_id": "ugyifogyi", "napszak": "barmikor"},
    "bizonyossag": {"eszkoz": 0.95, "bolt_id": 0.75, "datum": None},
}
_MASIK_KERESES = {
    "eszkoz": "szabad_idopontok",
    "parameterek": {"bolt_id": "szundi", "napszak": "barmikor"},
    "bizonyossag": {"eszkoz": 0.6},
}
_LEMONDAS = {
    "eszkoz": "foglalas_lemondas",
    "parameterek": {"foglalasi_kod": "X7K2M9QP"},
    "bizonyossag": {"eszkoz": 0.5},
}


# --- 3/3: teljes egyetértés ------------------------------------------


def test_harom_egyezes_valtozatlanul_megy_at() -> None:
    ertelmezo = _SzkripteltErtelmezo([_KERESES])
    burkolo = OnkonzisztensErtelmezo(ertelmezo, parhuzamos=False)

    eredmeny = _ertelmez(burkolo)

    assert eredmeny == _KERESES
    assert burkolo.utolso_egyetertes == 3
    assert ertelmezo.hivasok == 3


def test_harom_egyezes_a_bizonyossagot_NEM_csokkenti() -> None:
    """A teljes egyetértés nem "bónusz" — a bizonyosság változatlan.
    A modul csak GYENGÍTHET, sosem erősíthet: egy felfelé korrigált
    bizonyosság azt állítaná, hogy három azonos futás TÖBB, mint amit a
    logprobok mutatnak, és erre nincs alapunk."""
    burkolo = OnkonzisztensErtelmezo(_SzkripteltErtelmezo([_KERESES]), parhuzamos=False)
    assert _ertelmez(burkolo)["bizonyossag"] == _KERESES["bizonyossag"]


# --- 2/3: többség, csökkentett bizonyossággal ------------------------


def test_ketto_harmad_a_tobbseg_nyer() -> None:
    ertelmezo = _SzkripteltErtelmezo([_KERESES, _MASIK_KERESES, _KERESES])
    burkolo = OnkonzisztensErtelmezo(ertelmezo, parhuzamos=False)

    eredmeny = _ertelmez(burkolo)

    assert eredmeny["eszkoz"] == "szabad_idopontok"
    assert eredmeny["parameterek"]["bolt_id"] == "ugyifogyi"
    assert burkolo.utolso_egyetertes == 2


def test_ketto_harmad_csokkentett_bizonyossag() -> None:
    ertelmezo = _SzkripteltErtelmezo([_KERESES, _MASIK_KERESES, _KERESES])
    burkolo = OnkonzisztensErtelmezo(ertelmezo, parhuzamos=False)

    bizonyossag = _ertelmez(burkolo)["bizonyossag"]

    assert bizonyossag["eszkoz"] == round(0.95 * BIZONYOSSAG_SZORZO_KETTO_HARMADNAL, 4)
    assert bizonyossag["bolt_id"] == round(0.75 * BIZONYOSSAG_SZORZO_KETTO_HARMADNAL, 4)
    # A `None` marad `None` — a "nem tudok nyilatkozni" nem szorozható
    # (assistant/interpreter/__init__.py::Ertelmezo).
    assert bizonyossag["datum"] is None


def test_a_csokkentes_a_hataresetet_billenti_at_nem_mindent() -> None:
    """A szorzó megválasztásának indoklása, tesztben rögzítve
    (`BIZONYOSSAG_SZORZO_KETTO_HARMADNAL` kommentje).

    Egy magabiztos válasz (0,95) a csökkentés UTÁN is átmegy az
    eszköz-küszöbön (0,7) — a 2/3 egyetértés önmagában nem kényszerít
    visszakérdezést. Egy amúgy is gyenge mező (0,74 vagy alatta)
    viszont a kritikus-mező küszöb (0,6) alá esik.

    A 0,75 pont a fordulópont (0,75 × 0,8 = 0,60), és a küszöb szigorú
    kisebb (`< kritikus_mezo`), tehát az még ÁTMEGY — ezt is rögzítjük,
    mert egy fél százalékos szorzó-módosítás máshova tenné a határt."""
    from assistant.orchestrator import BizonyossagKuszobok

    kuszobok = BizonyossagKuszobok()
    assert 0.95 * BIZONYOSSAG_SZORZO_KETTO_HARMADNAL > kuszobok.eszkoz
    assert round(0.74 * BIZONYOSSAG_SZORZO_KETTO_HARMADNAL, 4) < kuszobok.kritikus_mezo
    assert not round(0.75 * BIZONYOSSAG_SZORZO_KETTO_HARMADNAL, 4) < kuszobok.kritikus_mezo


# --- mind más: zárt kérdés -------------------------------------------


def test_mind_mas_zart_kerdes() -> None:
    ertelmezo = _SzkripteltErtelmezo([_KERESES, _MASIK_KERESES, _LEMONDAS])
    burkolo = OnkonzisztensErtelmezo(ertelmezo, parhuzamos=False)

    eredmeny = _ertelmez(burkolo)

    assert eredmeny["eszkoz"] == "visszakerdez"
    assert eredmeny["parameterek"]["hianyzo_mezo"] == "eszkoz"
    assert eredmeny["parameterek"]["varhato_kerdes_tipusa"] == "zart"
    assert eredmeny["onkonzisztencia"] == "nincs_tobbseg"
    assert burkolo.utolso_egyetertes == 1


def test_mind_mas_a_valaszthato_ertekek_valodi_eszkozok() -> None:
    """A felkínált lehetőségek a HÁROM FUTÁS javaslatai, nem kitalált
    opciók — a vásárlónak csak olyat kínálunk, amit a rendszer
    ténylegesen meg tudna csinálni."""
    ertelmezo = _SzkripteltErtelmezo([_KERESES, _MASIK_KERESES, _LEMONDAS])
    burkolo = OnkonzisztensErtelmezo(ertelmezo, parhuzamos=False)

    ertekek = _ertelmez(burkolo)["parameterek"]["valaszthato_ertekek"]

    assert ertekek == ["szabad_idopontok", "foglalas_lemondas"]


def test_mind_mas_bizonyossaga_none_nem_nulla() -> None:
    """A `None` és a `0.0` két különböző állítás
    (`assistant/interpreter/__init__.py::Ertelmezo`): itt nem azt
    mondjuk, hogy a szándék biztosan rossz, hanem hogy nem tudunk róla
    nyilatkozni. A `0.0` az orchestrator kapuján ugyanúgy
    visszakérdezést váltana ki, de HAMIS állítás lenne."""
    ertelmezo = _SzkripteltErtelmezo([_KERESES, _MASIK_KERESES, _LEMONDAS])
    burkolo = OnkonzisztensErtelmezo(ertelmezo, parhuzamos=False)
    assert _ertelmez(burkolo)["bizonyossag"]["eszkoz"] is None


# --- a mintavétel ----------------------------------------------------


def test_az_elso_futas_kanonikus_a_tobbi_mintaveteles() -> None:
    """Az első futás `temperature: 0` (`mintavetel=None`) — pontosan
    az, amit a rendszer önkonzisztencia NÉLKÜL adna. Ez fontos: a
    kikapcsolás nem változtathat a kanonikus válaszon."""
    ertelmezo = _SzkripteltErtelmezo([_KERESES])
    burkolo = OnkonzisztensErtelmezo(ertelmezo, parhuzamos=False)
    _ertelmez(burkolo)

    assert ertelmezo.kapott_mintavetelek[0] is None
    assert all(m is not None for m in ertelmezo.kapott_mintavetelek[1:])
    # Rögzített magok → a mérés megismételhető.
    assert [m.seed for m in ertelmezo.kapott_mintavetelek[1:]] == [1, 2]


def test_alap_futasok_elso_eleme_kanonikus() -> None:
    assert ALAP_FUTASOK[0] is None
    assert len(ALAP_FUTASOK) == 3


# --- determinisztikus értelmező: nincs többszörös futás --------------


def test_mintavetelt_nem_tamogato_ertelmezot_egyszer_futtat() -> None:
    """Három azonos futásból nem lesz információ, csak késleltetés — a
    determinisztikus rétegen a burkoló viselkedése BITRE azonos a
    burkolatlanéval."""
    ertelmezo = _DeterminisztikusErtelmezo()
    burkolo = OnkonzisztensErtelmezo(ertelmezo, parhuzamos=False)

    eredmeny = _ertelmez(burkolo)

    assert ertelmezo.hivasok == 1
    assert burkolo.utolso_egyetertes is None
    assert eredmeny == {"eszkoz": "nincs", "parameterek": {}, "bizonyossag": {"eszkoz": 1.0}}


# --- az egyenlőség-vizsgálat -----------------------------------------


def test_a_kulcs_a_bizonyossagot_kihagyja() -> None:
    """A szavazás arról szól, hogy a rendszer UGYANAZT CSINÁLNÁ-e —
    nem arról, hogy ugyanannyira volt-e biztos benne. A bizonyosság
    mintavételes futásoknál szükségszerűen ingadozik; ha beleszámítana,
    a szavazás SOSEM adna egyezést."""
    a = {
        "eszkoz": "szabad_idopontok",
        "parameterek": {"bolt_id": "szundi"},
        "bizonyossag": {"e": 1},
    }
    b = {"eszkoz": "szabad_idopontok", "parameterek": {"bolt_id": "szundi"}, "bizonyossag": {}}
    assert eszkozhivas_kulcsa(a) == eszkozhivas_kulcsa(b)


def test_a_kulcs_kulcssorrendtol_fuggetlen() -> None:
    a = {"eszkoz": "szabad_idopontok", "parameterek": {"bolt_id": "szundi", "napszak": "este"}}
    b = {"eszkoz": "szabad_idopontok", "parameterek": {"napszak": "este", "bolt_id": "szundi"}}
    assert eszkozhivas_kulcsa(a) == eszkozhivas_kulcsa(b)


def test_a_kulcs_a_parameterek_elteresere_erzekeny() -> None:
    """PONTOS egyenlőség, nem hasonlóság: egyetlen eltérő paraméter is
    külön szavazat. Egy "hasonló" ág itt pont azt hozná vissza, amit a
    blueprint tilt (szabad szöveg súlyozott keverése)."""
    a = {"eszkoz": "szabad_idopontok", "parameterek": {"bolt_id": "szundi"}}
    b = {"eszkoz": "szabad_idopontok", "parameterek": {"bolt_id": "torpilla"}}
    assert eszkozhivas_kulcsa(a) != eszkozhivas_kulcsa(b)


# --- a kapcsoló ------------------------------------------------------


def test_kornyezeti_kapcsolo(monkeypatch) -> None:
    monkeypatch.delenv("APRAJAFALVA_ONKONZISZTENCIA", raising=False)
    assert bekapcsolva(True) is True
    assert bekapcsolva(False) is False

    for kikapcsolo in ("0", "false", "FALSE", "nem", "ki", " 0 "):
        monkeypatch.setenv("APRAJAFALVA_ONKONZISZTENCIA", kikapcsolo)
        assert bekapcsolva(True) is False, kikapcsolo

    for bekapcsolo in ("1", "igen", "true"):
        monkeypatch.setenv("APRAJAFALVA_ONKONZISZTENCIA", bekapcsolo)
        assert bekapcsolva(False) is True, bekapcsolo


# --- átjárók (a hívóknak nem kell tudniuk a burkolatról) -------------


def test_reteg_es_normalizalt_atjaro() -> None:
    burkolo = OnkonzisztensErtelmezo(_SzkripteltErtelmezo([_KERESES]), parhuzamos=False)
    _ertelmez(burkolo)
    assert burkolo.utolso_reteg == "llm"
    assert burkolo.utolso_normalizalt == "normalizált"

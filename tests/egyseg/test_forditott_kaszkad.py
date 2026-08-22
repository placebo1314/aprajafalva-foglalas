"""Egységtesztek a FORDÍTOTT kaszkád értelmezőre (`assistant/
interpreter/forditott_kaszkad.py`, ADR-018 — mért kísérlet, elvetve,
de reprodukálhatóan megtartva) — az LLM-réteget mindenütt egy
szkriptelt hamisítvány (`_FakeLLM`) helyettesíti, ez a fájl SOSEM hív
valódi Ollamát.

A hangsúly a DETERMINISZTIKUS KAPUKON van: a modell értelmez, de a
dátumot a parser adja, a bolt/szolgáltatás zárt halmazon marad, a
foglalási kód a mondatból jön, és Ollama-hiba esetén a szabály-alapú
réteg veszi át hiba nélkül."""

from __future__ import annotations

from assistant.interpreter import ErtelmezesKontextus
from assistant.interpreter.forditott_kaszkad import ForditottKaszkadErtelmezo
from assistant.interpreter.rule_based import SzabalyAlapuErtelmezo

_MOST = "2026-08-17T09:00:00Z"  # hétfő


class _FakeLLM:
    """Az `LLMErtelmezo`-t helyettesíti — nincs Ollama-hívás."""

    def __init__(self, valasz: dict | None = None, hiba: str | None = None):
        self.valasz = valasz or {"eszkoz": "nincs", "parameterek": {}}
        self.utolso_hiba = hiba
        self.kapott_mondatok: list[str] = []

    def ertelmez(self, mondat: str, *, most: str, kontextus: ErtelmezesKontextus) -> dict:
        self.kapott_mondatok.append(mondat)
        return self.valasz


def _kaszkad(llm=None) -> ForditottKaszkadErtelmezo:
    return ForditottKaszkadErtelmezo(SzabalyAlapuErtelmezo(), llm)


def _ertelmez(kaszkad, mondat, megorzott=None):
    return kaszkad.ertelmez(
        mondat,
        most=_MOST,
        kontextus=ErtelmezesKontextus(megorzott_parameterek=megorzott or {}),
    )


# --- tartalék: modell nélkül / modellhiba esetén ---------------------


def test_llm_nelkul_tisztan_determinisztikus():
    """`llm=None` — a felület modell nélkül is működik, és SOHA nem
    próbál Ollamát hívni."""
    kaszkad = _kaszkad(llm=None)
    mondat = "Petárdázni szeretnék kedden."

    eredmeny = _ertelmez(kaszkad, mondat)
    kozvetlen = SzabalyAlapuErtelmezo().ertelmez(
        mondat, most=_MOST, kontextus=ErtelmezesKontextus()
    )

    assert eredmeny == kozvetlen
    assert kaszkad.utolso_reteg == "szabaly"


def test_ollama_hiba_eseten_szabaly_alapu_tartalek_hiba_nelkul():
    """Ha az Ollama nem elérhető, NEM dobunk kivételt — a
    determinisztikus réteg veszi át, a vásárló ebből semmit nem vesz
    észre."""
    llm = _FakeLLM(hiba="Ollama nem elérhető: connection refused")
    kaszkad = _kaszkad(llm)
    mondat = "Petárdázni szeretnék kedden."

    eredmeny = _ertelmez(kaszkad, mondat)
    kozvetlen = SzabalyAlapuErtelmezo().ertelmez(
        mondat, most=_MOST, kontextus=ErtelmezesKontextus()
    )

    assert eredmeny == kozvetlen
    assert kaszkad.utolso_reteg == "szabaly"


def test_idotullepes_eseten_is_a_szabaly_alapu_tartalek_megy():
    """Időtúllépés — ugyanaz a tartalék-ág, mint a nem elérhető
    szolgáltatásnál: az `LLMErtelmezo` a `TimeoutError`-t is
    `utolso_hiba`-vá alakítja, nem engedi kivételként felszínre."""
    llm = _FakeLLM(hiba="Ollama nem elérhető: timed out")
    kaszkad = _kaszkad(llm)

    eredmeny = _ertelmez(kaszkad, "Petárdázni szeretnék kedden.")

    assert eredmeny["eszkoz"] == "szabad_idopontok"
    assert eredmeny["parameterek"]["bolt_id"] == "ugyifogyi"
    assert kaszkad.utolso_reteg == "szabaly"


# --- 1. kapu: normalizáló a modell ELŐTT ------------------------------


def test_normalizalo_a_modell_elott_fut():
    """A modell a NORMALIZÁLT mondatot kapja — a tájszólási alakokat
    (itt: "hónap" = holnap) nem neki kell kitalálnia."""
    llm = _FakeLLM({"eszkoz": "nincs", "parameterek": {}})
    kaszkad = _kaszkad(llm)

    _ertelmez(kaszkad, "Möggyek-ë hónap a petárdáshó?")

    kapott = llm.kapott_mondatok[0]
    assert "holnap" in kapott, f"a normalizálásnak meg kell történnie: {kapott!r}"
    assert "hónap" not in kapott


# --- 3. kapu: a dátum a parserből jön ---------------------------------


def test_datum_a_szoveges_kifejezesbol_a_parserrel_oldodik_fel():
    llm = _FakeLLM(
        {
            "eszkoz": "szabad_idopontok",
            "parameterek": {"bolt_id": "ugyifogyi", "datum_kifejezes": "jövő hét péntek"},
        }
    )
    eredmeny = _ertelmez(_kaszkad(llm), "és jövő hét pénteken?")

    assert eredmeny["parameterek"]["datum_tol"] == "2026-08-28T00:00:00Z"
    assert eredmeny["parameterek"]["datum_ig"] == "2026-08-28T23:59:59Z"


def test_a_parser_felulirja_a_modell_iso_datumat():
    """Ha a modell a prompt ellenére ISO-dátumot ad, ÉS az eltér a
    kifejezésből feloldottól, a PARSER nyer."""
    llm = _FakeLLM(
        {
            "eszkoz": "szabad_idopontok",
            "parameterek": {
                "bolt_id": "ugyifogyi",
                "datum_kifejezes": "holnap",
                "datum_tol": "1999-01-01T00:00:00Z",  # a modell téved
                "datum_ig": "1999-01-01T23:59:59Z",
            },
        }
    )
    eredmeny = _ertelmez(_kaszkad(llm), "holnap mennék")

    assert eredmeny["parameterek"]["datum_tol"] == "2026-08-18T00:00:00Z"
    assert eredmeny["parameterek"]["datum_ig"] == "2026-08-18T23:59:59Z"


def test_feloldhatatlan_kifejezes_nelkuli_iso_datumot_eldobunk():
    """Kifejezés nélkül a modell ISO-dátuma nem ellenőrizhető — nem
    fogadjuk el, inkább az általános ablak megy."""
    llm = _FakeLLM(
        {
            "eszkoz": "szabad_idopontok",
            "parameterek": {"bolt_id": "ugyifogyi", "datum_tol": "1999-01-01T00:00:00Z"},
        }
    )
    eredmeny = _ertelmez(_kaszkad(llm), "mikor lehet menni?")

    assert eredmeny["parameterek"]["datum_tol"] == "2026-08-17T09:00:00Z"
    assert eredmeny["parameterek"]["datum_ig"] == "2026-08-24T23:59:59Z"


def test_ket_datumkifejezes_ablaka_osszevonodik():
    """Vagylagos/feltételes időpont: a modell KÉT kifejezést idéz, az
    ablak összevonása determinisztikus (`_datum_ablak`) — mindkét kért
    nap belefér, a második nem vész el."""
    llm = _FakeLLM(
        {
            "eszkoz": "szabad_idopontok",
            "parameterek": {
                "bolt_id": "szundi",
                "datum_kifejezes": "szerdán",
                "datum_kifejezes_2": "csütörtök",
            },
        }
    )
    eredmeny = _ertelmez(_kaszkad(llm), "ha van hely szerdán, ha nincs, akkor csütörtök")

    assert eredmeny["parameterek"]["datum_tol"] == "2026-08-19T00:00:00Z"
    assert eredmeny["parameterek"]["datum_ig"] == "2026-08-20T23:59:59Z"


def test_ket_datumkifejezes_forditott_sorrendben_is_a_tagabb_ablakot_adja():
    """A sorrend nem számít: az összevonás a KORÁBBI kezdetet és a
    KÉSŐBBI véget veszi, nem az idézés sorrendjét."""
    llm = _FakeLLM(
        {
            "eszkoz": "szabad_idopontok",
            "parameterek": {
                "bolt_id": "szundi",
                "datum_kifejezes": "csütörtök",
                "datum_kifejezes_2": "szerdán",
            },
        }
    )
    eredmeny = _ertelmez(_kaszkad(llm), "csütörtök vagy szerda")

    assert eredmeny["parameterek"]["datum_tol"] == "2026-08-19T00:00:00Z"
    assert eredmeny["parameterek"]["datum_ig"] == "2026-08-20T23:59:59Z"


def test_feloldhatatlan_masodik_kifejezes_nem_rontja_el_az_elsot():
    llm = _FakeLLM(
        {
            "eszkoz": "szabad_idopontok",
            "parameterek": {
                "bolt_id": "szundi",
                "datum_kifejezes": "holnap",
                "datum_kifejezes_2": "amikor jó lesz",
            },
        }
    )
    eredmeny = _ertelmez(_kaszkad(llm), "holnap, vagy amikor jó lesz")

    assert eredmeny["parameterek"]["datum_tol"] == "2026-08-18T00:00:00Z"
    assert eredmeny["parameterek"]["datum_ig"] == "2026-08-18T23:59:59Z"


def test_a_modell_datum_kifejezesei_nem_szivarognak_at_a_parameterekbe():
    """A `datum_kifejezes*` mezők NYERSANYAGOK a parsernek — az eszköz
    paraméterei közé nem kerülhetnek be (az eszközsémák nem ismerik
    őket, `additionalProperties: false`)."""
    llm = _FakeLLM(
        {
            "eszkoz": "szabad_idopontok",
            "parameterek": {
                "bolt_id": "szundi",
                "datum_kifejezes": "szerdán",
                "datum_kifejezes_2": "csütörtök",
            },
        }
    )
    eredmeny = _ertelmez(_kaszkad(llm), "szerda vagy csütörtök")

    assert "datum_kifejezes" not in eredmeny["parameterek"]
    assert "datum_kifejezes_2" not in eredmeny["parameterek"]


def test_napszak_a_datum_kifejezesbol_is_kinyerheto():
    llm = _FakeLLM(
        {
            "eszkoz": "szabad_idopontok",
            "parameterek": {"bolt_id": "ugyifogyi", "datum_kifejezes": "holnap este"},
        }
    )
    eredmeny = _ertelmez(_kaszkad(llm), "holnap este?")

    assert eredmeny["parameterek"]["napszak"] == "este"
    assert eredmeny["parameterek"]["datum_ig"] == "2026-08-18T22:59:59Z"


# --- 2. kapu: zárt halmazok -------------------------------------------


def test_ervenytelen_boltot_eldobunk_es_visszakerdezunk():
    llm = _FakeLLM(
        {
            "eszkoz": "szabad_idopontok",
            "parameterek": {"bolt_id": "nemletezo_bolt", "datum_kifejezes": "holnap"},
        }
    )
    eredmeny = _ertelmez(_kaszkad(llm), "holnap valahova")

    assert eredmeny["eszkoz"] == "visszakerdez"
    assert eredmeny["parameterek"]["hianyzo_mezo"] == "bolt_id"
    # A már ismert dátum nem vész el a visszakérdezésben.
    assert eredmeny["parameterek"]["datum_tol"] == "2026-08-18T00:00:00Z"


def test_ervenytelen_szolgaltatast_eldobunk():
    """Érvénytelen szolgáltatás helyett a bolt egyértelmű
    szolgáltatása jön (determinisztikus katalógus), nem a modellé."""
    llm = _FakeLLM(
        {
            "eszkoz": "szabad_idopontok",
            "parameterek": {"bolt_id": "szundi", "szolgaltatas_id": "kitalalt_szolgaltatas"},
        }
    )
    eredmeny = _ertelmez(_kaszkad(llm), "szundihoz mennék")

    assert eredmeny["parameterek"]["szolgaltatas_id"] == "altato"


# --- foglalási kód: a mondatból, nem a modelltől ----------------------


def test_foglalasi_kod_a_mondatbol_jon_nem_a_modelltol():
    llm = _FakeLLM(
        {
            "eszkoz": "foglalas_lemondas",
            "parameterek": {"foglalasi_kod": "ELIRTKOD"},  # a modell elrontotta
        }
    )
    eredmeny = _ertelmez(_kaszkad(llm), "Lemondanám, a kód X7K2M9QP.")

    assert eredmeny["parameterek"]["foglalasi_kod"] == "X7K2M9QP"


def test_foglalasi_kod_nelkul_visszakerdez():
    llm = _FakeLLM({"eszkoz": "foglalas_lemondas", "parameterek": {}})
    eredmeny = _ertelmez(_kaszkad(llm), "Le szeretném mondani a foglalásomat.")

    assert eredmeny["eszkoz"] == "visszakerdez"
    assert eredmeny["parameterek"]["hianyzo_mezo"] == "foglalasi_kod"


# --- kontextus-öröklés és bizonyosság ---------------------------------


def test_bolt_a_kontextusbol_orokolheto():
    llm = _FakeLLM({"eszkoz": "szabad_idopontok", "parameterek": {"datum_kifejezes": "holnap"}})
    eredmeny = _ertelmez(_kaszkad(llm), "és holnap?", megorzott={"bolt_id": "torpilla"})

    assert eredmeny["parameterek"]["bolt_id"] == "torpilla"


def test_bizonyossag_atmegy_a_kapukon():
    """Az orchestrator a `bizonyossag` alapján dönt a visszakérdezésről
    — a kaszkádnak ezt továbbítania kell."""
    llm = _FakeLLM(
        {
            "eszkoz": "szabad_idopontok",
            "parameterek": {"bolt_id": "ugyifogyi", "datum_kifejezes": "holnap"},
            "bizonyossag": {"eszkoz": 0.42, "bolt_id": 0.9},
        }
    )
    eredmeny = _ertelmez(_kaszkad(llm), "holnap petárda")

    assert eredmeny["bizonyossag"]["eszkoz"] == 0.42


def test_kapuor_dontes_atmegy():
    llm = _FakeLLM({"eszkoz": "nincs", "parameterek": {}})
    eredmeny = _ertelmez(_kaszkad(llm), "Milyen idő lesz holnap?")

    assert eredmeny == {"eszkoz": "nincs", "parameterek": {}, "bizonyossag": {}}


def test_bolt_info_datum_csak_naptari_nap():
    llm = _FakeLLM(
        {
            "eszkoz": "bolt_info",
            "parameterek": {
                "bolt_id": "szundi",
                "mit": "nyitvatartas",
                "datum_kifejezes": "szombat",
            },
        }
    )
    eredmeny = _ertelmez(_kaszkad(llm), "Meddig van nyitva a Szundi szombaton?")

    assert eredmeny["parameterek"]["datum"] == "2026-08-22"

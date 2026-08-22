"""Egységtesztek a kaszkád értelmezőre (`assistant/interpreter/
kaszkad.py`, ADR-016) — VALÓDI `SzabalyAlapuErtelmezo`-val (gyors, LLM
nélkül), de az LLM-réteget mindenütt egy szkriptelt hamisítvány
(`_FakeLLM`) helyettesíti — ez a fájl SOSEM hív valódi Ollamát."""

from __future__ import annotations

from assistant.interpreter import ErtelmezesKontextus
from assistant.interpreter.kaszkad import KaszkadErtelmezo
from assistant.interpreter.rule_based import SzabalyAlapuErtelmezo

_MOST = "2026-08-17T09:00:00Z"  # hétfő


class _FakeLLM:
    """Az `LLMErtelmezo`-t helyettesíti — nincs Ollama-hívás. `valasz`
    a következő `ertelmez()` hívás visszatérési értéke; `hiba` az
    `utolso_hiba` mező."""

    def __init__(self, valasz: dict | None = None, hiba: str | None = None):
        self.valasz = valasz
        self.utolso_hiba = hiba
        self.hivasok = 0

    def ertelmez(self, mondat: str, *, most: str, kontextus: ErtelmezesKontextus) -> dict:
        self.hivasok += 1
        return self.valasz


def _kaszkad(llm=None) -> KaszkadErtelmezo:
    return KaszkadErtelmezo(SzabalyAlapuErtelmezo(), llm)


# --- a szabály-alapú réteg elég -----------------------------------------


def test_kaszkad_ha_a_szabaly_alapu_eldonti_az_llm_nem_hivodik():
    llm = _FakeLLM(valasz={"eszkoz": "szabad_idopontok", "parameterek": {"bolt_id": "torpilla"}})
    kaszkad = _kaszkad(llm)

    eredmeny = kaszkad.ertelmez(
        "Szeretnék petárdázni kedden.", most=_MOST, kontextus=ErtelmezesKontextus()
    )

    assert eredmeny["eszkoz"] == "szabad_idopontok"
    assert eredmeny["parameterek"]["bolt_id"] == "ugyifogyi"
    assert llm.hivasok == 0
    assert kaszkad.utolso_reteg == "szabaly"


def test_kaszkad_nem_kiegeszitheto_mezonel_llm_nem_hivodik():
    """A `foglalasi_kod` hiánya (lemondás) nem tartozik a kiegészíthető
    mezők közé (modul docstring) — az LLM-et meg sem kérdezi."""
    llm = _FakeLLM(valasz={"eszkoz": "foglalas_lemondas", "parameterek": {"foglalasi_kod": "X"}})
    kaszkad = _kaszkad(llm)
    szabaly = SzabalyAlapuErtelmezo()
    mondat = "Le szeretném mondani a foglalásomat."

    eredmeny = kaszkad.ertelmez(mondat, most=_MOST, kontextus=ErtelmezesKontextus())
    kozvetlen = szabaly.ertelmez(mondat, most=_MOST, kontextus=ErtelmezesKontextus())

    assert eredmeny == kozvetlen
    assert llm.hivasok == 0
    assert kaszkad.utolso_reteg == "szabaly"


# --- llm=None: sosem próbál Ollamát hívni --------------------------------


def test_kaszkad_llm_nelkul_valtozatlan_visszakerdez():
    kaszkad = _kaszkad(llm=None)
    szabaly = SzabalyAlapuErtelmezo()
    mondat = "Szeretnék menni kedden valahova."

    eredmeny = kaszkad.ertelmez(mondat, most=_MOST, kontextus=ErtelmezesKontextus())
    kozvetlen = szabaly.ertelmez(mondat, most=_MOST, kontextus=ErtelmezesKontextus())

    assert eredmeny == kozvetlen
    assert eredmeny["eszkoz"] == "visszakerdez"
    assert kaszkad.utolso_reteg == "szabaly"


# --- az LLM próbál kiegészíteni, de nem sikerül --------------------------


def test_kaszkad_llm_hiba_eseten_marad_a_szabaly_alapu_visszakerdez():
    llm = _FakeLLM(valasz=None, hiba="Ollama nem elérhető: connection refused")
    kaszkad = _kaszkad(llm)
    szabaly = SzabalyAlapuErtelmezo()
    mondat = "Szeretnék menni kedden valahova."

    eredmeny = kaszkad.ertelmez(mondat, most=_MOST, kontextus=ErtelmezesKontextus())
    kozvetlen = szabaly.ertelmez(mondat, most=_MOST, kontextus=ErtelmezesKontextus())

    assert eredmeny == kozvetlen
    assert llm.hivasok == 1
    assert kaszkad.utolso_reteg == "szabaly"


def test_kaszkad_llm_ervenytelen_boltot_javasol_elutasitva():
    """A bolt zárt halmazon marad — egy kitalált/érvénytelen `bolt_id`-t
    a kaszkád eldob, nem engedi tovább."""
    llm = _FakeLLM(
        valasz={"eszkoz": "szabad_idopontok", "parameterek": {"bolt_id": "nemletezo_bolt"}}
    )
    kaszkad = _kaszkad(llm)
    szabaly = SzabalyAlapuErtelmezo()
    mondat = "Szeretnék menni kedden valahova."

    eredmeny = kaszkad.ertelmez(mondat, most=_MOST, kontextus=ErtelmezesKontextus())
    kozvetlen = szabaly.ertelmez(mondat, most=_MOST, kontextus=ErtelmezesKontextus())

    assert eredmeny == kozvetlen
    assert kaszkad.utolso_reteg == "szabaly"


# --- az LLM sikeresen kiegészít ------------------------------------------


def test_kaszkad_llm_kiegesziti_a_hianyzo_boltot():
    llm = _FakeLLM(valasz={"eszkoz": "szabad_idopontok", "parameterek": {"bolt_id": "ugyifogyi"}})
    kaszkad = _kaszkad(llm)

    eredmeny = kaszkad.ertelmez(
        "Szeretnék menni kedden valahova.", most=_MOST, kontextus=ErtelmezesKontextus()
    )

    assert eredmeny["eszkoz"] == "szabad_idopontok"
    assert eredmeny["parameterek"]["bolt_id"] == "ugyifogyi"
    assert kaszkad.utolso_reteg == "llm"


def test_kaszkad_a_datum_mindig_a_determinisztikus_parserbol_jon():
    """Még ha az LLM (hibásan) dátumot is mond, azt a kaszkád EL SEM
    OLVASSA — a végleges dátum mindig az újrafuttatott determinisztikus
    parseré. Itt a mondat "kedden" (2026-08-18) — a hamis LLM egy
    teljesen más, hibás dátumot állít."""
    llm = _FakeLLM(
        valasz={
            "eszkoz": "szabad_idopontok",
            "parameterek": {
                "bolt_id": "ugyifogyi",
                "datum_tol": "1999-01-01T00:00:00Z",
                "datum_ig": "1999-01-01T23:59:59Z",
            },
        }
    )
    kaszkad = _kaszkad(llm)

    eredmeny = kaszkad.ertelmez(
        "Szeretnék menni kedden valahova.", most=_MOST, kontextus=ErtelmezesKontextus()
    )

    assert eredmeny["parameterek"]["datum_tol"] == "2026-08-18T00:00:00Z"
    assert eredmeny["parameterek"]["datum_ig"] == "2026-08-18T23:59:59Z"
    assert kaszkad.utolso_reteg == "llm"


def test_kaszkad_szolgaltatas_sosem_az_llm_tol_jon():
    """A szolgáltatás sosem az LLM válaszából kerül be — még ha az
    megpróbálná, az újrafuttatott determinisztikus parser tölti ki (vagy
    nem), a BOLT_EGYERTELMU_SZOLGALTATAS szabállyal. Itt a Szundinál
    egyértelmű a szolgáltatás (altató), azt kapjuk — nem a hamis
    LLM-javaslatot."""
    llm = _FakeLLM(
        valasz={
            "eszkoz": "szabad_idopontok",
            "parameterek": {
                "bolt_id": "szundi",
                "szolgaltatas_id": "nagy_orom",
            },  # hamis, Törpilláé
        }
    )
    kaszkad = _kaszkad(llm)

    eredmeny = kaszkad.ertelmez(
        "Szeretnék menni kedden valahova.", most=_MOST, kontextus=ErtelmezesKontextus()
    )

    assert eredmeny["parameterek"]["bolt_id"] == "szundi"
    assert eredmeny["parameterek"]["szolgaltatas_id"] == "altato"


def test_kaszkad_bovitett_kontextussal_is_visszakerdezesnel_marad_az_eredeti():
    """Ha a kiegészített bolttal ÚJRAFUTTATVA is visszakérdezésre jut a
    determinisztikus parser, nem erőltetjük — az eredeti válasz a
    mérvadó. A `bolt_info` ág (l. `_bolt_info` rule_based.py-ban) nem
    olvassa a kontextust a bolt feloldásához, csak a mondatot — egy
    kontextusból kapott bolt itt nem segít, a második futás is
    visszakérdez."""
    llm = _FakeLLM(valasz={"eszkoz": "szabad_idopontok", "parameterek": {"bolt_id": "szundi"}})
    kaszkad = _kaszkad(llm)
    szabaly = SzabalyAlapuErtelmezo()
    mondat = "Meddig van nyitva?"

    eredmeny = kaszkad.ertelmez(mondat, most=_MOST, kontextus=ErtelmezesKontextus())
    kozvetlen = szabaly.ertelmez(mondat, most=_MOST, kontextus=ErtelmezesKontextus())

    assert kozvetlen["eszkoz"] == "visszakerdez"  # előfeltétel-ellenőrzés
    assert eredmeny == kozvetlen
    assert kaszkad.utolso_reteg == "szabaly"


# --- elengedés-ág: a modell megmondja, mi esik ki --------------------


class _FakeElengedoLLM(_FakeLLM):
    """`valtozas_elemzes`-t is tud — a `elenged` listát adja vissza."""

    def __init__(self, elenged: list[str] | None = None, hiba: str | None = None):
        super().__init__(valasz=None, hiba=hiba)
        self._elenged = elenged
        self.elemzes_hivasok: list[dict] = []

    def valtozas_elemzes(self, mondat: str, megorzott_parameterek: dict) -> dict | None:
        self.elemzes_hivasok.append(dict(megorzott_parameterek))
        if self._elenged is None:
            return None
        megtart = [k for k in megorzott_parameterek if k not in self._elenged]
        return {"megtart": megtart, "elenged": list(self._elenged)}


_KONTEKTUS_NAPSZAKKAL = {
    "bolt_id": "ugyifogyi",
    "datum_tol": "2026-08-18T00:00:00Z",
    "datum_ig": "2026-08-18T11:59:59Z",
    "napszak": "delelott",
}


def test_kaszkad_elengedes_a_modell_szerint_kieso_mezot_elhagyja():
    """A "mégis mindegy, mikor" típusú mondat: a determinisztikus réteg
    magától megtartaná a korábbi napszakot/dátumot (nincs benne olyan
    szó, amit szabály kereshetne), a modell viszont megmondja, hogy
    ezek kiesnek."""
    llm = _FakeElengedoLLM(elenged=["datum_tol", "datum_ig", "napszak"])
    kaszkad = _kaszkad(llm)

    eredmeny = kaszkad.ertelmez(
        "mégis mindegy, mikor",
        most=_MOST,
        kontextus=ErtelmezesKontextus(megorzott_parameterek=dict(_KONTEKTUS_NAPSZAKKAL)),
    )

    assert kaszkad.utolso_reteg == "llm"
    assert eredmeny["parameterek"]["napszak"] == "barmikor", "a szűk napszak elengedve"
    assert eredmeny["parameterek"]["bolt_id"] == "ugyifogyi", "a bolt megmaradt"


def test_kaszkad_elengedes_a_boltot_is_el_tudja_engedni():
    """Kulcsszólista NÉLKÜL kezeli a "bármelyik másik boltban" típusú
    mondatot — a modell dönt, zárt (mezőnév) kimenettel."""
    llm = _FakeElengedoLLM(elenged=["bolt_id"])
    kaszkad = _kaszkad(llm)

    eredmeny = kaszkad.ertelmez(
        "és máshol?",
        most=_MOST,
        kontextus=ErtelmezesKontextus(megorzott_parameterek=dict(_KONTEKTUS_NAPSZAKKAL)),
    )

    assert kaszkad.utolso_reteg == "llm"
    assert eredmeny["eszkoz"] == "visszakerdez"
    assert eredmeny["parameterek"]["hianyzo_mezo"] == "bolt_id"


def test_kaszkad_elengedes_ures_listanal_marad_a_szabaly_alapu():
    llm = _FakeElengedoLLM(elenged=[])
    kaszkad = _kaszkad(llm)
    kontextus = ErtelmezesKontextus(megorzott_parameterek=dict(_KONTEKTUS_NAPSZAKKAL))

    eredmeny = kaszkad.ertelmez("és akkor?", most=_MOST, kontextus=kontextus)
    kozvetlen = SzabalyAlapuErtelmezo().ertelmez("és akkor?", most=_MOST, kontextus=kontextus)

    assert eredmeny == kozvetlen
    assert kaszkad.utolso_reteg == "szabaly"


def test_kaszkad_elengedes_kontextus_nelkul_meg_sem_kerdezi_a_modellt():
    llm = _FakeElengedoLLM(elenged=["bolt_id"])
    kaszkad = _kaszkad(llm)

    kaszkad.ertelmez("Petárdázni szeretnék kedden.", most=_MOST, kontextus=ErtelmezesKontextus())

    assert llm.elemzes_hivasok == []
    assert kaszkad.utolso_reteg == "szabaly"


def test_kaszkad_elengedes_sikertelen_elemzesnel_marad_a_szabaly_alapu():
    llm = _FakeElengedoLLM(elenged=None)  # a modell nem válaszolt
    kaszkad = _kaszkad(llm)
    kontextus = ErtelmezesKontextus(megorzott_parameterek=dict(_KONTEKTUS_NAPSZAKKAL))

    eredmeny = kaszkad.ertelmez("és akkor?", most=_MOST, kontextus=kontextus)
    kozvetlen = SzabalyAlapuErtelmezo().ertelmez("és akkor?", most=_MOST, kontextus=kontextus)

    assert eredmeny == kozvetlen
    assert kaszkad.utolso_reteg == "szabaly"


def test_kaszkad_elengedes_a_datumot_tovabbra_is_a_parser_adja():
    """A modell csak mezőneveket ad — az ÚJ dátumot a determinisztikus
    parser állítja elő a mondatból, nem a modell."""
    llm = _FakeElengedoLLM(elenged=["datum_tol", "datum_ig", "napszak"])
    kaszkad = _kaszkad(llm)

    eredmeny = kaszkad.ertelmez(
        "inkább jövő héten",
        most=_MOST,
        kontextus=ErtelmezesKontextus(megorzott_parameterek=dict(_KONTEKTUS_NAPSZAKKAL)),
    )

    assert eredmeny["parameterek"]["datum_tol"] == "2026-08-24T00:00:00Z"
    assert eredmeny["parameterek"]["datum_ig"] == "2026-08-30T23:59:59Z"

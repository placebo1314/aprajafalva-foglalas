"""Egységtesztek az orchestratorra (`assistant/orchestrator.py`, ADR-007):
állapotátmenetek — részleges adat → zárt kérdés → megőrzés → foglalás.

Az `Ertelmezo`-t egy szkriptelt dupla helyettesíti (`_ScriptedErtelmezo`)
— az orchestrator állapotgépét az értelmezőtől FÜGGETLENÜL teszteljük,
ahogy a determinisztikus vagy egy jövőbeli LLM-es implementáció mögé is
ugyanígy illeszkedne (`assistant/interpreter/__init__.py::Ertelmezo`)."""

from __future__ import annotations

import time

from assistant import allapotgep
from assistant.interpreter import ErtelmezesKontextus
from assistant.interpreter.rule_based import SzabalyAlapuErtelmezo
from assistant.orchestrator import (
    BizonyossagKuszobok,
    Orchestrator,
    kovetkezo_kontextus,
)
from assistant.tools.katalogus import BOLT_SLUGOK, MINDEGY
from core.repo import foglalas_repo, migracio, muszak_repo, torzsadat_repo
from core.slot import generator
from core.slot.blokk import FixedBlock

_MOST = "2026-08-17T09:00:00Z"


class _ScriptedErtelmezo:
    """A megadott válaszokat adja vissza sorban — minden híváshoz
    naplózza a kapott kontextust is, hogy a megőrzés tesztelhető legyen."""

    def __init__(self, valaszok: list[dict]):
        self._valaszok = list(valaszok)
        self.hivasok: list[tuple[str, dict]] = []
        self.utolso_kontextus: ErtelmezesKontextus | None = None

    def ertelmez(self, mondat: str, *, most: str, kontextus: ErtelmezesKontextus) -> dict:
        self.hivasok.append((mondat, dict(kontextus.megorzott_parameterek)))
        # A TELJES kontextus is megmarad — az állapotsor (ADR-028)
        # ellenőrzéséhez, ami nem a megőrzött paraméterek között utazik.
        self.utolso_kontextus = kontextus
        return self._valaszok.pop(0)


def _conn(tmp_path):
    conn = migracio.conn_nyitas(str(tmp_path / "teszt.db"))
    migracio.migral(conn)
    return conn


def _seed(conn) -> dict:
    org_id = torzsadat_repo.org_create(conn, name="Aprajafalva", timezone="Europe/Budapest")
    shop_id = torzsadat_repo.shop_create(conn, org_id=org_id, name="Ügyifogyi")
    counter_id = torzsadat_repo.counter_create(conn, org_id=org_id, shop_id=shop_id, name="Pult 1")
    employee_id = torzsadat_repo.employee_create(
        conn, org_id=org_id, shop_id=shop_id, name="Durranó"
    )
    service_id = torzsadat_repo.service_create(
        conn, org_id=org_id, shop_id=shop_id, name="petárda", alap_duration_minute=5
    )
    shift_id = muszak_repo.shift_create(
        conn,
        org_id=org_id,
        shop_id=shop_id,
        counter_id=counter_id,
        employee_id=employee_id,
        service_id=service_id,
        start="2026-08-18T06:00:00Z",
        end="2026-08-18T07:00:00Z",
        duration_minute=15,
        buffer_after_minute=0,
        min_grid_minute=15,
        bookable_ratio=1.0,
        block_rule={"szunetek": []},
    )
    shift = muszak_repo.shift_load(conn, shift_id)
    result = generator.generate(shift, FixedBlock())
    muszak_repo.blocks_slots_save(
        conn, shift_id=shift_id, org_id=org_id, blocks=result.blocks, slots=result.slots
    )
    return {"org_id": org_id, "shop_id": shop_id}


# --- gatekeeper / visszakérdezés ------------------------------------


def test_fordulo_nincs_elutasitas(tmp_path):
    conn = _conn(tmp_path)
    _seed(conn)
    ertelmezo = _ScriptedErtelmezo([{"eszkoz": "nincs", "parameterek": {}}])
    orch = Orchestrator(conn, ertelmezo, org_id="bármi")

    valasz = orch.fordulo("session-1", "Milyen idő lesz holnap?", _MOST)

    assert valasz == {
        "tipus": "elutasitas",
        "uzenet_kulcs": "nem_foglalasi_kerdes",
        "kapuor_ok": None,
    }


def test_fordulo_nincs_elutasitas_kapuor_okkal(tmp_path):
    """ADR-020: a kapuőr `ok`-kulcsa KONKRÉT elhárító mondatot választ.

    Az "ez nem foglalással kapcsolatos" mondat egy értelmezhetetlen
    bemenetre ("?????") értelmetlen lenne — a vásárló nem kérdezett
    rosszat, egyáltalán nem kérdezett. A leképezés zárt
    (`_ELUTASITAS_UZENET`); ismeretlen okra az általános mondat megy."""
    conn = _conn(tmp_path)
    _seed(conn)
    ertelmezo = _ScriptedErtelmezo(
        [
            {"eszkoz": "nincs", "parameterek": {}, "kapuor_ok": "ertelmezhetetlen"},
            {"eszkoz": "nincs", "parameterek": {}, "kapuor_ok": "ar"},
            {"eszkoz": "nincs", "parameterek": {}, "kapuor_ok": "politika"},
        ]
    )
    orch = Orchestrator(conn, ertelmezo, org_id="bármi")

    assert orch.fordulo("s", "?????", _MOST)["uzenet_kulcs"] == "ertelmezhetetlen_bemenet"
    assert orch.fordulo("s", "Mennyibe kerül?", _MOST)["uzenet_kulcs"] == "ar_nem_adhato"
    # Ismeretlen (nem leképezett) ok → az általános elhárítás.
    assert orch.fordulo("s", "Kire szavazzak?", _MOST)["uzenet_kulcs"] == "nem_foglalasi_kerdes"


def test_fordulo_utolso_ertelmezes_a_nyers_kimenetet_orzi(tmp_path):
    """`utolso_ertelmezes` a nyers {eszkoz, parameterek} kimenet —
    megfigyelhetőséghez (pl. ui/vasarlo.py próba-naplózása), nem a
    válasz része."""
    conn = _conn(tmp_path)
    _seed(conn)
    nyers = {"eszkoz": "nincs", "parameterek": {}}
    ertelmezo = _ScriptedErtelmezo([nyers])
    orch = Orchestrator(conn, ertelmezo, org_id="bármi")

    assert orch.utolso_ertelmezes is None
    orch.fordulo("session-1", "Milyen idő lesz holnap?", _MOST)
    assert orch.utolso_ertelmezes == nyers


def test_fordulo_visszakerdez_nyitott_elso_korben(tmp_path):
    conn = _conn(tmp_path)
    _seed(conn)
    ertelmezo = _ScriptedErtelmezo(
        [
            {
                "eszkoz": "visszakerdez",
                "parameterek": {"hianyzo_mezo": "bolt_id", "varhato_kerdes_tipusa": "nyitott"},
            }
        ]
    )
    orch = Orchestrator(conn, ertelmezo, org_id="bármi")

    valasz = orch.fordulo("session-1", "hát én csak azt szeretném hogy mikor lehet menni", _MOST)

    assert valasz["tipus"] == "visszakerdezes"
    assert valasz["kerdes_tipusa"] == "nyitott"
    assert valasz["hianyzo_mezo"] == "bolt_id"


def test_fordulo_ket_sikertelen_utan_zart_kerdesre_valt(tmp_path):
    conn = _conn(tmp_path)
    _seed(conn)
    ertelmezo = _ScriptedErtelmezo(
        [
            {
                "eszkoz": "visszakerdez",
                "parameterek": {"hianyzo_mezo": "bolt_id", "varhato_kerdes_tipusa": "nyitott"},
            },
            # A második forduló az értelmező szerint MÉG mindig "nyitott"
            # lenne — az orchestrator ennek ellenére zártra kényszeríti,
            # mert ez már a 2. sikertelen próbálkozás egymás után.
            {
                "eszkoz": "visszakerdez",
                "parameterek": {"hianyzo_mezo": "bolt_id", "varhato_kerdes_tipusa": "nyitott"},
            },
        ]
    )
    orch = Orchestrator(conn, ertelmezo, org_id="bármi")

    orch.fordulo("session-1", "mikor lehet menni", _MOST)
    masodik = orch.fordulo("session-1", "hát nem is tudom", _MOST)

    assert masodik["kerdes_tipusa"] == "zart"


def test_fordulo_megorzi_a_parametereket_visszakerdezes_utan(tmp_path):
    """A golden set legfontosabb elve (toredekes-03): a visszakérdezés
    után a MÁR ismert adatot (itt: datum_tol/datum_ig/napszak) nem
    szabad újra megkérdezni — a következő értelmező-hívás kontextusában
    meg kell jelennie."""
    conn = _conn(tmp_path)
    _seed(conn)
    ertelmezo = _ScriptedErtelmezo(
        [
            {
                "eszkoz": "visszakerdez",
                "parameterek": {
                    "hianyzo_mezo": "bolt_id",
                    "varhato_kerdes_tipusa": "zart",
                    "valaszthato_ertekek": ["szundi", "ugyifogyi", "torpilla"],
                    "datum_tol": "2026-08-18T00:00:00Z",
                    "datum_ig": "2026-08-18T11:59:59Z",
                    "napszak": "delelott",
                },
            },
            {"eszkoz": "nincs", "parameterek": {}},
        ]
    )
    orch = Orchestrator(conn, ertelmezo, org_id="bármi")

    orch.fordulo("session-1", "időpont. holnap. délelőtt.", _MOST)
    orch.fordulo("session-1", "ugyifogyi", _MOST)

    masodik_hivas_mondat, masodik_hivas_kontextus = ertelmezo.hivasok[1]
    assert masodik_hivas_kontextus == {
        "datum_tol": "2026-08-18T00:00:00Z",
        "datum_ig": "2026-08-18T11:59:59Z",
        "napszak": "delelott",
    }
    # Az irányítási mezők (hianyzo_mezo, varhato_kerdes_tipusa,
    # valaszthato_ertekek) NEM kerülnek a megőrzött paraméterek közé.
    assert "hianyzo_mezo" not in masodik_hivas_kontextus
    assert "valaszthato_ertekek" not in masodik_hivas_kontextus


# --- keresés → választás → megerősítés → foglalás -----------------


def test_teljes_ut_kereses_valasztas_megerosites_foglalas(tmp_path):
    conn = _conn(tmp_path)
    ctx = _seed(conn)
    ertelmezo = _ScriptedErtelmezo(
        [
            {
                "eszkoz": "szabad_idopontok",
                "parameterek": {
                    "bolt_id": "ugyifogyi",
                    "datum_tol": "2026-08-18T00:00:00Z",
                    "datum_ig": "2026-08-18T23:59:59Z",
                },
            }
        ]
    )
    orch = Orchestrator(conn, ertelmezo, org_id=ctx["org_id"])

    ajanlat = orch.fordulo("session-1", "petárdázni szeretnék kedden", _MOST)
    assert ajanlat["tipus"] == "ajanlat"
    assert ajanlat["jeloltek"]
    assert ajanlat["felismert_ablak"] == {
        "bolt_id": "ugyifogyi",
        "datum_tol": "2026-08-18T00:00:00Z",
        "datum_ig": "2026-08-18T23:59:59Z",
    }
    valasztott = ajanlat["jeloltek"][0]["slot_id"]

    megerosites_kerve = orch.valaszt("session-1", valasztott)
    assert megerosites_kerve == {"tipus": "megerositest_ker", "slot_id": valasztott}

    vegleges = orch.megerosit("session-1", "a" * 64)
    assert vegleges["tipus"] == "visszaigazolas"
    assert len(vegleges["foglalasi_kod"]) == 8

    # A slot ténylegesen foglalt, nem csak holdolt.
    assert foglalas_repo.slot_free(conn, valasztott) is False


def test_kereses_strukturaltan_koppintos_ut_ugyanoda_vezet(tmp_path):
    """A koppintós út (`ui/vasarlo.py`) nem az Ertelmezo-n megy át —
    ugyanahhoz az állapothoz és eszközhöz kell vezetnie, hogy a
    választás/megerősítés onnantól azonos legyen a szöveges úttal."""
    conn = _conn(tmp_path)
    ctx = _seed(conn)
    ertelmezo = _ScriptedErtelmezo([])  # nem hívódik — a strukturált út megkerüli
    orch = Orchestrator(conn, ertelmezo, org_id=ctx["org_id"])

    ajanlat = orch.kereses_strukturaltan(
        "session-1",
        {
            "bolt_id": "ugyifogyi",
            "datum_tol": "2026-08-18T00:00:00Z",
            "datum_ig": "2026-08-18T23:59:59Z",
        },
    )
    assert ajanlat["tipus"] == "ajanlat"
    assert ajanlat["jeloltek"]
    assert ertelmezo.hivasok == []

    valasztott = ajanlat["jeloltek"][0]["slot_id"]
    megerosites_kerve = orch.valaszt("session-1", valasztott)
    assert megerosites_kerve == {"tipus": "megerositest_ker", "slot_id": valasztott}
    vegleges = orch.megerosit("session-1", "a" * 64)
    assert vegleges["tipus"] == "visszaigazolas"


def test_valaszt_felszabaditja_a_nem_valasztott_jeloltek_holdjait(tmp_path):
    conn = _conn(tmp_path)
    ctx = _seed(conn)
    ertelmezo = _ScriptedErtelmezo(
        [
            {
                "eszkoz": "szabad_idopontok",
                "parameterek": {
                    "bolt_id": "ugyifogyi",
                    "datum_tol": "2026-08-18T00:00:00Z",
                    "datum_ig": "2026-08-18T23:59:59Z",
                },
            }
        ]
    )
    orch = Orchestrator(conn, ertelmezo, org_id=ctx["org_id"])
    ajanlat = orch.fordulo("session-1", "petárdázni szeretnék kedden", _MOST)
    jeloltek = [j["slot_id"] for j in ajanlat["jeloltek"]]
    assert len(jeloltek) >= 2, "a teszthez legalább két jelölt kell"

    orch.valaszt("session-1", jeloltek[0])

    for masik in jeloltek[1:]:
        assert foglalas_repo.slot_free(conn, masik) is True


def test_valaszt_ismeretlen_jelolt_hiba(tmp_path):
    conn = _conn(tmp_path)
    _seed(conn)
    ertelmezo = _ScriptedErtelmezo([])
    orch = Orchestrator(conn, ertelmezo, org_id="bármi")

    valasz = orch.valaszt("session-1", "nemletezo-slot")

    assert valasz == {"tipus": "hiba", "uzenet_kulcs": "nem_ajanlott_jelolt"}


def test_megerosit_valasztas_nelkul_hiba(tmp_path):
    conn = _conn(tmp_path)
    _seed(conn)
    ertelmezo = _ScriptedErtelmezo([])
    orch = Orchestrator(conn, ertelmezo, org_id="bármi")

    valasz = orch.megerosit("session-1", "a" * 64)

    assert valasz == {"tipus": "hiba", "uzenet_kulcs": "nincs_folyamatban_levo_valasztas"}


def test_elvet_felszabaditja_a_holdot(tmp_path):
    conn = _conn(tmp_path)
    ctx = _seed(conn)
    ertelmezo = _ScriptedErtelmezo(
        [
            {
                "eszkoz": "szabad_idopontok",
                "parameterek": {
                    "bolt_id": "ugyifogyi",
                    "datum_tol": "2026-08-18T00:00:00Z",
                    "datum_ig": "2026-08-18T23:59:59Z",
                },
            }
        ]
    )
    orch = Orchestrator(conn, ertelmezo, org_id=ctx["org_id"])
    ajanlat = orch.fordulo("session-1", "petárdázni szeretnék kedden", _MOST)
    valasztott = ajanlat["jeloltek"][0]["slot_id"]
    orch.valaszt("session-1", valasztott)

    valasz = orch.elvet("session-1")

    assert valasz == {"tipus": "elvetve"}
    assert foglalas_repo.slot_free(conn, valasztott) is True


# --- egyszerű eszközök közvetlen elérése fordulón keresztül --------


def test_fordulo_bolt_info_kozvetlenul_hivja_az_eszkozt(tmp_path):
    conn = _conn(tmp_path)
    ctx = _seed(conn)
    ertelmezo = _ScriptedErtelmezo(
        [{"eszkoz": "bolt_info", "parameterek": {"bolt_id": "ugyifogyi", "mit": "cim"}}]
    )
    orch = Orchestrator(conn, ertelmezo, org_id=ctx["org_id"])

    valasz = orch.fordulo("session-1", "Hol van az Ügyifogyi?", _MOST)

    assert valasz["sikeres"] is True
    assert "cim" in valasz


def test_fordulo_foglalas_lemondas_kozvetlenul_hivja_az_eszkozt(tmp_path):
    conn = _conn(tmp_path)
    _seed(conn)
    ertelmezo = _ScriptedErtelmezo(
        [{"eszkoz": "foglalas_lemondas", "parameterek": {"foglalasi_kod": "NEMLETEZO"}}]
    )
    orch = Orchestrator(conn, ertelmezo, org_id="bármi")

    valasz = orch.fordulo("session-1", "Le szeretném mondani, a kód NEMLETEZO.", _MOST)

    assert valasz["sikeres"] is False
    assert valasz["ok"] == "ervenytelen_kod"


# --- szándék rétegzés: kemény/puha (roadmap M4) ---------------------


def test_kovetkezo_kontextus_visszakerdez_megorzi_a_kinyert_mezoket():
    """Az irányítási mezők (hianyzo_mezo, varhato_kerdes_tipusa,
    valaszthato_ertekek) NEM kerülnek a kontextusba — csak a ténylegesen
    kinyert adat."""
    uj = kovetkezo_kontextus(
        {},
        {
            "eszkoz": "visszakerdez",
            "parameterek": {
                "hianyzo_mezo": "bolt_id",
                "varhato_kerdes_tipusa": "zart",
                "valaszthato_ertekek": ["szundi"],
                "datum_tol": "2026-08-18T00:00:00Z",
                "napszak": "delelott",
            },
        },
    )
    assert uj == {"datum_tol": "2026-08-18T00:00:00Z", "napszak": "delelott"}


def test_kovetkezo_kontextus_szabad_idopontok_csak_a_kemeny_reszt_orzi_meg():
    """Egy LEFUTOTT keresés (`szabad_idopontok`) után csak a kemény rész
    (bolt, szolgáltatás) marad — a puha rész (dátum/napszak/session_id)
    nem, azt egy alkudozó fordulónak frissen kell eldöntenie."""
    uj = kovetkezo_kontextus(
        {},
        {
            "eszkoz": "szabad_idopontok",
            "parameterek": {
                "bolt_id": "ugyifogyi",
                "szolgaltatas_id": "nagy_petarda",
                "datum_tol": "2026-08-18T00:00:00Z",
                "datum_ig": "2026-08-18T23:59:59Z",
                "napszak": "delelott",
                "session_id": "session-1",
            },
        },
    )
    assert uj == {"bolt_id": "ugyifogyi", "szolgaltatas_id": "nagy_petarda"}


def test_kovetkezo_kontextus_egyeb_eszkoznel_valtozatlan():
    elozo = {"bolt_id": "ugyifogyi"}
    uj = kovetkezo_kontextus(elozo, {"eszkoz": "bolt_info", "parameterek": {"bolt_id": "szundi"}})
    assert uj == elozo
    assert uj is not elozo  # másolat, nem ugyanaz az objektum


def test_fordulo_sikeres_ajanlat_utan_csak_a_kemeny_resz_marad_a_kontextusban(tmp_path):
    conn = _conn(tmp_path)
    ctx = _seed(conn)
    ertelmezo = _ScriptedErtelmezo(
        [
            {
                "eszkoz": "szabad_idopontok",
                "parameterek": {
                    "bolt_id": "ugyifogyi",
                    "datum_tol": "2026-08-18T00:00:00Z",
                    "datum_ig": "2026-08-18T23:59:59Z",
                    "napszak": "delelott",
                },
            },
            {"eszkoz": "nincs", "parameterek": {}},
        ]
    )
    orch = Orchestrator(conn, ertelmezo, org_id=ctx["org_id"])

    ajanlat = orch.fordulo("session-1", "petárdázni szeretnék kedden délelőtt", _MOST)
    assert ajanlat["tipus"] == "ajanlat"

    orch.fordulo("session-1", "és jövő héten péntek délelőtt?", _MOST)

    masodik_kontextus = ertelmezo.hivasok[1][1]
    assert masodik_kontextus == {"bolt_id": "ugyifogyi"}


def test_fordulo_sikertelen_keresés_utan_is_megmarad_a_kemeny_resz(tmp_path):
    """Elutasítás után alternatíva (3. pont, 6. eset): egy SIKERTELEN
    keresés (nincs szabad hely) után is megmarad a kemény rész — a
    következő forduló nem veszíti el a boltot."""
    conn = _conn(tmp_path)
    ctx = _seed(conn)
    ertelmezo = _ScriptedErtelmezo(
        [
            {
                "eszkoz": "szabad_idopontok",
                "parameterek": {
                    "bolt_id": "ugyifogyi",
                    "datum_tol": "2099-01-01T00:00:00Z",
                    "datum_ig": "2099-01-02T00:00:00Z",
                },
            },
            {"eszkoz": "nincs", "parameterek": {}},
        ]
    )
    orch = Orchestrator(conn, ertelmezo, org_id=ctx["org_id"])

    elutasitas = orch.fordulo("session-1", "petárdázni szeretnék jövőre", _MOST)
    assert elutasitas["tipus"] == "eszkoz_hiba"
    assert elutasitas["sikeres"] is False

    orch.fordulo("session-1", "van esetleg más napon?", _MOST)

    masodik_kontextus = ertelmezo.hivasok[1][1]
    assert masodik_kontextus == {"bolt_id": "ugyifogyi"}


def test_fordulo_eszkoz_hiba_tartalmazza_az_alternativ_dimenziot(tmp_path):
    """A `szabad_idopontok` `alternativ_dimenzio` mezője (assistant/
    tools/szabad_idopontok.py) változatlanul átfut az orchestratoron —
    az elutasítás megmondja, MELYIK dimenzióban van alternatíva, nem
    csak azt, hogy nincs hely."""
    conn = _conn(tmp_path)
    ctx = _seed(conn)
    ertelmezo = _ScriptedErtelmezo(
        [
            {
                "eszkoz": "szabad_idopontok",
                "parameterek": {
                    "bolt_id": "ugyifogyi",
                    "datum_tol": "2026-08-18T00:00:00Z",
                    "datum_ig": "2026-08-18T23:59:59Z",
                    "napszak": "este",
                },
            }
        ]
    )
    orch = Orchestrator(conn, ertelmezo, org_id=ctx["org_id"])

    valasz = orch.fordulo("session-1", "petárdázni szeretnék kedden este", _MOST)

    assert valasz["tipus"] == "eszkoz_hiba"
    assert valasz["alternativ_dimenzio"] == "napszak"


def test_alternativa_kereses_a_felajanlott_dimenzio_menten_talal(tmp_path):
    """A felajánlott alternatíva elfogadása ténylegesen ajánlatot ad —
    a vásárlónak nem kell újra elmondania, mit keresett. A `_seed`
    slotjai délelőttiek (helyi 08:00–09:00), ezért az "este" kérés
    üres, a "napszak" tágítás viszont megtalálja őket."""
    conn = _conn(tmp_path)
    ctx = _seed(conn)
    ertelmezo = _ScriptedErtelmezo(
        [
            {
                "eszkoz": "szabad_idopontok",
                "parameterek": {
                    "bolt_id": "ugyifogyi",
                    "datum_tol": "2026-08-18T00:00:00Z",
                    "datum_ig": "2026-08-18T23:59:59Z",
                    "napszak": "este",
                },
            }
        ]
    )
    orch = Orchestrator(conn, ertelmezo, org_id=ctx["org_id"])
    elutasitas = orch.fordulo("session-1", "petárdázni szeretnék kedden este", _MOST)
    assert elutasitas["alternativ_dimenzio"] == "napszak"

    ajanlat = orch.alternativa_kereses("session-1", "napszak")

    assert ajanlat["tipus"] == "ajanlat"
    assert ajanlat["jeloltek"]
    # A bolt és a nap változatlan — csak a napszak-kötöttség engedett el.
    assert ajanlat["felismert_ablak"]["bolt_id"] == "ugyifogyi"
    assert ajanlat["felismert_ablak"]["napszak"] == "barmikor"
    assert ajanlat["felismert_ablak"]["datum_tol"] == "2026-08-18T00:00:00Z"


def test_alternativa_kereses_korabbi_kereses_nelkul_hibat_ad(tmp_path):
    conn = _conn(tmp_path)
    ctx = _seed(conn)
    orch = Orchestrator(conn, _ScriptedErtelmezo([]), org_id=ctx["org_id"])

    valasz = orch.alternativa_kereses("uj-session", "napszak")

    assert valasz == {"tipus": "hiba", "uzenet_kulcs": "nincs_korabbi_kereses"}


def test_alternativa_kereses_ertelmezhetetlen_dimenziot_elutasit(tmp_path):
    """A "napszak" tágítás nem értelmezhető, ha a kérés eleve
    "barmikor" volt — ilyenkor a `tagitott_ablak` None-t ad, és az
    orchestrator sem futtat félrevezető keresést."""
    conn = _conn(tmp_path)
    ctx = _seed(conn)
    ertelmezo = _ScriptedErtelmezo(
        [
            {
                "eszkoz": "szabad_idopontok",
                "parameterek": {
                    "bolt_id": "ugyifogyi",
                    "datum_tol": "2026-08-19T00:00:00Z",
                    "datum_ig": "2026-08-19T23:59:59Z",
                    "napszak": "barmikor",
                },
            }
        ]
    )
    orch = Orchestrator(conn, ertelmezo, org_id=ctx["org_id"])
    orch.fordulo("session-1", "petárdázni szeretnék szerdán", _MOST)

    valasz = orch.alternativa_kereses("session-1", "napszak")

    assert valasz == {"tipus": "hiba", "uzenet_kulcs": "ervenytelen_alternativa"}


def test_fordulo_valodi_ertelmezovel_alkudozas_szukites_megorzi_a_boltot(tmp_path):
    """Végponttól végpontig, VALÓDI értelmezővel (nem szkriptelt) — a
    golden set "szűkítés" esetének (tests/golden/nyelvi_alap.yaml,
    alkudozas-01-szukites) orchestrator-szintű megfelelője: a bolt nem
    hangzik el újra a 2. fordulóban, mégis megjelenik a felismert
    ablakban, a dátum pedig helyesen szűkül jövő hét péntek délelőttre."""
    conn = _conn(tmp_path)
    ctx = _seed(conn)
    orch = Orchestrator(conn, SzabalyAlapuErtelmezo(), org_id=ctx["org_id"])

    orch.fordulo("session-1", "Szeretnék petárdázni valamikor a héten.", _MOST)
    masodik = orch.fordulo("session-1", "és jövő héten péntek délelőtt?", _MOST)

    assert masodik["felismert_ablak"] == {
        "bolt_id": "ugyifogyi",
        "datum_tol": "2026-08-28T00:00:00Z",
        "datum_ig": "2026-08-28T11:59:59Z",
        "napszak": "delelott",
    }


# --- foglalas_lekerdezes: enumeráció-védelem és rate limiting -------
# (blueprint 8. szakasz, adatvedelem skill — az orchestrator felelőssége,
# nem az eszközé.)


def _foglalj(conn, org_id: str, vasarlo_kulcs_hash: str) -> None:
    """Végigviszi a teljes foglalási utat, hogy legyen VALÓDI, meglévő
    azonosító a `foglalas_lekerdezes` teszteknek."""
    ertelmezo = _ScriptedErtelmezo(
        [
            {
                "eszkoz": "szabad_idopontok",
                "parameterek": {
                    "bolt_id": "ugyifogyi",
                    "datum_tol": "2026-08-18T00:00:00Z",
                    "datum_ig": "2026-08-18T23:59:59Z",
                },
            }
        ]
    )
    orch = Orchestrator(conn, ertelmezo, org_id=org_id)
    ajanlat = orch.fordulo("foglalo-session", "petárdázni szeretnék kedden", _MOST)
    slot_id = ajanlat["jeloltek"][0]["slot_id"]
    orch.valaszt("foglalo-session", slot_id)
    orch.megerosit("foglalo-session", vasarlo_kulcs_hash)


def test_fordulo_foglalas_lekerdezes_azonos_valasz_letezo_es_nem_letezo_azonositora(tmp_path):
    conn = _conn(tmp_path)
    ctx = _seed(conn)
    letezo_hash = "a" * 64
    _foglalj(conn, ctx["org_id"], letezo_hash)

    ertelmezo = _ScriptedErtelmezo(
        [
            {"eszkoz": "foglalas_lekerdezes", "parameterek": {"vasarlo_kulcs_hash": letezo_hash}},
            {
                "eszkoz": "foglalas_lekerdezes",
                "parameterek": {"vasarlo_kulcs_hash": "b" * 64},
            },
        ]
    )
    orch = Orchestrator(conn, ertelmezo, org_id=ctx["org_id"])

    letezo_valasz = orch.fordulo("lekerdezo-1", "mik a foglalásaim?", _MOST)
    nemletezo_valasz = orch.fordulo("lekerdezo-2", "mik a foglalásaim?", _MOST)

    # A válasz ALAKJA azonos (sikeres, `foglalasok` lista) — csak a
    # tartalom tér el, nem a boríték.
    assert letezo_valasz.keys() == nemletezo_valasz.keys()
    assert letezo_valasz["sikeres"] is True
    assert nemletezo_valasz["sikeres"] is True
    assert letezo_valasz["foglalasok"]
    assert nemletezo_valasz["foglalasok"] == []


def test_fordulo_foglalas_lekerdezes_azonos_valaszido_letezo_es_nem_letezo_azonositora(tmp_path):

    conn = _conn(tmp_path)
    ctx = _seed(conn)
    letezo_hash = "a" * 64
    _foglalj(conn, ctx["org_id"], letezo_hash)

    ertelmezo = _ScriptedErtelmezo(
        [
            {"eszkoz": "foglalas_lekerdezes", "parameterek": {"vasarlo_kulcs_hash": letezo_hash}},
            {
                "eszkoz": "foglalas_lekerdezes",
                "parameterek": {"vasarlo_kulcs_hash": "b" * 64},
            },
        ]
    )
    orch = Orchestrator(conn, ertelmezo, org_id=ctx["org_id"])

    kezdet1 = time.monotonic()
    orch.fordulo("lekerdezo-1", "mik a foglalásaim?", _MOST)
    telt1 = time.monotonic() - kezdet1

    kezdet2 = time.monotonic()
    orch.fordulo("lekerdezo-2", "mik a foglalásaim?", _MOST)
    telt2 = time.monotonic() - kezdet2

    # Mindkettő eléri a válaszidő-padding küszöbét, és nem térnek el
    # érdemben egymástól — a valós lekérdezés (van/nincs találat) ideje
    # elenyésző a paddinghez képest, ez nyeli el a különbséget.
    assert telt1 >= 0.09
    assert telt2 >= 0.09
    assert abs(telt1 - telt2) < 0.05


def test_fordulo_foglalas_lekerdezes_rate_limit_session_szintu(tmp_path):
    conn = _conn(tmp_path)
    ctx = _seed(conn)
    hivas = {"eszkoz": "foglalas_lekerdezes", "parameterek": {"vasarlo_kulcs_hash": "c" * 64}}
    ertelmezo = _ScriptedErtelmezo([hivas] * 6)
    orch = Orchestrator(conn, ertelmezo, org_id=ctx["org_id"])

    for _ in range(5):
        valasz = orch.fordulo("session-1", "mik a foglalásaim?", _MOST)
        assert valasz.get("ok") != "rate_limit"

    hatodik = orch.fordulo("session-1", "mik a foglalásaim?", _MOST)
    assert hatodik == {"sikeres": False, "ok": "rate_limit", "uzenet_kulcs": "tul_sok_keres"}

    # A korlát SESSION-szintű, nem globális — egy másik session még mehet.
    ertelmezo.hivasok.clear()
    masik_ertelmezo = _ScriptedErtelmezo([hivas])
    masik_orch = Orchestrator(conn, masik_ertelmezo, org_id=ctx["org_id"])
    masik_valasz = masik_orch.fordulo("session-2", "mik a foglalásaim?", _MOST)
    assert masik_valasz.get("ok") != "rate_limit"


# --- ismétlésfigyelés (blueprint 7., "Négy technika") ----------------


def _visszakerdez_valasz(mezo: str = "bolt_id") -> dict:
    return {
        "eszkoz": "visszakerdez",
        "parameterek": {"hianyzo_mezo": mezo, "varhato_kerdes_tipusa": "zart"},
    }


def test_ismetles_a_MASODIK_azonos_valasz_helyett_mar_kiut(tmp_path):
    """KÉZI PRÓBA találata (2026-08-30). Korábban ugyanaz a mondat
    kétszer ment ki, és a stratégiaváltás csak a harmadik fordulóban
    jött. Aki elakadt, annak a második azonos válasz már nem
    információ — a válaszunk megismétlése ezen nem segít."""
    conn = _conn(tmp_path)
    _seed(conn)
    # Mindkét forduló UGYANAZT a zárt kérdést adná ugyanarra a mezőre.
    orch = Orchestrator(conn, _ScriptedErtelmezo([_visszakerdez_valasz()] * 2), org_id="bármi")

    elso = orch.fordulo("s1", "hova is menjek", _MOST)
    masodik = orch.fordulo("s1", "hát nem tudom", _MOST)

    assert elso["tipus"] == "visszakerdezes"
    assert masodik["tipus"] == "kiut"
    assert masodik["uzenet_kulcs"] == "ismetlodo_valasz_kiut"
    assert masodik["valaszthato_dimenziok"] == ["nap", "napszak", "legkorabbi"]


def test_ismetles_a_nyitottrol_zartra_valtas_NEM_ismetles(tmp_path):
    """A blueprint 7. eszkalációja (nyitott kérdés → két sikertelen
    értelmezés után ZÁRT kérdés) a képernyőn MÁS választ jelent: más a
    mondat, és megjelennek a gombok. Ezt nem szabad ismétlésnek
    számolni, különben a létra egy fokát ugornánk át."""
    conn = _conn(tmp_path)
    _seed(conn)
    nyitott = {
        "eszkoz": "visszakerdez",
        "parameterek": {"hianyzo_mezo": "bolt_id", "varhato_kerdes_tipusa": "nyitott"},
    }
    orch = Orchestrator(conn, _ScriptedErtelmezo([nyitott] * 3), org_id="bármi")

    elso = orch.fordulo("s1", "mikor lehet menni", _MOST)
    masodik = orch.fordulo("s1", "hát nem is tudom", _MOST)
    harmadik = orch.fordulo("s1", "nem tudom megmondani", _MOST)

    assert (elso["tipus"], elso["kerdes_tipusa"]) == ("visszakerdezes", "nyitott")
    assert (masodik["tipus"], masodik["kerdes_tipusa"]) == ("visszakerdezes", "zart")
    # …és csak a MÁSODIK zárt kérdés helyett jön a kiút.
    assert harmadik["tipus"] == "kiut"


def test_ismetles_kiutja_nem_ismetlodhet_emberhez_eszkalal(tmp_path):
    """A kézi próba a „körbe-körbe" mondatot is KÉTSZER látta. Minden
    kiadott kiút ugyanabba a számlálóba megy, tehát a második kiút —
    jöjjön bármelyik jelzőtől — már embert ajánl."""
    conn = _conn(tmp_path)
    _seed(conn)
    orch = Orchestrator(conn, _ScriptedErtelmezo([_visszakerdez_valasz()] * 4), org_id="bármi")

    valaszok = [orch.fordulo("s1", f"hát nem tudom {i}", _MOST) for i in range(4)]

    kiutak = [v for v in valaszok if v["tipus"] == "kiut"]
    assert len(kiutak) >= 2
    assert kiutak[0]["emberhez"] is False
    assert kiutak[1]["emberhez"] is True
    assert kiutak[1]["uzenet_kulcs"] == "emberhez_iranyitas"


def test_ismetles_mas_valaszfajta_nullazza_a_szamlalot(tmp_path):
    """Ha a beszélgetés elmozdul (másik válaszfajta jön), a számláló
    nullázódik — nem büntetjük a vásárlót egy korábbi szakaszért."""
    conn = _conn(tmp_path)
    _seed(conn)
    ertelmezo = _ScriptedErtelmezo(
        [
            _visszakerdez_valasz(),
            {"eszkoz": "nincs", "parameterek": {}},  # elmozdulás
            _visszakerdez_valasz(),
        ]
    )
    # A frusztráció-figyelő szándékosan kikapcsolva: ez a teszt az
    # ISMÉTLÉS-számlálót méri, és a sok eredménytelen forduló különben a
    # frusztráció-kiutat indítaná el (l. saját tesztjeit).
    orch = Orchestrator(conn, ertelmezo, org_id="bármi", frusztracio_kuszob=999)

    orch.fordulo("s1", "a", _MOST)
    orch.fordulo("s1", "milyen idő lesz?", _MOST)
    harmadik = orch.fordulo("s1", "c", _MOST)

    assert harmadik["tipus"] == "visszakerdezes", "a számlálónak nullázódnia kellett"


def test_ismetles_kulon_mezore_kulon_szamlal(tmp_path):
    """A visszakérdezés azonossága a HIÁNYZÓ MEZŐN múlik — más mezőt
    kérdezni előrelépés, nem ismétlés."""
    conn = _conn(tmp_path)
    _seed(conn)
    ertelmezo = _ScriptedErtelmezo(
        [
            _visszakerdez_valasz("bolt_id"),
            _visszakerdez_valasz("bolt_id"),
            _visszakerdez_valasz("foglalasi_kod"),
        ]
    )
    orch = Orchestrator(conn, ertelmezo, org_id="bármi")

    orch.fordulo("s1", "a", _MOST)
    orch.fordulo("s1", "b", _MOST)
    harmadik = orch.fordulo("s1", "c", _MOST)

    assert harmadik["tipus"] == "visszakerdezes"
    assert harmadik["hianyzo_mezo"] == "foglalasi_kod"


def test_ismetles_sessionok_kozott_fuggetlen(tmp_path):
    conn = _conn(tmp_path)
    _seed(conn)
    orch = Orchestrator(conn, _ScriptedErtelmezo([_visszakerdez_valasz()] * 3), org_id="bármi")

    orch.fordulo("s1", "a", _MOST)
    orch.fordulo("s1", "b", _MOST)
    masik_session = orch.fordulo("s2", "c", _MOST)

    assert masik_session["tipus"] == "visszakerdezes"


# --- bizonyossági küszöbök (blueprint 10., "Bizalmi jelzés") ---------


def test_bizonyossag_determinisztikus_ertelmezot_nem_erint(tmp_path):
    """A determinisztikus értelmező 1.0-t vagy None-t ad — egyik sem esik
    küszöb alá, tehát a küszöbrendszer bekapcsolása NEM változtat a
    determinisztikus viselkedésen."""
    conn = _conn(tmp_path)
    ctx = _seed(conn)
    orch = Orchestrator(conn, SzabalyAlapuErtelmezo(), org_id=ctx["org_id"])

    valasz = orch.fordulo("s1", "Petárdázni szeretnék kedden.", _MOST)

    assert valasz["tipus"] == "ajanlat"


def test_bizonyossag_alacsony_eszkoz_zart_kerdest_valt_ki(tmp_path):
    conn = _conn(tmp_path)
    ctx = _seed(conn)
    ertelmezo = _ScriptedErtelmezo(
        [
            {
                "eszkoz": "szabad_idopontok",
                "parameterek": {"bolt_id": "ugyifogyi"},
                "bizonyossag": {"eszkoz": 0.4},
            }
        ]
    )
    orch = Orchestrator(conn, ertelmezo, org_id=ctx["org_id"])

    valasz = orch.fordulo("s1", "bizonytalan mondat", _MOST)

    assert valasz["tipus"] == "visszakerdezes"
    assert valasz["kerdes_tipusa"] == "zart"
    assert valasz["ok"] == "bizonytalan_szandek"


def test_bizonyossag_kuszob_feletti_eszkoz_atmegy(tmp_path):
    conn = _conn(tmp_path)
    ctx = _seed(conn)
    ertelmezo = _ScriptedErtelmezo(
        [
            {
                "eszkoz": "szabad_idopontok",
                "parameterek": {
                    "bolt_id": "ugyifogyi",
                    "datum_tol": "2026-08-18T00:00:00Z",
                    "datum_ig": "2026-08-18T23:59:59Z",
                },
                "bizonyossag": {"eszkoz": 0.95, "bolt_id": 0.9, "datum": 0.9},
            }
        ]
    )
    orch = Orchestrator(conn, ertelmezo, org_id=ctx["org_id"])

    assert orch.fordulo("s1", "petárdázni kedden", _MOST)["tipus"] == "ajanlat"


def test_bizonyossag_alacsony_kritikus_mezo_arra_a_mezore_kerdez(tmp_path):
    conn = _conn(tmp_path)
    ctx = _seed(conn)
    ertelmezo = _ScriptedErtelmezo(
        [
            {
                "eszkoz": "szabad_idopontok",
                "parameterek": {"bolt_id": "ugyifogyi"},
                "bizonyossag": {"eszkoz": 0.95, "bolt_id": 0.3},
            }
        ]
    )
    orch = Orchestrator(conn, ertelmezo, org_id=ctx["org_id"])

    valasz = orch.fordulo("s1", "valami boltba", _MOST)

    assert valasz["tipus"] == "visszakerdezes"
    assert valasz["hianyzo_mezo"] == "bolt_id"
    assert valasz["ok"] == "bizonytalan_mezo"
    assert valasz["valaszthato_ertekek"] == sorted(BOLT_SLUGOK)


def test_bizonyossag_bizonytalan_napszak_nem_valt_ki_kerdest(tmp_path):
    """A napszak nem kritikus mező — az eszkoz-szerzodes skill szerint
    "mehet tovább, tág értelmezéssel"."""
    conn = _conn(tmp_path)
    ctx = _seed(conn)
    ertelmezo = _ScriptedErtelmezo(
        [
            {
                "eszkoz": "szabad_idopontok",
                "parameterek": {
                    "bolt_id": "ugyifogyi",
                    "datum_tol": "2026-08-18T00:00:00Z",
                    "datum_ig": "2026-08-18T23:59:59Z",
                },
                "bizonyossag": {"eszkoz": 0.95, "bolt_id": 0.9, "napszak": 0.1},
            }
        ]
    )
    orch = Orchestrator(conn, ertelmezo, org_id=ctx["org_id"])

    assert orch.fordulo("s1", "petárdázni kedden", _MOST)["tipus"] == "ajanlat"


def test_bizonyossag_none_sosem_esik_kuszob_ala(tmp_path):
    """A None jelentése "nem tudok nyilatkozni", nem "biztosan rossz" —
    ebből nem vonunk le következtetést."""
    conn = _conn(tmp_path)
    ctx = _seed(conn)
    ertelmezo = _ScriptedErtelmezo(
        [
            {
                "eszkoz": "szabad_idopontok",
                "parameterek": {
                    "bolt_id": "ugyifogyi",
                    "datum_tol": "2026-08-18T00:00:00Z",
                    "datum_ig": "2026-08-18T23:59:59Z",
                },
                "bizonyossag": {"eszkoz": None, "bolt_id": None, "datum": None},
            }
        ]
    )
    orch = Orchestrator(conn, ertelmezo, org_id=ctx["org_id"])

    assert orch.fordulo("s1", "petárdázni kedden", _MOST)["tipus"] == "ajanlat"


def test_bizonyossag_kozeli_szandekok_zart_kerdest_adnak(tmp_path):
    """ "Lemondani szeretné, vagy áthelyezni?" — ha két szándék közel van
    egymáshoz, nem választunk helyette."""
    conn = _conn(tmp_path)
    ctx = _seed(conn)
    ertelmezo = _ScriptedErtelmezo(
        [
            {
                "eszkoz": "foglalas_lemondas",
                "parameterek": {"foglalasi_kod": "X7K2M9QP"},
                "bizonyossag": {"eszkoz": 0.9},
                "szandek_jeloltek": [
                    {"eszkoz": "foglalas_lemondas", "bizonyossag": 0.48},
                    {"eszkoz": "foglalas_athelyezes", "bizonyossag": 0.44},
                ],
            }
        ]
    )
    orch = Orchestrator(conn, ertelmezo, org_id=ctx["org_id"])

    valasz = orch.fordulo("s1", "a péntekit inkább ne", _MOST)

    assert valasz["tipus"] == "visszakerdezes"
    assert valasz["ok"] == "kozeli_szandekok"
    assert set(valasz["valaszthato_ertekek"]) == {"foglalas_lemondas", "foglalas_athelyezes"}


def test_bizonyossag_tavoli_szandekok_nem_kerdeznek_vissza(tmp_path):
    conn = _conn(tmp_path)
    ctx = _seed(conn)
    ertelmezo = _ScriptedErtelmezo(
        [
            {
                "eszkoz": "foglalas_lemondas",
                "parameterek": {"foglalasi_kod": "NEMLETEZO"},
                "bizonyossag": {"eszkoz": 0.9},
                "szandek_jeloltek": [
                    {"eszkoz": "foglalas_lemondas", "bizonyossag": 0.9},
                    {"eszkoz": "foglalas_athelyezes", "bizonyossag": 0.05},
                ],
            }
        ]
    )
    orch = Orchestrator(conn, ertelmezo, org_id=ctx["org_id"])

    valasz = orch.fordulo("s1", "le szeretném mondani", _MOST)

    assert valasz.get("tipus") != "visszakerdezes"


def test_bizonyossag_kuszobok_konfiguralhatok(tmp_path):
    """Ugyanaz a 0.5-ös bizonyosság az alapértelmezett (0.7) küszöbnél
    visszakérdez, egy megengedőbb (0.3) küszöbnél átmegy."""
    conn = _conn(tmp_path)
    ctx = _seed(conn)

    def _ertelmezo():
        return _ScriptedErtelmezo(
            [
                {
                    "eszkoz": "szabad_idopontok",
                    "parameterek": {
                        "bolt_id": "ugyifogyi",
                        "datum_tol": "2026-08-18T00:00:00Z",
                        "datum_ig": "2026-08-18T23:59:59Z",
                    },
                    "bizonyossag": {"eszkoz": 0.5},
                }
            ]
        )

    szigoru = Orchestrator(conn, _ertelmezo(), org_id=ctx["org_id"])
    assert szigoru.fordulo("s1", "x", _MOST)["tipus"] == "visszakerdezes"

    megengedo = Orchestrator(
        conn, _ertelmezo(), org_id=ctx["org_id"], kuszobok=BizonyossagKuszobok(eszkoz=0.3)
    )
    assert megengedo.fordulo("s2", "x", _MOST)["tipus"] == "ajanlat"


# --- frusztráció-felismerés (blueprint: "legyen kiút emberhez") --------


def test_frusztracio_kiutat_ajanl_akkor_is_ha_mas_a_valasz(tmp_path):
    """Az `_ismetlest_figyel` csak a SAJÁT ismétlődésünket látja. Ha a
    rendszer minden fordulóban mást válaszol, de a vásárló mégsem jut
    előre, korábban semmi nem szólalt meg — most igen."""
    conn = _conn(tmp_path)
    _seed(conn)
    ertelmezo = _ScriptedErtelmezo(
        [
            _visszakerdez_valasz(mezo="bolt_id"),
            _visszakerdez_valasz(mezo="szolgaltatas_id"),
            {"eszkoz": "nincs", "parameterek": {}},
            _visszakerdez_valasz(mezo="foglalasi_kod"),
        ]
    )
    orch = Orchestrator(conn, ertelmezo, org_id="bármi")

    orch.fordulo("s1", "a", _MOST)
    orch.fordulo("s1", "b", _MOST)
    orch.fordulo("s1", "c", _MOST)
    negyedik = orch.fordulo("s1", "d", _MOST)

    assert negyedik["tipus"] == "kiut"
    assert negyedik["ok"] == "frusztracio"
    assert negyedik["emberhez"] is False


def test_frusztracio_masodik_kiutja_emberhez_iranyit(tmp_path):
    """A vásárló 8. igénye: ha a szűkítési javaslat sem segített, ne
    ugyanazt kínáljuk újra."""
    conn = _conn(tmp_path)
    _seed(conn)
    # Váltakozó hiányzó mező: így az ISMÉTLÉS-figyelő nem szólal meg
    # (más-más választ adunk), csak a frusztráció-figyelő.
    ertelmezo = _ScriptedErtelmezo(
        [_visszakerdez_valasz(mezo="bolt_id"), _visszakerdez_valasz(mezo="szolgaltatas_id")] * 6
    )
    orch = Orchestrator(conn, ertelmezo, org_id="bármi")

    kiutak = []
    for i in range(10):
        valasz = orch.fordulo("s1", f"nem értem {i}", _MOST)
        if valasz["tipus"] == "kiut" and valasz.get("ok") == "frusztracio":
            kiutak.append(valasz)

    assert len(kiutak) >= 2
    assert kiutak[0]["emberhez"] is False
    assert kiutak[1]["emberhez"] is True
    assert kiutak[1]["uzenet_kulcs"] == "emberhez_iranyitas"


def test_frusztracio_emberhez_iranyit_az_ISMETLES_kiutja_utan_is(tmp_path):
    """A FEJ NÉLKÜLI VÉGIGJÁTSZÁS találata (2026-08-26).

    A fenti teszt szándékosan VÁLTAKOZÓ hiányzó mezőt használ, hogy az
    ismétlésfigyelő ne szólaljon meg — csakhogy a valóságban épp a
    fordítottja történik: aki elakadt, ugyanazt a mondatot ismétli, a
    rendszer ugyanazt válaszolja, tehát az ismétlésfigyelő ad ki
    kiutat. A kiút pedig szándékosan nem számít „eredménytelen
    fordulónak", így a frusztráció-pontszám sosem érte el újra a
    küszöböt: **az emberhez irányítás a leggyakoribb elakadásban SOSEM
    szólalt meg.**

    A bemenet szó szerint a `docs/TESZTELES.md` 12. kézi próbája."""
    conn = _conn(tmp_path)
    _seed(conn)
    # UGYANAZ a válasz minden fordulóban — ettől szólal meg az
    # ismétlésfigyelő a harmadikra.
    ertelmezo = _ScriptedErtelmezo([_visszakerdez_valasz(mezo="bolt_id")] * 6)
    orch = Orchestrator(conn, ertelmezo, org_id="bármi")

    valaszok = [orch.fordulo("s1", "nem értem, mit kell csinálni", _MOST) for _ in range(4)]

    emberhez = [v for v in valaszok if v.get("emberhez")]
    assert emberhez, [v.get("uzenet_kulcs") for v in valaszok]
    assert emberhez[0]["uzenet_kulcs"] == "emberhez_iranyitas"
    # A kiút NEM ajánl újabb szűkítést, amikor embert ajánl.
    assert emberhez[0]["valaszthato_dimenziok"] == []


def test_frusztracio_sikeres_ajanlat_utan_nem_szolal_meg(tmp_path):
    """Egy sikeres ajánlat nullázza a számlálót — a beszélgetés jó
    irányba ment, a korábbi döccenőket nem hordozzuk tovább."""
    conn = _conn(tmp_path)
    adat = _seed(conn)
    ertelmezo = _ScriptedErtelmezo(
        [
            _visszakerdez_valasz(),
            _visszakerdez_valasz(),
            _visszakerdez_valasz(),
            {
                "eszkoz": "szabad_idopontok",
                "parameterek": {
                    "bolt_id": "ugyifogyi",
                    "datum_tol": "2026-08-18T00:00:00Z",
                    "datum_ig": "2026-08-18T23:59:59Z",
                },
            },
            _visszakerdez_valasz(),
        ]
    )
    orch = Orchestrator(conn, ertelmezo, org_id=adat["org_id"])

    for mondat in ("a", "b", "c"):
        orch.fordulo("s1", mondat, _MOST)
    negyedik = orch.fordulo("s1", "Ügyifogyiba mennék", _MOST)
    otodik = orch.fordulo("s1", "e", _MOST)

    assert negyedik["tipus"] == "ajanlat"
    assert otodik["tipus"] == "visszakerdezes", "a sikeres ajánlatnak nulláznia kellett"


# --- sorszámos hivatkozás (assistant/sorszam.py) -----------------------


def _ajanlat_harom_jelolttel(conn, ctx, ertelmezo=None):
    """Egy valódi ajánlat, hogy legyen mire hivatkozni."""
    orch = Orchestrator(conn, ertelmezo or _ScriptedErtelmezo([]), org_id=ctx["org_id"])
    ajanlat = orch.kereses_strukturaltan(
        "s1",
        {
            "bolt_id": "ugyifogyi",
            "datum_tol": "2026-08-18T00:00:00Z",
            "datum_ig": "2026-08-18T23:59:59Z",
        },
    )
    assert ajanlat["tipus"] == "ajanlat"
    return orch, ajanlat


def test_sorszamos_hivatkozas_a_MODELL_ELOTT_dont(tmp_path):
    """„A másodikat" — a leggyakoribb természetes válasz egy listára.
    Az értelmezőt meg sem hívjuk: annyi lehetőség van, ahány jelöltet
    mi ajánlottunk fel, és egy elrontott sorszám nem visszakérdezést
    okoz, hanem MÁS IDŐPONTOT foglal le."""
    conn = _conn(tmp_path)
    ctx = _seed(conn)
    ertelmezo = _ScriptedErtelmezo([])
    orch, ajanlat = _ajanlat_harom_jelolttel(conn, ctx, ertelmezo)

    valasz = orch.fordulo("s1", "a másodikat", _MOST)

    assert valasz["tipus"] == "megerositest_ker"
    assert valasz["slot_id"] == ajanlat["jeloltek"][1]["slot_id"]
    assert valasz["reteg"] == "orchestrator:sorszam"
    assert ertelmezo.hivasok == [], "az értelmezőt meg sem kellett hívni"


def test_sorszamos_hivatkozas_az_utolso_a_lista_vegere_mutat(tmp_path):
    conn = _conn(tmp_path)
    ctx = _seed(conn)
    orch, ajanlat = _ajanlat_harom_jelolttel(conn, ctx)

    valasz = orch.fordulo("s1", "az utolsó jó lesz", _MOST)

    assert valasz["slot_id"] == ajanlat["jeloltek"][-1]["slot_id"]


def test_sorszamos_hivatkozas_csak_akkor_ha_van_jelolt(tmp_path):
    """Felajánlott jelöltek nélkül a „második" bármi lehet — ilyenkor a
    szokásos út megy, az értelmezővel."""
    conn = _conn(tmp_path)
    _seed(conn)
    ertelmezo = _ScriptedErtelmezo([_visszakerdez_valasz()])
    orch = Orchestrator(conn, ertelmezo, org_id="bármi")

    valasz = orch.fordulo("s1", "a másodikat", _MOST)

    assert valasz["tipus"] == "visszakerdezes"
    assert len(ertelmezo.hivasok) == 1


def test_sorszamos_hivatkozas_tartomanyon_kivul_nem_valaszt(tmp_path):
    """Ha hármat ajánlottunk és a vásárló a hatodikat kéri, nem
    kerekítünk — a mondat a szokásos úton megy tovább, és a rendszer
    kérdez."""
    conn = _conn(tmp_path)
    ctx = _seed(conn)
    ertelmezo = _ScriptedErtelmezo([_visszakerdez_valasz()])
    orch, _ = _ajanlat_harom_jelolttel(conn, ctx, ertelmezo)

    valasz = orch.fordulo("s1", "a hatodikat", _MOST)

    assert valasz["tipus"] != "megerositest_ker"
    assert len(ertelmezo.hivasok) == 1


def test_sorszamos_hivatkozas_utan_a_megerosites_ugyanoda_vezet(tmp_path):
    """A rövidzár nem mellékbejárat: onnantól a szokásos út megy —
    megerősítés, majd foglalási kód."""
    conn = _conn(tmp_path)
    ctx = _seed(conn)
    orch, _ = _ajanlat_harom_jelolttel(conn, ctx)

    orch.fordulo("s1", "az elsőt kérem", _MOST)
    vegleges = orch.megerosit("s1", "a" * 64)

    assert vegleges["tipus"] == "visszaigazolas"
    assert vegleges["foglalasi_kod"]


# --- ÁLLAPOTVEZÉRELT DISZPÉCSER (ADR-028) ----------------------------


def test_az_allapot_a_valaszbol_kovetkezik_es_naplozhato(tmp_path):
    """Az állapot nem a válasz mezője (az a felület szerződése), hanem
    megfigyelhetőség — ugyanaz a minta, mint az `utolso_ertelmezes`."""
    conn = _conn(tmp_path)
    _seed(conn)
    ertelmezo = _ScriptedErtelmezo([_visszakerdez_valasz()])
    orch = Orchestrator(conn, ertelmezo, org_id="bármi")

    valasz = orch.fordulo("s1", "mennék valamikor", _MOST)

    assert "allapot" not in valasz, "a válasz szerződése nem változik"
    assert orch.utolso_allapot == {
        "elotte": allapotgep.INDULAS,
        "utana": allapotgep.HIANYZO_ADAT,
        "valtozott": True,
    }


def test_az_ajanlat_utan_az_allapotsor_a_jeloltek_szamat_mondja(tmp_path):
    """Ez az egész ADR-028 lényege: a modell eddig nem tudta, hogy épp
    felajánlottunk három időpontot, ezért egy csupasz „a második"
    kétértelmű volt."""
    conn = _conn(tmp_path)
    ctx = _seed(conn)
    orch, ajanlat = _ajanlat_harom_jelolttel(conn, ctx)

    sor = orch.allapot_sor("s1")

    assert sor is not None
    assert f"{len(ajanlat['jeloltek'])} időpontot" in sor


def test_az_allapotsor_eljut_az_ertelmezohoz(tmp_path):
    """A kontextuson utazik (`ErtelmezesKontextus.allapot_sor`), nem a
    mondatba fűzve — a mondat a vásárlóé marad."""
    conn = _conn(tmp_path)
    ctx = _seed(conn)
    ertelmezo = _ScriptedErtelmezo([_visszakerdez_valasz()])
    orch, _ = _ajanlat_harom_jelolttel(conn, ctx, ertelmezo)

    orch.fordulo("s1", "az a fél kilences jó lesz", _MOST)

    kontextus = ertelmezo.utolso_kontextus
    assert kontextus.allapot_sor is not None
    assert "AJANLAT_VAR" in kontextus.allapot_sor


def test_megerosites_utan_a_kesz_allapot_all_be(tmp_path):
    conn = _conn(tmp_path)
    ctx = _seed(conn)
    orch, _ = _ajanlat_harom_jelolttel(conn, ctx)
    orch.fordulo("s1", "az elsőt kérem", _MOST)

    orch.megerosit("s1", "a" * 64)

    assert orch._allapot("s1").allapot == allapotgep.KESZ


def test_a_kozbevetett_kerdes_nem_veszti_el_az_ajanlatot(tmp_path):
    """A vásárló a foglalás közepén mást kérdez — a felajánlott
    időpontokra utána is lehet hivatkozni."""
    conn = _conn(tmp_path)
    ctx = _seed(conn)
    ertelmezo = _ScriptedErtelmezo([{"eszkoz": "nincs", "parameterek": {}}])
    orch, _ = _ajanlat_harom_jelolttel(conn, ctx, ertelmezo)

    orch.fordulo("s1", "amúgy milyen idő lesz?", _MOST)

    assert orch._allapot("s1").allapot == allapotgep.AJANLAT_VAR


def test_jelolt_valasztas_a_modelltol(tmp_path):
    """A modell kimondhatja, hogy a vásárló a LISTÁBÓL választott —
    erre eddig nem volt mivel (a legjobb, amit tehetett, egy újabb
    keresés volt)."""
    conn = _conn(tmp_path)
    ctx = _seed(conn)
    ertelmezo = _ScriptedErtelmezo([{"eszkoz": "jelolt_valasztas", "parameterek": {"sorszam": 2}}])
    orch, ajanlat = _ajanlat_harom_jelolttel(conn, ctx, ertelmezo)

    valasz = orch.fordulo("s1", "az a fél kilences jó lesz", _MOST)

    assert valasz["tipus"] == "megerositest_ker"
    assert valasz["slot_id"] == ajanlat["jeloltek"][1]["slot_id"]


def test_jelolt_valasztas_csak_ajanlat_utan(tmp_path):
    """Ha nincs mire hivatkozni, a „harmadik" bármi lehet — ilyenkor
    kérdezünk, nem választunk."""
    conn = _conn(tmp_path)
    _seed(conn)
    ertelmezo = _ScriptedErtelmezo([{"eszkoz": "jelolt_valasztas", "parameterek": {"sorszam": 2}}])
    orch = Orchestrator(conn, ertelmezo, org_id="bármi")

    valasz = orch.fordulo("s1", "a másodikat", _MOST)

    assert valasz["tipus"] == "visszakerdezes"


def test_jelolt_valasztas_tartomanyon_kivul_nem_kerekit(tmp_path):
    """Egy elrontott választás nem visszakérdezést okoz, hanem MÁS
    IDŐPONTOT foglal le — a negyedikre ezért nem kerekítünk."""
    conn = _conn(tmp_path)
    ctx = _seed(conn)
    ertelmezo = _ScriptedErtelmezo([{"eszkoz": "jelolt_valasztas", "parameterek": {"sorszam": 9}}])
    orch, _ = _ajanlat_harom_jelolttel(conn, ctx, ertelmezo)

    valasz = orch.fordulo("s1", "a kilencediket", _MOST)

    assert valasz["tipus"] == "visszakerdezes"


# --- ÍRÁSBELI IGEN / NEM a megerősítés-kérdésre ----------------------
#
# MÉRT HIBA javítása (2026-08-31, `vegigjatszas` modellel ÉS
# tartalékágon): az „igen, foglald le" mondatból ÚJ KERESÉS lett, és a
# folyamatban lévő megerősítés — a kiválasztott időponttal együtt —
# eltűnt. A foglalás írásban emiatt nem volt befejezhető.


def test_irasbeli_igen_megtartja_a_megerositest(tmp_path):
    """Az „igen" nem foglal (ahhoz vásárlói kulcs kell, CLAUDE.md 2.
    invariáns) — a megerősítés-kérdést ISMÉTLI meg, ugyanarra a
    slotra. Ettől marad a képernyőn az azonosító-mező."""
    conn = _conn(tmp_path)
    ctx = _seed(conn)
    ertelmezo = _ScriptedErtelmezo([])
    orch, ajanlat = _ajanlat_harom_jelolttel(conn, ctx, ertelmezo)
    valasztott = orch.fordulo("s1", "az elsőt kérem", _MOST)["slot_id"]

    valasz = orch.fordulo("s1", "igen, foglald le", _MOST)

    assert valasz["tipus"] == "megerositest_ker"
    assert valasz["slot_id"] == valasztott
    assert valasz["reteg"] == "orchestrator:megerosites"
    assert ertelmezo.hivasok == [], "az értelmezőt meg sem kellett hívni"
    assert valasz["valasztott_jelolt"]["slot_id"] == ajanlat["jeloltek"][0]["slot_id"]


def test_irasbeli_igen_utan_a_foglalas_befejezheto(tmp_path):
    """A teljes írásbeli út: keresés → sorszám → igen → azonosító →
    foglalási kód."""
    conn = _conn(tmp_path)
    ctx = _seed(conn)
    orch, _ = _ajanlat_harom_jelolttel(conn, ctx)

    orch.fordulo("s1", "a másodikat kérem", _MOST)
    orch.fordulo("s1", "igen, foglald le", _MOST)
    vegleges = orch.megerosit("s1", "a" * 64)

    assert vegleges["tipus"] == "visszaigazolas"
    assert vegleges["foglalasi_kod"]


def test_irasbeli_nem_elveti_de_a_tobbi_jelolt_marad(tmp_path):
    """A vásárló EGY időpontra mondott nemet, nem az egész keresésre —
    a többi jelölt még áll, és újra felkínálható."""
    conn = _conn(tmp_path)
    ctx = _seed(conn)
    orch, ajanlat = _ajanlat_harom_jelolttel(conn, ctx)
    orch.fordulo("s1", "az elsőt kérem", _MOST)

    valasz = orch.fordulo("s1", "mégse kell", _MOST)

    assert valasz["tipus"] == "elvetve"
    assert valasz["reteg"] == "orchestrator:megerosites"
    assert len(valasz["jeloltek"]) == len(ajanlat["jeloltek"])


def test_a_megerosites_rovidzar_csak_megerositesre_varva_szolal_meg(tmp_path):
    """Megerősítés nélkül az „igen" önmagában semmit nem jelent — a
    mondat a szokásos úton megy tovább, az értelmezőhöz."""
    conn = _conn(tmp_path)
    _seed(conn)
    ertelmezo = _ScriptedErtelmezo([_visszakerdez_valasz()])
    orch = Orchestrator(conn, ertelmezo, org_id="bármi")

    valasz = orch.fordulo("s1", "igen", _MOST)

    assert valasz["tipus"] == "visszakerdezes"
    assert len(ertelmezo.hivasok) == 1


def test_uj_keres_a_megerosites_kozben_atmegy_az_ertelmezore(tmp_path):
    """A rövidzár SZŰK: ami nem igen és nem nem, az a szokásos úton megy
    — különben egy „és mennyibe kerül?" közbevetett kérdés elnyelődne."""
    conn = _conn(tmp_path)
    ctx = _seed(conn)
    ertelmezo = _ScriptedErtelmezo([_visszakerdez_valasz()])
    orch, _ = _ajanlat_harom_jelolttel(conn, ctx, ertelmezo)
    orch.fordulo("s1", "az elsőt kérem", _MOST)

    orch.fordulo("s1", "igen, de inkább szerdán", _MOST)

    assert len(ertelmezo.hivasok) == 1


def test_boltvaltaskor_a_masik_bolt_szolgaltatasa_nem_marad_ra(tmp_path):
    """KÉZI PRÓBA találata: a „nézzük a másik boltban" gomb után üres
    lett a találat.

    Ok: a szándék KEMÉNY része (bolt + szolgáltatás) átjön a következő
    fordulóra, de a szolgáltatás bolt-specifikus — az „altató" a
    Szundié. Boltváltáskor így egy olyan pár keletkezett, amire
    definíció szerint nincs slot (Törpilla + altató), és a tünet néma
    volt: „ez a bolt nem hirdetett meg időpontot", holott hirdetett."""
    conn = _conn(tmp_path)
    ctx = _seed(conn)
    orch = Orchestrator(conn, _ScriptedErtelmezo([]), org_id=ctx["org_id"])

    # A megőrzött kontextusba egy MÁSIK bolt szolgáltatása kerül.
    orch._allapot("s1").megorzott_parameterek = {
        "bolt_id": "szundi",
        "szolgaltatas_id": "altato",
    }

    valasz = orch.kereses_strukturaltan(
        "s1",
        {
            "bolt_id": "ugyifogyi",
            "datum_tol": "2026-08-18T00:00:00Z",
            "datum_ig": "2026-08-18T23:59:59Z",
        },
    )

    assert valasz["tipus"] == "ajanlat", valasz
    assert valasz["jeloltek"]


def test_a_bolthoz_tartozo_szolgaltatas_megmarad(tmp_path):
    """Az ellenpróba: ha a szolgáltatás ehhez a bolthoz tartozik, marad
    — a szűrés zárt halmazon dolgozik, nem „minden szolgáltatást
    eldobunk boltváltáskor"."""
    conn = _conn(tmp_path)
    _seed(conn)
    orch = Orchestrator(conn, _ScriptedErtelmezo([]), org_id="bármi")

    teljes = orch._idegen_szolgaltatast_eldob(
        {"bolt_id": "ugyifogyi", "szolgaltatas_id": "nagy_petarda"}
    )

    assert teljes["szolgaltatas_id"] == "nagy_petarda"


# --- lazítási sorrend bolton belül (ADR-024) -------------------------


def test_alternativa_kesobb_a_legkozelebbi_idopont_eszkozre_megy(tmp_path):
    """A `kesobb` dimenzió NEM ablaktágítás: a gomb a
    `legkozelebbi_idopont` eszközt futtatja, tehát a válasz EGY konkrét,
    holdolt időpont — akár hetekkel a kért ablak után (ADR-024).

    A régi `het` dimenzió csak egy héttel lépett előre; a demóadat
    slotja (2026-08-18) a kért ablak (2026-08-10 - 2026-08-16) után egy
    HÉTTEL van, ezért a régi úton is előjött volna — a különbség az,
    hogy most a horizont végéig néz, és a válasz az eszközé, nem egy
    kitalált ablaké."""
    conn = _conn(tmp_path)
    ctx = _seed(conn)
    orch = Orchestrator(conn, SzabalyAlapuErtelmezo(), org_id=ctx["org_id"])
    orch.kereses_strukturaltan(
        "s1",
        {
            "bolt_id": "ugyifogyi",
            "datum_tol": "2026-08-10T00:00:00Z",
            "datum_ig": "2026-08-16T23:59:59Z",
        },
    )

    valasz = orch.alternativa_kereses("s1", "kesobb")

    assert valasz["tipus"] == "ajanlat"
    assert valasz["legkozelebbi"] is True
    assert len(valasz["jeloltek"]) == 1
    assert valasz["jeloltek"][0]["kezdet"].startswith("2026-08-18")


def test_alternativa_varians_elengedi_a_szolgaltatast(tmp_path):
    """A `varians` gomb ugyanabba az ablakba keres, de elengedett
    szolgáltatás-szűréssel (`MINDEGY`) — ez a "más változat a bolton
    belül" lazítás. A tervet a `szabad_idopontok.lazitas_terve` adja,
    nem az orchestrator: itt csak az látszik, hogy a keresés tényleg
    MINDEGY-gyel fut."""
    conn = _conn(tmp_path)
    ctx = _seed(conn)
    orch = Orchestrator(conn, SzabalyAlapuErtelmezo(), org_id=ctx["org_id"])
    orch.kereses_strukturaltan(
        "s1",
        {
            "bolt_id": "ugyifogyi",
            "szolgaltatas_id": "nagy_petarda",
            "datum_tol": "2026-08-17T00:00:00Z",
            "datum_ig": "2026-08-17T23:59:59Z",
        },
    )

    valasz = orch.alternativa_kereses("s1", "varians")

    assert orch._allapot("s1").utolso_kereses["szolgaltatas_id"] == MINDEGY
    # A kért napon (08-17) semmi sincs, tehát a keresés üres — a lényeg
    # a PARAMÉTER, nem a találat.
    assert valasz["tipus"] == "eszkoz_hiba"


def test_a_bolt_nem_szerepel_a_kiut_dimenziok_kozott():
    """ADR-024: a bolt nem lazítási dimenzió, hanem maga a termék. Aki
    petárdát kér, annak a boldogság-bolt nem alternatíva, hanem MÁS
    KÉRDÉSRE adott válasz."""
    from assistant.orchestrator import _KIUT_DIMENZIOK

    assert "bolt" not in _KIUT_DIMENZIOK
    assert "legkorabbi" in _KIUT_DIMENZIOK


# --- MINDEGY szentinel (ADR-024) -------------------------------------


def test_mindegy_bolt_eseten_nem_kerdez_vissza_es_mindenhol_keres(tmp_path):
    """A `MINDEGY` nem hiányzó érték: a keresés lefut, minden boltra.

    A hiba, amit kizár: a "mindegy melyik" válasz korábban ugyanoda
    vezetett, mint a hallgatás — a mező üres maradt, a rendszer pedig
    újra rákérdezett arra, amit a vásárló épp elengedett."""
    conn = _conn(tmp_path)
    ctx = _seed(conn)
    ertelmezo = _ScriptedErtelmezo(
        [
            {
                "eszkoz": "szabad_idopontok",
                "parameterek": {
                    "bolt_id": MINDEGY,
                    "datum_tol": "2026-08-18T00:00:00Z",
                    "datum_ig": "2026-08-18T23:59:59Z",
                },
            }
        ]
    )
    orch = Orchestrator(conn, ertelmezo, org_id=ctx["org_id"])

    valasz = orch.fordulo("s1", "mindegy melyik, csak legyen hely", _MOST)

    assert valasz["tipus"] == "ajanlat"
    assert valasz["jeloltek"]


def test_mindegy_tulel_egy_fordulot_ugyanugy_mint_egy_konkret_ertek(tmp_path):
    """Az orchestrator a MINDEGY-et a kontextusban ugyanúgy őrzi meg,
    mint egy konkrét slugot — ez teszi lehetővé, hogy a következő
    fordulóban se kérdezzen rá."""
    kovetkezo = kovetkezo_kontextus(
        {},
        {
            "eszkoz": "szabad_idopontok",
            "parameterek": {"bolt_id": "ugyifogyi", "szolgaltatas_id": MINDEGY},
        },
    )
    assert kovetkezo == {"bolt_id": "ugyifogyi", "szolgaltatas_id": MINDEGY}

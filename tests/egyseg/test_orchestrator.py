"""Egységtesztek az orchestratorra (`assistant/orchestrator.py`, ADR-007):
állapotátmenetek — részleges adat → zárt kérdés → megőrzés → foglalás.

Az `Ertelmezo`-t egy szkriptelt dupla helyettesíti (`_ScriptedErtelmezo`)
— az orchestrator állapotgépét az értelmezőtől FÜGGETLENÜL teszteljük,
ahogy a determinisztikus vagy egy jövőbeli LLM-es implementáció mögé is
ugyanígy illeszkedne (`assistant/interpreter/__init__.py::Ertelmezo`)."""

from __future__ import annotations

from assistant.interpreter import ErtelmezesKontextus
from assistant.orchestrator import Orchestrator
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

    def ertelmez(self, mondat: str, *, most: str, kontextus: ErtelmezesKontextus) -> dict:
        self.hivasok.append((mondat, dict(kontextus.megorzott_parameterek)))
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

    assert valasz == {"tipus": "elutasitas", "uzenet_kulcs": "nem_foglalasi_kerdes"}


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
    valasztott = ajanlat["jeloltek"][0]["slot_id"]

    megerosites_kerve = orch.valaszt("session-1", valasztott)
    assert megerosites_kerve == {"tipus": "megerositest_ker", "slot_id": valasztott}

    vegleges = orch.megerosit("session-1", "a" * 64)
    assert vegleges["tipus"] == "visszaigazolas"
    assert len(vegleges["foglalasi_kod"]) == 8

    # A slot ténylegesen foglalt, nem csak holdolt.
    assert foglalas_repo.slot_free(conn, valasztott) is False


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

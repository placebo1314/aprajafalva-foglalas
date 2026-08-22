"""Egységtesztek az orchestratorra (`assistant/orchestrator.py`, ADR-007):
állapotátmenetek — részleges adat → zárt kérdés → megőrzés → foglalás.

Az `Ertelmezo`-t egy szkriptelt dupla helyettesíti (`_ScriptedErtelmezo`)
— az orchestrator állapotgépét az értelmezőtől FÜGGETLENÜL teszteljük,
ahogy a determinisztikus vagy egy jövőbeli LLM-es implementáció mögé is
ugyanígy illeszkedne (`assistant/interpreter/__init__.py::Ertelmezo`)."""

from __future__ import annotations

from assistant.interpreter import ErtelmezesKontextus
from assistant.interpreter.rule_based import SzabalyAlapuErtelmezo
from assistant.orchestrator import Orchestrator, kovetkezo_kontextus
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

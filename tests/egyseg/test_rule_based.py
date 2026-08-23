"""Egységtesztek a determinisztikus értelmezőre
(`assistant/interpreter/rule_based.py`) — reprezentatív esetek a golden
set (`tests/golden/nyelvi_alap.yaml`) mintájából, hogy a valódi, teljes
körű mérés a golden runner `--ertelmezo szabaly` módja legyen
(`spike/golden_futtato.py`), ne itt duplikálódjon esetenként.
"""

from __future__ import annotations

from datetime import datetime

import pytest

from assistant.interpreter import ErtelmezesKontextus
from assistant.interpreter.rule_based import SzabalyAlapuErtelmezo

_MOST = "2026-08-17T09:00:00Z"  # hétfő


def _ertelmez_teljes(mondat: str, kontextus: ErtelmezesKontextus | None = None) -> dict:
    """A NYERS értelmezés, a `bizonyossag` mezővel együtt."""
    return SzabalyAlapuErtelmezo().ertelmez(
        mondat, most=_MOST, kontextus=kontextus or ErtelmezesKontextus()
    )


def _ertelmez(mondat: str, kontextus: ErtelmezesKontextus | None = None) -> dict:
    """Csak az `eszkoz` + `parameterek` rész — a `bizonyossag`-ot
    kihagyja, hogy az "mit ismert fel" tesztek egyetlen dologról
    szóljanak. A bizonyosságnak saját, dedikált tesztjei vannak lent
    ("bizonyosság" szakasz), `_ertelmez_teljes`-szel."""
    eredmeny = _ertelmez_teljes(mondat, kontextus)
    return {k: v for k, v in eredmeny.items() if k != "bizonyossag"}


# --- kapuőr ---------------------------------------------------------


def test_kapuor_idojaras():
    assert _ertelmez("Milyen idő lesz holnap?") == {"eszkoz": "nincs", "parameterek": {}}


def test_kapuor_ar():
    assert _ertelmez("Mennyibe kerül a nagy petárda?") == {"eszkoz": "nincs", "parameterek": {}}


def test_kapuor_nem_akad_fenn_a_holnap_szon():
    """A "holnap" a mondatban nem térítheti el a kapuőrt egy foglalási
    ág felé — az időjárás-kérdés prioritást élvez."""
    eredmeny = _ertelmez("Milyen idő lesz holnap?")
    assert eredmeny["eszkoz"] == "nincs"


# --- bolt_info -------------------------------------------------------


def test_bolt_info_nyitvatartas_datummal():
    eredmeny = _ertelmez("Meddig van nyitva a Szundi bolt szombaton?")
    assert eredmeny == {
        "eszkoz": "bolt_info",
        "parameterek": {"bolt_id": "szundi", "mit": "nyitvatartas", "datum": "2026-08-22"},
    }


def test_bolt_info_cim_tajszolassal():
    eredmeny = _ertelmez("Hun van az az üzlet, ahun a boldogságot árullyák?")
    assert eredmeny == {"eszkoz": "bolt_info", "parameterek": {"bolt_id": "torpilla", "mit": "cim"}}


def test_bolt_info_megjelenes_kozvetlen_forma():
    eredmeny = _ertelmez("Hogy néz ki a Törpilla bolt?")
    assert eredmeny == {
        "eszkoz": "bolt_info",
        "parameterek": {"bolt_id": "torpilla", "mit": "megjelenes"},
    }


def test_bolt_info_megjelenes_szetvalasztott_milyen_forma():
    """A "milyen" és a tárgyszó (kirakat/bolt/...) nem feltétlenül
    szomszédos a mondatban — a boltnév közéjük ékelődhet."""
    eredmeny = _ertelmez("Milyen a Szundi kirakata?")
    assert eredmeny == {
        "eszkoz": "bolt_info",
        "parameterek": {"bolt_id": "szundi", "mit": "megjelenes"},
    }


def test_bolt_info_termek():
    eredmeny = _ertelmez("Mit árulnak az Ügyifogyiban?")
    assert eredmeny == {
        "eszkoz": "bolt_info",
        "parameterek": {"bolt_id": "ugyifogyi", "mit": "termek"},
    }


def test_bolt_info_termek_milyen_forma():
    eredmeny = _ertelmez("Milyen termékeik vannak a Törpillánál?")
    assert eredmeny == {
        "eszkoz": "bolt_info",
        "parameterek": {"bolt_id": "torpilla", "mit": "termek"},
    }


def test_bolt_info_ar_kapuornel_akad_el_nem_jut_el_bolt_infoig():
    """Az "ar" séma-szinten (bolt_info v2) lekérdezhető, de a kapuőr ma
    is elutasítja — a golden set kapuor-02 esete (docs/blueprint.md
    10. szakasz, "Bolti tudás")."""
    eredmeny = _ertelmez("Mennyibe kerül a nagy petárda?")
    assert eredmeny == {"eszkoz": "nincs", "parameterek": {}}


def test_bolt_info_bolt_nelkul_visszakerdez():
    eredmeny = _ertelmez("Hol van az üzlet?")
    assert eredmeny["eszkoz"] == "visszakerdez"
    assert eredmeny["parameterek"]["hianyzo_mezo"] == "bolt_id"


# --- lemondás / áthelyezés -------------------------------------------


def test_lemondas_koddal():
    eredmeny = _ertelmez("Le szeretném mondani a foglalásomat, a kód X7K2M9QP.")
    assert eredmeny == {
        "eszkoz": "foglalas_lemondas",
        "parameterek": {"foglalasi_kod": "X7K2M9QP"},
    }


def test_lemondas_kod_nelkul_visszakerdez():
    eredmeny = _ertelmez("Le szeretném mondani a foglalásomat.")
    assert eredmeny == {
        "eszkoz": "visszakerdez",
        "parameterek": {"hianyzo_mezo": "foglalasi_kod", "varhato_kerdes_tipusa": "nyitott"},
    }


def test_athelyezes_visszakerdez_foglalasi_kodra():
    eredmeny = _ertelmez("Át tudnám tenni szerdára a péntek délelőtti időpontomat?")
    assert eredmeny == {
        "eszkoz": "visszakerdez",
        "parameterek": {"hianyzo_mezo": "foglalasi_kod", "varhato_kerdes_tipusa": "nyitott"},
    }


# --- keresés: köznyelvi, teljes paraméterkészlet ----------------------


def test_kereses_relativ_datum_es_szolgaltatas():
    eredmeny = _ertelmez("Szeretnék időpontot foglalni jövő hét keddre nagy petárdához.")
    assert eredmeny == {
        "eszkoz": "szabad_idopontok",
        "parameterek": {
            "bolt_id": "ugyifogyi",
            "szolgaltatas_id": "nagy_petarda",
            "datum_tol": "2026-08-25T00:00:00Z",
            "datum_ig": "2026-08-25T23:59:59Z",
            "napszak": "barmikor",
        },
    }


def test_legkorabbi_kerdes_sajat_eszkozre_megy():
    """ "Mikor tudok legkorábban menni?" — ez nem időszak-keresés: egy
    konkrét kérdés, egy konkrét válasszal (`legkozelebbi_idopont`).
    Dátumablak SZÁNDÉKOSAN nincs a paraméterek közt: a kérdésben sincs."""
    eredmeny = _ertelmez("Mikor tudok legkorábban menni Törpillához?")
    assert eredmeny == {
        "eszkoz": "legkozelebbi_idopont",
        "parameterek": {"bolt_id": "torpilla", "szolgaltatas_id": "nagy_orom"},
    }


def test_legkorabbi_kerdes_napszakkal():
    eredmeny = _ertelmez("Mikor tudok legkorábban menni Törpillához délelőtt?")
    assert eredmeny["eszkoz"] == "legkozelebbi_idopont"
    assert eredmeny["parameterek"]["napszak"] == "delelott"


def test_legkorabbi_kerdes_bolt_nelkul_visszakerdez():
    """Bolt nélkül nincs mit megkeresni — a szokásos zárt kérdés megy,
    nem egy találgatott bolt legkorábbi időpontja."""
    eredmeny = _ertelmez("Mikor tudok legkorábban menni?")
    assert eredmeny["eszkoz"] == "visszakerdez"
    assert eredmeny["parameterek"]["hianyzo_mezo"] == "bolt_id"


def test_sima_mikor_kerdes_marad_kereses():
    """A szűk minta ellenpróbája: a "leg…" nélküli kérdés továbbra is
    időszak-keresés, nyitott ablakkal."""
    eredmeny = _ertelmez("Mikor mehetek Törpillához?")
    assert eredmeny["eszkoz"] == "szabad_idopontok"
    assert eredmeny["parameterek"]["datum_ig"] == "2026-08-24T23:59:59Z"


def test_kereses_ma_a_jelen_pillanattol_indul():
    eredmeny = _ertelmez("yo, be lehet nézni ma Törpillához vagy tele van?")
    assert eredmeny["parameterek"]["datum_tol"] == "2026-08-17T09:00:00Z"
    assert eredmeny["parameterek"]["datum_ig"] == "2026-08-17T23:59:59Z"


def test_kereses_preferalt_ora():
    eredmeny = _ertelmez("Van hely hónap délelőtt a petárdásnál? Kb 10 körül lenne jó")
    assert eredmeny["parameterek"]["preferalt_ora"] == 10
    assert eredmeny["parameterek"]["napszak"] == "delelott"


def test_kereses_meret_nelkuli_petarda_szolgaltatas_nelkul():
    """Méret-jelző (kis/nagy) nélkül a szolgáltatás nem egyértelmű —
    ez NEM hiba, a keresés bolt-szinten is elindulhat (golden set,
    toredekes-01 megjegyzése)."""
    eredmeny = _ertelmez("kedden… petárda… lehet?")
    assert "szolgaltatas_id" not in eredmeny["parameterek"]
    assert eredmeny["parameterek"]["bolt_id"] == "ugyifogyi"


# --- tájszólás normalizálás ------------------------------------------


def test_tajszolas_honap_csapdaszo_holnapkent_oldodik():
    eredmeny = _ertelmez("Möggyek-ë hónap délelőtt a petárdáshó?")
    assert eredmeny["eszkoz"] == "szabad_idopontok"
    assert eredmeny["parameterek"]["datum_tol"] == "2026-08-18T00:00:00Z"
    assert eredmeny["parameterek"]["napszak"] == "delelott"


def test_tajszolas_bolt_hianyzik_zart_kerdes():
    eredmeny = _ertelmez("Kéretnék egy időpontot szombat reggelre, ha lehetséges vóna.")
    assert eredmeny["eszkoz"] == "visszakerdez"
    assert eredmeny["parameterek"]["hianyzo_mezo"] == "bolt_id"
    assert eredmeny["parameterek"]["varhato_kerdes_tipusa"] == "zart"
    assert eredmeny["parameterek"]["valaszthato_ertekek"] == ["szundi", "torpilla", "ugyifogyi"]


def test_szleng_roviditett_nap_jovo_het_ertelmezes():
    eredmeny = _ertelmez("asszem jövő csüt jó lenne, addig ráérek")
    assert eredmeny["eszkoz"] == "visszakerdez"
    assert eredmeny["parameterek"]["datum_tol"] == "2026-08-27T00:00:00Z"
    assert eredmeny["parameterek"]["datum_ig"] == "2026-08-27T23:59:59Z"


# --- visszakérdezés: megőrzés és a "ne találj ki dátumot" szabály ----


def test_visszakerdez_megorzi_a_datumot_es_napszakot():
    eredmeny = _ertelmez("időpont. holnap. délelőtt.")
    assert eredmeny["eszkoz"] == "visszakerdez"
    assert eredmeny["parameterek"]["datum_tol"] == "2026-08-18T00:00:00Z"
    assert eredmeny["parameterek"]["datum_ig"] == "2026-08-18T11:59:59Z"
    assert eredmeny["parameterek"]["napszak"] == "delelott"


def test_visszakerdez_a_heten_kifejezes():
    eredmeny = _ertelmez("Szeretnék… izé… hogy is mondjam… bemenni a boltba valamikor a héten.")
    assert eredmeny["parameterek"]["datum_tol"] == "2026-08-17T09:00:00Z"
    assert eredmeny["parameterek"]["datum_ig"] == "2026-08-23T23:59:59Z"


# --- HÉT-kifejezések: a hétnek hét napot kell adnia ------------------


@pytest.mark.parametrize(
    "mondat",
    [
        "Petárdázni szeretnék a következő héten.",
        "Petárdázni szeretnék következő héten.",
        "Petárdázni szeretnék a következő hétre.",
        "Petárdázni szeretnék a következő hét folyamán.",
        "Petárdázni szeretnék jövő héten.",
        "Petárdázni szeretnék a jövő hétre.",
        "Petárdázni szeretnék a jövő hét folyamán.",
        "Szeretnék időpontot a petárdáshoz a következő hétre valamikor.",
    ],
)
def test_kovetkezo_het_teljes_hetet_ad_nem_egy_napot(mondat):
    """A "következő/jövő hét" MINDEN toldalékolt alakja a teljes
    következő naptári hetet (hétfő–vasárnap, 7 nap) adja. Korábban a
    `\\bhéten\\b` alak volt csak lefedve, ezért a "hétre"/"hét folyamán"
    egy általános, 7 napos MAI ablakra esett vissza, a "következő" szót
    pedig a dátumparser egyáltalán nem ismerte."""
    parameterek = _ertelmez(mondat)["parameterek"]
    assert parameterek["datum_tol"] == "2026-08-24T00:00:00Z"
    assert parameterek["datum_ig"] == "2026-08-30T23:59:59Z"

    kezdet = datetime.fromisoformat(parameterek["datum_tol"].replace("Z", "+00:00"))
    veg = datetime.fromisoformat(parameterek["datum_ig"].replace("Z", "+00:00"))
    assert (veg - kezdet).days == 6, "a hétnek hét naptári napot kell lefednie"
    assert kezdet.weekday() == 0, "hétfőn kezdődik"
    assert veg.weekday() == 6, "vasárnap ér véget"


@pytest.mark.parametrize(
    "mondat",
    ["Petárdázni szeretnék valamikor a héten.", "Petárdázni szeretnék ezen a héten."],
)
def test_ezen_a_heten_a_most_pillanatatol_a_het_vegeig(mondat):
    """A FOLYÓ hét nem hétfőtől indul — az már részben eltelt, arra
    visszamenőleg nem lehet foglalni."""
    parameterek = _ertelmez(mondat)["parameterek"]
    assert parameterek["datum_tol"] == "2026-08-17T09:00:00Z"
    assert parameterek["datum_ig"] == "2026-08-23T23:59:59Z"


@pytest.mark.parametrize(
    "mondat", ["következő héten pénteken", "jövő héten pénteken", "jövő hét péntek"]
)
def test_konkret_nap_felulirja_a_het_ablakot(mondat):
    """Ha a mondat a hét mellett konkrét napot is megnevez, a konkrétabb
    nyer — nem az egész hetet adjuk vissza."""
    parameterek = _ertelmez(
        mondat, ErtelmezesKontextus(megorzott_parameterek={"bolt_id": "ugyifogyi"})
    )["parameterek"]
    assert parameterek["datum_tol"] == "2026-08-28T00:00:00Z"
    assert parameterek["datum_ig"] == "2026-08-28T23:59:59Z"


def test_visszakerdez_nem_talal_ki_datumot_mult_idobol():
    """A "tilos: kitalalt_datum" eset — a bare napszak-szó ("délelőtt")
    múlt idejű mondatban nem alakulhat mai dátummá."""
    eredmeny = _ertelmez("Múltkor is voltam. Ugyanakkor szeretnék megint. Az délelőtt volt.")
    assert eredmeny["eszkoz"] == "visszakerdez"
    assert "datum_tol" not in eredmeny["parameterek"]
    assert "datum_ig" not in eredmeny["parameterek"]
    assert eredmeny["parameterek"]["napszak"] == "delelott"


def test_visszakerdez_semmi_konkretum_nincs_extra_mezo_nelkul():
    eredmeny = _ertelmez("hát én csak azt szeretném hogy hogy mikor lehet menni")
    assert eredmeny == {
        "eszkoz": "visszakerdez",
        "parameterek": {
            "hianyzo_mezo": "bolt_id",
            "varhato_kerdes_tipusa": "zart",
            "valaszthato_ertekek": ["szundi", "torpilla", "ugyifogyi"],
        },
    }


def test_kontextus_megorzott_parameterek_atadodik_a_kovetkezo_hivasnak():
    """Az orchestrator a kontextuson keresztül adja át a korábban
    megőrzött mezőket — az értelmezőnek ezeket kell a most kinyerttel
    egyesítenie, az új adat felülírja a régit ütközésnél."""
    kontextus = ErtelmezesKontextus(
        megorzott_parameterek={
            "datum_tol": "2026-08-18T00:00:00Z",
            "datum_ig": "2026-08-18T11:59:59Z",
            "napszak": "delelott",
        }
    )
    eredmeny = _ertelmez("ugyifogyi", kontextus)
    assert eredmeny["eszkoz"] == "szabad_idopontok"
    assert eredmeny["parameterek"]["bolt_id"] == "ugyifogyi"
    assert eredmeny["parameterek"]["datum_tol"] == "2026-08-18T00:00:00Z"
    assert eredmeny["parameterek"]["napszak"] == "delelott"


# --- bizonyosság: 1.0 amit szabályból tud, None amit nem -------------


def test_bizonyossag_kapuor_dontese_biztos():
    b = _ertelmez_teljes("Milyen idő lesz holnap?")["bizonyossag"]
    assert b["eszkoz"] == 1.0


def test_bizonyossag_explicit_datum_es_bolt_biztos():
    b = _ertelmez_teljes("Petárdázni szeretnék kedden.")["bizonyossag"]
    assert b["eszkoz"] == 1.0
    assert b["bolt_id"] == 1.0
    assert b["datum"] == 1.0


def test_bizonyossag_alapertelmezett_datum_nem_tudas():
    """A `_altalanos_ablak()` tartalék-dátum nem a mondatból származik —
    a bizonyosság ezért None, nem 1.0. Ebből tudja az orchestrator, hogy
    a dátumra érdemes lehet rákérdezni."""
    eredmeny = _ertelmez_teljes("Petárdát kéne venni. Mikor mehetek?")
    assert eredmeny["eszkoz"] == "szabad_idopontok"
    assert "datum_tol" in eredmeny["parameterek"], "a keresés attól még elindul"
    assert eredmeny["bizonyossag"]["datum"] is None


def test_bizonyossag_alapertelmezett_napszak_nem_tudas():
    eredmeny = _ertelmez_teljes("Petárdázni szeretnék kedden.")
    assert eredmeny["parameterek"]["napszak"] == "barmikor"
    assert eredmeny["bizonyossag"]["napszak"] is None


def test_bizonyossag_explicit_napszak_biztos():
    eredmeny = _ertelmez_teljes("Petárdázni szeretnék kedden délelőtt.")
    assert eredmeny["parameterek"]["napszak"] == "delelott"
    assert eredmeny["bizonyossag"]["napszak"] == 1.0


def test_bizonyossag_hianyzo_bolt_none_de_a_visszakerdezes_biztos():
    b = _ertelmez_teljes("Szeretnék menni kedden valahova.")["bizonyossag"]
    assert b["bolt_id"] is None
    assert b["eszkoz"] == 1.0, "a visszakérdezés maga biztos döntés"


def test_bizonyossag_eliminacios_keresesnel_nincs_pozitiv_bizonyitek():
    """A keresés az eliminációs ág — ha sem boltot, sem dátumot nem
    ismertünk fel a mondatból, az `eszkoz` sem biztos."""
    eredmeny = _ertelmez_teljes(
        "hát én csak azt szeretném hogy hogy mikor lehet menni",
        ErtelmezesKontextus(megorzott_parameterek={"bolt_id": "ugyifogyi"}),
    )
    assert eredmeny["bizonyossag"]["eszkoz"] is None


def test_bizonyossag_kontextusbol_orokolt_datum_is_tudas():
    """A kontextusból hozott dátum korábban maga is szabályból
    keletkezett — az nem alapértelmezés, hanem tudás."""
    b = _ertelmez_teljes(
        "a Törpillánál",
        ErtelmezesKontextus(
            megorzott_parameterek={
                "datum_tol": "2026-08-18T00:00:00Z",
                "datum_ig": "2026-08-18T23:59:59Z",
            }
        ),
    )["bizonyossag"]
    assert b["datum"] == 1.0

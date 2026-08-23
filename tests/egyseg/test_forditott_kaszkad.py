"""Egységtesztek a FORDÍTOTT kaszkád értelmezőre (`assistant/
interpreter/forditott_kaszkad.py`, ADR-018 — **ez az éles út**) — az
LLM-réteget mindenütt egy szkriptelt hamisítvány (`_FakeLLM`)
helyettesíti, ez a fájl SOSEM hív valódi Ollamát.

A hangsúly a DETERMINISZTIKUS KAPUKON van: a modell értelmez, de a
dátumot a parser adja, a bolt/szolgáltatás zárt halmazon marad, a
foglalási kód a mondatból jön, és Ollama-hiba esetén a szabály-alapú
réteg veszi át hiba nélkül."""

from __future__ import annotations

from assistant.interpreter import KI_RENDSZER, KI_VASARLO, ErtelmezesKontextus
from assistant.interpreter.forditott_kaszkad import ForditottKaszkadErtelmezo
from assistant.interpreter.rule_based import SzabalyAlapuErtelmezo

_MOST = "2026-08-17T09:00:00Z"  # hétfő


class _FakeLLM:
    """Az `LLMErtelmezo`-t helyettesíti — nincs Ollama-hívás."""

    TAMOGAT_MINTAVETELT = True

    def __init__(self, valasz: dict | None = None, hiba: str | None = None):
        self.valasz = valasz or {"eszkoz": "nincs", "parameterek": {}}
        self.utolso_hiba = hiba
        self.kapott_mondatok: list[str] = []
        self.kapott_kontextusok: list[ErtelmezesKontextus] = []
        # Az önkonzisztencia-burkoló által átadott mintavételek
        # (ADR-021) — `None` a kanonikus, `temperature: 0` futás.
        self.kapott_mintavetelek: list[object] = []

    def ertelmez(
        self,
        mondat: str,
        *,
        most: str,
        kontextus: ErtelmezesKontextus,
        mintavetel=None,
    ) -> dict:
        self.kapott_mondatok.append(mondat)
        self.kapott_kontextusok.append(kontextus)
        self.kapott_mintavetelek.append(mintavetel)
        return self.valasz


def _kaszkad(llm=None) -> ForditottKaszkadErtelmezo:
    return ForditottKaszkadErtelmezo(SzabalyAlapuErtelmezo(), llm)


def _ertelmez(kaszkad, mondat, megorzott=None, elozmenyek=None):
    return kaszkad.ertelmez(
        mondat,
        most=_MOST,
        kontextus=ErtelmezesKontextus(
            megorzott_parameterek=megorzott or {}, elozmenyek=elozmenyek or []
        ),
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
    eredmeny = _ertelmez(_kaszkad(llm), "csütörtökön vagy szerdán")

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


# --- a beszélgetés a bemenet, a kontextus csak tartalék (ADR-019) -----


def test_a_beszelgetes_atmegy_az_ertelmezonek():
    """A kaszkád nem nyeli el az előzményeket — a modell azt kapja, amit
    a hívó adott."""
    llm = _FakeLLM({"eszkoz": "szabad_idopontok", "parameterek": {"bolt_id": "szundi"}})
    elozmenyek = [(KI_VASARLO, "Szundihoz mennék"), (KI_RENDSZER, "Nincs szabad időpont.")]

    _ertelmez(_kaszkad(llm), "és holnap?", elozmenyek=elozmenyek)

    assert llm.kapott_kontextusok[0].elozmenyek == elozmenyek


def test_elozmeny_nelkul_a_megorzott_bolt_kitolt():
    """Tartalék-ág: a modell nem látta a beszélgetést, ezért a megőrzött
    bolt kitölthet — különben újra rákérdeznénk arra, amit tudunk."""
    llm = _FakeLLM({"eszkoz": "szabad_idopontok", "parameterek": {"datum_kifejezes": "holnap"}})

    eredmeny = _ertelmez(_kaszkad(llm), "és holnap?", megorzott={"bolt_id": "torpilla"})

    assert eredmeny["parameterek"]["bolt_id"] == "torpilla"


def test_elozmennyel_a_modell_ures_mezoje_eros():
    """ADR-019 magja: ha a modell LÁTTA a beszélgetést, és mégis üresen
    hagyta a boltot, az a DÖNTÉSE — a beszélgetésből nyilván az derült
    ki, hogy a korábbi bolt már nem érvényes ("és bármelyik másik
    boltban?"). A megőrzött értéket ilyenkor NEM csempésszük vissza:
    pontosan ez az a hiba, amiért korábban külön elengedés-hívás kellett."""
    llm = _FakeLLM({"eszkoz": "szabad_idopontok", "parameterek": {}})

    eredmeny = _ertelmez(
        _kaszkad(llm),
        "és bármelyik másik boltban?",
        megorzott={"bolt_id": "ugyifogyi"},
        elozmenyek=[(KI_VASARLO, "Petárdázni szeretnék kedden.")],
    )

    assert eredmeny["eszkoz"] == "visszakerdez"
    assert eredmeny["parameterek"]["hianyzo_mezo"] == "bolt_id"


def test_elozmennyel_a_modell_altal_megadott_bolt_ervenyes():
    """Az ellenpár: ha a modell a beszélgetésből kiolvasta a boltot, azt
    használjuk — nem kell hozzá megőrzött paraméter."""
    llm = _FakeLLM(
        {
            "eszkoz": "szabad_idopontok",
            "parameterek": {"bolt_id": "torpilla", "datum_kifejezes": "holnap"},
        }
    )

    eredmeny = _ertelmez(
        _kaszkad(llm),
        "és holnap?",
        elozmenyek=[(KI_VASARLO, "Törpillához mennék")],
    )

    assert eredmeny["parameterek"]["bolt_id"] == "torpilla"
    assert eredmeny["parameterek"]["datum_tol"] == "2026-08-18T00:00:00Z"


def test_elozmennyel_a_modell_visszakerdezese_kimegy():
    """A tartalék-kapu is csak előzmény NÉLKÜL segít: ha a modell látta
    a beszélgetést és a boltra kérdez, az érvényes visszakérdezés."""
    llm = _FakeLLM(
        {
            "eszkoz": "visszakerdez",
            "parameterek": {"hianyzo_mezo": "bolt_id", "varhato_kerdes_tipusa": "zart"},
        }
    )

    eredmeny = _ertelmez(
        _kaszkad(llm),
        "mindegy melyik bolt, csak legyen hely",
        megorzott={"bolt_id": "szundi"},
        elozmenyek=[(KI_VASARLO, "Szeretnék időpontot a Szundiba szerdára.")],
    )

    assert eredmeny["eszkoz"] == "visszakerdez"
    assert eredmeny["parameterek"]["hianyzo_mezo"] == "bolt_id"


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


def test_a_modell_visszakerdezese_nem_megy_ki_ha_a_kontextus_ismeri_a_boltot():
    """KONTEXTUS-KAPU: a modell minden fordulót nulláról lát, ezért egy
    alkudozó follow-up mondatra a boltra kérdezne rá — arra, amit a
    beszélgetés már tisztázott. Amit determinisztikusan tudunk, arra nem
    kérdezünk vissza."""
    llm = _FakeLLM(
        {
            "eszkoz": "visszakerdez",
            "parameterek": {"hianyzo_mezo": "bolt_id", "varhato_kerdes_tipusa": "zart"},
        }
    )
    eredmeny = _ertelmez(
        _kaszkad(llm), "talán jövő héten, még nem tudom biztosan", megorzott={"bolt_id": "szundi"}
    )

    assert eredmeny["eszkoz"] == "szabad_idopontok"
    assert eredmeny["parameterek"]["bolt_id"] == "szundi"
    assert eredmeny["parameterek"]["datum_tol"] == "2026-08-24T00:00:00Z"


def test_a_visszakerdezes_megmarad_ha_a_bolt_tenyleg_ismeretlen():
    """A kontextus-kapu ellenpárja: üres kontextusnál a visszakérdezés a
    HELYES válasz, nem szabad találgatásra váltani."""
    llm = _FakeLLM(
        {
            "eszkoz": "visszakerdez",
            "parameterek": {"hianyzo_mezo": "bolt_id", "varhato_kerdes_tipusa": "zart"},
        }
    )
    eredmeny = _ertelmez(_kaszkad(llm), "valamikor mennék")

    assert eredmeny["eszkoz"] == "visszakerdez"
    assert eredmeny["parameterek"]["hianyzo_mezo"] == "bolt_id"


def test_a_datum_a_mondatbol_potlodik_ha_a_modell_nem_idezett():
    """Amit determinisztikusan LÁTUNK a mondatban, ne vesszen el csak
    azért, mert a modell kihagyta — különben a vásárlónak egy
    visszakérdezés után újra el kellene mondania a napot."""
    llm = _FakeLLM(
        {
            "eszkoz": "visszakerdez",
            "parameterek": {"hianyzo_mezo": "bolt_id", "varhato_kerdes_tipusa": "zart"},
        }
    )
    eredmeny = _ertelmez(_kaszkad(llm), "Szeretnék bemenni a boltba holnap délelőtt.")

    assert eredmeny["parameterek"]["datum_tol"] == "2026-08-18T00:00:00Z"
    assert eredmeny["parameterek"]["napszak"] == "delelott"


def test_a_modell_datuma_nyer_a_mondat_egesze_folott():
    """A pótlás CSAK akkor lép be, ha a modell semmit nem idézett — nem
    bírálja felül a modell (feloldható) kifejezését."""
    llm = _FakeLLM(
        {
            "eszkoz": "szabad_idopontok",
            "parameterek": {"bolt_id": "szundi", "datum_kifejezes": "szerdán"},
        }
    )
    eredmeny = _ertelmez(_kaszkad(llm), "szerdán jó lenne, holnap semmiképp")

    assert eredmeny["parameterek"]["datum_tol"] == "2026-08-19T00:00:00Z"


def test_preferalt_ora_a_mondatbol_potlodik_ha_a_modell_kihagyta():
    llm = _FakeLLM(
        {
            "eszkoz": "szabad_idopontok",
            "parameterek": {"bolt_id": "ugyifogyi", "datum_kifejezes": "holnap"},
        }
    )
    eredmeny = _ertelmez(_kaszkad(llm), "Van hely holnap délelőtt? Kb 10 körül lenne jó")

    assert eredmeny["parameterek"]["preferalt_ora"] == 10


def test_szolgaltatas_a_mondatbol_potlodik_ha_a_modell_kihagyta():
    """A méret zárt halmaz és determinisztikusan kinyerhető — a modell
    kihagyása nem jelenti, hogy nincs is a mondatban."""
    llm = _FakeLLM(
        {
            "eszkoz": "szabad_idopontok",
            "parameterek": {"bolt_id": "ugyifogyi", "datum_kifejezes": "kedd"},
        }
    )
    eredmeny = _ertelmez(_kaszkad(llm), "Szeretnék időpontot kedden nagy petárdához.")

    assert eredmeny["parameterek"]["szolgaltatas_id"] == "nagy_petarda"


# --- nem blokkoló mezőre nem kérdezünk vissza -------------------------


def test_szolgaltatasra_nem_kerdezunk_vissza_hanem_keresunk():
    """A méret nem blokkoló mező: a keresés elindulhat a bolt szintjén.
    Ha a modell mégis erre kérdezne, az ÉRTÉKÉT is eldobjuk — ha ő maga
    mondja, hogy hiányzik, akkor nem használható."""
    llm = _FakeLLM(
        {
            "eszkoz": "visszakerdez",
            "parameterek": {
                "hianyzo_mezo": "szolgaltatas_id",
                "varhato_kerdes_tipusa": "zart",
                "bolt_id": "ugyifogyi",
                "szolgaltatas_id": "nagy_petarda",
            },
        }
    )
    eredmeny = _ertelmez(_kaszkad(llm), "mindegy milyen méret")

    assert eredmeny["eszkoz"] == "szabad_idopontok"
    assert eredmeny["parameterek"]["bolt_id"] == "ugyifogyi"
    assert "szolgaltatas_id" not in eredmeny["parameterek"]


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


def test_kapuor_a_modell_elott_dont_es_a_modell_meg_sem_szolal():
    """ADR-020: a hatókör-döntés a modell ELŐTT fut, és kívül eső
    kérésnél a modellt meg sem hívjuk.

    A hamis modell itt szándékosan olyan választ adna, ami helytelen
    lenne (keresés egy időjárás-kérdésre) — a teszt épp azt bizonyítja,
    hogy ez a válasz meg sem születik: a `hivasok` számláló nulla
    marad."""
    llm = _FakeLLM({"eszkoz": "szabad_idopontok", "parameterek": {"bolt_id": "szundi"}})
    kaszkad = _kaszkad(llm)
    eredmeny = _ertelmez(kaszkad, "Milyen idő lesz holnap?")

    assert eredmeny["eszkoz"] == "nincs"
    assert eredmeny["kapuor_ok"] == "idojaras"
    assert kaszkad.utolso_reteg == "kapuor"
    assert llm.kapott_mondatok == []


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


# --- zárt kérdésre adott gombnyomás: nincs modellhívás ----------------


def test_bolt_slug_onmagaban_nem_megy_a_modellhez():
    """Zárt kérdésre adott gombnyomás (`ui/vasarlo.py` a
    `valaszthato_ertekek` egyik elemét küldi vissza új fordulóként) —
    ez zárt halmazbeli érték, nem szabad szöveg. A végigjátszás
    megfogta, hogy a modell a puszta "torpilla" szóra ÚJRA
    visszakérdezett a boltra, vagyis az akadálymentes gombos út
    modellel használhatatlan volt."""
    llm = _FakeLLM(
        {
            "eszkoz": "visszakerdez",
            "parameterek": {"hianyzo_mezo": "bolt_id", "varhato_kerdes_tipusa": "zart"},
        }
    )
    kaszkad = _kaszkad(llm)

    eredmeny = _ertelmez(kaszkad, "torpilla")

    assert eredmeny["eszkoz"] == "szabad_idopontok"
    assert eredmeny["parameterek"]["bolt_id"] == "torpilla"
    assert kaszkad.utolso_reteg == "szabaly"
    assert llm.kapott_mondatok == []


def test_bolt_nev_onmagaban_sem_megy_a_modellhez():
    llm = _FakeLLM({"eszkoz": "nincs", "parameterek": {}})
    kaszkad = _kaszkad(llm)

    eredmeny = _ertelmez(kaszkad, "Ügyifogyi")

    assert eredmeny["parameterek"]["bolt_id"] == "ugyifogyi"
    assert llm.kapott_mondatok == []


def test_a_zart_valasz_kapu_megorzi_a_korabbi_datumot():
    """A gombnyomás előtti fordulóban felismert dátum nem veszhet el —
    a determinisztikus réteg a kontextusból viszi tovább."""
    llm = _FakeLLM({"eszkoz": "nincs", "parameterek": {}})
    eredmeny = _ertelmez(
        _kaszkad(llm),
        "torpilla",
        megorzott={"datum_tol": "2026-08-18T00:00:00Z", "datum_ig": "2026-08-18T23:59:59Z"},
    )

    assert eredmeny["parameterek"]["datum_tol"] == "2026-08-18T00:00:00Z"


def test_bolt_nev_mondatban_tovabbra_is_a_modellhez_megy():
    """A kapu CSAK a teljes sztring-egyezésre szól — egy boltnevet
    TARTALMAZÓ mondat továbbra is a modellé."""
    llm = _FakeLLM(
        {
            "eszkoz": "szabad_idopontok",
            "parameterek": {"bolt_id": "torpilla", "datum_kifejezes": "holnap"},
        }
    )
    kaszkad = _kaszkad(llm)

    _ertelmez(kaszkad, "Törpillához mennék holnap")

    assert kaszkad.utolso_reteg == "llm"
    assert llm.kapott_mondatok


def test_a_bolt_info_kerdestipust_a_szabaly_dontheti_el():
    """A `mit` az EGYETLEN mező, ahol a szabály felülírja a modellt: egy
    rossz kérdéstípus nem hiányzó adat, hanem MÁS kérdésre adott válasz
    szerkesztett bolti adattal. A végigjátszás megfogta, hogy a "Hogy
    néz ki…" kérdésre előbb az árat, majd a címet olvasta fel."""
    llm = _FakeLLM({"eszkoz": "bolt_info", "parameterek": {"bolt_id": "torpilla", "mit": "cim"}})
    eredmeny = _ertelmez(_kaszkad(llm), "Hogy néz ki a Törpilla bolt?")

    assert eredmeny["parameterek"]["mit"] == "megjelenes"


def test_a_modell_mit_mezoje_marad_ha_a_szabaly_nem_ismeri_fel_a_kerdest():
    """A felülírás CSAK pozitív szabály-találatra szól — ha a szabály
    nem ismeri fel a kérdéstípust, a modellé a döntés."""
    llm = _FakeLLM({"eszkoz": "bolt_info", "parameterek": {"bolt_id": "torpilla", "mit": "termek"}})
    eredmeny = _ertelmez(_kaszkad(llm), "Na és a Törpillánál?")

    assert eredmeny["parameterek"]["mit"] == "termek"


# --- a dátum az AKTUÁLIS mondatból való (ADR-019) ---------------------


def test_korabbi_fordulobol_idezett_datumot_eldobunk():
    """A modell a teljes beszélgetést látja, és hajlamos egy KORÁBBI
    forduló napját is beírni. A szándék-rétegzés szerint viszont a puha
    rész minden fordulóban frissen dől el — az utolsó mondat felülírja a
    korábbit, nem kiegészíti."""
    llm = _FakeLLM(
        {
            "eszkoz": "szabad_idopontok",
            "parameterek": {
                "bolt_id": "ugyifogyi",
                "datum_kifejezes": "jövő héten",
                "datum_kifejezes_2": "kedden",  # ez az ELŐZŐ fordulóból van
            },
        }
    )

    eredmeny = _ertelmez(
        _kaszkad(llm),
        "bármikor a jövő héten",
        elozmenyek=[(KI_VASARLO, "Szeretnék petárdázni kedden délelőtt.")],
    )

    assert eredmeny["parameterek"]["datum_tol"] == "2026-08-24T00:00:00Z"
    assert eredmeny["parameterek"]["datum_ig"] == "2026-08-30T23:59:59Z"


def test_ket_kifejezes_egy_mondatbol_tovabbra_is_osszevonodik():
    """Az ellenpróba: ha MINDKÉT idézet az aktuális mondatból való, a
    vagylagos ablak-összevonás változatlanul működik."""
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

    eredmeny = _ertelmez(
        _kaszkad(llm),
        "ha van hely szerdán, ha nincs, akkor csütörtök",
        elozmenyek=[(KI_VASARLO, "Szeretnék időpontot a Szundiba.")],
    )

    assert eredmeny["parameterek"]["datum_tol"] == "2026-08-19T00:00:00Z"
    assert eredmeny["parameterek"]["datum_ig"] == "2026-08-20T23:59:59Z"


def test_toldalekolt_alak_meg_elfogadott_idezet():
    """A magyar toldalékolás a kapu kedvére dolgozik: a rövidebb idézet
    ("péntek") részszövege az inflektáltnak ("pénteken")."""
    llm = _FakeLLM(
        {
            "eszkoz": "szabad_idopontok",
            "parameterek": {"bolt_id": "ugyifogyi", "datum_kifejezes": "jövő hét péntek"},
        }
    )

    eredmeny = _ertelmez(_kaszkad(llm), "és jövő héten pénteken?")

    assert eredmeny["parameterek"]["datum_tol"] == "2026-08-28T00:00:00Z"


def test_korabbi_fordulo_napszaka_nem_szivarog_at():
    """A napszak is a PUHA rész: a "kedden délelőtt" → "bármikor a jövő
    héten" menetben a délelőtt némán leszűkítette a kitágított ablakot."""
    llm = _FakeLLM(
        {
            "eszkoz": "szabad_idopontok",
            "parameterek": {
                "bolt_id": "ugyifogyi",
                "datum_kifejezes": "jövő héten",
                "napszak": "delelott",  # az ELŐZŐ fordulóból
            },
        }
    )

    eredmeny = _ertelmez(
        _kaszkad(llm),
        "bármikor a jövő héten",
        elozmenyek=[(KI_VASARLO, "Szeretnék petárdázni kedden délelőtt.")],
    )

    assert eredmeny["parameterek"]["napszak"] == "barmikor"
    assert eredmeny["parameterek"]["datum_ig"] == "2026-08-30T23:59:59Z"


def test_a_modell_napszak_dontese_megmarad_ha_a_mondat_beszel_rola():
    """A DÖNTÉST nem vesszük el: ha a mondatban két napszak-szó is van,
    a modell választása érvényes — épp ez a tükörpár lényege."""
    llm = _FakeLLM(
        {
            "eszkoz": "szabad_idopontok",
            "parameterek": {
                "bolt_id": "ugyifogyi",
                "datum_kifejezes": "holnap",
                "napszak": "delutan",
            },
        }
    )

    eredmeny = _ertelmez(
        _kaszkad(llm), "A petárdáshoz azért délután mennék holnap, mert délelőtt dolgozom."
    )

    assert eredmeny["parameterek"]["napszak"] == "delutan"
    assert eredmeny["parameterek"]["datum_ig"] == "2026-08-18T17:59:59Z"

"""A CSÚSZÓ ELŐZMÉNY-ABLAK egységtesztjei (`assistant/interpreter/
ablak.py`, ADR-025).

Amit ez a fájl bizonyít, három állítás:

1. az ablak **rövidít** — a régebbi fordulók nem sorról sorra mennek át;
2. az ablak **nem felejt** — a levágott fordulókban kimondott bolt, a
   szolgáltatás és az ELENGEDETT mező az összefoglaló sorban túléli
   (ez a különbség a puszta vágáshoz képest);
3. az ablak **nem szivárogtat időpontot** — a levágott napok „eddig
   keresett"-ként jelennek meg, és a modell dátum-kapuja
   (`forditott_kaszkad._mondatbeli_kifejezes`) amúgy sem engedne át
   onnan idézetet.
"""

from __future__ import annotations

from assistant.interpreter import KI_RENDSZER, KI_VASARLO, ErtelmezesKontextus, ablak
from assistant.interpreter.llm_based import beszelgetes_szovege
from assistant.tools.katalogus import MINDEGY
from assistant.valasz import sablonok

MOST = "2026-08-17T09:00:00Z"  # hétfő


def _beszelgetes(fordulok: int) -> list[tuple[str, str]]:
    """N fordulós beszélgetés: minden fordulóban egy vásárlói és egy
    rendszer-sor."""
    sorok: list[tuple[str, str]] = []
    for i in range(fordulok):
        sorok.append((KI_VASARLO, f"{i}. kérdés"))
        sorok.append((KI_RENDSZER, f"{i}. válasz"))
    return sorok


# -- fordulókra bontás -------------------------------------------------


def test_a_rendszer_sorai_az_elottuk_allo_vasarloi_sorhoz_tartoznak():
    """Egy fordulóban a rendszer több sort is írhat (nyugtázó,
    eredmény, felajánlott időpontok) — ezért fordulót számolunk, nem
    sort."""
    fordulok = ablak.fordulokra_bont(
        [
            (KI_VASARLO, "Szundihoz mennék"),
            (KI_RENDSZER, "Keresem"),
            (KI_RENDSZER, "Felajánlott időpontok: 1. hétfő 8:00"),
            (KI_VASARLO, "a másodikat"),
        ]
    )

    assert len(fordulok) == 2
    assert len(fordulok[0]) == 3
    assert fordulok[1] == [(KI_VASARLO, "a másodikat")]


def test_a_vasarloi_sor_elotti_rendszer_sor_kulon_fordulo():
    fordulok = ablak.fordulokra_bont([(KI_RENDSZER, "Szia!"), (KI_VASARLO, "Szia")])

    assert fordulok == [[(KI_RENDSZER, "Szia!")], [(KI_VASARLO, "Szia")]]


# -- rövidítés ---------------------------------------------------------


def test_negy_fordulonal_rovidebb_beszelgetes_valtozatlanul_megy_at():
    """Az ablak alatt nincs viselkedésváltozás: a rövid beszélgetések
    ugyanúgy futnak, mint az ADR-025 előtt, és a mérésük
    összehasonlítható marad."""
    elozmenyek = _beszelgetes(4)

    osszefoglalo, sorok = ablak.ablakol(elozmenyek, most=MOST, fordulo=4)

    assert osszefoglalo is None
    assert sorok == elozmenyek


def test_husz_fordulobol_negy_megy_at_szo_szerint():
    elozmenyek = _beszelgetes(20)

    _, sorok = ablak.ablakol(elozmenyek, most=MOST, fordulo=4)

    assert sorok == elozmenyek[-8:]  # 4 forduló × (vásárló + rendszer)


def test_kikapcsolt_ablak_mindent_szo_szerint_ad():
    """A mérési alapvonal (`APRAJAFALVA_ABLAK_FORDULO=0`): enélkül nem
    lehetne megmondani, mennyit rövidít az ablak."""
    elozmenyek = _beszelgetes(20)

    osszefoglalo, sorok = ablak.ablakol(elozmenyek, most=MOST, fordulo=ablak.ABLAK_KI)

    assert osszefoglalo is None
    assert sorok == elozmenyek


# -- nem felejt --------------------------------------------------------


def test_a_levagott_forduloban_kimondott_bolt_tullel_az_osszefoglaloban():
    """A puszta vágás ELVESZÍTETTE a legelső mondatban kimondott
    boltot. Ez a teszt pontosan azt a különbséget méri, amiért az
    összefoglaló egyáltalán van."""
    elozmenyek = [
        (KI_VASARLO, "A Szundi boltba szeretnék időpontot."),
        (KI_RENDSZER, "Melyik napra?"),
        *_beszelgetes(6),
    ]

    osszefoglalo, sorok = ablak.ablakol(elozmenyek, most=MOST, fordulo=4)

    assert osszefoglalo is not None
    assert "bolt=szundi" in osszefoglalo
    assert all("Szundi" not in szoveg for _, szoveg in sorok)


def test_az_elengedett_mezo_kulon_jelolve_jelenik_meg():
    """A MINDEGY nem érték a többi között: az `elengedve` és a konkrét
    slug két különböző állítás (ADR-024). Ha az összefoglaló ezt
    összemosná, a levágott részen visszaállna a kétállapotú világ, és a
    rendszer újra rákérdezne arra, amit a vásárló elengedett."""
    elozmenyek = [
        (KI_VASARLO, "Ügyifogyi, bármelyik petárda jó."),
        *_beszelgetes(6),
    ]

    osszefoglalo, _ = ablak.ablakol(
        elozmenyek,
        most=MOST,
        megorzott_parameterek={"bolt_id": "ugyifogyi", "szolgaltatas_id": MINDEGY},
        fordulo=4,
    )

    assert "szolgaltatas_id=ELENGEDVE" in osszefoglalo
    assert "szolgáltatás=" not in osszefoglalo, "az elengedett mező NEM konkrét értékként megy"


def test_a_megorzott_ertek_kitolti_amit_a_szoveg_nem_ad():
    elozmenyek = [(KI_VASARLO, "Jó napot!"), *_beszelgetes(6)]

    osszefoglalo, _ = ablak.ablakol(
        elozmenyek, most=MOST, megorzott_parameterek={"bolt_id": "torpilla"}, fordulo=4
    )

    assert "bolt=torpilla" in osszefoglalo


def test_a_sikertelen_keresesek_szama_a_rendszer_soraibol_johet():
    """A számot a rendszer TÉNYLEGES mondataira mérjük (`sablonok.py`),
    nem egy kézzel másolt szövegre — egy átfogalmazás így a tesztet
    buktatja, nem a számlálást rontja el némán."""
    nincs_hely = sablonok.SABLONOK["hu"]["hiba"]["nincs_szabad_hely_az_ablakban"]
    elozmenyek = [
        (KI_VASARLO, "Szundi, kedden"),
        (KI_RENDSZER, nincs_hely),
        (KI_VASARLO, "és szerdán?"),
        (KI_RENDSZER, nincs_hely),
        *_beszelgetes(5),
    ]

    osszefoglalo, _ = ablak.ablakol(elozmenyek, most=MOST, fordulo=4)

    assert "üresen tért vissza 2 keresés" in osszefoglalo


def test_a_beszelheto_valasz_is_sikertelen_keresesnek_szamit():
    beszelheto = sablonok.SABLONOK["hu"]["beszelheto"]["hiba"]["nincs_szabad_hely_az_ablakban"]
    elozmenyek = [
        (KI_VASARLO, "Szundi, kedden"),
        (KI_RENDSZER, beszelheto),
        *_beszelgetes(6),
    ]

    osszefoglalo, _ = ablak.ablakol(elozmenyek, most=MOST, fordulo=4)

    assert "üresen tért vissza 1 keresés" in osszefoglalo


def test_a_levagott_napok_eddig_keresettkent_jelennek_meg():
    """Az időablak az összefoglalóban MÚLT IDŐ: „eddig keresett napok".
    Nem kérés — a kérést mindig az utolsó mondat adja, és a
    dátum-kapu ezt ki is kényszeríti."""
    elozmenyek = [
        (KI_VASARLO, "Szundihoz mennék kedden."),
        *_beszelgetes(6),
    ]

    osszefoglalo, _ = ablak.ablakol(elozmenyek, most=MOST, fordulo=4)

    assert "eddig keresett napok: 2026-08-18" in osszefoglalo


def test_ures_osszefoglalobol_nem_lesz_promptsor():
    """Tartalom nélküli összefoglaló csak tokent visz, jelentést nem."""
    osszefoglalo, _ = ablak.ablakol(_beszelgetes(20), most=MOST, fordulo=4)

    assert osszefoglalo is None


# -- a promptba illesztett alak ----------------------------------------


def test_a_promptban_az_osszefoglalo_all_elol():
    kontextus = ErtelmezesKontextus(
        elozmenyek=[(KI_VASARLO, "A Törpillához mennék."), *_beszelgetes(6)]
    )

    szoveg, van_osszefoglalo = beszelgetes_szovege(kontextus, "és holnap?", most=MOST)

    assert van_osszefoglalo is True
    assert szoveg.startswith("Összefoglaló (")
    assert szoveg.endswith("Vásárló: és holnap?")


def test_rovid_beszelgetesnel_nincs_osszefoglalo_es_nincs_utmutato():
    kontextus = ErtelmezesKontextus(elozmenyek=[(KI_VASARLO, "A Törpillához mennék.")])

    szoveg, van_osszefoglalo = beszelgetes_szovege(kontextus, "és holnap?", most=MOST)

    assert van_osszefoglalo is False
    assert szoveg == "Vásárló: A Törpillához mennék.\nVásárló: és holnap?"


def test_elozmeny_nelkul_csak_a_mondat_megy():
    szoveg, van_osszefoglalo = beszelgetes_szovege(
        ErtelmezesKontextus(), "Szundihoz mennék holnap", most=MOST
    )

    assert szoveg == "Szundihoz mennék holnap"
    assert van_osszefoglalo is False


# -- a környezeti kapcsoló ---------------------------------------------


def test_a_kornyezeti_valtozo_allitja_az_ablakot(monkeypatch):
    monkeypatch.setenv("APRAJAFALVA_ABLAK_FORDULO", "2")
    assert ablak.fordulo_max() == 2


def test_ertelmetlen_kornyezeti_ertek_az_alapertelmezest_hagyja(monkeypatch):
    """Egy elgépelt környezeti változó ne csendben változtassa meg a
    viselkedést — az a legrosszabb fajta mérési hiba."""
    monkeypatch.setenv("APRAJAFALVA_ABLAK_FORDULO", "négy")
    assert ablak.fordulo_max() == ablak.ALAP_FORDULO

    monkeypatch.setenv("APRAJAFALVA_ABLAK_FORDULO", "-3")
    assert ablak.fordulo_max() == ablak.ALAP_FORDULO

"""AZ ÁLLAPOTVEZÉRELT DISZPÉCSER egységtesztjei (`assistant/
allapotgep.py`, ADR-028).

Három állítást őriznek:

1. **az átmenetek zártak** — ami nincs engedélyezve, az nem történhet
   meg csendben (naplózva a biztonságos `INDULAS`-ba tér);
2. **az állapot a VÁLASZ típusából dől el** — ugyanabból, amit a felület
   is lát, tehát a kettő nem csúszhat szét;
3. **az állapotsor helyzetet ír le, nem utasítást ad** — és csak ott
   szólal meg, ahol tényleg van mit mondani.
"""

from __future__ import annotations

import pytest

from assistant import allapotgep as a

# -- az állapot levezetése a válaszból ---------------------------------


@pytest.mark.parametrize(
    ("valasz_tipus", "varhato"),
    [
        ("ajanlat", a.AJANLAT_VAR),
        ("megerositest_ker", a.MEGEROSITES_VAR),
        ("visszakerdezes", a.HIANYZO_ADAT),
        ("kiut", a.KIUT),
        ("visszaigazolas", a.KESZ),
        ("elvetve", a.AJANLAT_VAR),
    ],
)
def test_a_valasz_tipusa_hatarozza_meg_az_allapotot(valasz_tipus, varhato):
    assert a.kovetkezo_allapot(a.INDULAS, {"tipus": valasz_tipus}) == varhato


@pytest.mark.parametrize("tipus", ["elutasitas", "eszkoz_hiba", "hiba", "meta_valasz"])
def test_az_elharitas_es_a_hiba_nem_mozditja_az_allapotot(tipus):
    """KÖZBEVETETT KÉRDÉS (beszédhelyzetek halmaz, `kozbevetes` réteg):
    a vásárló a foglalás közepén mást kérdez, aztán ugyanoda tér vissza.
    Ha ilyenkor elveszne az `AJANLAT_VAR`, a felajánlott időpontokra
    utána már nem lehetne hivatkozni."""
    assert a.kovetkezo_allapot(a.AJANLAT_VAR, {"tipus": tipus}) == a.AJANLAT_VAR


def test_a_tenyvalasz_sem_mozdit():
    assert a.kovetkezo_allapot(a.MEGEROSITES_VAR, {"sikeres": True, "cim": "Fő utca 7."}) == (
        a.MEGEROSITES_VAR
    )


def test_ismeretlen_valasztipusnal_marad_az_allapot():
    """A hallgatás itt kevesebb kárt okoz, mint egy találgatott
    átmenet."""
    assert a.kovetkezo_allapot(a.AJANLAT_VAR, {"tipus": "valami_uj"}) == a.AJANLAT_VAR


# -- az átmenetek zártsága ---------------------------------------------


def test_minden_allapotbol_lehet_ujat_kezdeni():
    """A beszélgetés nem űrlap: a vásárló bármikor kezdhet új témát."""
    for allapot in a.ALLAPOTOK:
        assert a.atmenet(allapot, a.INDULAS) == a.INDULAS


def test_a_lezart_foglalas_utan_nincs_visszaut_a_megerositesre():
    """Egy már lefoglalt időpontot nem lehet „még egyszer"
    megerősíteni — a KESZ-ből csak új beszélgetés indulhat.

    A tiltás 2026-09-21 óta MARADÁST jelent, nem INDULAS-t (ADR-035):
    a foglalás akkor is megvan, ha közben valami furcsa történt."""
    assert a.MEGEROSITES_VAR not in a.ATMENETEK[a.KESZ]
    assert a.atmenet(a.KESZ, a.MEGEROSITES_VAR) == a.KESZ


def test_ajanlat_nelkul_nincs_megerosites():
    """Megerősítést csak felajánlott időpontra lehet kérni."""
    assert a.MEGEROSITES_VAR not in a.ATMENETEK[a.INDULAS]


def test_a_tiltott_atmenet_nem_dob_kivetelt(caplog):
    """Egy nem engedélyezett átmenet FEJLESZTŐI tévedés — a vásárló nem
    eshet ki tőle a beszélgetésből. De nem is néma: a naplóban ott van.

    **2026-09-21 óta MARAD az állapot, nem INDULAS-ba tér** (ADR-035):
    a beszélgetésben az a legdrágább, ha elfelejtjük, hol tartunk."""
    with caplog.at_level("WARNING"):
        eredmeny = a.atmenet(a.KESZ, a.MEGEROSITES_VAR)

    assert eredmeny == a.KESZ
    assert "nem engedélyezett állapotátmenet" in caplog.text


def test_az_AJANLAT_VAR_nem_megy_vissza_HIANYZO_ADATBA():
    """AZ IDEGEN PRÓBA 10. FORDULÓJA. A „Így nem haladunk előre.
    Miafasz van veled?" mondatra a rendszer visszakérdezett, hogy MELYIK
    BOLTBA szeretne menni — pedig két fordulóval korábban maga ajánlott
    fel időpontokat ugyanabban a boltban.

    Egy frusztrált mondat nem törli az ajánlatokat. Aki tényleg új
    adatot akar megadni, az új KÉRÉST mond."""
    assert a.HIANYZO_ADAT not in a.ATMENETEK[a.AJANLAT_VAR]
    assert a.atmenet(a.AJANLAT_VAR, a.HIANYZO_ADAT) == a.AJANLAT_VAR


def test_a_MEGEROSITES_VAR_sem_megy_vissza_HIANYZO_ADATBA():
    """Ugyanaz egy fokkal később: a „biztosan lefoglaljam?" kérdés után
    egy értelmezhetetlen mondat nem kezdheti elölről az adatgyűjtést."""
    assert a.HIANYZO_ADAT not in a.ATMENETEK[a.MEGEROSITES_VAR]
    assert a.atmenet(a.MEGEROSITES_VAR, a.HIANYZO_ADAT) == a.MEGEROSITES_VAR


def test_az_uj_keres_viszont_TOVABBVISZ():
    """A tiltás nem zárja be a beszélgetést: aki új kérést mond, annak
    az ajánlat (AJANLAT_VAR) vagy az új téma (INDULAS) jár."""
    assert a.atmenet(a.AJANLAT_VAR, a.AJANLAT_VAR) == a.AJANLAT_VAR
    assert a.atmenet(a.AJANLAT_VAR, a.INDULAS) == a.INDULAS
    assert a.atmenet(a.MEGEROSITES_VAR, a.KESZ) == a.KESZ


def test_minden_allapotnak_van_atmenet_szabalya():
    """Elgépelés-védelem: egy hiányzó kulcs azt jelentené, hogy abból az
    állapotból SEMMI nem engedélyezett — és minden átmenet csendben
    INDULAS-ba esne."""
    assert set(a.ATMENETEK) == set(a.ALLAPOTOK)
    for celok in a.ATMENETEK.values():
        assert celok <= set(a.ALLAPOTOK)


# -- az állapotsor -----------------------------------------------------


def test_az_ajanlat_sora_megmondja_hany_idopontot_ajanlottunk():
    sor = a.prompt_sor(a.AJANLAT_VAR, jeloltek_szama=3)

    assert sor is not None
    assert "AJANLAT_VAR" in sor
    assert "3 időpontot" in sor


def test_a_hianyzo_adat_sora_megnevezi_a_mezot():
    sor = a.prompt_sor(a.HIANYZO_ADAT, hianyzo_mezo="bolt_id")

    assert "bolt_id" in sor


def test_indulaskor_nincs_allapotsor():
    """Az üres beszélgetésről a hallgatás a pontos állítás — egy
    „Állapot: INDULAS" sor csak tokent vinne."""
    assert a.prompt_sor(a.INDULAS) is None


def test_ajanlat_jeloltek_nelkul_nincs_sor():
    """Ha nincs mire hivatkozni, ne állítsuk, hogy van."""
    assert a.prompt_sor(a.AJANLAT_VAR, jeloltek_szama=0) is None


def test_kikapcsolhato_a_meresert(monkeypatch):
    """A/B-zni csak úgy lehet, ha ugyanaz a kód fut az állapotsor
    nélkül is."""
    monkeypatch.setenv("APRAJAFALVA_ALLAPOT_SOR", "ki")
    assert a.bekapcsolva() is False
    assert a.prompt_sor(a.AJANLAT_VAR, jeloltek_szama=3) is None

    monkeypatch.setenv("APRAJAFALVA_ALLAPOT_SOR", "be")
    assert a.bekapcsolva() is True


def test_a_meta_valasz_a_lezart_foglalast_sem_rontja_el():
    """ÉLES PRÓBA (2026-09-05): a „csak a választ beszéled?" mondat a
    KESZ állapotból AJANLAT_VAR-ba rántotta vissza a beszélgetést, egy
    már lezárt foglalás után."""
    assert a.kovetkezo_allapot(a.KESZ, {"tipus": "meta_valasz"}) == a.KESZ

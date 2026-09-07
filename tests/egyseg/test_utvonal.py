"""AZ ÚTVONAL-NÉZŐ magyarázatai (`tools/utvonal.py`).

A nézet felület, de a lelke tiszta függvény: egy naplósorból mondatokat
csinál. Ezek a tesztek AZT őrzik, hogy a magyarázat a naplóban ÁLLÓ
mezőkre mutasson vissza, és ne találjon ki semmit — mert egy elemző
eszköz, ami sejt, rosszabb, mint amelyik hallgat.
"""

from __future__ import annotations

import pytest

from tools.utvonal import (
    Lepes,
    beszelgetes_szovege,
    hova_tovabb,
    lepes_szovege,
    mi_tortent,
    miert,
    sessionokra_bont,
    szures,
)


def _sor(**mezok) -> dict:
    alap = {
        "idobelyeg": "2026-09-07T15:00:00Z",
        "session_id": "aaaa1111",
        "bemenet": "Törpillához mennék holnap",
        "reteg": "llm",
        "eszkoz": "szabad_idopontok",
        "parameterek": {"bolt_id": "torpilla"},
        "valasz_tipus": "ajanlat",
        "nyomkovetes": {"modellhivas_db": 1},
    }
    alap.update(mezok)
    return alap


def _lepes(**mezok) -> Lepes:
    return Lepes(sorszam=1, sor=_sor(**mezok))


# -- session-bontás ----------------------------------------------------


def test_a_session_id_szerint_bont():
    sorok = [_sor(session_id="a"), _sor(session_id="a"), _sor(session_id="b")]

    beszelgetesek = sessionokra_bont(sorok)

    assert [len(b.lepesek) for b in beszelgetesek] == [2, 1]
    assert not any(b.becsult for b in beszelgetesek)


def test_session_id_nelkul_az_IDOKOZ_dont_es_ezt_bevalljuk():
    """A 2026-09-21 előtti sorokban nincs azonosító. Csoportosítunk, de
    a becsült határ nem ugyanaz a bizonyíték, mint egy azonosító —
    ezért kapja meg a `becsult` jelet."""
    sorok = [
        _sor(session_id=None, idobelyeg="2026-09-07T15:00:00Z"),
        _sor(session_id=None, idobelyeg="2026-09-07T15:01:00Z"),
        _sor(session_id=None, idobelyeg="2026-09-07T15:40:00Z"),
    ]

    beszelgetesek = sessionokra_bont(sorok)

    assert [len(b.lepesek) for b in beszelgetesek] == [2, 1]
    assert all(b.becsult for b in beszelgetesek)


def test_a_vegkimenetel_a_LEGTOBBET_mondo_fordulobol_jon():
    """Nem a legutolsó forduló típusa: egy létrejött foglalás akkor is a
    végkimenetel, ha utána még elhangzott valami."""
    sorok = [
        _sor(valasz_tipus="ajanlat"),
        _sor(valasz_tipus="visszaigazolas"),
        _sor(valasz_tipus="meta_valasz"),
    ]

    assert sessionokra_bont(sorok)[0].vegkimenetel == "foglalás létrejött"


def test_szures_az_azonosito_ELEJE_alapjan():
    """Egy 32 karakteres UUID-t nem gépel be senki."""
    beszelgetesek = sessionokra_bont([_sor(session_id="abcdef123456")])

    assert len(szures(beszelgetesek, "abcd")) == 1
    assert szures(beszelgetesek, "zzz") == []


# -- „miért oda ment tovább" -------------------------------------------


def test_a_kapuor_dontese_az_elso_mondat():
    lepes = _lepes(
        reteg="kapuor",
        nyomkovetes={
            "modellhivas_db": 0,
            "kapuor": {"kategoria": "hatokoron_kivul", "ok": "ar_kerdes", "minta": "mennyibe"},
        },
    )

    mondatok = miert(lepes)

    assert "hatokoron_kivul" in mondatok[0]
    assert "ar_kerdes" in mondatok[0]
    assert "modell" in mondatok[0], "azt is mondja ki, hogy a modell nem szólalt meg"


def test_az_atengedes_is_dontes():
    """A „nem történt semmi" is információ: a kapuőr MEGNÉZTE a
    mondatot, és foglalási szándéknak látta."""
    lepes = _lepes(nyomkovetes={"modellhivas_db": 1, "kapuor": {"kategoria": "foglalasi_szandek"}})

    assert "ÁTENGEDTE" in miert(lepes)[0]


def test_a_datum_versenyet_kimondja():
    """Ez az a pont, ahol a legtöbbet lehet tévedni (ADR-011): mit adott
    a modell, mit a parser, és MELYIK nyert."""
    lepes = _lepes(
        nyomkovetes={
            "modellhivas_db": 1,
            "datum": {
                "modell_kifejezes": "jövő héten",
                "parser_tol": "2026-12-28T00:00:00Z",
                "parser_ig": "2027-01-03T23:59:59Z",
                "nyertes": "parser (a modell idézetéből)",
            },
        }
    )

    egyben = " ".join(miert(lepes))

    assert "jövő héten" in egyben
    assert "parser (a modell idézetéből)" in egyben
    assert "2026-12-28" in egyben


def test_a_tartalek_ablak_nem_kitalalt_datum():
    """Külön mondat jár neki: ez nem kudarc, hanem BEVALLOTT
    hiánypótlás — a golden mérés is így különbözteti meg."""
    lepes = _lepes(
        nyomkovetes={"modellhivas_db": 1, "datum": {"nyertes": "nincs feloldható dátum"}}
    )

    egyben = " ".join(miert(lepes))

    assert "tartalék" in egyben
    assert "nem kitalált" in egyben


def test_modellhivas_nelkul_nem_beszelunk_modell_bizonyossagrol():
    """A rövidzárak 1.0-t írnak be, mert determinisztikusan biztosak.
    Ezt „a modell magabiztos volt" mondattal visszaadni hazugság lenne:
    modell nem is futott."""
    lepes = _lepes(
        reteg="orchestrator:sorszam",
        bizonyossag={"eszkoz": 1.0},
        nyomkovetes={"modellhivas_db": 0, "rovidzar": "orchestrator:sorszam"},
    )

    egyben = " ".join(miert(lepes))

    assert "determinisztikus" in egyben
    assert "magabiztos" not in egyben


def test_alacsony_bizonyossagot_kiemel():
    lepes = _lepes(bizonyossag={"eszkoz": 0.99, "bolt_id": 0.42})

    egyben = " ".join(miert(lepes))

    assert "ALACSONY" in egyben
    assert "bolt_id 0.42" in egyben


def test_a_None_bizonyossag_nem_bizonytalansag():
    """A `None` azt jelenti, hogy a mezőt NEM a modell adta (pl. a
    dátumot a parser oldotta fel) — nem azt, hogy bizonytalan volt."""
    lepes = _lepes(bizonyossag={"eszkoz": 0.99, "datum": None, "napszak": None})

    assert "ALACSONY" not in " ".join(miert(lepes))


def test_a_koppintas_nem_ertelmezes():
    """Egy gombnyomás nem ugyanaz a bizonyíték, mint egy helyesen
    értelmezett mondat — a nézet ezt külön mondja ki."""
    lepes = _lepes(reteg="felulet:megerosites", nyomkovetes={"modellhivas_db": 0})

    assert "KOPPINTÁS" in miert(lepes)[0]


# -- „hova tovább" -----------------------------------------------------


def test_az_allapot_MARADASA_is_allitas():
    lepes = _lepes(allapot="AJANLAT_VAR", atmenet=None, valasz_tipus="eszkoz_hiba")

    egyben = " ".join(hova_tovabb(lepes, None))

    assert "MARADT: AJANLAT_VAR" in egyben


def test_a_kovetkezo_mondat_is_resze_az_utvonalnak():
    """Az útvonal a KAPCSOLATRÓL szól: a rendszer felkínált valamit, és
    a vásárló arra válaszolt."""
    kovetkezo = Lepes(sorszam=2, sor=_sor(bemenet="a másodikat kérem"))

    egyben = " ".join(hova_tovabb(_lepes(), kovetkezo))

    assert "a másodikat kérem" in egyben


def test_az_utolso_fordulot_megnevezi():
    assert "utolsó fordulója" in " ".join(hova_tovabb(_lepes(), None))


# -- a szöveg ----------------------------------------------------------


def test_a_lepes_szovege_harom_reszbol_all():
    """Ugyanaz a szöveg megy az ablakba és a `--szoveg` kimenetbe: egy
    forrás, két megjelenés."""
    szoveg = lepes_szovege(_lepes(), None, 3)

    assert "1/3. forduló" in szoveg
    assert "MIÉRT ÍGY DÖNTÖTT:" in szoveg
    assert "HOVA TOVÁBB:" in szoveg


def test_a_becsult_hatart_a_fejlec_is_kiirja():
    beszelgetes = sessionokra_bont([_sor(session_id=None)])[0]

    assert "BECSÜLTEK" in beszelgetes_szovege(beszelgetes)


def test_mi_tortent_a_gombnyomast_is_megnevezi():
    cimkek = dict(mi_tortent(_lepes(bemenet="")))

    assert cimkek["Beírta"] == "(gombnyomás)"


# -- az ABLAK (valódi Tk, eseményhurok nélkül) -------------------------


def _ablak(sorok: list[dict]):
    """Valódi `UtvonalAblak`, `mainloop()` nélkül és elrejtve — ugyanaz
    a minta, mint a fej nélküli végigjátszásnál. Ha nincs képernyő
    (CI, SSH), a teszt kimarad: a nézet ilyenkor a `--szoveg` alakra
    esik vissza, azt pedig a többi teszt méri."""
    tkinter = pytest.importorskip("tkinter")
    from tools.utvonal import UtvonalAblak

    try:
        ablak = UtvonalAblak(sessionokra_bont(sorok), "teszt.jsonl")
    except tkinter.TclError as kivetel:  # nincs megjeleníthető felület
        pytest.skip(f"nincs Tk-képernyő: {kivetel}")
    ablak.ablak.withdraw()
    return ablak


def test_az_ablak_a_LEGUTOLSO_beszelgetest_nyitja_meg():
    """Aki most próbált, azt akarja látni, amit épp csinált."""
    ablak = _ablak([_sor(session_id="regi"), _sor(session_id="uj")])
    try:
        assert ablak.aktualis.azonosito == "uj"
    finally:
        ablak.ablak.destroy()


def test_a_lepteto_a_ket_vegen_MEGALL():
    """Az első fordulón az „Előző", az utolsón a „Következő" tiltott —
    egy szürke gomb megmondja, hol a beszélgetés széle."""
    ablak = _ablak([_sor(session_id="a"), _sor(session_id="a"), _sor(session_id="a")])
    try:
        assert ablak.szamlalo.cget("text") == "1 / 3"
        assert "disabled" in ablak.elozo_gomb.state()

        ablak.elozo()
        assert ablak.szamlalo.cget("text") == "1 / 3", "az elején nem lépünk vissza"

        ablak.kovetkezo()
        ablak.kovetkezo()
        ablak.kovetkezo()
        assert ablak.szamlalo.cget("text") == "3 / 3", "a végén nem lépünk tovább"
        assert "disabled" in ablak.kovetkezo_gomb.state()
    finally:
        ablak.ablak.destroy()


def test_az_ablak_ugyanazt_a_szoveget_mutatja_mint_a_konzol():
    """Egy forrás, két megjelenés — különben a kettő elcsúszik, és a
    hibajelentésben más áll, mint a képernyőn."""
    ablak = _ablak([_sor(session_id="a")])
    try:
        kepernyon = ablak.szoveg.get("1.0", "end").strip()
        konzolon = lepes_szovege(ablak.aktualis.lepesek[0], None, 1).strip()
        assert kepernyon == konzolon
    finally:
        ablak.ablak.destroy()

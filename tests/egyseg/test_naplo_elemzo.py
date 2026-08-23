"""Egységtesztek a napló-elemzőre (`tools/naplo_elemzo.py`,
`python feladat.py naplo`).

Az `elemez()` és a `hibamintak()` tiszta függvények (napló-sorok listája
→ összesítés), ezért fájl nélkül tesztelhetők — ez volt a fő szempont a
modul felosztásánál.
"""

from __future__ import annotations

from tools.naplo_elemzo import KERET_MASODPERC, elemez, golden_vaz, hibamintak, jelentes


def _sor(**mezok):
    """Egy naplósor, alapértelmezésekkel — a tesztek csak azt írják
    felül, ami az adott vizsgálat tárgya."""
    alap = {
        "idobelyeg": "2026-08-23T12:00:00Z",
        "bemenet": "Törpillához mennék holnap.",
        "normalizalt": "Törpillához mennék holnap.",
        "reteg": "llm",
        "eszkoz": "szabad_idopontok",
        "parameterek": {"bolt_id": "torpilla"},
        "bizonyossag": {"eszkoz": 0.98, "bolt_id": 0.95},
        "valasz_tipus": "ajanlat",
        "uzenet_kulcs": None,
        "kapuor_ok": None,
        "egyetertes": None,
        "valaszido_masodperc": 4.2,
    }
    return {**alap, **mezok}


# --- alap-összesítés -------------------------------------------------


def test_ures_naplo_nem_borul_fel() -> None:
    osszesites = elemez([])
    assert osszesites["fordulok"] == 0
    assert osszesites["valaszido"]["atlag"] is None
    # A jelentés is előálljon — a "nincs adat" nem hibaág.
    assert "Fordulók: 0" in jelentes(osszesites)


def test_reteg_megoszlas() -> None:
    osszesites = elemez([_sor(reteg="llm"), _sor(reteg="llm"), _sor(reteg="kapuor")])
    assert osszesites["retegek"] == {"llm": 2, "kapuor": 1}


def test_valaszido_atlag_p95_es_keret() -> None:
    idok = [1.0, 2.0, 3.0, 4.0, 30.0]
    osszesites = elemez([_sor(valaszido_masodperc=i) for i in idok])
    ido = osszesites["valaszido"]
    assert ido["n"] == 5
    assert ido["atlag"] == 8.0
    assert ido["max"] == 30.0
    assert ido["keret_felett"] == 1


def test_regi_naplosorok_valaszido_nelkul_olvashatok() -> None:
    """A válaszidő-mező később került a naplóba — a korábbi sorok nem
    tehetik használhatatlanná az elemzőt. Ez nem elméleti eset: a
    repóban lévő napló pont ilyen sorokkal indul."""
    regi = {"idobelyeg": "x", "bemenet": "a", "reteg": "llm", "valasz_tipus": "ajanlat"}
    osszesites = elemez([regi, regi])
    assert osszesites["fordulok"] == 2
    assert osszesites["valaszido"]["n"] == 0
    assert "nincs válaszidő-adat" in jelentes(osszesites)


# --- bizonyosság-eloszlás --------------------------------------------


def test_bizonyossag_savok_a_kuszoboket_kovetik() -> None:
    """A sávhatárok az orchestrator küszöbei (0,6 és 0,7) — így a
    hisztogramról LEOLVASHATÓ, hány forduló esett ténylegesen
    visszakérdezésbe, nem csak az, hogy "alacsony volt"."""
    sorok = [
        _sor(bizonyossag={"eszkoz": 0.5}),  # kritikus mező küszöb alatt
        _sor(bizonyossag={"eszkoz": 0.65}),  # eszköz küszöb alatt
        _sor(bizonyossag={"eszkoz": 0.9}),  # átmegy
        _sor(bizonyossag={"eszkoz": None}),  # nincs adat
    ]
    savok = elemez(sorok)["bizonyossag"]["eszkoz"]
    assert savok["0,0–0,6  (kritikus mező küszöb ALATT)"] == 1
    assert savok["0,6–0,7  (eszköz küszöb ALATT)"] == 1
    assert savok["0,7–1,0  (átmegy)"] == 1
    assert savok["nincs adat (None)"] == 1


def test_a_none_bizonyossag_nem_nulla() -> None:
    """A `None` ("nem tudok nyilatkozni") NEM eshet a legalsó sávba —
    az azt állítaná, hogy a rendszer bizonytalan volt, holott csak nem
    nyilatkozott (`assistant/interpreter/__init__.py::Ertelmezo`)."""
    savok = elemez([_sor(bizonyossag={"eszkoz": None})])["bizonyossag"]["eszkoz"]
    assert savok == {"nincs adat (None)": 1}


# --- hibaminták ------------------------------------------------------


def test_ismetelt_visszakerdezes() -> None:
    visszakerdez = _sor(
        valasz_tipus="visszakerdezes",
        eszkoz="visszakerdez",
        parameterek={"hianyzo_mezo": "bolt_id"},
    )
    mintak = hibamintak([visszakerdez, visszakerdez, visszakerdez])
    # Az ELSŐ nem ismétlés — csak a 2. és a 3.
    assert mintak["ismetelt_visszakerdezes"] == [2, 3]


def test_kulonbozo_mezore_kerdezes_nem_ismetles() -> None:
    """Ha a rendszer MÁS mezőre kérdez, a beszélgetés elmozdult — az
    nem körbe futás. Ugyanez az elv az orchestrator
    ismétlésfigyelőjében (`_ismetlest_figyel`)."""
    mintak = hibamintak(
        [
            _sor(valasz_tipus="visszakerdezes", parameterek={"hianyzo_mezo": "bolt_id"}),
            _sor(valasz_tipus="visszakerdezes", parameterek={"hianyzo_mezo": "foglalasi_kod"}),
        ]
    )
    assert "ismetelt_visszakerdezes" not in mintak


def test_elharitas_okonkent_bontva() -> None:
    """Az elhárítás önmagában nem mond semmit — az OK mondja meg, mi
    történt. Egy "ar" és egy "ertelmezhetetlen" elhárítás két teljesen
    különböző jelenség."""
    mintak = hibamintak(
        [
            _sor(valasz_tipus="elutasitas", kapuor_ok="ar"),
            _sor(valasz_tipus="elutasitas", kapuor_ok="ar"),
            _sor(valasz_tipus="elutasitas", kapuor_ok="ertelmezhetetlen"),
        ]
    )
    assert mintak["elharitas:ar"] == [1, 2]
    assert mintak["elharitas:ertelmezhetetlen"] == [3]


def test_csendes_tartalek_csak_ha_volt_modell() -> None:
    """A `szabaly` réteg önmagában NEM hiba: a gombnyomásos út és a
    zárt válaszok szándékosan oda futnak. Csak akkor gyanús, ha a
    naplóban van llm-es forduló is — mert akkor volt konfigurált
    modell, és ez a forduló mégis a tartalékra esett."""
    csak_szabaly = hibamintak([_sor(reteg="szabaly"), _sor(reteg="szabaly")])
    assert "csendes_tartalek" not in csak_szabaly

    vegyes = hibamintak([_sor(reteg="llm"), _sor(reteg="szabaly")])
    assert vegyes["csendes_tartalek"] == [2]


def test_alacsony_bizonyossag_mezonkent() -> None:
    mintak = hibamintak([_sor(bizonyossag={"eszkoz": 0.4, "bolt_id": 0.95})])
    assert mintak["alacsony_bizonyossag:eszkoz"] == [1]
    assert "alacsony_bizonyossag:bolt_id" not in mintak


def test_ismetelt_bemenet() -> None:
    mintak = hibamintak([_sor(bemenet="mennék"), _sor(bemenet="mennék"), _sor(bemenet="máskor")])
    assert mintak["ismetelt_bemenet"] == [2]


def test_lassu_fordulo_a_keret_felett() -> None:
    mintak = hibamintak(
        [
            _sor(valaszido_masodperc=KERET_MASODPERC - 0.1),
            _sor(valaszido_masodperc=KERET_MASODPERC + 0.1),
        ]
    )
    assert mintak["lassu_fordulo"] == [2]


def test_hibatlan_naplobol_nincs_minta() -> None:
    """Egy tiszta futásból egyetlen minta sem szólalhat meg — különben
    a jelentés zajos lenne, és senki nem nézné."""
    assert hibamintak([_sor(), _sor(bemenet="más mondat")]) == {}


# --- önkonzisztencia -------------------------------------------------


def test_onkonzisztencia_eloszlas() -> None:
    osszesites = elemez([_sor(egyetertes=3), _sor(egyetertes=3), _sor(egyetertes=2)])
    assert osszesites["onkonzisztencia"] == {"3/3": 2, "2/3": 1}


def test_onkonzisztencia_nelkul_ures() -> None:
    assert elemez([_sor(egyetertes=None)])["onkonzisztencia"] == {}


# --- golden-eset konverter -------------------------------------------


def test_golden_vaz_uresen_hagyja_a_varhatot() -> None:
    """A golden-set skill szabálya: "Ne a modell kimenetéből írj
    tesztesetet". Ha a konverter kitöltené a `varhato`-t a naplózott
    kimenettel, a teszteset azt rögzítené, amit a rendszer AKKOR
    csinált, és a mérés önmagát igazolná."""
    vaz = golden_vaz(_sor(), 7)
    assert "TÖLTSD KI" in vaz
    assert "id: naplo-0007" in vaz
    assert "'Törpillához mennék holnap.'" in vaz
    # A tényleges kimenet KOMMENTBEN ott van — látni hasznos.
    assert "#   eszkoz:      szabad_idopontok" in vaz
    # …de nem a `varhato` alatt, hanem kommentsorban.
    varhato_resz = vaz.split("varhato:")[1]
    assert "szabad_idopontok" not in varhato_resz


def test_golden_vaz_redaktalt_bemenetet_visz_tovabb() -> None:
    """A napló már redaktált (`privacy/redakcio`), tehát a vázba is a
    redaktált alak kerül. Ez így helyes: nyers személyes adat
    verziókezelt fájlba sem kerülhet."""
    vaz = golden_vaz(_sor(bemenet="a számom <TELEFON>, időpontot kérek"), 1)
    assert "<TELEFON>" in vaz


# --- a jelentés előáll -----------------------------------------------


def test_jelentes_minden_szakaszt_kiir() -> None:
    szoveg = jelentes(elemez([_sor(), _sor(reteg="kapuor", valasz_tipus="elutasitas")]))
    for szakasz in ("Réteg-megoszlás", "Válasz-típusok", "Válaszidő", "Bizonyosság-eloszlás"):
        assert szakasz in szoveg, szakasz

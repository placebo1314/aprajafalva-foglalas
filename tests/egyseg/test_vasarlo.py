"""Egységtesztek a vásárlói felület (`ui/vasarlo.py`) mögötti, Tkinter
nélküli tiszta függvényekre — a Tkinter-widgeteket nem teszteljük
(ugyanaz a minta, mint `ui/admin/app.py`-nál: "Tkinter-teszt nincs").

A `nyugtazo_szoveg()` a legfontosabb: ez a hangcsatorna töltelék-
mondatának szöveges próbája, és a docs/blueprint.md 7. szakaszban most
rögzített szabályt kell kövesse — csak igazolt, determinisztikus
forrásból származó tényt mondhat (felismert keresési ablak, azonosított
bolt), konkrét szabad időpontot vagy kapacitást sosem.
"""

from __future__ import annotations

from ui.vasarlo import _idopont_cimke, nyugtazo_szoveg, tenyvalasz_szoveg

# --- nyugtazo_szoveg ---------------------------------------------------


def test_nyugtazo_szoveg_ures_ablak_altalanos_mondat():
    assert nyugtazo_szoveg({}) == "Egy pillanat, nézem…"


def test_nyugtazo_szoveg_bolt_es_egynapos_ablak():
    szoveg = nyugtazo_szoveg(
        {
            "bolt_id": "ugyifogyi",
            "datum_tol": "2026-08-18T00:00:00Z",
            "datum_ig": "2026-08-18T23:59:59Z",
        }
    )
    assert szoveg == "Nézem, mi van a(z) Ügyifogyi boltban, 2026-08-18…"


def test_nyugtazo_szoveg_napszakkal():
    szoveg = nyugtazo_szoveg(
        {
            "bolt_id": "torpilla",
            "datum_tol": "2026-08-18T00:00:00Z",
            "datum_ig": "2026-08-18T11:59:59Z",
            "napszak": "delelott",
        }
    )
    assert szoveg == "Nézem, mi van a(z) Törpilla boltban, 2026-08-18 délelőtt…"


def test_nyugtazo_szoveg_barmikor_napszak_nem_jelenik_meg():
    szoveg = nyugtazo_szoveg(
        {
            "bolt_id": "szundi",
            "datum_tol": "2026-08-18T00:00:00Z",
            "datum_ig": "2026-08-18T23:59:59Z",
            "napszak": "barmikor",
        }
    )
    assert szoveg == "Nézem, mi van a(z) Szundi boltban, 2026-08-18…"


def test_nyugtazo_szoveg_tobbnapos_ablak():
    szoveg = nyugtazo_szoveg(
        {
            "bolt_id": "torpilla",
            "datum_tol": "2026-08-17T09:00:00Z",
            "datum_ig": "2026-08-24T23:59:59Z",
        }
    )
    assert szoveg == "Nézem, mi van a(z) Törpilla boltban, 2026-08-17 és 2026-08-24 között…"


def test_nyugtazo_szoveg_csak_bolt_datum_nelkul():
    szoveg = nyugtazo_szoveg({"bolt_id": "szundi"})
    assert szoveg == "Nézem, mi van a(z) Szundi boltban…"


def test_nyugtazo_szoveg_sosem_tartalmaz_konkret_idopontot_vagy_darabszamot():
    """A blueprint 7. szakasz "nem mondható" oszlopa — a felismert
    ablakban NINCS konkrét slot vagy darabszám, ezért a nyugtázó szöveg
    sem tartalmazhat ilyet, akármit is kap bemenetként."""
    szoveg = nyugtazo_szoveg(
        {
            "bolt_id": "ugyifogyi",
            "datum_tol": "2026-08-18T00:00:00Z",
            "datum_ig": "2026-08-18T23:59:59Z",
            "napszak": "delelott",
        }
    )
    # Csak a naptári nap jelenik meg (ÉÉÉÉ-HH-NN), óra:perc-szintű
    # időbélyeg vagy "T...Z" jelölés nem — az konkrét slotot sejtetne.
    assert ":" not in szoveg
    assert "T" not in szoveg
    assert "Z" not in szoveg


# --- tenyvalasz_szoveg ---------------------------------------------------


def test_tenyvalasz_szoveg_nyitvatartas():
    assert (
        tenyvalasz_szoveg({"sikeres": True, "nyitvatartas": "H-V 08:00-20:00"})
        == "Nyitvatartás: H-V 08:00-20:00"
    )


def test_tenyvalasz_szoveg_nyitvatartas_ures():
    assert (
        tenyvalasz_szoveg({"sikeres": True, "nyitvatartas": ""})
        == "Nyitvatartás: ezt még nem adtuk meg"
    )


def test_tenyvalasz_szoveg_cim():
    assert (
        tenyvalasz_szoveg({"sikeres": True, "cim": "Aprajafalva, Fő utca 7."})
        == "Cím: Aprajafalva, Fő utca 7."
    )


def test_tenyvalasz_szoveg_megjelenes():
    assert tenyvalasz_szoveg({"sikeres": True, "megjelenes": "Piros cégér."}) == "Piros cégér."


def test_tenyvalasz_szoveg_megjelenes_ures():
    assert tenyvalasz_szoveg({"sikeres": True, "megjelenes": ""}) == "Erről még nincs leírásunk."


def test_tenyvalasz_szoveg_termek_es_ar():
    valasz = {
        "sikeres": True,
        "szolgaltatasok": [{"nev": "petárda", "termekleiras": "durranó", "ar": "50 arany"}],
    }
    assert tenyvalasz_szoveg(valasz) == "petárda — durranó — (50 arany)"


def test_tenyvalasz_szoveg_idotartam():
    valasz = {"sikeres": True, "szolgaltatasok": [{"nev": "petárda", "idotartam_perc": 5}]}
    assert tenyvalasz_szoveg(valasz) == "petárda — 5 perc"


def test_tenyvalasz_szoveg_szolgaltatasok_ures_lista():
    assert tenyvalasz_szoveg({"sikeres": True, "szolgaltatasok": []}) == "Erről nincs adatunk."


def test_tenyvalasz_szoveg_ismeretlen_alak_visszaesik_dict_szovegre():
    valasz = {"sikeres": True, "foglalasok": []}
    assert tenyvalasz_szoveg(valasz) == "{'foglalasok': []}"


# --- _idopont_cimke ------------------------------------------------------


def test_idopont_cimke_formazas():
    cimke = _idopont_cimke("2026-08-18T08:00:00Z", "2026-08-18T08:30:00Z")
    assert cimke == "2026-08-18 08:00–08:30 (UTC)"

"""Egységtesztek az `assistant/valasz/` modulra — a magyar
mondatgenerálás sablonokból (M5).

A `nyugtazo_szoveg()` a legfontosabb: ez a hangcsatorna töltelék-
mondatának szöveges próbája, és a docs/blueprint.md 7. szakaszban
rögzített szabályt kell kövesse — csak igazolt, determinisztikus
forrásból származó tényt mondhat (felismert keresési ablak, azonosított
bolt), konkrét szabad időpontot vagy kapacitást sosem.

Két külön szempont fut végig a teszteken:

1. **A sablon soha nem generál tényt, csak behelyettesít** — ha egy
   tetszőleges, korábban sosem látott értéket adunk be, annak szó
   szerint (nem átalakítva, nem kicserélve) meg kell jelennie a
   kimenetben.
2. **A nyugtázó sablonokból több változat van, véletlenszerű
   választással** — sok hívás után több különböző szöveget kell látnunk,
   nem mindig ugyanazt (a hangcsatornán az ismétlődés feltűnő lenne)."""

from __future__ import annotations

import random

from assistant import valasz
from assistant.valasz.sablonok import SABLONOK

# --- a sablon soha nem generál tényt, csak behelyettesít ---------------


def test_sikeres_foglalas_szoveg_a_kodot_valtoztatas_nelkul_visszaadja():
    """Tetszőleges, a sablonban sosem szereplő kód is szó szerint
    megjelenik — ez zárja ki, hogy a sablon a kódot "kitalálja" vagy
    átalakítsa, csak behelyettesíti."""
    kod = "ZZ9Q7K3P"
    assert kod in valasz.sikeres_foglalas_szoveg(kod)


def test_tenyvalasz_szoveg_nyitvatartas_erteket_valtoztatas_nelkul_adja_vissza():
    ertek = "H-P 09:00-13:00, ez egy teszt-egyedi érték"
    szoveg = valasz.tenyvalasz_szoveg({"sikeres": True, "nyitvatartas": ertek})
    assert ertek in szoveg


def test_tenyvalasz_szoveg_ket_kulonbozo_bemenet_ket_kulonbozo_kimenetet_ad():
    """Ha a sablon fix szöveget adna vissza a bemenettől függetlenül, az
    generálás lenne, nem behelyettesítés — ez a teszt ezt zárja ki."""
    elso = valasz.tenyvalasz_szoveg({"sikeres": True, "cim": "Fő utca 1."})
    masodik = valasz.tenyvalasz_szoveg({"sikeres": True, "cim": "Fő utca 2."})
    assert elso != masodik
    assert "Fő utca 1." in elso
    assert "Fő utca 2." in masodik


def test_hiba_szoveg_ismeretlen_kulcsnal_a_kulcsot_irja_ki():
    """Ismeretlen `uzenet_kulcs`-nál a modul nem talál ki mondatot —
    látható marad, hogy a sablon hiányzik."""
    assert "teszt_ismeretlen_kulcs_xyz" in valasz.hiba_szoveg("teszt_ismeretlen_kulcs_xyz")


# --- hiba ----------------------------------------------------------------


def test_hiba_szoveg_ismert_kulcs():
    assert (
        valasz.hiba_szoveg("nem_foglalasi_kerdes")
        == "Ez a kérdés nem foglalással kapcsolatos, ebben nem tudok segíteni."
    )


# --- visszaigazolas --------------------------------------------------------


def test_megerosites_ker_szoveg():
    assert valasz.megerosites_ker_szoveg() == "Biztosan lefoglaljam ezt az időpontot?"


def test_elvetve_szoveg():
    assert valasz.elvetve_szoveg() == "Rendben, nem foglaltuk le. Kereshetsz újra."


# --- zart_kerdes (visszakérdezés) ------------------------------------------


def test_visszakerdezes_szoveg_ismert_mezo():
    assert valasz.visszakerdezes_szoveg("bolt_id") == (
        "Ehhez még kellene tudnom: melyik boltba szeretnél menni."
    )


def test_visszakerdezes_szoveg_ismeretlen_mezo_tartalek():
    """Ismeretlen mezőnévnél a nyers mezőnév a tartalék — kevésbé
    folyékony, de sosem hamis vagy üres."""
    szoveg = valasz.visszakerdezes_szoveg("uj_mezo_amit_meg_nem_ismerunk")
    assert "uj_mezo_amit_meg_nem_ismerunk" in szoveg


# --- tenyvalasz ------------------------------------------------------------


def test_tenyvalasz_szoveg_nyitvatartas():
    assert (
        valasz.tenyvalasz_szoveg({"sikeres": True, "nyitvatartas": "H-V 08:00-20:00"})
        == "Nyitvatartás: H-V 08:00-20:00"
    )


def test_tenyvalasz_szoveg_nyitvatartas_ures():
    assert (
        valasz.tenyvalasz_szoveg({"sikeres": True, "nyitvatartas": ""})
        == "Nyitvatartás: ezt még nem adtuk meg"
    )


def test_tenyvalasz_szoveg_cim():
    assert (
        valasz.tenyvalasz_szoveg({"sikeres": True, "cim": "Aprajafalva, Fő utca 7."})
        == "Cím: Aprajafalva, Fő utca 7."
    )


def test_tenyvalasz_szoveg_megjelenes():
    assert (
        valasz.tenyvalasz_szoveg({"sikeres": True, "megjelenes": "Piros cégér."}) == "Piros cégér."
    )


def test_tenyvalasz_szoveg_megjelenes_ures():
    assert (
        valasz.tenyvalasz_szoveg({"sikeres": True, "megjelenes": ""})
        == "Erről még nincs leírásunk."
    )


def test_tenyvalasz_szoveg_termek_es_ar():
    eredmeny = {
        "sikeres": True,
        "szolgaltatasok": [{"nev": "petárda", "termekleiras": "durranó", "ar": "50 arany"}],
    }
    assert valasz.tenyvalasz_szoveg(eredmeny) == "petárda — durranó — (50 arany)"


def test_tenyvalasz_szoveg_idotartam():
    eredmeny = {"sikeres": True, "szolgaltatasok": [{"nev": "petárda", "idotartam_perc": 5}]}
    assert valasz.tenyvalasz_szoveg(eredmeny) == "petárda — 5 perc"


def test_tenyvalasz_szoveg_szolgaltatasok_ures_lista():
    assert (
        valasz.tenyvalasz_szoveg({"sikeres": True, "szolgaltatasok": []}) == "Erről nincs adatunk."
    )


def test_tenyvalasz_szoveg_ismeretlen_alak_visszaesik_dict_szovegre():
    eredmeny = {"sikeres": True, "foglalasok": []}
    assert valasz.tenyvalasz_szoveg(eredmeny) == "{'foglalasok': []}"


# --- nyugtazo ----------------------------------------------------------


def test_nyugtazo_szoveg_ures_ablak_egy_altalanos_valtozatot_ad():
    szoveg = valasz.nyugtazo_szoveg({})
    assert szoveg in SABLONOK["hu"]["nyugtazo"]["altalanos"]


def test_nyugtazo_szoveg_bolt_es_egynapos_ablak_determinisztikus_valasztoval():
    # Az első változatot választó, determinisztikus "véletlen" a tartalom
    # ellenőrzéséhez — a változatválasztást külön teszt bizonyítja.
    veletlen = random.Random()
    veletlen.choice = lambda szekvencia: szekvencia[0]  # type: ignore[method-assign]
    szoveg = valasz.nyugtazo_szoveg(
        {
            "bolt_id": "ugyifogyi",
            "datum_tol": "2026-08-18T00:00:00Z",
            "datum_ig": "2026-08-18T23:59:59Z",
        },
        veletlen=veletlen,
    )
    assert szoveg == SABLONOK["hu"]["nyugtazo"]["ablakkal"][0].format(
        resz="a(z) Ügyifogyi boltban, 2026-08-18"
    )


def test_nyugtazo_szoveg_napszakkal():
    veletlen = random.Random()
    veletlen.choice = lambda szekvencia: szekvencia[0]  # type: ignore[method-assign]
    szoveg = valasz.nyugtazo_szoveg(
        {
            "bolt_id": "torpilla",
            "datum_tol": "2026-08-18T00:00:00Z",
            "datum_ig": "2026-08-18T11:59:59Z",
            "napszak": "delelott",
        },
        veletlen=veletlen,
    )
    assert "Törpilla boltban, 2026-08-18 délelőtt" in szoveg


def test_nyugtazo_szoveg_tobbnapos_ablak():
    veletlen = random.Random()
    veletlen.choice = lambda szekvencia: szekvencia[0]  # type: ignore[method-assign]
    szoveg = valasz.nyugtazo_szoveg(
        {
            "bolt_id": "torpilla",
            "datum_tol": "2026-08-17T09:00:00Z",
            "datum_ig": "2026-08-24T23:59:59Z",
        },
        veletlen=veletlen,
    )
    assert "2026-08-17 és 2026-08-24 között" in szoveg


def test_nyugtazo_szoveg_sosem_tartalmaz_konkret_idopontot_vagy_darabszamot():
    """A blueprint 7. szakasz "nem mondható" oszlopa — a felismert
    ablakban NINCS konkrét slot vagy darabszám, ezért a nyugtázó szöveg
    sem tartalmazhat ilyet, akármit is kap bemenetként."""
    szoveg = valasz.nyugtazo_szoveg(
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


def test_nyugtazo_szoveg_tobb_valtozat_kozott_valaszt_veletlenszeruen():
    """A nyugtázó sablonokból több változat van — elég sok hívás után
    több KÜLÖNBÖZŐ szöveget kell kapnunk, nem mindig ugyanazt. Ez a
    hangcsatorna szempontjából a lényeg: ismétlődő töltelékmondat
    feltűnő lenne."""
    ablak = {
        "bolt_id": "szundi",
        "datum_tol": "2026-08-18T00:00:00Z",
        "datum_ig": "2026-08-18T23:59:59Z",
    }
    valtozatok = {valasz.nyugtazo_szoveg(ablak) for _ in range(200)}
    assert len(valtozatok) > 1

    ures_valtozatok = {valasz.nyugtazo_szoveg({}) for _ in range(200)}
    assert len(ures_valtozatok) > 1


def test_nyugtazo_szoveg_minden_valtozat_a_deklaralt_sablonok_kozul_kerul_ki():
    ablak = {"bolt_id": "szundi"}
    for _ in range(50):
        szoveg = valasz.nyugtazo_szoveg(ablak)
        elvart = {
            sablon.format(resz="a(z) Szundi boltban")
            for sablon in SABLONOK["hu"]["nyugtazo"]["ablakkal"]
        }
        assert szoveg in elvart

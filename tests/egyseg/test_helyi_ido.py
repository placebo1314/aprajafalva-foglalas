"""HELYI IDŐ — a 4. invariáns második fele (ADR-033).

„Minden idő UTC-ben tárolódik… helyi idő csak a megjelenítésnél
keletkezik." Az első fele mindig igaz volt, a második sokáig papíron
maradt: a felület a tárolt UTC-t írta ki, `(UTC)` felirattal, a
felolvasó pedig ugyanazt mondta. A demóadat boltjai 8 órakor nyitnak —
a vásárló 7 órát látott.
"""

from __future__ import annotations

import pytest

from assistant import valasz
from assistant.valasz import helyi_ido, szamok

BUDAPEST = "Europe/Budapest"


@pytest.mark.parametrize(
    ("utc", "varhato"),
    [
        # Tél: CET, +1 óra.
        ("2026-12-21T07:00:00Z", "2026-12-21T08:00:00"),
        # Nyár: CEST, +2 óra.
        ("2026-07-21T07:00:00Z", "2026-07-21T09:00:00"),
        # Az óraátállítás NAPJA — a zoneinfo dolga, de itt látszik, hogy
        # tényleg rá van bízva, nem egy fix eltolásra.
        ("2026-03-29T00:30:00Z", "2026-03-29T01:30:00"),
        ("2026-03-29T01:30:00Z", "2026-03-29T03:30:00"),
    ],
)
def test_helyi_iso(utc, varhato):
    assert helyi_ido.helyi_iso(utc, BUDAPEST) == varhato


def test_a_Z_eltunik():
    """A `Z` hiánya a jelzés, hogy ez már nem UTC — ilyen szöveget csak
    kiírni szabad, visszaírni az adatbázisba soha."""
    assert not helyi_ido.helyi_iso("2026-12-21T07:00:00Z", BUDAPEST).endswith("Z")


def test_a_nap_is_atfordulhat():
    """Nem elég az `iso[:10]`: egy 23:30Z kezdetű időpont Budapesten
    már a KÖVETKEZŐ napon van."""
    assert helyi_ido.helyi_datum("2026-12-21T23:30:00Z", BUDAPEST) == "2026-12-22"


def test_zona_nelkul_valtozatlan():
    """Nincs szervezet → nincs mihez igazítani. Nem kitalálunk egy
    zónát, hanem a nyers értéket adjuk vissza."""
    assert helyi_ido.helyi_iso("2026-12-21T07:00:00Z", None) == "2026-12-21T07:00:00Z"


def test_ismeretlen_zona_nem_dob():
    """Egy elgépelt időzóna-törzsadat miatt nem maradhat el a
    megjelenítés: a hiba látható (rossz óra), de nem néma kivétel a
    felület közepén."""
    assert helyi_ido.helyi_iso("2026-12-21T07:00:00Z", "Nincs/Ilyen").startswith("2026-12-21")


# -- a mondatok --------------------------------------------------------


def test_a_visszaolvasas_helyi_idot_mond():
    """Ez az a mondat, amire a vásárló IGENT mond — itt a legdrágább
    egy órát tévedni."""
    szoveg = valasz.megerosites_ker_szoveg(
        "2026-12-22T09:00:00Z", mod=valasz.MOD_BESZELHETO, zona=BUDAPEST
    )
    assert "tíz órakor" in szoveg
    assert "kilenc" not in szoveg


def test_az_ajanlat_helyi_idot_mond():
    jeloltek = [{"kezdet": "2026-12-22T07:00:00Z", "veg": "2026-12-22T07:10:00Z"}]
    szoveg = valasz.ajanlat_mondat(jeloltek, mod=valasz.MOD_BESZELHETO, zona=BUDAPEST)
    assert "nyolc órakor" in szoveg


def test_az_ajanlat_szoveges_alakja_is_helyi():
    jeloltek = [
        {"kezdet": "2026-12-22T07:00:00Z", "veg": "2026-12-22T07:10:00Z"},
        {"kezdet": "2026-12-22T07:20:00Z", "veg": "2026-12-22T07:30:00Z"},
    ]
    szoveg = valasz.ajanlat_mondat(jeloltek, zona=BUDAPEST)
    assert "8:00" in szoveg and "8:20" in szoveg
    assert "7:00" not in szoveg


def test_a_nyugtazo_sor_datuma_is_helyi():
    """Az ablak határa 23:00Z — helyi naptár szerint már a következő
    nap. A nyugtázó sor a vásárló naptárát mondja, nem a tárolóét."""
    ablak = {
        "datum_tol": "2026-12-21T23:00:00Z",
        "datum_ig": "2026-12-21T23:30:00Z",
        "napszak": "barmikor",
    }
    assert "2026-12-22" in valasz.nyugtazo_szoveg(ablak, zona=BUDAPEST)


def test_az_UTC_szo_nem_hagyja_el_a_rendszert():
    """A vásárlónak nincs dolga az időzónákkal — az ő ideje a falióra."""
    assert "UTC" not in szamok.idopont_rovid("2026-12-21T08:00:00")


@pytest.mark.parametrize(
    ("iso", "varhato"), [("2026-12-21T08:00:00", "8:00"), ("2026-12-21T14:05:00", "14:05")]
)
def test_ora_perc_rovid_nincs_vezeto_nulla(iso, varhato):
    """A mondatban a `08:00` gépies; a GOMBOKON marad a kétjegyű alak,
    mert ott oszlopba rendeződnek."""
    assert szamok.ora_perc_rovid(iso) == varhato

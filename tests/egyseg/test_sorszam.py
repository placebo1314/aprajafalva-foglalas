"""A SORSZÁMOS HIVATKOZÁS felismerője (`assistant/sorszam.py`).

„A másodikat", „az elsőt kérem", „az utolsó jó lesz" — ez a
leggyakoribb természetes válasz egy listára, és a rendszer eddig
egyiket sem értette.

**A tévedés ára itt aszimmetrikus, de fordítva, mint a kapuőrnél.** Ott
a téves ÁTENGEDÉS olcsó (a mögöttes rétegek fognak), itt a téves
FELISMERÉS drága: nem visszakérdezést okoz, hanem más időpontot foglal
le, mint amit a vásárló kért. Ezért van a felismerésben zárt szólista
és hosszkorlát, és ezért van ennyi ellenpróba.
"""

from __future__ import annotations

import pytest

from assistant.sorszam import sorszam_hivatkozas

HAROM = 3


# --- amit fel KELL ismerni -------------------------------------------


@pytest.mark.parametrize(
    ("mondat", "varhato"),
    [
        ("a második", 2),
        ("második", 2),
        ("a másodikat", 2),
        ("a másodikra", 2),
        ("az elsőt kérem", 1),
        ("a legelső jó", 1),
        ("az utolsó jó lesz", 3),
        ("az utolsót", 3),
        ("a harmadikat", 3),
        ("a második jó lesz nekem", 2),
        ("a másodikat kérem szépen", 2),
        # Számjegyes alakok — a sorszám jele a pont vagy a kötőjeles rag.
        ("2.", 2),
        ("a 2-t", 2),
        ("a 3.", 3),
    ],
)
def test_felismert_alakok(mondat: str, varhato: int) -> None:
    assert sorszam_hivatkozas(mondat, HAROM) == varhato


def test_az_utolso_a_jeloltek_szamatol_fugg() -> None:
    """Az „utolsó" nem szám, hanem pozíció."""
    assert sorszam_hivatkozas("az utolsót", 2) == 2
    assert sorszam_hivatkozas("az utolsót", 5) == 5


# --- amit NEM szabad felismerni --------------------------------------


@pytest.mark.parametrize(
    "mondat",
    [
        # A sorszó más szerepben.
        "első alkalommal járok itt",
        "elsősorban délelőtt lenne jó",
        "az első időpont nem jó",
        # Mennyiség, nem hivatkozás — csoportos foglalás nem létezik.
        "két időpontot kérek",
        # Sima foglalási kérés.
        "Törpillához mennék holnap",
        # Óra, nem sorszám: a puszta szám sosem elég.
        "10 körül lenne jó",
        "8",
    ],
)
def test_nem_hivatkozas(mondat: str) -> None:
    assert sorszam_hivatkozas(mondat, HAROM) is None


def test_tartomanyon_kivuli_sorszam_nem_kerekit() -> None:
    """Ha hármat ajánlottunk és a vásárló a hatodikat kéri, az nem
    elírás, hanem félreértés — azt kérdéssel kell tisztázni, nem a
    legközelebbi jelöltre kerekíteni."""
    assert sorszam_hivatkozas("a hatodikat", HAROM) is None
    assert sorszam_hivatkozas("a negyediket", HAROM) is None
    # …de ha tényleg négyet ajánlottunk, a negyedik érvényes.
    assert sorszam_hivatkozas("a negyediket", 4) == 4


def test_jelolt_nelkul_nincs_hivatkozas() -> None:
    """Felajánlott jelöltek nélkül a „második" bármi lehet."""
    assert sorszam_hivatkozas("a másodikat", 0) is None


def test_hosszu_mondatban_nem_hivatkozas() -> None:
    """Egy sorszámos hivatkozás rövid. Hosszú mondatban ugyanaz a szó
    jóval nagyobb eséllyel jelent mást."""
    assert (
        sorszam_hivatkozas(
            "az első alkalommal még nem tudtam eljönni, de most szeretnék időpontot", HAROM
        )
        is None
    )


def test_tajszolasi_alak_is_atmegy_a_normalizalon() -> None:
    """A felismerő a normalizált alakon dolgozik, mint a kapuőr és a
    frusztráció-jelző."""
    assert sorszam_hivatkozas("a második vóna jó", HAROM) is None  # „vóna" → „volna": nem zárt szó
    assert sorszam_hivatkozas("a második", HAROM) == 2

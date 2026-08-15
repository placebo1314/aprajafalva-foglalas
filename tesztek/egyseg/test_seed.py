"""Egységtesztek a seed/betolt.py demóadatra."""

from __future__ import annotations

import sqlite3

import pytest

from seed.betolt import betolt


@pytest.fixture
def db_utvonal(tmp_path) -> str:
    return str(tmp_path / "seed.db")


def test_harom_boltot_hoz_letre(db_utvonal):
    adat = betolt(db_utvonal)
    assert set(adat["boltok"].keys()) == {"szundi", "ugyifogyi", "torpilla"}


def test_torpillanal_harom_pult_van(db_utvonal):
    adat = betolt(db_utvonal)
    assert len(adat["torpilla_pultok"]) == 3
    nevek = {p["konfig"]["alkalmazott_nev"] for p in adat["torpilla_pultok"]}
    assert nevek == {"GipszJakab", "Törpilla", "Hulk Hugan"}


def test_egy_het_muszak_a_harom_pultra(db_utvonal):
    adat = betolt(db_utvonal)
    assert len(adat["muszakok"]) == 3 * 7


def test_kivetel_napon_minden_pultra_kihagyva(db_utvonal):
    adat = betolt(db_utvonal)
    kihagyott = [m for m in adat["muszakok"] if m["kihagyva"]]
    assert len(kihagyott) == 3
    assert all(m["datum"] == adat["kivetel_datum"] for m in kihagyott)


def test_kivetel_napra_is_letrejon_a_muszak_sor_a_db_ben(db_utvonal):
    """A kihagyás a generátor szintjén történik (nincs slot/blokk), de a
    műszak sora létrejön — így a kihagyás ténylegesen látszik, nem csak
    egy hiányzó nap a beosztásban."""
    adat = betolt(db_utvonal)
    conn = sqlite3.connect(db_utvonal)
    try:
        for muszak in adat["muszakok"]:
            if muszak["kihagyva"]:
                letezik = conn.execute(
                    "SELECT 1 FROM muszak WHERE id = ?", (muszak["muszak_id"],)
                ).fetchone()
                assert letezik is not None
                slot_szam = conn.execute(
                    "SELECT COUNT(*) FROM slot WHERE muszak_id = ?", (muszak["muszak_id"],)
                ).fetchone()[0]
                assert slot_szam == 0
    finally:
        conn.close()


def test_gipszjakab_egy_napja_8x3_slot_es_blokk(db_utvonal):
    """8 órás műszak, (10+10) perces ciklusokkal, foglalhato_arany=1.0
    (nincs szabad sáv GipszJakabnál — a saját szünetritmusa már
    meghatározza a napját) -> óránként pontosan 3 slot + 3 szünetblokk,
    tehát a teljes napra 8×3 = 24."""
    adat = betolt(db_utvonal)
    gipszjakab_muszakok = [
        m for m in adat["muszakok"] if m["alkalmazott"] == "GipszJakab" and not m["kihagyva"]
    ]
    assert gipszjakab_muszakok
    assert all(m["slot_szam"] == 8 * 3 for m in gipszjakab_muszakok)
    assert all(m["blokk_szam"] == 8 * 3 for m in gipszjakab_muszakok)


def test_szabad_sav_csak_torpillanal_es_hulk_hugannal(db_utvonal):
    adat = betolt(db_utvonal)
    conn = sqlite3.connect(db_utvonal)
    try:
        for muszak in adat["muszakok"]:
            if muszak["kihagyva"]:
                continue
            van_szabad_sav = (
                conn.execute(
                    "SELECT 1 FROM muszak_blokk WHERE muszak_id = ? AND tipus = 'szabad_sav'",
                    (muszak["muszak_id"],),
                ).fetchone()
                is not None
            )
            if muszak["alkalmazott"] == "GipszJakab":
                assert not van_szabad_sav, "GipszJakabnál nem lehet szabad sáv"
            else:
                assert van_szabad_sav, f"{muszak['alkalmazott']}nél kellene legyen szabad sáv"
    finally:
        conn.close()


def test_nincs_atfedes_egyetlen_muszakon_sem(db_utvonal):
    """A szabad sáv és a szünetmintázat nem fedheti egymást — ezt a
    blokk.py FixBlokk.general() garantálja, itt a teljes seed adaton
    ellenőrizzük végponttól végpontig, nem csak izoláltan."""
    adat = betolt(db_utvonal)
    conn = sqlite3.connect(db_utvonal)
    try:
        for muszak in adat["muszakok"]:
            if muszak["kihagyva"]:
                continue
            sorok = conn.execute(
                "SELECT kezdet, veg FROM muszak_blokk WHERE muszak_id = ? "
                "UNION ALL "
                "SELECT kezdet, veg FROM slot WHERE muszak_id = ? "
                "ORDER BY kezdet",
                (muszak["muszak_id"], muszak["muszak_id"]),
            ).fetchall()
            for elozo, kovetkezo in zip(sorok, sorok[1:], strict=False):
                assert elozo[1] <= kovetkezo[0], (
                    f"átfedés {muszak['alkalmazott']} {muszak['datum']} napján: "
                    f"{elozo} és {kovetkezo}"
                )
    finally:
        conn.close()


def test_determinisztikus_azonositok(db_utvonal, tmp_path):
    masik_db_utvonal = str(tmp_path / "masik.db")
    adat1 = betolt(db_utvonal)
    adat2 = betolt(masik_db_utvonal)

    assert adat1["szervezet_id"] == adat2["szervezet_id"]
    assert adat1["boltok"] == adat2["boltok"]
    assert [m["muszak_id"] for m in adat1["muszakok"]] == [
        m["muszak_id"] for m in adat2["muszakok"]
    ]


def test_dupla_betoltes_ugyanarra_a_db_ra_utkozik(db_utvonal):
    """A determinisztikus id-k szándékos következménye: kétszeri betöltés
    ugyanarra a fájlra egyediségi kényszerbe ütközik, nem duplázza csendben
    az adatot."""
    betolt(db_utvonal)
    with pytest.raises(sqlite3.IntegrityError):
        betolt(db_utvonal)

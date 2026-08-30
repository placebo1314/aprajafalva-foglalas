"""Egységtesztek a seed/betolt.py demóadatra."""

from __future__ import annotations

import sqlite3

import pytest

from seed.betolt import AdatbazisMarFeltoltve, betolt


@pytest.fixture
def db_path(tmp_path) -> str:
    return str(tmp_path / "seed.db")


def test_three_shop_hoz_create(db_path):
    data = betolt(db_path)
    assert set(data["boltok"].keys()) == {"szundi", "ugyifogyi", "torpilla"}


def test_torpillanal_three_counter_has(db_path):
    data = betolt(db_path)
    assert len(data["pultok"]["torpilla"]) == 3
    names = {p["konfig"]["alkalmazott_nev"] for p in data["pultok"]["torpilla"]}
    assert names == {"GipszJakab", "Törpilla", "Hulk Hugan"}


def test_mindharom_bolt_kap_beosztast(db_path):
    """Korábban csak a Törpillában volt műszak, tehát a másik két boltra
    irányuló minden kérés üres eredményre futott — a próbákban ez
    megkülönböztethetetlen volt egy párbeszédhibától."""
    data = betolt(db_path)

    assert set(data["pultok"]) == {"szundi", "ugyifogyi", "torpilla"}
    boltok_muszakkal = {m["bolt"] for m in data["muszakok"] if not m["kihagyva"]}
    assert boltok_muszakkal == {"szundi", "ugyifogyi", "torpilla"}
    for bolt in ("szundi", "ugyifogyi", "torpilla"):
        slotok = sum(
            m["slot_szam"] for m in data["muszakok"] if m["bolt"] == bolt and not m["kihagyva"]
        )
        assert slotok > 0, f"{bolt}: nulla slot"


def test_a_harom_bolt_ritmusa_kulonbozik(db_path):
    """A demóadat nem csak „van beosztás mindenhol" — a három ritmus
    szándékosan más, hogy a próbán az is látszódjon, ugyanaz a kérés
    hogyan néz ki egy hosszú-ritka és egy rövid-sűrű beosztáson."""
    data = betolt(db_path)
    naponta = {}
    for bolt in ("szundi", "ugyifogyi"):
        muszakok = [m for m in data["muszakok"] if m["bolt"] == bolt and not m["kihagyva"]]
        naponta[bolt] = muszakok[0]["slot_szam"]

    # Az Ügyifogyi legalább ötször sűrűbb, mint a Szundi.
    assert naponta["ugyifogyi"] > 5 * naponta["szundi"], naponta


def test_one_week_shift_minden_pultra(db_path):
    """Öt pult (Szundi 1, Ügyifogyi 1, Törpilla 3) × hét nap."""
    data = betolt(db_path)
    assert len(data["muszakok"]) == 5 * 7


def test_exception_on_day_all_to_counter_skipped(db_path):
    data = betolt(db_path)
    skipped = [m for m in data["muszakok"] if m["kihagyva"]]
    assert len(skipped) == 5, "a karácsony MINDEN pultot érint, mindhárom boltban"
    assert all(m["datum"] == data["kivetel_datum"] for m in skipped)


def test_exception_for_day_is_is_created_shift_row_db_ben(db_path):
    """A kihagyás a generátor szintjén történik (nincs slot/blokk), de a
    műszak sora létrejön — így a kihagyás ténylegesen látszik, nem csak
    egy hiányzó nap a beosztásban."""
    data = betolt(db_path)
    conn = sqlite3.connect(db_path)
    try:
        for shift in data["muszakok"]:
            if shift["kihagyva"]:
                exists = conn.execute(
                    "SELECT 1 FROM muszak WHERE id = ?", (shift["muszak_id"],)
                ).fetchone()
                assert exists is not None
                slot_count = conn.execute(
                    "SELECT COUNT(*) FROM slot WHERE muszak_id = ?", (shift["muszak_id"],)
                ).fetchone()[0]
                assert slot_count == 0
    finally:
        conn.close()


def test_gipszjakab_one_day_8x3_slot_and_block(db_path):
    """8 órás műszak, (10+10) perces ciklusokkal, foglalhato_arany=1.0
    (nincs szabad sáv GipszJakabnál — a saját szünetritmusa már
    meghatározza a napját) -> óránként pontosan 3 slot + 3 szünetblokk,
    tehát a teljes napra 8×3 = 24."""
    data = betolt(db_path)
    gipszjakab_shifts = [
        m for m in data["muszakok"] if m["alkalmazott"] == "GipszJakab" and not m["kihagyva"]
    ]
    assert gipszjakab_shifts
    assert all(m["slot_szam"] == 8 * 3 for m in gipszjakab_shifts)
    assert all(m["blokk_szam"] == 8 * 3 for m in gipszjakab_shifts)


def test_free_band_only_torpillanal_and_hulk_hugannal(db_path):
    data = betolt(db_path)
    conn = sqlite3.connect(db_path)
    try:
        for shift in data["muszakok"]:
            if shift["kihagyva"]:
                continue
            has_free_band = (
                conn.execute(
                    "SELECT 1 FROM muszak_blokk WHERE muszak_id = ? AND tipus = 'szabad_sav'",
                    (shift["muszak_id"],),
                ).fetchone()
                is not None
            )
            if shift["alkalmazott"] == "GipszJakab":
                assert not has_free_band, "GipszJakabnál nem lehet szabad sáv"
            else:
                assert has_free_band, f"{shift['alkalmazott']}nél kellene legyen szabad sáv"
    finally:
        conn.close()


def test_no_overlap_single_on_shift_nor(db_path):
    """A szabad sáv és a szünetmintázat nem fedheti egymást — ezt a
    blokk.py FixBlokk.general() garantálja, itt a teljes seed adaton
    ellenőrizzük végponttól végpontig, nem csak izoláltan."""
    data = betolt(db_path)
    conn = sqlite3.connect(db_path)
    try:
        for shift in data["muszakok"]:
            if shift["kihagyva"]:
                continue
            rows = conn.execute(
                "SELECT kezdet, veg FROM muszak_blokk WHERE muszak_id = ? "
                "UNION ALL "
                "SELECT kezdet, veg FROM slot WHERE muszak_id = ? "
                "ORDER BY kezdet",
                (shift["muszak_id"], shift["muszak_id"]),
            ).fetchall()
            for previous, next in zip(rows, rows[1:], strict=False):
                assert previous[1] <= next[0], (
                    f"átfedés {shift['alkalmazott']} {shift['datum']} napján: {previous} és {next}"
                )
    finally:
        conn.close()


def test_deterministic_azonositok(db_path, tmp_path):
    other_db_path = str(tmp_path / "masik.db")
    adat1 = betolt(db_path)
    adat2 = betolt(other_db_path)

    assert adat1["szervezet_id"] == adat2["szervezet_id"]
    assert adat1["boltok"] == adat2["boltok"]
    assert [m["muszak_id"] for m in adat1["muszakok"]] == [
        m["muszak_id"] for m in adat2["muszakok"]
    ]


def test_double_load_same_db_ra_ertelmes_hibat_ad(db_path):
    """A determinisztikus id-k szándékos következménye: kétszeri betöltés
    ugyanarra a fájlra egyediségi kényszerbe ütközne — ezt előre,
    olvasható hibaüzenettel jelezzük (`AdatbazisMarFeltoltve`), nem
    hagyjuk, hogy nyers `sqlite3.IntegrityError` szálljon fel."""
    betolt(db_path)
    with pytest.raises(AdatbazisMarFeltoltve, match="--ujra"):
        betolt(db_path)


def test_ujra_kapcsolo_ures_adatbazisra_is_mukodik(db_path):
    """`ujra=True` üres (még sosem töltött) adatbázisra is működik —
    nincs mit kiüríteni előtte, egyszerűen betölt."""
    data = betolt(db_path, ujra=True)
    assert set(data["boltok"].keys()) == {"szundi", "ugyifogyi", "torpilla"}


def test_ujra_kapcsolo_mar_feltoltott_adatbazist_ujratolt(db_path):
    """`ujra=True` egy már feltöltött adatbázison nem dob hibát, hanem
    kiüríti a táblákat (visszagörgetés + újramigrálás), és utána
    ugyanazt a (determinisztikus) demóadatot tölti be újra — nem
    duplázza, nem hagy régi sorokat."""
    elso = betolt(db_path)
    masodik = betolt(db_path, ujra=True)

    assert masodik["szervezet_id"] == elso["szervezet_id"]
    assert masodik["boltok"] == elso["boltok"]
    assert len(masodik["muszakok"]) == len(elso["muszakok"])

    conn = sqlite3.connect(db_path)
    try:
        (darab,) = conn.execute("SELECT COUNT(*) FROM szervezet").fetchone()
        assert darab == 1, "az újratöltés nem duplázhatja a szervezet sorát"
    finally:
        conn.close()

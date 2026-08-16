"""Egységtesztek a mag/api/adminszolgaltatas.py szolgáltatásrétegére.

A Tkinter felületet (`felulet/admin/app.py`) nem teszteljük — ez a fájl
csak a mag/api/ oldalt, ami tiszta Python, GUI nélkül hívható.
"""

from __future__ import annotations

import pytest

from mag.api import adminszolgaltatas as api
from mag.repo import migracio, torzsadat_repo


@pytest.fixture
def db_utvonal(tmp_path) -> str:
    return str(tmp_path / "teszt.db")


@pytest.fixture
def kapcsolat(db_utvonal):
    conn = migracio.kapcsolat_nyitas(db_utvonal)
    migracio.migral(conn)
    yield conn
    conn.close()


@pytest.fixture
def torzs(kapcsolat) -> dict[str, str]:
    szervezet_id = torzsadat_repo.szervezet_letrehoz(kapcsolat, nev="Aprajafalva", idozona="UTC")
    bolt_id = torzsadat_repo.bolt_letrehoz(kapcsolat, szervezet_id=szervezet_id, nev="Ügyifogyi")
    pult_id = torzsadat_repo.pult_letrehoz(
        kapcsolat, szervezet_id=szervezet_id, bolt_id=bolt_id, nev="Pult 1"
    )
    alkalmazott_id = torzsadat_repo.alkalmazott_letrehoz(
        kapcsolat, szervezet_id=szervezet_id, bolt_id=bolt_id, nev="Durranó"
    )
    szolgaltatas_id = torzsadat_repo.szolgaltatas_letrehoz(
        kapcsolat,
        szervezet_id=szervezet_id,
        bolt_id=bolt_id,
        nev="petárda",
        alap_idotartam_perc=10,
    )
    return {
        "szervezet_id": szervezet_id,
        "bolt_id": bolt_id,
        "pult_id": pult_id,
        "alkalmazott_id": alkalmazott_id,
        "szolgaltatas_id": szolgaltatas_id,
    }


def _felvitel(kapcsolat, torzs, kezdet: str, veg: str) -> dict:
    return api.muszak_felvitel(
        kapcsolat,
        szervezet_id=torzs["szervezet_id"],
        bolt_id=torzs["bolt_id"],
        pult_id=torzs["pult_id"],
        alkalmazott_id=torzs["alkalmazott_id"],
        szolgaltatas_id=torzs["szolgaltatas_id"],
        kezdet=kezdet,
        veg=veg,
        idotartam_perc=10,
        puffer_utana_perc=0,
        min_racs_perc=10,
        foglalhato_arany=1.0,
        blokk_szabaly={"szunetek": []},
    )


# --- muszak_felvitel — normál eset ----------------------------------------


def test_muszak_felvitel_sikeres(kapcsolat, torzs):
    eredmeny = _felvitel(kapcsolat, torzs, "2026-08-18T08:00:00Z", "2026-08-18T09:00:00Z")
    assert eredmeny["hiba"] is None
    assert eredmeny["kihagyva"] is False
    assert eredmeny["slot_szam"] == 6
    assert eredmeny["muszak_id"] is not None


# --- muszak_felvitel — fordított / nulla hosszú időablak: ÉRTELMES elutasítás ---


def test_muszak_felvitel_fordított_idoablakot_elutasit_kivetel_nelkul(kapcsolat, torzs):
    eredmeny = _felvitel(kapcsolat, torzs, "2026-08-18T09:00:00Z", "2026-08-18T08:00:00Z")
    assert eredmeny["hiba"] is not None
    assert eredmeny["muszak_id"] is None
    assert eredmeny["slot_szam"] == 0
    # A DB-be nem került be a hibás sor.
    assert kapcsolat.execute("SELECT COUNT(*) FROM muszak").fetchone()[0] == 0


def test_muszak_felvitel_nulla_hosszu_idoablakot_elutasit_kivetel_nelkul(kapcsolat, torzs):
    eredmeny = _felvitel(kapcsolat, torzs, "2026-08-18T08:00:00Z", "2026-08-18T08:00:00Z")
    assert eredmeny["hiba"] is not None
    assert kapcsolat.execute("SELECT COUNT(*) FROM muszak").fetchone()[0] == 0


# --- muszak_felvitel — kivétel nap ------------------------------------


def test_muszak_felvitel_kivetel_napon_nulla_slot(kapcsolat, torzs):
    torzsadat_repo.kivetel_nap_letrehoz(
        kapcsolat,
        szervezet_id=torzs["szervezet_id"],
        bolt_id=None,
        datum="2026-08-18",
        indok="teszt ünnep",
    )
    eredmeny = _felvitel(kapcsolat, torzs, "2026-08-18T08:00:00Z", "2026-08-18T09:00:00Z")
    assert eredmeny["hiba"] is None
    assert eredmeny["kihagyva"] is True
    assert eredmeny["kihagyas_oka"] == "2026-08-18"
    assert eredmeny["slot_szam"] == 0
    # A műszak SOR létrejön (ez mutatja meg a kihagyást), csak slot/blokk nem.
    assert kapcsolat.execute("SELECT COUNT(*) FROM muszak").fetchone()[0] == 1
    assert kapcsolat.execute("SELECT COUNT(*) FROM slot").fetchone()[0] == 0


# --- muszak_reszletei / het_muszakjai — üres eredmények -------------------


def test_het_muszakjai_ures_uj_szervezetben(kapcsolat, torzs):
    eredmeny = api.het_muszakjai(
        kapcsolat, szervezet_id=torzs["szervezet_id"], het_kezdete_datum="2026-08-17"
    )
    assert eredmeny == []


def test_muszak_reszletei_ures_uj_muszakra(kapcsolat, torzs):
    _felvitel(kapcsolat, torzs, "2026-08-18T08:00:00Z", "2026-08-18T08:00:00Z")  # elutasítva
    het = api.het_muszakjai(
        kapcsolat, szervezet_id=torzs["szervezet_id"], het_kezdete_datum="2026-08-17"
    )
    assert het == []  # az elutasított felvitel nem hozott létre műszakot


# =====================================================================
# Műszak-sablonok (muszak_sablon, migraciok/0003)
# =====================================================================


def test_muszak_sablon_mentese_sikeres(kapcsolat, torzs):
    felvitel = _felvitel(kapcsolat, torzs, "2026-08-18T08:00:00Z", "2026-08-18T16:00:00Z")
    eredmeny = api.muszak_sablon_mentese(
        kapcsolat, muszak_id=felvitel["muszak_id"], nev="Alap napi"
    )
    assert eredmeny["hiba"] is None
    assert eredmeny["sablon_id"] is not None

    sablonok = api.muszak_sablonok(kapcsolat, szervezet_id=torzs["szervezet_id"])
    assert len(sablonok) == 1
    assert sablonok[0]["nev"] == "Alap napi"
    assert sablonok[0]["kezdet_ora"] == 8
    assert sablonok[0]["veg_ora"] == 16
    assert sablonok[0]["pult_id"] == torzs["pult_id"]
    assert sablonok[0]["alkalmazott_id"] == torzs["alkalmazott_id"]
    assert sablonok[0]["szolgaltatas_id"] == torzs["szolgaltatas_id"]


def test_muszak_sablon_mentese_nem_letezo_muszakra(kapcsolat, torzs):
    eredmeny = api.muszak_sablon_mentese(kapcsolat, muszak_id="nincs-ilyen", nev="X")
    assert eredmeny["hiba"] is not None
    assert eredmeny["sablon_id"] is None


def test_muszak_sablon_mentese_ejfelen_atnyulo_elutasitva(kapcsolat, torzs):
    felvitel = _felvitel(kapcsolat, torzs, "2026-08-18T22:00:00Z", "2026-08-19T02:00:00Z")
    eredmeny = api.muszak_sablon_mentese(kapcsolat, muszak_id=felvitel["muszak_id"], nev="X")
    assert eredmeny["hiba"] is not None
    assert eredmeny["sablon_id"] is None


def test_muszak_sablon_mentese_nem_kerek_ora_elutasitva(kapcsolat, torzs):
    felvitel = _felvitel(kapcsolat, torzs, "2026-08-18T08:15:00Z", "2026-08-18T16:00:00Z")
    eredmeny = api.muszak_sablon_mentese(kapcsolat, muszak_id=felvitel["muszak_id"], nev="X")
    assert eredmeny["hiba"] is not None
    assert eredmeny["sablon_id"] is None


def _sablon_mentese(
    kapcsolat, torzs, kezdet="2026-08-18T08:00:00Z", veg="2026-08-18T16:00:00Z"
) -> str:
    felvitel = _felvitel(kapcsolat, torzs, kezdet, veg)
    eredmeny = api.muszak_sablon_mentese(
        kapcsolat, muszak_id=felvitel["muszak_id"], nev="Alap napi"
    )
    return eredmeny["sablon_id"]


def test_muszak_sablon_alkalmazasa_napra(kapcsolat, torzs):
    sablon_id = _sablon_mentese(kapcsolat, torzs)
    eredmeny = api.muszak_sablon_alkalmazasa_napra(
        kapcsolat, sablon_id=sablon_id, datum="2026-08-25"
    )
    assert eredmeny["hiba"] is None
    assert eredmeny["kihagyva"] is False
    assert eredmeny["slot_szam"] == 48  # 8 óra, 10 perces slot


def test_muszak_sablon_alkalmazasa_napra_nem_letezo_sablonra(kapcsolat):
    eredmeny = api.muszak_sablon_alkalmazasa_napra(
        kapcsolat, sablon_id="nincs-ilyen", datum="2026-08-25"
    )
    assert eredmeny["hiba"] is not None


def test_muszak_sablon_alkalmazasa_napra_kivetel_napon_kihagyva(kapcsolat, torzs):
    sablon_id = _sablon_mentese(kapcsolat, torzs)
    torzsadat_repo.kivetel_nap_letrehoz(
        kapcsolat,
        szervezet_id=torzs["szervezet_id"],
        bolt_id=None,
        datum="2026-08-25",
        indok="teszt ünnep",
    )
    eredmeny = api.muszak_sablon_alkalmazasa_napra(
        kapcsolat, sablon_id=sablon_id, datum="2026-08-25"
    )
    assert eredmeny["hiba"] is None
    assert eredmeny["kihagyva"] is True
    assert eredmeny["slot_szam"] == 0


def test_muszak_sablon_alkalmazasa_hetre_het_muszakot_hoz_letre(kapcsolat, torzs):
    sablon_id = _sablon_mentese(kapcsolat, torzs)
    eredmenyek = api.muszak_sablon_alkalmazasa_hetre(
        kapcsolat, sablon_id=sablon_id, het_kezdete_datum="2026-09-07"
    )
    assert len(eredmenyek) == 7
    assert all(e["hiba"] is None for e in eredmenyek)
    assert all(e["slot_szam"] == 48 for e in eredmenyek)

    het = api.het_muszakjai(
        kapcsolat, szervezet_id=torzs["szervezet_id"], het_kezdete_datum="2026-09-07"
    )
    assert len(het) == 7


def test_muszak_sablon_alkalmazasa_hetre_kivetel_napot_kihagyja(kapcsolat, torzs):
    sablon_id = _sablon_mentese(kapcsolat, torzs)
    torzsadat_repo.kivetel_nap_letrehoz(
        kapcsolat,
        szervezet_id=torzs["szervezet_id"],
        bolt_id=None,
        datum="2026-09-09",  # a 2026-09-07-i hét szerdája
        indok="teszt ünnep",
    )
    eredmenyek = api.muszak_sablon_alkalmazasa_hetre(
        kapcsolat, sablon_id=sablon_id, het_kezdete_datum="2026-09-07"
    )
    kihagyottak = [e for e in eredmenyek if e["kihagyva"]]
    assert len(kihagyottak) == 1

    het = api.het_muszakjai(
        kapcsolat, szervezet_id=torzs["szervezet_id"], het_kezdete_datum="2026-09-07"
    )
    assert len(het) == 7  # a muszak SOR a kivétel napon is létrejön
    generalt_slot_szamok = sorted(m["slot_szam"] for m in het)
    assert generalt_slot_szamok[0] == 0  # a kivétel napi műszaknak nincs slotja
    assert generalt_slot_szamok[-1] == 48


# --- het_masolasa -------------------------------------------------------


def test_het_masolasa_lemasolja_a_muszakokat_masik_hetre(kapcsolat, torzs):
    _felvitel(kapcsolat, torzs, "2026-08-17T08:00:00Z", "2026-08-17T16:00:00Z")  # hétfő
    _felvitel(kapcsolat, torzs, "2026-08-19T08:00:00Z", "2026-08-19T16:00:00Z")  # szerda

    eredmenyek = api.het_masolasa(
        kapcsolat,
        szervezet_id=torzs["szervezet_id"],
        forras_het_kezdete="2026-08-17",
        cel_het_kezdete="2026-09-07",
    )
    assert len(eredmenyek) == 2
    assert all(e["hiba"] is None and e["kihagyva"] is False for e in eredmenyek)

    cel_het = api.het_muszakjai(
        kapcsolat, szervezet_id=torzs["szervezet_id"], het_kezdete_datum="2026-09-07"
    )
    cel_datumok = sorted(m["kezdet"][:10] for m in cel_het)
    assert cel_datumok == ["2026-09-07", "2026-09-09"]  # ugyanaz a hétfő/szerda mintázat


def test_het_masolasa_ures_forras_het_ures_eredmeny(kapcsolat, torzs):
    eredmenyek = api.het_masolasa(
        kapcsolat,
        szervezet_id=torzs["szervezet_id"],
        forras_het_kezdete="2026-08-17",
        cel_het_kezdete="2026-09-07",
    )
    assert eredmenyek == []


def test_het_masolasa_kivetel_napot_kihagyja_a_cel_heten(kapcsolat, torzs):
    _felvitel(kapcsolat, torzs, "2026-08-17T08:00:00Z", "2026-08-17T16:00:00Z")  # hétfő
    torzsadat_repo.kivetel_nap_letrehoz(
        kapcsolat,
        szervezet_id=torzs["szervezet_id"],
        bolt_id=None,
        datum="2026-09-07",  # a cél hét hétfője
        indok="teszt ünnep",
    )

    eredmenyek = api.het_masolasa(
        kapcsolat,
        szervezet_id=torzs["szervezet_id"],
        forras_het_kezdete="2026-08-17",
        cel_het_kezdete="2026-09-07",
    )
    assert len(eredmenyek) == 1
    assert eredmenyek[0]["kihagyva"] is True
    assert eredmenyek[0]["slot_szam"] == 0

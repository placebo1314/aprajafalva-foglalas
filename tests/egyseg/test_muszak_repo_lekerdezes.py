"""Egységtesztek a mag/repo/muszak_repo.py olvasó (listázó) függvényeire:
`muszakok_lekerdezese` és `blokkok_lekerdezese`.

Az író/generáló oldalt (`muszak_letrehoz`, `blokkok_slotok_mentese`,
`kivetel_napok_lekerdezese`) a `test_seed.py` és a `test_muszak_slot.py`
már közvetetten fedi — itt az admin felület (`felulet/admin/`) naptár-
nézetéhez írt lekérdezéseket teszteljük.
"""

from __future__ import annotations

import pytest

from mag.modell.muszak import Blokk, Slot
from mag.repo import migracio, muszak_repo, torzsadat_repo

_MOST = "2026-08-15T10:00:00Z"


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


def _muszak(kapcsolat, torzs, kezdet: str, veg: str) -> str:
    return muszak_repo.muszak_letrehoz(
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


# --- muszakok_lekerdezese -------------------------------------------------


def test_muszakok_lekerdezese_ures(kapcsolat, torzs):
    eredmeny = muszak_repo.muszakok_lekerdezese(kapcsolat, szervezet_id=torzs["szervezet_id"])
    assert eredmeny == []


def test_muszakok_lekerdezese_egy_elem_nevekkel(kapcsolat, torzs):
    muszak_id = _muszak(kapcsolat, torzs, "2026-08-18T08:00:00Z", "2026-08-18T09:00:00Z")
    eredmeny = muszak_repo.muszakok_lekerdezese(kapcsolat, szervezet_id=torzs["szervezet_id"])
    assert len(eredmeny) == 1
    sor = eredmeny[0]
    assert sor["muszak_id"] == muszak_id
    assert sor["bolt_nev"] == "Ügyifogyi"
    assert sor["pult_nev"] == "Pult 1"
    assert sor["alkalmazott_nev"] == "Durranó"
    assert sor["szolgaltatas_nev"] == "petárda"
    assert sor["slot_szam"] == 0  # nincs slot mentve, csak a muszak sor


def test_muszakok_lekerdezese_tobb_elem_kezdet_szerint_rendezve(kapcsolat, torzs):
    kesobbi = _muszak(kapcsolat, torzs, "2026-08-19T08:00:00Z", "2026-08-19T09:00:00Z")
    korabbi = _muszak(kapcsolat, torzs, "2026-08-18T08:00:00Z", "2026-08-18T09:00:00Z")
    eredmeny = muszak_repo.muszakok_lekerdezese(kapcsolat, szervezet_id=torzs["szervezet_id"])
    assert [e["muszak_id"] for e in eredmeny] == [korabbi, kesobbi]


def test_muszakok_lekerdezese_datum_ablakra_szur(kapcsolat, torzs):
    _muszak(kapcsolat, torzs, "2026-08-17T08:00:00Z", "2026-08-17T09:00:00Z")
    bent = _muszak(kapcsolat, torzs, "2026-08-18T08:00:00Z", "2026-08-18T09:00:00Z")
    _muszak(kapcsolat, torzs, "2026-08-25T08:00:00Z", "2026-08-25T09:00:00Z")

    eredmeny = muszak_repo.muszakok_lekerdezese(
        kapcsolat,
        szervezet_id=torzs["szervezet_id"],
        datum_tol="2026-08-18T00:00:00Z",
        datum_ig="2026-08-19T00:00:00Z",
    )
    assert [e["muszak_id"] for e in eredmeny] == [bent]


def test_muszakok_lekerdezese_bolt_szerint_szur(kapcsolat, torzs):
    sajat = _muszak(kapcsolat, torzs, "2026-08-18T08:00:00Z", "2026-08-18T09:00:00Z")
    masik_bolt = torzsadat_repo.bolt_letrehoz(
        kapcsolat, szervezet_id=torzs["szervezet_id"], nev="Törpilla"
    )
    masik_pult = torzsadat_repo.pult_letrehoz(
        kapcsolat, szervezet_id=torzs["szervezet_id"], bolt_id=masik_bolt, nev="Törpilla pult"
    )
    masik_alkalmazott = torzsadat_repo.alkalmazott_letrehoz(
        kapcsolat, szervezet_id=torzs["szervezet_id"], bolt_id=masik_bolt, nev="Törpilla"
    )
    masik_szolg = torzsadat_repo.szolgaltatas_letrehoz(
        kapcsolat,
        szervezet_id=torzs["szervezet_id"],
        bolt_id=masik_bolt,
        nev="boldogság",
        alap_idotartam_perc=15,
    )
    muszak_repo.muszak_letrehoz(
        kapcsolat,
        szervezet_id=torzs["szervezet_id"],
        bolt_id=masik_bolt,
        pult_id=masik_pult,
        alkalmazott_id=masik_alkalmazott,
        szolgaltatas_id=masik_szolg,
        kezdet="2026-08-18T08:00:00Z",
        veg="2026-08-18T09:00:00Z",
        idotartam_perc=10,
        puffer_utana_perc=0,
        min_racs_perc=10,
        foglalhato_arany=1.0,
        blokk_szabaly={"szunetek": []},
    )

    eredmeny = muszak_repo.muszakok_lekerdezese(
        kapcsolat, szervezet_id=torzs["szervezet_id"], bolt_id=torzs["bolt_id"]
    )
    assert [e["muszak_id"] for e in eredmeny] == [sajat]


def test_muszakok_lekerdezese_slot_szam_a_mentett_slotokat_tukrozi(kapcsolat, torzs):
    muszak_id = _muszak(kapcsolat, torzs, "2026-08-18T08:00:00Z", "2026-08-18T09:00:00Z")
    slotok = [Slot("2026-08-18T08:00:00Z", "2026-08-18T08:10:00Z")]
    muszak_repo.blokkok_slotok_mentese(
        kapcsolat,
        muszak_id=muszak_id,
        szervezet_id=torzs["szervezet_id"],
        blokkok=[],
        slotok=slotok,
    )
    eredmeny = muszak_repo.muszakok_lekerdezese(kapcsolat, szervezet_id=torzs["szervezet_id"])
    assert eredmeny[0]["slot_szam"] == 1


# --- blokkok_lekerdezese --------------------------------------------------


def test_blokkok_lekerdezese_ures(kapcsolat, torzs):
    muszak_id = _muszak(kapcsolat, torzs, "2026-08-18T08:00:00Z", "2026-08-18T09:00:00Z")
    assert muszak_repo.blokkok_lekerdezese(kapcsolat, muszak_id=muszak_id) == []


def test_blokkok_lekerdezese_tobb_elem_kezdet_szerint_rendezve(kapcsolat, torzs):
    muszak_id = _muszak(kapcsolat, torzs, "2026-08-18T08:00:00Z", "2026-08-18T09:00:00Z")
    blokkok = [
        Blokk("szunet", "2026-08-18T08:30:00Z", "2026-08-18T08:40:00Z", True, True),
        Blokk("szunet", "2026-08-18T08:00:00Z", "2026-08-18T08:10:00Z", True, True),
    ]
    muszak_repo.blokkok_slotok_mentese(
        kapcsolat,
        muszak_id=muszak_id,
        szervezet_id=torzs["szervezet_id"],
        blokkok=blokkok,
        slotok=[],
    )
    eredmeny = muszak_repo.blokkok_lekerdezese(kapcsolat, muszak_id=muszak_id)
    assert [b["kezdet"] for b in eredmeny] == ["2026-08-18T08:00:00Z", "2026-08-18T08:30:00Z"]
    assert eredmeny[0]["tipus"] == "szunet"
    assert eredmeny[0]["rogzitett"] is True
    assert eredmeny[0]["beszamit_kvotaba"] is True


def test_blokkok_lekerdezese_szur_muszak_szerint(kapcsolat, torzs):
    muszak_1 = _muszak(kapcsolat, torzs, "2026-08-18T08:00:00Z", "2026-08-18T09:00:00Z")
    muszak_2 = _muszak(kapcsolat, torzs, "2026-08-19T08:00:00Z", "2026-08-19T09:00:00Z")
    muszak_repo.blokkok_slotok_mentese(
        kapcsolat,
        muszak_id=muszak_2,
        szervezet_id=torzs["szervezet_id"],
        blokkok=[Blokk("szabad_sav", "2026-08-19T08:50:00Z", "2026-08-19T09:00:00Z", True, False)],
        slotok=[],
    )
    assert muszak_repo.blokkok_lekerdezese(kapcsolat, muszak_id=muszak_1) == []
    assert len(muszak_repo.blokkok_lekerdezese(kapcsolat, muszak_id=muszak_2)) == 1

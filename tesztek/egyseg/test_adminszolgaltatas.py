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

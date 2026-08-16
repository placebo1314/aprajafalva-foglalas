"""Egységtesztek a mag/repo/torzsadat_repo.py olvasó (listázó) függvényeire.

Az író függvényeket (`*_letrehoz`) a `test_seed.py` már közvetetten fedi —
itt kifejezetten az admin felület (`felulet/admin/`) és a demo-verseny
(`mag/api/verseny.py`) kiszolgálására írt lekérdezéseket teszteljük: üres
eredmény, egy elem, több elem (névre rendezve), és a bolt/szervezet
szerinti szűrés.
"""

from __future__ import annotations

import uuid

import pytest

from mag.repo import migracio, torzsadat_repo

_MOST = "2026-08-15T10:00:00Z"


def _uuid() -> str:
    return uuid.uuid4().hex


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
def szervezet(kapcsolat) -> str:
    return torzsadat_repo.szervezet_letrehoz(kapcsolat, nev="Aprajafalva", idozona="UTC")


@pytest.fixture
def bolt(kapcsolat, szervezet) -> str:
    return torzsadat_repo.bolt_letrehoz(kapcsolat, szervezet_id=szervezet, nev="Ügyifogyi")


# --- szervezetek_lekerdezese -----------------------------------------------


def test_szervezetek_lekerdezese_ures(kapcsolat):
    assert torzsadat_repo.szervezetek_lekerdezese(kapcsolat) == []


def test_szervezetek_lekerdezese_egy_elem(kapcsolat, szervezet):
    eredmeny = torzsadat_repo.szervezetek_lekerdezese(kapcsolat)
    assert eredmeny == [{"id": szervezet, "nev": "Aprajafalva"}]


def test_szervezetek_lekerdezese_tobb_elem_nevre_rendezve(kapcsolat):
    torzsadat_repo.szervezet_letrehoz(kapcsolat, nev="Zebra Kft", idozona="UTC")
    torzsadat_repo.szervezet_letrehoz(kapcsolat, nev="Aprajafalva", idozona="UTC")
    nevek = [s["nev"] for s in torzsadat_repo.szervezetek_lekerdezese(kapcsolat)]
    assert nevek == ["Aprajafalva", "Zebra Kft"]


# --- boltok_lekerdezese ------------------------------------------------


def test_boltok_lekerdezese_ures(kapcsolat, szervezet):
    assert torzsadat_repo.boltok_lekerdezese(kapcsolat, szervezet_id=szervezet) == []


def test_boltok_lekerdezese_egy_elem(kapcsolat, szervezet, bolt):
    eredmeny = torzsadat_repo.boltok_lekerdezese(kapcsolat, szervezet_id=szervezet)
    assert eredmeny == [{"id": bolt, "nev": "Ügyifogyi"}]


def test_boltok_lekerdezese_tobb_elem_nevre_rendezve(kapcsolat, szervezet):
    torzsadat_repo.bolt_letrehoz(kapcsolat, szervezet_id=szervezet, nev="Törpilla")
    torzsadat_repo.bolt_letrehoz(kapcsolat, szervezet_id=szervezet, nev="Szundi")
    nevek = [b["nev"] for b in torzsadat_repo.boltok_lekerdezese(kapcsolat, szervezet_id=szervezet)]
    assert nevek == ["Szundi", "Törpilla"]


def test_boltok_lekerdezese_szur_szervezet_szerint(kapcsolat, szervezet, bolt):
    masik_szervezet = torzsadat_repo.szervezet_letrehoz(kapcsolat, nev="Másik", idozona="UTC")
    torzsadat_repo.bolt_letrehoz(kapcsolat, szervezet_id=masik_szervezet, nev="Idegen bolt")
    eredmeny = torzsadat_repo.boltok_lekerdezese(kapcsolat, szervezet_id=szervezet)
    assert eredmeny == [{"id": bolt, "nev": "Ügyifogyi"}]


# --- pultok_lekerdezese --------------------------------------------------


def test_pultok_lekerdezese_ures(kapcsolat, bolt):
    assert torzsadat_repo.pultok_lekerdezese(kapcsolat, bolt_id=bolt) == []


def test_pultok_lekerdezese_tobb_elem_es_szur_bolt_szerint(kapcsolat, szervezet, bolt):
    p1 = torzsadat_repo.pult_letrehoz(kapcsolat, szervezet_id=szervezet, bolt_id=bolt, nev="Pult B")
    p2 = torzsadat_repo.pult_letrehoz(kapcsolat, szervezet_id=szervezet, bolt_id=bolt, nev="Pult A")
    masik_bolt = torzsadat_repo.bolt_letrehoz(kapcsolat, szervezet_id=szervezet, nev="Másik bolt")
    torzsadat_repo.pult_letrehoz(
        kapcsolat, szervezet_id=szervezet, bolt_id=masik_bolt, nev="Idegen"
    )

    eredmeny = torzsadat_repo.pultok_lekerdezese(kapcsolat, bolt_id=bolt)
    assert eredmeny == [{"id": p2, "nev": "Pult A"}, {"id": p1, "nev": "Pult B"}]


# --- alkalmazottak_lekerdezese ------------------------------------------


def test_alkalmazottak_lekerdezese_ures(kapcsolat, bolt):
    assert torzsadat_repo.alkalmazottak_lekerdezese(kapcsolat, bolt_id=bolt) == []


def test_alkalmazottak_lekerdezese_tobb_elem_es_szur_bolt_szerint(kapcsolat, szervezet, bolt):
    a1 = torzsadat_repo.alkalmazott_letrehoz(
        kapcsolat, szervezet_id=szervezet, bolt_id=bolt, nev="Durranó"
    )
    masik_bolt = torzsadat_repo.bolt_letrehoz(kapcsolat, szervezet_id=szervezet, nev="Másik bolt")
    torzsadat_repo.alkalmazott_letrehoz(
        kapcsolat, szervezet_id=szervezet, bolt_id=masik_bolt, nev="Idegen"
    )

    eredmeny = torzsadat_repo.alkalmazottak_lekerdezese(kapcsolat, bolt_id=bolt)
    assert eredmeny == [{"id": a1, "nev": "Durranó"}]


# --- szolgaltatasok_lekerdezese ------------------------------------------


def test_szolgaltatasok_lekerdezese_ures(kapcsolat, bolt):
    assert torzsadat_repo.szolgaltatasok_lekerdezese(kapcsolat, bolt_id=bolt) == []


def test_szolgaltatasok_lekerdezese_egy_elem_alap_idotartammal(kapcsolat, szervezet, bolt):
    sz_id = torzsadat_repo.szolgaltatas_letrehoz(
        kapcsolat, szervezet_id=szervezet, bolt_id=bolt, nev="petárda", alap_idotartam_perc=5
    )
    eredmeny = torzsadat_repo.szolgaltatasok_lekerdezese(kapcsolat, bolt_id=bolt)
    assert eredmeny == [{"id": sz_id, "nev": "petárda", "alap_idotartam_perc": 5}]


def test_szolgaltatasok_lekerdezese_szur_bolt_szerint(kapcsolat, szervezet, bolt):
    torzsadat_repo.szolgaltatas_letrehoz(
        kapcsolat, szervezet_id=szervezet, bolt_id=bolt, nev="petárda", alap_idotartam_perc=5
    )
    masik_bolt = torzsadat_repo.bolt_letrehoz(kapcsolat, szervezet_id=szervezet, nev="Másik bolt")
    torzsadat_repo.szolgaltatas_letrehoz(
        kapcsolat, szervezet_id=szervezet, bolt_id=masik_bolt, nev="idegen", alap_idotartam_perc=10
    )

    eredmeny = torzsadat_repo.szolgaltatasok_lekerdezese(kapcsolat, bolt_id=bolt)
    assert [s["nev"] for s in eredmeny] == ["petárda"]

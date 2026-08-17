"""Egységtesztek a mag/api/cli.py parancsokra.

A parancsfüggvényeket közvetlenül hívja (nem subprocess-ként) — ezek
tiszta `argv → kilépőkód` függvények, `sys.exit`/subprocess nélkül
tesztelhetők.
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta

import pytest

from mag.api import cli
from mag.repo import foglalas_repo, migracio, muszak_repo, torzsadat_repo


@pytest.fixture
def db_utvonal(tmp_path) -> str:
    return str(tmp_path / "cli.db")


@pytest.fixture
def alapadat(db_utvonal) -> dict:
    """Migrál, és felvesz egy minimális törzsadatot + egy 1 órás,
    szünet nélküli műszakot — elég egy CLI-teszthez, seed nélkül."""
    conn = migracio.kapcsolat_nyitas(db_utvonal)
    try:
        migracio.migral(conn)
        szervezet_id = torzsadat_repo.szervezet_letrehoz(
            conn, nev="Aprajafalva", idozona="Europe/Budapest"
        )
        bolt_id = torzsadat_repo.bolt_letrehoz(conn, szervezet_id=szervezet_id, nev="Törpilla")
        pult_id = torzsadat_repo.pult_letrehoz(
            conn, szervezet_id=szervezet_id, bolt_id=bolt_id, nev="Pult 1"
        )
        alkalmazott_id = torzsadat_repo.alkalmazott_letrehoz(
            conn, szervezet_id=szervezet_id, bolt_id=bolt_id, nev="Hulk Hugan"
        )
        szolgaltatas_id = torzsadat_repo.szolgaltatas_letrehoz(
            conn,
            szervezet_id=szervezet_id,
            bolt_id=bolt_id,
            nev="boldogság",
            alap_idotartam_perc=15,
        )
        muszak_id = muszak_repo.muszak_letrehoz(
            conn,
            szervezet_id=szervezet_id,
            bolt_id=bolt_id,
            pult_id=pult_id,
            alkalmazott_id=alkalmazott_id,
            szolgaltatas_id=szolgaltatas_id,
            kezdet="2027-01-05T08:00:00Z",
            veg="2027-01-05T09:00:00Z",
            idotartam_perc=15,
            puffer_utana_perc=0,
            min_racs_perc=15,
            foglalhato_arany=1.0,
            blokk_szabaly={"szunetek": []},
        )
    finally:
        conn.close()
    return {
        "szervezet_id": szervezet_id,
        "bolt_id": bolt_id,
        "szolgaltatas_id": szolgaltatas_id,
        "muszak_id": muszak_id,
    }


def test_migral_uj_adatbazison(db_utvonal):
    kod = cli._migral([db_utvonal])
    assert kod == 0
    conn = sqlite3.connect(db_utvonal)
    tablak = {sor[0] for sor in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    conn.close()
    assert "muszak" in tablak


def test_slotok_general_es_ment(db_utvonal, alapadat):
    kod = cli._slotok([db_utvonal, alapadat["muszak_id"]])
    assert kod == 0
    conn = sqlite3.connect(db_utvonal)
    slot_szam = conn.execute(
        "SELECT COUNT(*) FROM slot WHERE muszak_id = ?", (alapadat["muszak_id"],)
    ).fetchone()[0]
    conn.close()
    assert slot_szam == 4  # 60 perc / 15 perc, szünet nélkül


def test_slotok_nincs_ilyen_muszak(db_utvonal, alapadat):
    kod = cli._slotok([db_utvonal, "0" * 32])
    assert kod == 1


def test_keres_ures_szabad_slot_nelkul(db_utvonal, alapadat):
    kod = cli._keres([db_utvonal, alapadat["szervezet_id"]])
    assert kod == 0  # "nincs szabad időpont" is sikeres futás, nem hiba


def test_keres_talal_szabad_slotot(db_utvonal, alapadat, capsys):
    cli._slotok([db_utvonal, alapadat["muszak_id"]])
    capsys.readouterr()  # az eddigi kimenet eldobása

    kod = cli._keres([db_utvonal, alapadat["szervezet_id"], "--bolt", alapadat["bolt_id"]])

    assert kod == 0
    kimenet = capsys.readouterr().out
    assert kimenet.count("\n") == 4  # 4 slot, soronként egy


def test_foglal_es_lemond_folyamata(db_utvonal, alapadat, capsys):
    cli._slotok([db_utvonal, alapadat["muszak_id"]])
    conn = sqlite3.connect(db_utvonal)
    slot_id = conn.execute(
        "SELECT id FROM slot WHERE muszak_id = ? ORDER BY kezdet LIMIT 1",
        (alapadat["muszak_id"],),
    ).fetchone()[0]
    conn.close()
    capsys.readouterr()

    foglal_kod = cli._foglal([db_utvonal, slot_id, "a" * 64, "idem-1", "session-1"])
    assert foglal_kod == 0
    kimenet = capsys.readouterr().out
    assert "sikeres" in kimenet
    assert "Foglalási kód:" in kimenet

    conn = sqlite3.connect(db_utvonal)
    foglalasi_kod = conn.execute(
        "SELECT foglalasi_kod FROM foglalas WHERE idempotencia_kulcs = 'idem-1'"
    ).fetchone()[0]
    conn.close()

    lemond_kod = cli._lemond([db_utvonal, foglalasi_kod])
    assert lemond_kod == 0

    ujra_lemond_kod = cli._lemond([db_utvonal, foglalasi_kod])
    assert ujra_lemond_kod == 1  # már lemondva — nem SIKERES


def test_foglal_masodik_probalkozas_megeloztek(db_utvonal, alapadat, capsys):
    cli._slotok([db_utvonal, alapadat["muszak_id"]])
    conn = sqlite3.connect(db_utvonal)
    slot_id = conn.execute(
        "SELECT id FROM slot WHERE muszak_id = ? ORDER BY kezdet LIMIT 1",
        (alapadat["muszak_id"],),
    ).fetchone()[0]
    conn.close()

    cli._foglal([db_utvonal, slot_id, "a" * 64, "idem-1", "session-1"])
    capsys.readouterr()
    masodik_kod = cli._foglal([db_utvonal, slot_id, "b" * 64, "idem-2", "session-2"])

    assert masodik_kod == 1
    assert "megeloztek" in capsys.readouterr().out


def test_holdok_takaritas(db_utvonal, alapadat, capsys):
    cli._slotok([db_utvonal, alapadat["muszak_id"]])
    conn = migracio.kapcsolat_nyitas(db_utvonal)
    slot_id = conn.execute(
        "SELECT id FROM slot WHERE muszak_id = ? LIMIT 1", (alapadat["muszak_id"],)
    ).fetchone()[0]
    # A lejar > letrejott CHECK a valódi rendszerórát nézi (most_iso()),
    # ezért a hold létrehozásakor a jövőben kell lennie — a "takarítás"
    # pillanatát viszont ennél is későbbre, 2099-re állítjuk, hogy már
    # lejártnak számítson.
    kozeli_jovo = (datetime.now(UTC) + timedelta(minutes=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
    foglalas_repo.hold_letrehoz(conn, slot_id, "session-1", kozeli_jovo)
    conn.close()
    capsys.readouterr()

    kod = cli._holdok_takaritas([db_utvonal, "2099-01-01T00:00:00Z"])

    assert kod == 0
    assert "Törölve: 1" in capsys.readouterr().out


def test_parancs_nelkuli_hivas_sugot_ir_ki(capsys):
    import sys

    ismert = list(sys.argv)
    try:
        sys.argv = ["mag.api.cli"]
        kod = cli._fo()
    finally:
        sys.argv = ismert

    assert kod == 1
    assert "Parancssori felület" in capsys.readouterr().out

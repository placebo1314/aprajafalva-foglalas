"""Egységtesztek a 0001_alapsema migrációra.

Minden teszt saját, ideiglenes SQLite fájlon fut (`tmp_path` pytest
fixture), tiszta állapotból indul, és a migrációt előbb lefuttatja.
"""

from __future__ import annotations

import sqlite3
import uuid

import pytest

from mag.repo import migracio

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


def _szervezet_beszur(conn: sqlite3.Connection) -> str:
    szervezet_id = _uuid()
    conn.execute(
        "INSERT INTO szervezet (id, nev, idozona, letrehozva) VALUES (?, ?, ?, ?)",
        (szervezet_id, "Aprajafalva", "Europe/Budapest", _MOST),
    )
    return szervezet_id


def _bolt_beszur(conn: sqlite3.Connection, szervezet_id: str, nev: str = "Bolt") -> str:
    bolt_id = _uuid()
    conn.execute(
        "INSERT INTO bolt (id, szervezet_id, nev, letrehozva) VALUES (?, ?, ?, ?)",
        (bolt_id, szervezet_id, nev, _MOST),
    )
    return bolt_id


def _szolgaltatas_beszur(conn: sqlite3.Connection, szervezet_id: str, bolt_id: str) -> str:
    szolgaltatas_id = _uuid()
    conn.execute(
        "INSERT INTO szolgaltatas "
        "(id, szervezet_id, bolt_id, nev, alap_idotartam_perc, letrehozva) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (szolgaltatas_id, szervezet_id, bolt_id, "kis petárda", 5, _MOST),
    )
    return szolgaltatas_id


def test_migracio_up_letrehozza_a_het_torzsadat_tablat(kapcsolat):
    tablak = {
        sor[0] for sor in kapcsolat.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
    }
    elvart = {
        "szervezet",
        "bolt",
        "pult",
        "alkalmazott",
        "szolgaltatas",
        "varians",
        "kivetel_nap",
    }
    assert elvart <= tablak


def test_visszagorgetes_teljesen_visszaallit(db_utvonal):
    conn = migracio.kapcsolat_nyitas(db_utvonal)
    migracio.migral(conn)
    visszagorgetve = migracio.visszagorget(conn)
    assert visszagorgetve == ["0001"]

    tablak = {sor[0] for sor in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    conn.close()

    # A sema_verzio a migrációs rendszer saját nyilvántartása, nem
    # migrációból jön (lásd mag/repo/migracio.py), ezért down után is
    # megmarad — de üresen, hiszen a 0001 sora törlődött.
    assert tablak == {"sema_verzio"}


def test_fk_kenyszer_elutasitja_nemletezo_hivatkozast(kapcsolat):
    with pytest.raises(sqlite3.IntegrityError):
        kapcsolat.execute(
            "INSERT INTO bolt (id, szervezet_id, nev, letrehozva) VALUES (?, ?, ?, ?)",
            (_uuid(), _uuid(), "Bolt egy nemlétező szervezetben", _MOST),
        )


def test_varians_idotartam_feluliras_nem_tolthetho_ki(kapcsolat):
    szervezet_id = _szervezet_beszur(kapcsolat)
    bolt_id = _bolt_beszur(kapcsolat, szervezet_id)
    szolgaltatas_id = _szolgaltatas_beszur(kapcsolat, szervezet_id, bolt_id)

    with pytest.raises(sqlite3.IntegrityError):
        kapcsolat.execute(
            "INSERT INTO varians "
            "(id, szervezet_id, szolgaltatas_id, nev, idotartam_feluliras, letrehozva) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (_uuid(), szervezet_id, szolgaltatas_id, "piros", 10, _MOST),
        )

    # NULL viszont megengedett — ez a normál, elvárt eset.
    kapcsolat.execute(
        "INSERT INTO varians "
        "(id, szervezet_id, szolgaltatas_id, nev, idotartam_feluliras, letrehozva) "
        "VALUES (?, ?, ?, ?, NULL, ?)",
        (_uuid(), szervezet_id, szolgaltatas_id, "piros", _MOST),
    )


@pytest.mark.xfail(
    reason=(
        "A kereszt-szervezeti hivatkozást a séma önmagában nem szűri ki. "
        "A mag/repo/ írási függvényeinek kell majd ellenőrizniük, hogy egy "
        "beszúrt/módosított sor szervezet_id-je megegyezik a hivatkozott "
        "sorok szervezet_id-jével — ez még nem íródott meg."
    ),
    strict=True,
)
def test_kereszt_szervezeti_hivatkozas_ma_nem_bukik_el(kapcsolat):
    """A séma nem köti össze DB-szinten a `varians.szervezet_id`-t a
    hivatkozott `szolgaltatas.szervezet_id`-vel — ezt a
    migraciok/0001_alapsema.sql fejléc-kommentje is jelzi. Ez a teszt azt
    az elvárt viselkedést írja le, hogy A szervezet egy variánsa nem
    hivatkozhatna B szervezet szolgáltatására; ma ez sikeresen beszúrható,
    ezért a teszt xfail — amint a mag/repo/ írási rétege ezt kikényszeríti,
    a teszt átfordul, és a `strict=True` miatt ez hibaként jelzi, hogy az
    xfail jelölést el kell távolítani.
    """
    a_szervezet = _szervezet_beszur(kapcsolat)
    b_szervezet = _szervezet_beszur(kapcsolat)

    b_bolt = _bolt_beszur(kapcsolat, b_szervezet, "B bolt")
    b_szolgaltatas = _szolgaltatas_beszur(kapcsolat, b_szervezet, b_bolt)

    # A varians A szervezet szervezet_id-jét kapja, de B szervezet
    # szolgáltatására hivatkozik — üzletileg értelmetlen kombináció.
    with pytest.raises(sqlite3.IntegrityError):
        kapcsolat.execute(
            "INSERT INTO varians "
            "(id, szervezet_id, szolgaltatas_id, nev, letrehozva) "
            "VALUES (?, ?, ?, ?, ?)",
            (_uuid(), a_szervezet, b_szolgaltatas, "kereszt-szervezeti", _MOST),
        )

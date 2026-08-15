"""Egységtesztek a 0002_muszak_slot migrációra.

Minden teszt saját, ideiglenes SQLite fájlon fut (`tmp_path` pytest
fixture), tiszta állapotból indul, és mindkét migrációt (0001, 0002)
lefuttatja.
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


def _torzsadat_beszur(conn: sqlite3.Connection) -> dict[str, str]:
    """Teljes láncot szúr be: szervezet → bolt → pult/alkalmazott/szolgaltatas."""
    szervezet_id = _uuid()
    conn.execute(
        "INSERT INTO szervezet (id, nev, idozona, letrehozva) VALUES (?, ?, ?, ?)",
        (szervezet_id, "Aprajafalva", "Europe/Budapest", _MOST),
    )
    bolt_id = _uuid()
    conn.execute(
        "INSERT INTO bolt (id, szervezet_id, nev, letrehozva) VALUES (?, ?, ?, ?)",
        (bolt_id, szervezet_id, "Törpilla boltja", _MOST),
    )
    pult_id = _uuid()
    conn.execute(
        "INSERT INTO pult (id, szervezet_id, bolt_id, nev, letrehozva) VALUES (?, ?, ?, ?, ?)",
        (pult_id, szervezet_id, bolt_id, "Pult 1", _MOST),
    )
    alkalmazott_id = _uuid()
    conn.execute(
        "INSERT INTO alkalmazott (id, szervezet_id, bolt_id, nev, letrehozva) "
        "VALUES (?, ?, ?, ?, ?)",
        (alkalmazott_id, szervezet_id, bolt_id, "Törpilla", _MOST),
    )
    szolgaltatas_id = _uuid()
    conn.execute(
        "INSERT INTO szolgaltatas "
        "(id, szervezet_id, bolt_id, nev, alap_idotartam_perc, letrehozva) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (szolgaltatas_id, szervezet_id, bolt_id, "kis petárda", 30, _MOST),
    )
    return {
        "szervezet_id": szervezet_id,
        "bolt_id": bolt_id,
        "pult_id": pult_id,
        "alkalmazott_id": alkalmazott_id,
        "szolgaltatas_id": szolgaltatas_id,
    }


def _muszak_beszur(conn: sqlite3.Connection, torzs: dict[str, str]) -> str:
    muszak_id = _uuid()
    conn.execute(
        "INSERT INTO muszak "
        "(id, szervezet_id, bolt_id, pult_id, alkalmazott_id, szolgaltatas_id, "
        "kezdet, veg, idotartam_perc, puffer_utana_perc, min_racs_perc, "
        "foglalhato_arany, blokk_szabaly, allapot, letrehozva) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            muszak_id,
            torzs["szervezet_id"],
            torzs["bolt_id"],
            torzs["pult_id"],
            torzs["alkalmazott_id"],
            torzs["szolgaltatas_id"],
            "2026-08-18T08:00:00Z",
            "2026-08-18T16:00:00Z",
            30,
            0,
            5,
            0.8,
            '{"strategia": "FixBlokk"}',
            "aktiv",
            _MOST,
        ),
    )
    return muszak_id


def _slot_beszur(
    conn: sqlite3.Connection,
    torzs: dict[str, str],
    muszak_id: str,
    kezdet: str = "2026-08-18T08:00:00Z",
    veg: str = "2026-08-18T08:30:00Z",
) -> str:
    slot_id = _uuid()
    conn.execute(
        "INSERT INTO slot (id, szervezet_id, muszak_id, kezdet, veg, letrehozva) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (slot_id, torzs["szervezet_id"], muszak_id, kezdet, veg, _MOST),
    )
    return slot_id


def _foglalas_beszur(
    conn: sqlite3.Connection,
    torzs: dict[str, str],
    slot_id: str,
    allapot: str = "aktiv",
    idempotencia_kulcs: str | None = None,
    foglalasi_kod: str | None = None,
) -> str:
    foglalas_id = _uuid()
    conn.execute(
        "INSERT INTO foglalas "
        "(id, szervezet_id, slot_id, vasarlo_kulcs, kulcs_verzio, "
        "idempotencia_kulcs, foglalasi_kod, allapot, letrehozva) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            foglalas_id,
            torzs["szervezet_id"],
            slot_id,
            "a" * 64,
            1,
            idempotencia_kulcs or _uuid(),
            foglalasi_kod or _uuid()[:8],
            allapot,
            _MOST,
        ),
    )
    return foglalas_id


def test_migracio_up_letrehozza_az_uj_tablakat(kapcsolat):
    tablak = {
        sor[0] for sor in kapcsolat.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
    }
    elvart = {"muszak", "muszak_blokk", "slot", "foglalas", "hold", "esemenyek"}
    assert elvart <= tablak


def test_visszagorgetes_teljesen_visszaallit(db_utvonal):
    conn = migracio.kapcsolat_nyitas(db_utvonal)
    migracio.migral(conn)
    visszagorgetve = migracio.visszagorget(conn)
    assert visszagorgetve == ["0002", "0001"]

    tablak = {sor[0] for sor in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    conn.close()
    assert tablak == {"sema_verzio"}


def test_egy_slotra_csak_egy_aktiv_foglalas_lehet(kapcsolat):
    torzs = _torzsadat_beszur(kapcsolat)
    muszak_id = _muszak_beszur(kapcsolat, torzs)
    slot_id = _slot_beszur(kapcsolat, torzs, muszak_id)

    _foglalas_beszur(kapcsolat, torzs, slot_id)

    with pytest.raises(sqlite3.IntegrityError):
        _foglalas_beszur(kapcsolat, torzs, slot_id)


def test_lemondas_utan_ugyanarra_a_slotra_ujra_foglalhato(kapcsolat):
    torzs = _torzsadat_beszur(kapcsolat)
    muszak_id = _muszak_beszur(kapcsolat, torzs)
    slot_id = _slot_beszur(kapcsolat, torzs, muszak_id)

    elso_foglalas_id = _foglalas_beszur(kapcsolat, torzs, slot_id)
    kapcsolat.execute("UPDATE foglalas SET allapot = 'lemondva' WHERE id = ?", (elso_foglalas_id,))

    # Most, hogy az egyetlen aktív foglalás lemondva, ugyanarra a slotra
    # újra be kell tudni szúrni — a parciális index csak az aktívakat védi.
    masodik_foglalas_id = _foglalas_beszur(kapcsolat, torzs, slot_id)
    assert masodik_foglalas_id != elso_foglalas_id


def test_hold_slotonkent_egyedi(kapcsolat):
    torzs = _torzsadat_beszur(kapcsolat)
    muszak_id = _muszak_beszur(kapcsolat, torzs)
    slot_id = _slot_beszur(kapcsolat, torzs, muszak_id)

    kapcsolat.execute(
        "INSERT INTO hold (id, szervezet_id, slot_id, session_id, letrejott, lejar) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (_uuid(), torzs["szervezet_id"], slot_id, "session-1", _MOST, "2026-08-15T10:03:00Z"),
    )

    with pytest.raises(sqlite3.IntegrityError):
        kapcsolat.execute(
            "INSERT INTO hold (id, szervezet_id, slot_id, session_id, letrejott, lejar) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (_uuid(), torzs["szervezet_id"], slot_id, "session-2", _MOST, "2026-08-15T10:03:00Z"),
        )


def test_idempotencia_kulcs_egyedi(kapcsolat):
    torzs = _torzsadat_beszur(kapcsolat)
    muszak_id = _muszak_beszur(kapcsolat, torzs)
    slot_1 = _slot_beszur(
        kapcsolat, torzs, muszak_id, "2026-08-18T08:00:00Z", "2026-08-18T08:30:00Z"
    )
    slot_2 = _slot_beszur(
        kapcsolat, torzs, muszak_id, "2026-08-18T08:30:00Z", "2026-08-18T09:00:00Z"
    )

    kozos_kulcs = _uuid()
    _foglalas_beszur(kapcsolat, torzs, slot_1, idempotencia_kulcs=kozos_kulcs)

    with pytest.raises(sqlite3.IntegrityError):
        _foglalas_beszur(kapcsolat, torzs, slot_2, idempotencia_kulcs=kozos_kulcs)


def test_foglalasi_kod_egyedi(kapcsolat):
    torzs = _torzsadat_beszur(kapcsolat)
    muszak_id = _muszak_beszur(kapcsolat, torzs)
    slot_1 = _slot_beszur(
        kapcsolat, torzs, muszak_id, "2026-08-18T08:00:00Z", "2026-08-18T08:30:00Z"
    )
    slot_2 = _slot_beszur(
        kapcsolat, torzs, muszak_id, "2026-08-18T08:30:00Z", "2026-08-18T09:00:00Z"
    )

    kozos_kod = "ABC12345"
    _foglalas_beszur(kapcsolat, torzs, slot_1, foglalasi_kod=kozos_kod)

    with pytest.raises(sqlite3.IntegrityError):
        _foglalas_beszur(kapcsolat, torzs, slot_2, foglalasi_kod=kozos_kod)


def test_fk_elutasitja_slot_beszurast_nemletezo_muszakra(kapcsolat):
    torzs = _torzsadat_beszur(kapcsolat)

    with pytest.raises(sqlite3.IntegrityError):
        kapcsolat.execute(
            "INSERT INTO slot (id, szervezet_id, muszak_id, kezdet, veg, letrehozva) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                _uuid(),
                torzs["szervezet_id"],
                _uuid(),  # nem létező muszak_id
                "2026-08-18T08:00:00Z",
                "2026-08-18T08:30:00Z",
                _MOST,
            ),
        )


def test_fk_elutasitja_foglalas_beszurast_nemletezo_slotra(kapcsolat):
    torzs = _torzsadat_beszur(kapcsolat)

    with pytest.raises(sqlite3.IntegrityError):
        _foglalas_beszur(kapcsolat, torzs, _uuid())  # nem létező slot_id


def test_fk_elutasitja_hold_beszurast_nemletezo_slotra(kapcsolat):
    torzs = _torzsadat_beszur(kapcsolat)

    with pytest.raises(sqlite3.IntegrityError):
        kapcsolat.execute(
            "INSERT INTO hold (id, szervezet_id, slot_id, session_id, letrejott, lejar) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                _uuid(),
                torzs["szervezet_id"],
                _uuid(),  # nem létező slot_id
                "session-1",
                _MOST,
                "2026-08-15T10:03:00Z",
            ),
        )


def test_muszak_blokk_tipus_ervenytelen_erteket_elutasit(kapcsolat):
    torzs = _torzsadat_beszur(kapcsolat)
    muszak_id = _muszak_beszur(kapcsolat, torzs)

    with pytest.raises(sqlite3.IntegrityError):
        kapcsolat.execute(
            "INSERT INTO muszak_blokk "
            "(id, szervezet_id, muszak_id, tipus, kezdet, veg, rogzitett, "
            "beszamit_kvotaba, letrehozva) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                _uuid(),
                torzs["szervezet_id"],
                muszak_id,
                "ebedszunet",  # nem szerepel a {szunet, ebed, szabad_sav} halmazban
                "2026-08-18T12:00:00Z",
                "2026-08-18T12:15:00Z",
                1,
                1,
                _MOST,
            ),
        )

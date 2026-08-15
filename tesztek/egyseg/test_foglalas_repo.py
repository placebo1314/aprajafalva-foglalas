"""Egységtesztek a mag/repo/foglalas_repo.py írási rétegére.

Nem konkurenciateszt — egyetlen kapcsolatból, szekvenciálisan hívja a
függvényeket, a versenyhelyzeti (párhuzamos írás) eseteket a
`konkurencia-teszto` agent tesztjei fedik (tesztek/konkurencia/).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from mag.repo import foglalas_repo, migracio
from mag.repo.foglalas_repo import Eredmeny

_MOST = "2026-08-15T10:00:00Z"


def _uuid() -> str:
    return uuid.uuid4().hex


def _jovoben(perc: int = 5) -> str:
    """Valódi 'most'-hoz képest a jövőben lévő ISO-8601 időpont — a hold
    lejar > letrejott CHECK-je a tényleges rendszerórát (most_iso())
    használja, nem a fix _MOST teszt-konstanst."""
    return (datetime.now(UTC) + timedelta(minutes=perc)).strftime("%Y-%m-%dT%H:%M:%SZ")


@pytest.fixture
def db_utvonal(tmp_path) -> str:
    return str(tmp_path / "teszt.db")


@pytest.fixture
def kapcsolat(db_utvonal):
    conn = migracio.kapcsolat_nyitas(db_utvonal)
    migracio.migral(conn)
    yield conn
    conn.close()


def _torzsadat_beszur(conn) -> dict[str, str]:
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


def _muszak_beszur(conn, torzs: dict[str, str]) -> str:
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
    conn,
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


@pytest.fixture
def slot(kapcsolat) -> str:
    torzs = _torzsadat_beszur(kapcsolat)
    muszak_id = _muszak_beszur(kapcsolat, torzs)
    return _slot_beszur(kapcsolat, torzs, muszak_id)


# --- slot_szabad ---------------------------------------------------------


def test_slot_szabad_igaz_uj_sloton(kapcsolat, slot):
    assert foglalas_repo.slot_szabad(kapcsolat, slot) is True


def test_slot_szabad_hamis_nemletezo_slotra(kapcsolat):
    assert foglalas_repo.slot_szabad(kapcsolat, _uuid()) is False


def test_slot_szabad_hamis_ha_van_hold(kapcsolat, slot):
    foglalas_repo.hold_letrehoz(kapcsolat, slot, "session-1", _jovoben())
    assert foglalas_repo.slot_szabad(kapcsolat, slot) is False


def test_slot_szabad_hamis_ha_van_aktiv_foglalas(kapcsolat, slot):
    foglalas_repo.foglalas_letrehoz(kapcsolat, slot, "a" * 64, _uuid(), "session-1")
    assert foglalas_repo.slot_szabad(kapcsolat, slot) is False


def test_slot_szabad_igaz_lemondott_foglalas_utan(kapcsolat, slot):
    foglalas_repo.foglalas_letrehoz(kapcsolat, slot, "a" * 64, _uuid(), "session-1")
    kod = kapcsolat.execute(
        "SELECT foglalasi_kod FROM foglalas WHERE slot_id = ?", (slot,)
    ).fetchone()[0]
    foglalas_repo.foglalas_lemond(kapcsolat, kod)
    assert foglalas_repo.slot_szabad(kapcsolat, slot) is True


# --- hold ------------------------------------------------------------------


def test_hold_letrehoz_sikeres(kapcsolat, slot):
    eredmeny = foglalas_repo.hold_letrehoz(kapcsolat, slot, "session-1", _jovoben())
    assert eredmeny is Eredmeny.SIKERES
    sorok = kapcsolat.execute("SELECT slot_id, session_id FROM hold").fetchall()
    assert sorok == [(slot, "session-1")]


def test_hold_letrehoz_nincs_ilyen_slotra(kapcsolat):
    eredmeny = foglalas_repo.hold_letrehoz(kapcsolat, _uuid(), "session-1", _jovoben())
    assert eredmeny is Eredmeny.NINCS_ILYEN


def test_hold_letrehoz_megeloztek_masik_hold_miatt(kapcsolat, slot):
    foglalas_repo.hold_letrehoz(kapcsolat, slot, "session-1", _jovoben())
    eredmeny = foglalas_repo.hold_letrehoz(kapcsolat, slot, "session-2", _jovoben())
    assert eredmeny is Eredmeny.MEGELOZTEK
    assert kapcsolat.execute("SELECT COUNT(*) FROM hold").fetchone()[0] == 1


def test_hold_letrehoz_megeloztek_aktiv_foglalas_miatt(kapcsolat, slot):
    foglalas_repo.foglalas_letrehoz(kapcsolat, slot, "a" * 64, _uuid(), "session-1")
    eredmeny = foglalas_repo.hold_letrehoz(kapcsolat, slot, "session-2", _jovoben())
    assert eredmeny is Eredmeny.MEGELOZTEK
    assert kapcsolat.execute("SELECT COUNT(*) FROM hold").fetchone()[0] == 0


def test_hold_felszabadit_sikeres(kapcsolat, slot):
    foglalas_repo.hold_letrehoz(kapcsolat, slot, "session-1", _jovoben())
    hold_id = kapcsolat.execute("SELECT id FROM hold WHERE slot_id = ?", (slot,)).fetchone()[0]

    eredmeny = foglalas_repo.hold_felszabadit(kapcsolat, hold_id)
    assert eredmeny is Eredmeny.SIKERES
    assert kapcsolat.execute("SELECT COUNT(*) FROM hold").fetchone()[0] == 0
    # A felszabadított slot újra foglalható.
    assert foglalas_repo.slot_szabad(kapcsolat, slot) is True


def test_hold_felszabadit_nincs_ilyen(kapcsolat):
    eredmeny = foglalas_repo.hold_felszabadit(kapcsolat, _uuid())
    assert eredmeny is Eredmeny.NINCS_ILYEN


def test_lejart_holdok_takaritasa_csak_a_lejarottakat_torli(kapcsolat):
    torzs = _torzsadat_beszur(kapcsolat)
    muszak_id = _muszak_beszur(kapcsolat, torzs)
    lejaro_slot = _slot_beszur(
        kapcsolat, torzs, muszak_id, "2026-08-18T08:00:00Z", "2026-08-18T08:30:00Z"
    )
    elo_slot = _slot_beszur(
        kapcsolat, torzs, muszak_id, "2026-08-18T08:30:00Z", "2026-08-18T09:00:00Z"
    )

    hamarosan_lejaro = _jovoben(1)
    sokaig_elo = _jovoben(60)
    foglalas_repo.hold_letrehoz(kapcsolat, lejaro_slot, "session-1", hamarosan_lejaro)
    foglalas_repo.hold_letrehoz(kapcsolat, elo_slot, "session-2", sokaig_elo)

    # A "most" a két lejárat közé esik: az első már lejárt, a második nem.
    kozepso_ido = (
        datetime.strptime(hamarosan_lejaro, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
        + timedelta(seconds=30)
    ).strftime("%Y-%m-%dT%H:%M:%SZ")

    torolt_id_k = foglalas_repo.lejart_holdok_takaritasa(kapcsolat, kozepso_ido)

    megmaradt = {sor[0] for sor in kapcsolat.execute("SELECT slot_id FROM hold")}
    assert megmaradt == {elo_slot}
    assert len(torolt_id_k) == 1

    esemenyek = {
        sor[0]
        for sor in kapcsolat.execute("SELECT tipus FROM esemenyek WHERE tipus = 'hold_lejart'")
    }
    assert esemenyek == {"hold_lejart"}


def test_lejart_holdok_takaritasa_ures_ha_nincs_lejart(kapcsolat, slot):
    foglalas_repo.hold_letrehoz(kapcsolat, slot, "session-1", _jovoben(60))
    torolt = foglalas_repo.lejart_holdok_takaritasa(kapcsolat, _MOST)
    assert torolt == []
    assert kapcsolat.execute("SELECT COUNT(*) FROM hold").fetchone()[0] == 1


# --- foglalas_letrehoz -------------------------------------------------


def test_foglalas_letrehoz_sikeres_es_torli_a_holdot(kapcsolat, slot):
    foglalas_repo.hold_letrehoz(kapcsolat, slot, "session-1", _jovoben())

    eredmeny = foglalas_repo.foglalas_letrehoz(kapcsolat, slot, "a" * 64, _uuid(), "session-1")

    assert eredmeny is Eredmeny.SIKERES
    assert kapcsolat.execute("SELECT COUNT(*) FROM foglalas").fetchone()[0] == 1
    # Nincs kettős könyvelés: a hold eltűnik, amint valódi foglalás lesz.
    assert kapcsolat.execute("SELECT COUNT(*) FROM hold").fetchone()[0] == 0


def test_foglalas_letrehoz_nincs_ilyen_slotra(kapcsolat):
    eredmeny = foglalas_repo.foglalas_letrehoz(kapcsolat, _uuid(), "a" * 64, _uuid(), "session-1")
    assert eredmeny is Eredmeny.NINCS_ILYEN


def test_foglalas_letrehoz_megeloztek_masodik_aktiv_foglalasra(kapcsolat, slot):
    elso = foglalas_repo.foglalas_letrehoz(kapcsolat, slot, "a" * 64, _uuid(), "session-1")
    assert elso is Eredmeny.SIKERES

    masodik = foglalas_repo.foglalas_letrehoz(kapcsolat, slot, "b" * 64, _uuid(), "session-2")
    assert masodik is Eredmeny.MEGELOZTEK
    assert kapcsolat.execute("SELECT COUNT(*) FROM foglalas").fetchone()[0] == 1


def test_foglalas_letrehoz_idempotens_ismetles_nem_hoz_letre_uj_sort(kapcsolat, slot):
    kulcs = _uuid()
    elso = foglalas_repo.foglalas_letrehoz(kapcsolat, slot, "a" * 64, kulcs, "session-1")
    masodik = foglalas_repo.foglalas_letrehoz(kapcsolat, slot, "a" * 64, kulcs, "session-1")

    assert elso is Eredmeny.SIKERES
    assert masodik is Eredmeny.SIKERES
    assert kapcsolat.execute("SELECT COUNT(*) FROM foglalas").fetchone()[0] == 1


def test_foglalas_letrehoz_esemenyt_ir(kapcsolat, slot):
    foglalas_repo.foglalas_letrehoz(kapcsolat, slot, "a" * 64, _uuid(), "session-1")
    esemenyek = [
        sor[0]
        for sor in kapcsolat.execute("SELECT tipus FROM esemenyek WHERE entitas_tipus = 'foglalas'")
    ]
    assert esemenyek == ["foglalas_letrejott"]


# --- foglalas_lemond -----------------------------------------------------


def test_foglalas_lemond_sikeres(kapcsolat, slot):
    foglalas_repo.foglalas_letrehoz(kapcsolat, slot, "a" * 64, _uuid(), "session-1")
    kod = kapcsolat.execute(
        "SELECT foglalasi_kod FROM foglalas WHERE slot_id = ?", (slot,)
    ).fetchone()[0]

    eredmeny = foglalas_repo.foglalas_lemond(kapcsolat, kod)

    assert eredmeny is Eredmeny.SIKERES
    allapot = kapcsolat.execute(
        "SELECT allapot FROM foglalas WHERE slot_id = ?", (slot,)
    ).fetchone()[0]
    assert allapot == "lemondva"


def test_foglalas_lemond_nincs_ilyen_kodra(kapcsolat):
    eredmeny = foglalas_repo.foglalas_lemond(kapcsolat, "NEMLETEZO")
    assert eredmeny is Eredmeny.NINCS_ILYEN


def test_foglalas_lemond_mar_lemondva(kapcsolat, slot):
    foglalas_repo.foglalas_letrehoz(kapcsolat, slot, "a" * 64, _uuid(), "session-1")
    kod = kapcsolat.execute(
        "SELECT foglalasi_kod FROM foglalas WHERE slot_id = ?", (slot,)
    ).fetchone()[0]
    foglalas_repo.foglalas_lemond(kapcsolat, kod)

    eredmeny = foglalas_repo.foglalas_lemond(kapcsolat, kod)
    assert eredmeny is Eredmeny.MAR_LEMONDVA


def test_foglalas_lemond_esemenyeket_ir(kapcsolat, slot):
    foglalas_repo.foglalas_letrehoz(kapcsolat, slot, "a" * 64, _uuid(), "session-1")
    kod = kapcsolat.execute(
        "SELECT foglalasi_kod FROM foglalas WHERE slot_id = ?", (slot,)
    ).fetchone()[0]
    foglalas_repo.foglalas_lemond(kapcsolat, kod)

    tipusok = [
        sor[0]
        for sor in kapcsolat.execute(
            "SELECT tipus FROM esemenyek WHERE tipus IN ('foglalas_lemondva', 'slot_felszabadult')"
        )
    ]
    assert set(tipusok) == {"foglalas_lemondva", "slot_felszabadult"}

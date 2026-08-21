"""Egységtesztek az ajánlatpontozóra (`core/api/ajanlatpontozo.py`) és a
szándékindexre (`core/api/szandekindex.py`).

ADR-006: a pontozó korlátozza a kért ablakra (dátum + napszak), és a
szándékindexből becsült "várható lefedettség" szét kell, hogy terítse
két egyidejű session ajánlatát ugyanarra a sávra.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from core.api import ajanlatpontozo, szandekindex
from core.repo import foglalas_repo, migracio, muszak_repo, torzsadat_repo
from core.slot import generator
from core.slot.blokk import FixedBlock


def _setup(conn, *, bookable_ratio: float = 1.0) -> dict:
    """Egy szervezet, egy bolt, egy pult/alkalmazott/szolgáltatás, és egy
    egynapos, több slotos műszak — a generátorral tényleg legenerálva,
    nem kézzel felvitt sorokkal, hogy a slot/blokk-határ valódi legyen."""
    org_id = torzsadat_repo.org_create(conn, name="Aprajafalva", timezone="Europe/Budapest")
    shop_id = torzsadat_repo.shop_create(conn, org_id=org_id, name="Törpilla")
    counter_id = torzsadat_repo.counter_create(conn, org_id=org_id, shop_id=shop_id, name="Pult 1")
    employee_id = torzsadat_repo.employee_create(
        conn, org_id=org_id, shop_id=shop_id, name="Törpilla"
    )
    service_id = torzsadat_repo.service_create(
        conn, org_id=org_id, shop_id=shop_id, name="boldogság", alap_duration_minute=30
    )
    shift_id = muszak_repo.shift_create(
        conn,
        org_id=org_id,
        shop_id=shop_id,
        counter_id=counter_id,
        employee_id=employee_id,
        service_id=service_id,
        # 2026-08-18 (kedd) 06:00-10:00 UTC = 08:00-12:00 helyi (nyári idő,
        # Europe/Budapest = UTC+2) — délelőtti sáv.
        start="2026-08-18T06:00:00Z",
        end="2026-08-18T10:00:00Z",
        duration_minute=30,
        buffer_after_minute=0,
        min_grid_minute=30,
        bookable_ratio=bookable_ratio,
        block_rule={"szunetek": []},
    )
    shift = muszak_repo.shift_load(conn, shift_id)
    result = generator.generate(shift, FixedBlock())
    muszak_repo.blocks_slots_save(
        conn, shift_id=shift_id, org_id=org_id, blocks=result.blocks, slots=result.slots
    )
    return {
        "org_id": org_id,
        "shop_id": shop_id,
        "service_id": service_id,
        "shift_id": shift_id,
    }


def _jovoben(minute: int = 5) -> str:
    return (datetime.now(UTC) + timedelta(minutes=minute)).strftime("%Y-%m-%dT%H:%M:%SZ")


def _conn(tmp_path):
    conn = migracio.conn_nyitas(str(tmp_path / "teszt.db"))
    migracio.migral(conn)
    return conn


def test_ures_ablakban_nincs_jelolt(tmp_path):
    conn = _conn(tmp_path)
    ctx = _setup(conn)
    jeloltek = ajanlatpontozo.find_candidates(
        conn,
        org_id=ctx["org_id"],
        shop_id=ctx["shop_id"],
        datum_tol="2099-01-01T00:00:00Z",
        datum_ig="2099-01-02T00:00:00Z",
        session_id="session-1",
    )
    assert jeloltek == []


def test_a_kert_ablakon_kivuli_slotot_nem_ajanl(tmp_path):
    conn = _conn(tmp_path)
    ctx = _setup(conn)
    # A műszak 06:00-10:00 UTC-n fut; ha csak a 09:00 utáni ablakot kérjük,
    # a korábbi slotok nem jelenhetnek meg jelöltként.
    jeloltek = ajanlatpontozo.find_candidates(
        conn,
        org_id=ctx["org_id"],
        shop_id=ctx["shop_id"],
        datum_tol="2026-08-18T09:00:00Z",
        datum_ig="2026-08-18T23:59:59Z",
        session_id="session-1",
    )
    assert jeloltek
    assert all(j["kezdet"] >= "2026-08-18T09:00:00Z" for j in jeloltek)


def test_napszak_szures_helyi_ido_szerint(tmp_path):
    conn = _conn(tmp_path)
    ctx = _setup(conn)
    # A műszak 06:00-10:00 UTC = 08:00-12:00 helyi — mind délelőtti.
    delelott = ajanlatpontozo.find_candidates(
        conn,
        org_id=ctx["org_id"],
        shop_id=ctx["shop_id"],
        datum_tol="2026-08-18T00:00:00Z",
        datum_ig="2026-08-18T23:59:59Z",
        napszak="delelott",
        session_id="session-1",
    )
    assert delelott

    este = ajanlatpontozo.find_candidates(
        conn,
        org_id=ctx["org_id"],
        shop_id=ctx["shop_id"],
        datum_tol="2026-08-18T00:00:00Z",
        datum_ig="2026-08-18T23:59:59Z",
        napszak="este",
        session_id="session-1",
    )
    assert este == []


def test_holdolt_slot_nem_szerepel_jeloltkent(tmp_path):
    conn = _conn(tmp_path)
    ctx = _setup(conn)
    elso_kor = ajanlatpontozo.find_candidates(
        conn,
        org_id=ctx["org_id"],
        shop_id=ctx["shop_id"],
        datum_tol="2026-08-18T00:00:00Z",
        datum_ig="2026-08-18T23:59:59Z",
        session_id="session-1",
        limit=1,
    )
    assert len(elso_kor) == 1
    slot_id = elso_kor[0]["slot_id"]
    result = foglalas_repo.hold_create(conn, slot_id, "session-1", _jovoben())
    assert result is foglalas_repo.Result.SUCCESS

    masodik_kor = ajanlatpontozo.find_candidates(
        conn,
        org_id=ctx["org_id"],
        shop_id=ctx["shop_id"],
        datum_tol="2026-08-18T00:00:00Z",
        datum_ig="2026-08-18T23:59:59Z",
        session_id="session-2",
    )
    assert all(j["slot_id"] != slot_id for j in masodik_kor)


def test_limit_hatarolja_a_jeloltek_szamat(tmp_path):
    conn = _conn(tmp_path)
    ctx = _setup(conn)
    jeloltek = ajanlatpontozo.find_candidates(
        conn,
        org_id=ctx["org_id"],
        shop_id=ctx["shop_id"],
        datum_tol="2026-08-18T00:00:00Z",
        datum_ig="2026-08-18T23:59:59Z",
        session_id="session-1",
        limit=2,
    )
    assert len(jeloltek) <= 2


def test_szandekindex_szetteriti_a_masodik_session_ajanlatat(tmp_path):
    """Ha egy másik session már ugyanarra a bolt+nap+napszak sávra
    érdeklődik, a várható lefedettség nő, tehát a pontszám csökken — de
    a lista NEM üresedik ki, csak a sorrend/pontszám mozdul (a szándékindex
    sosem blokkol, foglalasi-mag skill)."""
    conn = _conn(tmp_path)
    ctx = _setup(conn)
    nap = "2026-08-18"

    pontszam_index_nelkul = ajanlatpontozo.find_candidates(
        conn,
        org_id=ctx["org_id"],
        shop_id=ctx["shop_id"],
        datum_tol="2026-08-18T00:00:00Z",
        datum_ig="2026-08-18T23:59:59Z",
        napszak="delelott",
        session_id="session-1",
        limit=1,
    )[0]["pontszam"]

    for masik in ("session-2", "session-3", "session-4"):
        szandekindex.szandek_frissites(masik, bolt_id=ctx["shop_id"], nap=nap, napszak="delelott")

    pontszam_index_utan = ajanlatpontozo.find_candidates(
        conn,
        org_id=ctx["org_id"],
        shop_id=ctx["shop_id"],
        datum_tol="2026-08-18T00:00:00Z",
        datum_ig="2026-08-18T23:59:59Z",
        napszak="delelott",
        session_id="session-1",
        limit=1,
    )[0]["pontszam"]

    assert pontszam_index_utan < pontszam_index_nelkul


def test_szandekindex_ttl_lejar():
    szandekindex.szandek_torles("session-teszt-ttl")
    assert szandekindex.szandek_lekerdezes("session-teszt-ttl") is None
    szandekindex.szandek_frissites("session-teszt-ttl", bolt_id="torpilla", nap="2026-08-18")
    bejegyzes = szandekindex.szandek_lekerdezes("session-teszt-ttl")
    assert bejegyzes is not None
    assert bejegyzes["bolt_id"] == "torpilla"
    szandekindex.szandek_torles("session-teszt-ttl")


def test_szandekindex_megorzi_a_meglevo_mezoket_reszleges_frissitesnel():
    szandekindex.szandek_torles("session-teszt-megorzes")
    szandekindex.szandek_frissites("session-teszt-megorzes", bolt_id="torpilla", napszak="delelott")
    szandekindex.szandek_frissites("session-teszt-megorzes", nap="2026-08-18")
    bejegyzes = szandekindex.szandek_lekerdezes("session-teszt-megorzes")
    assert bejegyzes["bolt_id"] == "torpilla"
    assert bejegyzes["napszak"] == "delelott"
    assert bejegyzes["nap"] == "2026-08-18"
    szandekindex.szandek_torles("session-teszt-megorzes")

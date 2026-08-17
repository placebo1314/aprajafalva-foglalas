"""Helyreállítási próba: ment, töröl, visszaállít, ellenőrzi, hogy a
foglalások megvannak.

Blueprint 9. szakasz: "az a mentés, amit sosem állítottak vissza, nem
mentés" — ez a teszt maga a próba, nem csak a mentés függvényének
egységtesztje.
"""

from __future__ import annotations

import os
import sqlite3

import pytest

from core.repo import foglalas_repo, mentes, migracio, muszak_repo, torzsadat_repo


@pytest.fixture
def original_db(tmp_path) -> str:
    return str(tmp_path / "eredeti.db")


def _booking_create(db_path: str) -> dict:
    """Migrál, felvesz egy minimális törzsadatot, egy slotot, és egy
    aktív foglalást rajta. Visszaadja a legfontosabb azonosítókat."""
    conn = migracio.conn_nyitas(db_path)
    try:
        migracio.migral(conn)
        org_id = torzsadat_repo.org_create(conn, name="Aprajafalva", timezone="Europe/Budapest")
        shop_id = torzsadat_repo.shop_create(conn, org_id=org_id, name="Törpilla")
        counter_id = torzsadat_repo.counter_create(
            conn, org_id=org_id, shop_id=shop_id, name="Pult 1"
        )
        employee_id = torzsadat_repo.employee_create(
            conn, org_id=org_id, shop_id=shop_id, name="Hulk Hugan"
        )
        service_id = torzsadat_repo.service_create(
            conn,
            org_id=org_id,
            shop_id=shop_id,
            name="boldogság",
            alap_duration_minute=15,
        )
        shift_id = muszak_repo.shift_create(
            conn,
            org_id=org_id,
            shop_id=shop_id,
            counter_id=counter_id,
            employee_id=employee_id,
            service_id=service_id,
            start="2027-01-05T08:00:00Z",
            end="2027-01-05T08:15:00Z",
            duration_minute=15,
            buffer_after_minute=0,
            min_grid_minute=15,
            bookable_ratio=1.0,
            block_rule={"szunetek": []},
        )
        shift = muszak_repo.shift_load(conn, shift_id)
        from core.slot import generator
        from core.slot.blokk import FixedBlock

        result = generator.generate(shift, FixedBlock())
        muszak_repo.blocks_slots_save(
            conn,
            shift_id=shift_id,
            org_id=org_id,
            blocks=result.blocks,
            slots=result.slots,
        )
        (slot_id,) = conn.execute("SELECT id FROM slot WHERE muszak_id = ?", (shift_id,)).fetchone()

        booking_result = foglalas_repo.booking_create(
            conn, slot_id, "a" * 64, "idem-mentes-teszt", "session-1"
        )
        assert booking_result is foglalas_repo.Result.SUCCESS

        booking = foglalas_repo.booking_query_idempotency_by(conn, "idem-mentes-teszt")
    finally:
        conn.close()

    return {
        "slot_id": slot_id,
        "foglalas_id": booking["id"],
        "foglalasi_kod": booking["foglalasi_kod"],
    }


def test_mentes_delete_restore_booking_exists(tmp_path, original_db):
    data = _booking_create(original_db)

    snapshot_path = tmp_path / "pillanatkep.db"
    mentes.snapshot_create(original_db, snapshot_path)
    assert snapshot_path.exists()

    # "Katasztrófa": az eredeti adatbázis (és a WAL-melléktermékei) eltűnnek.
    os.remove(original_db)
    for attachment in (original_db + "-wal", original_db + "-shm"):
        if os.path.exists(attachment):
            os.remove(attachment)
    assert not os.path.exists(original_db)

    restored_db = tmp_path / "visszaallitott.db"
    mentes.restore(snapshot_path, restored_db)

    conn = sqlite3.connect(str(restored_db))
    try:
        row = conn.execute(
            "SELECT id, slot_id, foglalasi_kod, allapot FROM foglalas WHERE id = ?",
            (data["foglalas_id"],),
        ).fetchone()
        assert row is not None, "a foglalás nem élte túl a mentés-visszaállítás kört"
        assert row[1] == data["slot_id"]
        assert row[2] == data["foglalasi_kod"]
        assert row[3] == "aktiv"

        # A parciális UNIQUE index a visszaállított DB-ben is érvényben
        # van — nem csak az adat, a kényszer is túléli a kört.
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO foglalas "
                "(id, szervezet_id, slot_id, vasarlo_kulcs, kulcs_verzio, "
                "idempotencia_kulcs, foglalasi_kod, allapot, letrehozva) "
                "SELECT '1' || substr(id, 2), szervezet_id, slot_id, vasarlo_kulcs, "
                "kulcs_verzio, 'masik-kulcs', 'MASIKKOD', allapot, letrehozva "
                "FROM foglalas WHERE id = ?",
                (data["foglalas_id"],),
            )
    finally:
        conn.close()


def test_snapshot_not_writes_felul_existing_target(tmp_path, original_db):
    _booking_create(original_db)
    target = tmp_path / "pillanatkep.db"
    mentes.snapshot_create(original_db, target)

    with pytest.raises(FileExistsError):
        mentes.snapshot_create(original_db, target)

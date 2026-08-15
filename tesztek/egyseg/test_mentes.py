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

from mag.repo import foglalas_repo, mentes, migracio, muszak_repo, torzsadat_repo


@pytest.fixture
def eredeti_db(tmp_path) -> str:
    return str(tmp_path / "eredeti.db")


def _foglalast_letrehoz(db_utvonal: str) -> dict:
    """Migrál, felvesz egy minimális törzsadatot, egy slotot, és egy
    aktív foglalást rajta. Visszaadja a legfontosabb azonosítókat."""
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
            veg="2027-01-05T08:15:00Z",
            idotartam_perc=15,
            puffer_utana_perc=0,
            min_racs_perc=15,
            foglalhato_arany=1.0,
            blokk_szabaly={"szunetek": []},
        )
        muszak = muszak_repo.muszak_betoltese(conn, muszak_id)
        from mag.slot import generator
        from mag.slot.blokk import FixBlokk

        eredmeny = generator.general(muszak, FixBlokk())
        muszak_repo.blokkok_slotok_mentese(
            conn,
            muszak_id=muszak_id,
            szervezet_id=szervezet_id,
            blokkok=eredmeny.blokkok,
            slotok=eredmeny.slotok,
        )
        (slot_id,) = conn.execute(
            "SELECT id FROM slot WHERE muszak_id = ?", (muszak_id,)
        ).fetchone()

        foglalas_eredmeny = foglalas_repo.foglalas_letrehoz(
            conn, slot_id, "a" * 64, "idem-mentes-teszt", "session-1"
        )
        assert foglalas_eredmeny is foglalas_repo.Eredmeny.SIKERES

        foglalas = foglalas_repo.foglalas_lekerdezes_idempotencia_szerint(conn, "idem-mentes-teszt")
    finally:
        conn.close()

    return {
        "slot_id": slot_id,
        "foglalas_id": foglalas["id"],
        "foglalasi_kod": foglalas["foglalasi_kod"],
    }


def test_mentes_torles_visszaallitas_a_foglalas_megvan(tmp_path, eredeti_db):
    adat = _foglalast_letrehoz(eredeti_db)

    pillanatkep_utvonal = tmp_path / "pillanatkep.db"
    mentes.pillanatkep_keszit(eredeti_db, pillanatkep_utvonal)
    assert pillanatkep_utvonal.exists()

    # "Katasztrófa": az eredeti adatbázis (és a WAL-melléktermékei) eltűnnek.
    os.remove(eredeti_db)
    for melleklet in (eredeti_db + "-wal", eredeti_db + "-shm"):
        if os.path.exists(melleklet):
            os.remove(melleklet)
    assert not os.path.exists(eredeti_db)

    visszaallitott_db = tmp_path / "visszaallitott.db"
    mentes.visszaallit(pillanatkep_utvonal, visszaallitott_db)

    conn = sqlite3.connect(str(visszaallitott_db))
    try:
        sor = conn.execute(
            "SELECT id, slot_id, foglalasi_kod, allapot FROM foglalas WHERE id = ?",
            (adat["foglalas_id"],),
        ).fetchone()
        assert sor is not None, "a foglalás nem élte túl a mentés-visszaállítás kört"
        assert sor[1] == adat["slot_id"]
        assert sor[2] == adat["foglalasi_kod"]
        assert sor[3] == "aktiv"

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
                (adat["foglalas_id"],),
            )
    finally:
        conn.close()


def test_pillanatkep_nem_irja_felul_a_meglevo_celt(tmp_path, eredeti_db):
    _foglalast_letrehoz(eredeti_db)
    cel = tmp_path / "pillanatkep.db"
    mentes.pillanatkep_keszit(eredeti_db, cel)

    with pytest.raises(FileExistsError):
        mentes.pillanatkep_keszit(eredeti_db, cel)

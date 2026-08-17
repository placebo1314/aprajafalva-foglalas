"""Parancssori felület a foglalási maghoz.

Ez a mag mérföldköve: innen minden művelet elvégezhető LLM nélkül
(CLAUDE.md, alapelv: "Az LLM nem foglal, hanem fordít.").

    python -m mag.api.cli migral <db_utvonal>
    python -m mag.api.cli seed [<db_utvonal>]
    python -m mag.api.cli slotok <db_utvonal> <muszak_id>
    python -m mag.api.cli keres <db_utvonal> <szervezet_id> [--bolt ID] [--szolgaltatas ID]
    python -m mag.api.cli foglal <db_utvonal> <slot_id> <vasarlo_kulcs_hash> \
        <idempotencia_kulcs> <session_id>
    python -m mag.api.cli lemond <db_utvonal> <foglalasi_kod>
    python -m mag.api.cli holdok-takaritas <db_utvonal> [most_iso]
    python -m mag.api.cli demo-verseny [--sessziok 2|3] [--mag SZAM]

A `vasarlo_kulcs_hash` MÁR HMAC-hashelt érték (64 hex karakter) — a nyers
vásárlóazonosítót a mag/ soha nem kapja meg (CLAUDE.md, 2. invariáns). A
hashelés az `adatvedelem/` modul feladata lesz; amíg az nincs megírva, a
hívó (asszisztens/ vagy a te kezed) felelőssége előre kiszámítani.

A `keres` parancs NEM az ajánlatpontozó (ADR-006) — puszta, rendezetlen
listázás, lásd `mag/repo/foglalas_repo.py::szabad_slotok_keresese`.
"""

from __future__ import annotations

import sys

from mag.ido import most_iso
from mag.repo import foglalas_repo, migracio, muszak_repo
from mag.slot import generator
from mag.slot.blokk import FixBlokk


def _opcio(argv: list[str], nev: str) -> str | None:
    if nev in argv:
        idx = argv.index(nev)
        if idx + 1 < len(argv):
            return argv[idx + 1]
    return None


def _migral(argv: list[str]) -> int:
    if not argv:
        print("Használat: migral <db_utvonal>")
        return 1
    conn = migracio.kapcsolat_nyitas(argv[0])
    try:
        eredmeny = migracio.migral(conn)
        print(f"Lefuttatva: {eredmeny}" if eredmeny else "Minden migráció naprakész.")
    finally:
        conn.close()
    return 0


def _seed(argv: list[str]) -> int:
    from seed.betolt import ALAP_DB_UTVONAL, betolt

    db_utvonal = argv[0] if argv else str(ALAP_DB_UTVONAL)
    adat = betolt(db_utvonal)
    print(f"Betöltve: {db_utvonal} (szervezet: {adat['szervezet_id']})")
    return 0


def _slotok(argv: list[str]) -> int:
    if len(argv) < 2:
        print("Használat: slotok <db_utvonal> <muszak_id>")
        return 1
    db_utvonal, muszak_id = argv[0], argv[1]
    conn = migracio.kapcsolat_nyitas(db_utvonal)
    try:
        muszak = muszak_repo.muszak_betoltese(conn, muszak_id)
        if muszak is None:
            print(f"Nincs ilyen műszak: {muszak_id}")
            return 1
        # Csak szervezet-szintű kivetel_nap-ot néz — a Muszak modell nem
        # tartalmaz bolt_id-t (a generálás nem függ tőle), ezért egy
        # bolt-specifikus kivételnap itt nem szűrődik ki. Ha ez élesben
        # gond, a muszak_repo.muszak_betoltese-t kell bővíteni.
        kivetel_napok = muszak_repo.kivetel_napok_lekerdezese(
            conn, szervezet_id=muszak.szervezet_id
        )
        eredmeny = generator.general(muszak, FixBlokk(), kivetel_napok=kivetel_napok)
        if eredmeny.kihagyva:
            print(f"Kihagyva (kivetel_nap: {eredmeny.kihagyas_oka})")
            return 0
        muszak_repo.blokkok_slotok_mentese(
            conn,
            muszak_id=muszak_id,
            szervezet_id=muszak.szervezet_id,
            blokkok=eredmeny.blokkok,
            slotok=eredmeny.slotok,
        )
        print(f"Létrehozva: {len(eredmeny.slotok)} slot, {len(eredmeny.blokkok)} blokk.")
    finally:
        conn.close()
    return 0


def _keres(argv: list[str]) -> int:
    if len(argv) < 2:
        print("Használat: keres <db_utvonal> <szervezet_id> [--bolt ID] [--szolgaltatas ID]")
        return 1
    db_utvonal, szervezet_id = argv[0], argv[1]
    bolt_id = _opcio(argv, "--bolt")
    szolgaltatas_id = _opcio(argv, "--szolgaltatas")
    conn = migracio.kapcsolat_nyitas(db_utvonal)
    try:
        talalatok = foglalas_repo.szabad_slotok_keresese(
            conn,
            szervezet_id=szervezet_id,
            bolt_id=bolt_id,
            szolgaltatas_id=szolgaltatas_id,
        )
        if not talalatok:
            print("Nincs szabad időpont.")
            return 0
        for slot_id, kezdet, veg in talalatok:
            print(f"{slot_id}  {kezdet} – {veg}")
    finally:
        conn.close()
    return 0


def _foglal(argv: list[str]) -> int:
    if len(argv) < 5:
        print(
            "Használat: foglal <db_utvonal> <slot_id> <vasarlo_kulcs_hash> "
            "<idempotencia_kulcs> <session_id>"
        )
        return 1
    db_utvonal, slot_id, vasarlo_kulcs, idempotencia_kulcs, session_id = argv[:5]
    conn = migracio.kapcsolat_nyitas(db_utvonal)
    try:
        eredmeny = foglalas_repo.foglalas_letrehoz(
            conn, slot_id, vasarlo_kulcs, idempotencia_kulcs, session_id
        )
        print(f"Eredmény: {eredmeny.value}")
        if eredmeny is foglalas_repo.Eredmeny.SIKERES:
            foglalas = foglalas_repo.foglalas_lekerdezes_idempotencia_szerint(
                conn, idempotencia_kulcs
            )
            if foglalas:
                print(f"Foglalási kód: {foglalas['foglalasi_kod']}")
    finally:
        conn.close()
    return 0 if eredmeny is foglalas_repo.Eredmeny.SIKERES else 1


def _lemond(argv: list[str]) -> int:
    if len(argv) < 2:
        print("Használat: lemond <db_utvonal> <foglalasi_kod>")
        return 1
    db_utvonal, foglalasi_kod = argv[0], argv[1]
    conn = migracio.kapcsolat_nyitas(db_utvonal)
    try:
        eredmeny = foglalas_repo.foglalas_lemond(conn, foglalasi_kod)
        print(f"Eredmény: {eredmeny.value}")
    finally:
        conn.close()
    return 0 if eredmeny is foglalas_repo.Eredmeny.SIKERES else 1


def _holdok_takaritas(argv: list[str]) -> int:
    if not argv:
        print("Használat: holdok-takaritas <db_utvonal> [most_iso]")
        return 1
    db_utvonal = argv[0]
    most = argv[1] if len(argv) > 1 else most_iso()
    conn = migracio.kapcsolat_nyitas(db_utvonal)
    try:
        torolt = foglalas_repo.lejart_holdok_takaritasa(conn, most)
        print(f"Törölve: {len(torolt)} lejárt hold.")
    finally:
        conn.close()
    return 0


def _demo_verseny(argv: list[str]) -> int:
    sessziok = int(_opcio(argv, "--sessziok") or 3)
    mag = int(_opcio(argv, "--mag") or 42)
    from mag.api import verseny

    verseny.futtat(sessziok=sessziok, mag=mag)
    return 0


PARANCSOK = {
    "migral": _migral,
    "seed": _seed,
    "slotok": _slotok,
    "keres": _keres,
    "foglal": _foglal,
    "lemond": _lemond,
    "holdok-takaritas": _holdok_takaritas,
    "demo-verseny": _demo_verseny,
}


def _fo() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    if len(sys.argv) < 2 or sys.argv[1] not in PARANCSOK:
        print(__doc__)
        return 1
    return PARANCSOK[sys.argv[1]](sys.argv[2:])


if __name__ == "__main__":
    sys.exit(_fo())

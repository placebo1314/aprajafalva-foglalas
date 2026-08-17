"""Parancssori felület a foglalási maghoz.

Ez a mag mérföldköve: innen minden művelet elvégezhető LLM nélkül
(CLAUDE.md, alapelv: "Az LLM nem foglal, hanem fordít.").

    python -m core.api.cli migral <db_utvonal>
    python -m core.api.cli seed [<db_utvonal>]
    python -m core.api.cli slotok <db_utvonal> <muszak_id>
    python -m core.api.cli keres <db_utvonal> <szervezet_id> [--bolt ID] [--szolgaltatas ID]
    python -m core.api.cli foglal <db_utvonal> <slot_id> <vasarlo_kulcs_hash> \
        <idempotencia_kulcs> <session_id>
    python -m core.api.cli lemond <db_utvonal> <foglalasi_kod>
    python -m core.api.cli holdok-takaritas <db_utvonal> [most_iso]
    python -m core.api.cli demo-verseny [--sessziok 2|3] [--mag SZAM]

A `vasarlo_kulcs_hash` MÁR HMAC-hashelt érték (64 hex karakter) — a nyers
vásárlóazonosítót a core/ soha nem kapja meg (CLAUDE.md, 2. invariáns). A
hashelés a `privacy/` modul feladata lesz; amíg az nincs megírva, a
hívó (assistant/ vagy a te kezed) felelőssége előre kiszámítani.

A `keres` parancs NEM az ajánlatpontozó (ADR-006) — puszta, rendezetlen
listázás, lásd `core/repo/foglalas_repo.py::free_slots_search`.
"""

from __future__ import annotations

import sys

from core.ido import most_iso
from core.repo import foglalas_repo, migracio, muszak_repo
from core.slot import generator
from core.slot.blokk import FixedBlock


def _option(argv: list[str], name: str) -> str | None:
    if name in argv:
        idx = argv.index(name)
        if idx + 1 < len(argv):
            return argv[idx + 1]
    return None


def _migral(argv: list[str]) -> int:
    if not argv:
        print("Használat: migral <db_utvonal>")
        return 1
    conn = migracio.conn_nyitas(argv[0])
    try:
        result = migracio.migral(conn)
        print(f"Lefuttatva: {result}" if result else "Minden migráció naprakész.")
    finally:
        conn.close()
    return 0


def _seed(argv: list[str]) -> int:
    from seed.betolt import ALAP_DB_PATH, betolt

    db_path = argv[0] if argv else str(ALAP_DB_PATH)
    data = betolt(db_path)
    print(f"Betöltve: {db_path} (szervezet: {data['szervezet_id']})")
    return 0


def _slots(argv: list[str]) -> int:
    if len(argv) < 2:
        print("Használat: slotok <db_utvonal> <muszak_id>")
        return 1
    db_path, shift_id = argv[0], argv[1]
    conn = migracio.conn_nyitas(db_path)
    try:
        shift = muszak_repo.shift_load(conn, shift_id)
        if shift is None:
            print(f"Nincs ilyen műszak: {shift_id}")
            return 1
        # Csak szervezet-szintű kivetel_nap-ot néz — a Muszak modell nem
        # tartalmaz bolt_id-t (a generálás nem függ tőle), ezért egy
        # bolt-specifikus kivételnap itt nem szűrődik ki. Ha ez élesben
        # gond, a muszak_repo.muszak_betoltese-t kell bővíteni.
        exception_days = muszak_repo.exception_days_list(conn, org_id=shift.org_id)
        result = generator.generate(shift, FixedBlock(), exception_days=exception_days)
        if result.skipped:
            print(f"Kihagyva (kivetel_nap: {result.skip_oka})")
            return 0
        muszak_repo.blocks_slots_save(
            conn,
            shift_id=shift_id,
            org_id=shift.org_id,
            blocks=result.blocks,
            slots=result.slots,
        )
        print(f"Létrehozva: {len(result.slots)} slot, {len(result.blocks)} blokk.")
    finally:
        conn.close()
    return 0


def _search(argv: list[str]) -> int:
    if len(argv) < 2:
        print("Használat: keres <db_utvonal> <szervezet_id> [--bolt ID] [--szolgaltatas ID]")
        return 1
    db_path, org_id = argv[0], argv[1]
    shop_id = _option(argv, "--bolt")
    service_id = _option(argv, "--szolgaltatas")
    conn = migracio.conn_nyitas(db_path)
    try:
        matches = foglalas_repo.free_slots_search(
            conn,
            org_id=org_id,
            shop_id=shop_id,
            service_id=service_id,
        )
        if not matches:
            print("Nincs szabad időpont.")
            return 0
        for slot_id, start, end in matches:
            print(f"{slot_id}  {start} – {end}")
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
    db_path, slot_id, customer_key, idempotency_key, session_id = argv[:5]
    conn = migracio.conn_nyitas(db_path)
    try:
        result = foglalas_repo.booking_create(
            conn, slot_id, customer_key, idempotency_key, session_id
        )
        print(f"Eredmény: {result.value}")
        if result is foglalas_repo.Result.SUCCESS:
            booking = foglalas_repo.booking_query_idempotency_by(conn, idempotency_key)
            if booking:
                print(f"Foglalási kód: {booking['foglalasi_kod']}")
    finally:
        conn.close()
    return 0 if result is foglalas_repo.Result.SUCCESS else 1


def _lemond(argv: list[str]) -> int:
    if len(argv) < 2:
        print("Használat: lemond <db_utvonal> <foglalasi_kod>")
        return 1
    db_path, booking_code = argv[0], argv[1]
    conn = migracio.conn_nyitas(db_path)
    try:
        result = foglalas_repo.booking_lemond(conn, booking_code)
        print(f"Eredmény: {result.value}")
    finally:
        conn.close()
    return 0 if result is foglalas_repo.Result.SUCCESS else 1


def _holds_cleanup(argv: list[str]) -> int:
    if not argv:
        print("Használat: holdok-takaritas <db_utvonal> [most_iso]")
        return 1
    db_path = argv[0]
    most = argv[1] if len(argv) > 1 else most_iso()
    conn = migracio.conn_nyitas(db_path)
    try:
        deleted = foglalas_repo.lejart_holds_cleanup(conn, most)
        print(f"Törölve: {len(deleted)} lejárt hold.")
    finally:
        conn.close()
    return 0


def _demo_verseny(argv: list[str]) -> int:
    sessions = int(_option(argv, "--sessziok") or 3)
    seed = int(_option(argv, "--mag") or 42)
    from core.api import verseny

    verseny.run(sessions=sessions, seed=seed)
    return 0


COMMANDS = {
    "migral": _migral,
    "seed": _seed,
    "slotok": _slots,
    "keres": _search,
    "foglal": _foglal,
    "lemond": _lemond,
    "holdok-takaritas": _holds_cleanup,
    "demo-verseny": _demo_verseny,
}


def _fo() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    if len(sys.argv) < 2 or sys.argv[1] not in COMMANDS:
        print(__doc__)
        return 1
    return COMMANDS[sys.argv[1]](sys.argv[2:])


if __name__ == "__main__":
    sys.exit(_fo())

"""SQLite írási latencia — M-1 spike. ELDOBHATÓ KÓD.

N egyidejű session szimulálása a MEGLÉVŐ mag/repo/foglalas_repo.py-val
(nem duplikált logika — a spike a valódi repo réteget méri). Ez az
ADR-004 egyik kiváltó feltétele: "p95 írási latencia > 50 ms".

Minden szál a saját slotjára foglal (nem versenyeznek ugyanazért a
slotért — ez a p95 IDŐZÍTÉS mérése, nem a konkurencia-teszto
versenyhelyzeti tesztje, amit már a tesztek/konkurencia/ fed).

Alapból 3 és 10 egyidejű session-t mér — az 50 nem v1 cél (a bolti
forgalom mérete mellett irreális terhelés), csak félrevezető lenne.

Használat:
    python spike/sqlite_iras.py                  # 3 és 10
    python spike/sqlite_iras.py --session 3 10 25 --json eredmeny.json
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import tempfile
import threading
import time
import uuid
from pathlib import Path

GYOKER = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(GYOKER))

from core.modell.shift import Slot  # noqa: E402
from core.repo import foglalas_repo, migracio, muszak_repo, torzsadat_repo  # noqa: E402
from core.slot._idomatek import add_minute  # noqa: E402

_MOST = "2026-08-17T09:00:00Z"


def _uuid() -> str:
    return uuid.uuid4().hex


def _elokeszit(db_utvonal: str, szalszam: int) -> list[str]:
    """Migrál, felvesz törzsadatot, és szalszam db külön slotot — minden
    szál a sajátjára ír, hogy a mérés az írási latenciáról szóljon, ne a
    slot-egyediségi versenyről."""
    conn = migracio.conn_nyitas(db_utvonal)
    try:
        migracio.migral(conn)
        szervezet_id = torzsadat_repo.org_create(conn, name="Spike", timezone="Europe/Budapest")
        bolt_id = torzsadat_repo.shop_create(conn, org_id=szervezet_id, name="Spike bolt")
        pult_id = torzsadat_repo.counter_create(
            conn, org_id=szervezet_id, shop_id=bolt_id, name="Pult"
        )
        alkalmazott_id = torzsadat_repo.employee_create(
            conn, org_id=szervezet_id, shop_id=bolt_id, name="Dolgozo"
        )
        szolgaltatas_id = torzsadat_repo.service_create(
            conn,
            org_id=szervezet_id,
            shop_id=bolt_id,
            name="Spike szolgaltatas",
            alap_duration_minute=10,
        )
        muszak_id = muszak_repo.shift_create(
            conn,
            org_id=szervezet_id,
            shop_id=bolt_id,
            counter_id=pult_id,
            employee_id=alkalmazott_id,
            service_id=szolgaltatas_id,
            start="2027-01-04T08:00:00Z",
            end="2027-01-05T08:00:00Z",  # 24 óra — bőven elég szalszam slotra
            duration_minute=10,
            buffer_after_minute=0,
            min_grid_minute=10,
            bookable_ratio=1.0,
            block_rule={"szunetek": []},
        )
        kezdet = "2027-01-04T08:00:00Z"
        slotok = [
            Slot(add_minute(kezdet, i * 10), add_minute(kezdet, (i + 1) * 10))
            for i in range(szalszam)
        ]
        muszak_repo.blocks_slots_save(
            conn, shift_id=muszak_id, org_id=szervezet_id, blocks=[], slots=slotok
        )
        # A slot-id-ket a meglévő repo-függvényen keresztül kérjük vissza —
        # nem raw SQL-lel (CLAUDE.md 5. invariáns a spike/-ra is vonatkozik).
        talalatok = foglalas_repo.free_slots_search(conn, org_id=szervezet_id)
        slot_id_k = [slot_id for slot_id, _kezdet, _veg in talalatok]
    finally:
        conn.close()
    return slot_id_k


def _feladat(
    db_utvonal: str, slot_id: str, korlat: threading.Barrier, eredmenyek: list, hibak: list, i: int
) -> None:
    conn = migracio.conn_nyitas(db_utvonal)
    try:
        korlat.wait()
        kezdet = time.perf_counter()
        try:
            eredmeny = foglalas_repo.booking_create(
                conn, slot_id, "a" * 64, _uuid(), f"session-{i}"
            )
            telt_ms = (time.perf_counter() - kezdet) * 1000
            eredmenyek.append((telt_ms, eredmeny))
        except Exception as exc:  # noqa: BLE001 - a mérés szempontjából minden kivétel hiba
            hibak.append(exc)
    finally:
        conn.close()


def fut(szalszam: int) -> dict:
    tmp_dir = Path(tempfile.mkdtemp(prefix="spike_sqlite_"))
    db_utvonal = str(tmp_dir / "spike.db")
    print(f"Ideiglenes DB: {db_utvonal}")

    slot_id_k = _elokeszit(db_utvonal, szalszam)
    print(f"{len(slot_id_k)} slot előkészítve.")

    korlat = threading.Barrier(szalszam)
    eredmenyek: list[tuple[float, foglalas_repo.Result]] = []
    hibak: list[Exception] = []
    szalak = [
        threading.Thread(
            target=_feladat, args=(db_utvonal, slot_id_k[i], korlat, eredmenyek, hibak, i)
        )
        for i in range(szalszam)
    ]

    teljes_kezdet = time.perf_counter()
    for szal in szalak:
        szal.start()
    for szal in szalak:
        szal.join(timeout=60)
    teljes_ido = time.perf_counter() - teljes_kezdet

    meg_elo = [s for s in szalak if s.is_alive()]
    if meg_elo:
        print(f"FIGYELEM: {len(meg_elo)} szál nem fejeződött be 60s alatt")

    if hibak:
        print(f"HIBÁK ({len(hibak)}):")
        for hiba in hibak[:5]:
            print(f"  {hiba!r}")

    idok_ms = sorted(t for t, _ in eredmenyek)
    sikeresek = sum(1 for _, e in eredmenyek if e is foglalas_repo.Result.SUCCESS)

    print(
        f"\n{len(eredmenyek)}/{szalszam} írás lefutott, {sikeresek} SIKERES, "
        f"{teljes_ido * 1000:.1f} ms össz."
    )
    if idok_ms:
        p50 = statistics.median(idok_ms)
        p95 = idok_ms[min(int(len(idok_ms) * 0.95), len(idok_ms) - 1)]
        print(f"p50 = {p50:.2f} ms, p95 = {p95:.2f} ms, max = {idok_ms[-1]:.2f} ms")
        allapot = "IGEN — teljesül" if p95 > 50 else "nem teljesül"
        print(f"ADR-004 kiváltó feltétel (p95 > 50 ms): {allapot}")
        return {
            "szalszam": szalszam,
            "n": len(idok_ms),
            "p50_ms": p50,
            "p95_ms": p95,
            "max_ms": idok_ms[-1],
            "hibak": len(hibak),
        }
    return {"szalszam": szalszam, "n": 0, "hibak": len(hibak)}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--session",
        type=int,
        nargs="+",
        default=[3, 10],
        help="Egyidejű session-számok, több is megadható (alap: 3 10)",
    )
    parser.add_argument("--json", type=Path, default=None, help="Eredmény mentése JSON-ba")
    args = parser.parse_args()

    eredmenyek = [fut(n) for n in args.session]

    if args.json:
        args.json.write_text(
            json.dumps({"korok": eredmenyek}, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"\nJSON mentve: {args.json}")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())

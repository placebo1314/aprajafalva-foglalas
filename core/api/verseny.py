"""Verseny-demó a konzolon — több szimulált session ugyanarra a napra.

Ez NEM teszt (a versenyhelyzeti bizonyítás a `tesztek/konkurencia/`
dolga, valódi szálakkal) — ez egy DEMONSTRÁCIÓ, ami látni engedi, mit
csinál a mag valódi `mag/repo/foglalas_repo.py` függvényhívásokon
keresztül, amikor több "vásárló" ugyanazt a legkorábbi időpontot akarja.

Szándékosan EGYETLEN szálon, szkriptelt sorrendben hívja a repo
függvényeket (nem `threading`-gel) — ez felel meg a "determinisztikus
legyen, ugyanaz a futás ugyanazt adja" követelménynek. A versenyvédelem
(a `foglalas`/`hold` táblák parciális UNIQUE indexei) ettől függetlenül
VALÓDI: két egymás utáni `hold_letrehoz()` hívás ugyanarra a slotra
ugyanúgy egy `MEGELOZTEK`-et ad vissza, mint konkurens szálakból hívva —
a DB-szintű védelem nem különbözteti meg a hívó szálszámát.

A `mag=<szám>` a session-sorrendet és a megerősítés-ágakat vezérli: a
"ki nyert" szereposztás és a kontesztált slot változik seedenként, de egy
adott seed mellett a kimenet mindig ugyanaz. A slotok/műszak IDŐPONTJAI
viszont fixek (nem a valódi "most"-tól függenek) — csak a `hold` lejárati
ideje épül a tényleges falióra-időre, mert a `hold_letrehoz()` a mag/repo
rétegben saját maga számítja ki a "most"-ot, ez a demó nem tudja (és nem
is szabad, hogy) megkerülje.

Használat:
    python -m core.api.cli demo-verseny
    python -m core.api.cli demo-verseny --sessziok 2 --mag 7
"""

from __future__ import annotations

import hashlib
import random
import tempfile
from collections.abc import Callable
from pathlib import Path

from core.repo import foglalas_repo, migracio, muszak_repo, torzsadat_repo
from core.slot import generator
from core.slot._idomatek import add_minute
from core.slot.blokk import FixedBlock

_SHIFT_START = "2026-08-18T08:00:00Z"
_SHIFT_END = "2026-08-18T09:00:00Z"
_SCARCITY_THRESHOLD = 3


def _customer_key(name: str) -> str:
    """Demó vásárlóazonosító-HASH — nyers azonosító itt SOSEM létezett,
    ez a demó direktben egy már-hashelt (64 hex karakter) értéket állít
    elő egy olvasható névből, CLAUDE.md 2. invariánsával összhangban."""
    return hashlib.sha256(f"demo-vasarlo:{name}".encode()).hexdigest()


def _prepare(conn) -> dict:
    migracio.migral(conn)
    org_id = torzsadat_repo.org_create(conn, name="Verseny-demó", timezone="UTC")
    shop_id = torzsadat_repo.shop_create(conn, org_id=org_id, name="Ügyifogyi demó")
    counter_id = torzsadat_repo.counter_create(conn, org_id=org_id, shop_id=shop_id, name="Pult 1")
    employee_id = torzsadat_repo.employee_create(
        conn, org_id=org_id, shop_id=shop_id, name="Durranó"
    )
    service_id = torzsadat_repo.service_create(
        conn,
        org_id=org_id,
        shop_id=shop_id,
        name="petárda",
        alap_duration_minute=10,
    )
    shift_id = muszak_repo.shift_create(
        conn,
        org_id=org_id,
        shop_id=shop_id,
        counter_id=counter_id,
        employee_id=employee_id,
        service_id=service_id,
        start=_SHIFT_START,
        end=_SHIFT_END,
        duration_minute=10,
        buffer_after_minute=0,
        min_grid_minute=10,
        bookable_ratio=1.0,
        block_rule={"szunetek": []},
    )
    shift = muszak_repo.shift_load(conn, shift_id)
    result = generator.generate(shift, FixedBlock())
    muszak_repo.blocks_slots_save(
        conn,
        shift_id=shift_id,
        org_id=org_id,
        blocks=result.blocks,
        slots=result.slots,
    )
    return {
        "szervezet_id": org_id,
        "bolt_id": shop_id,
        "szolgaltatas_id": service_id,
        "slot_szam": len(result.slots),
    }


def _search(conn, data: dict, ki: Callable[[str], None]) -> list[tuple[str, str, str]]:
    matches = foglalas_repo.free_slots_search(
        conn, org_id=data["szervezet_id"], shop_id=data["bolt_id"]
    )
    ki(f"    {len(matches)} szabad időpont a kért ablakban.")
    if 0 < len(matches) <= _SCARCITY_THRESHOLD:
        ki(
            f"    ⚠ szűkösségi figyelmeztetés ITT lépne be "
            f"(≤ {_SCARCITY_THRESHOLD} szabad hely maradt, homályosan jelezve a vásárlónak — "
            f"blueprint 7. szakasz)."
        )
    return matches


def _hold_try(
    conn, session: str, slot_id: str, start: str, ki: Callable[[str], None]
) -> foglalas_repo.Result:
    """Csak a hold-próbálkozás — a döntést (`_dontes`) tudatosan külön
    lépésként hívjuk, hogy két session hold-próbálkozása között valódi
    ütközés keletkezhessen (a második session AKKOR próbálkozik, amikor
    az első MÉG tartja a holdot — nem azután, hogy már eldöntötte és
    esetleg felszabadította)."""
    lejar = add_minute(_most_real(), 5)
    result = foglalas_repo.hold_create(conn, slot_id, session, lejar)
    if result is foglalas_repo.Result.SUCCESS:
        ki(f"    {session}: hold megszerezve a {start} időpontra.")
    else:
        ki(f"    {session}: hold {start}-re → {result.value.upper()} (más már ott áll)")
    return result


def _decision(
    conn, session: str, slot_id: str, start: str, yes: bool, ki: Callable[[str], None]
) -> foglalas_repo.Result:
    """A session ELŐZŐLEG megszerzett holdjáról dönt: megerősíti (foglalás
    létrejön) vagy visszalép (a hold felszabadul, a slot újra szabad)."""
    answer = "igen" if yes else "nem"
    ki(f"    {session}: biztosan lefoglaljam? → {answer}")
    if not yes:
        hold_id = foglalas_repo.hold_list(conn, slot_id=slot_id, session_id=session)
        foglalas_repo.hold_release(conn, hold_id)
        ki(f"    {session}: hold felszabadítva — a slot ({start}) újra szabad.")
        return foglalas_repo.Result.PREEMPTED  # a hívó szemszögéből: nem lett foglalás

    customer_key = _customer_key(session)
    booking_result = foglalas_repo.booking_create(
        conn, slot_id, customer_key, f"idem-{session}-{slot_id}", session
    )
    if booking_result is foglalas_repo.Result.SUCCESS:
        found = foglalas_repo.booking_query_idempotency_by(conn, f"idem-{session}-{slot_id}")
        ki(f"    {session}: FOGLALÁS LÉTREJÖTT — kód: {found['foglalasi_kod']}")
    else:
        ki(f"    {session}: foglalás → {booking_result.value.upper()}")
    return booking_result


def _most_real() -> str:
    from core.ido import most_iso

    return most_iso()


def run(
    *,
    sessions: int = 3,
    seed: int = 42,
    db_path: str | None = None,
    ki: Callable[[str], None] = print,
) -> dict:
    """A teljes verseny-demót lefuttatja, lépésenként kiírva `ki`-vel
    (alapból `print`). Visszaadja az összefoglalót is (tesztelhetőség
    végett) — a `sessziok` 2 vagy 3, a `mag` a session-sorrendet és a
    megerősítés-ágakat vezérli determinisztikusan."""
    if sessions not in (2, 3):
        raise ValueError("sessziok csak 2 vagy 3 lehet")

    rng = random.Random(seed)
    own_tmp = db_path is None
    db_path = db_path or tempfile.mktemp(prefix="demo_verseny_", suffix=".db")

    conn = migracio.conn_nyitas(db_path)
    try:
        ki(f"=== Verseny-demó — {sessions} session, mag={seed} ===")
        ki(f"(ideiglenes DB: {db_path})\n")

        data = _prepare(conn)
        ki(f"Műszak előkészítve: {data['slot_szam']} slot, {_SHIFT_START}–{_SHIFT_END}.\n")

        session_names = [f"session-{i + 1}" for i in range(sessions)]
        order = session_names.copy()
        rng.shuffle(order)
        ki(f"Sorrend (mag={seed} szerint): {', '.join(order)}\n")

        # 1. fázis: mindenki keres, MIELŐTT bárki holdolna — mindenki
        # ugyanazt a legkorábbi szabad időpontot akarja (realisztikus
        # verseny: "mindenki a legkorábbi időpontot kéri").
        ki("--- Keresési fázis ---")
        targeted: dict[str, str] = {}
        targeted_start: dict[str, str] = {}
        for session in order:
            ki(f"  {session}: keres...")
            matches = _search(conn, data, ki)
            if not matches:
                ki(f"    {session}: nincs szabad időpont, kimarad.")
                continue
            slot_id, start, _end = matches[0]
            targeted[session] = slot_id
            targeted_start[session] = start
            ki(f"    {session}: a legkorábbit célozza ({start}).")
        ki("")

        # 2. fázis: hold-verseny a kontesztált (legkorábbi) slotra, a
        # sorrend szerint. FONTOS: a második session AKKOR próbál
        # holdolni, amikor az első MÉG tartja a holdot — csak így
        # keletkezik valódi MEGELOZTEK. Csak ezután dönt az első (a
        # nyertes SZÁNDÉKOSAN visszalép, hogy a hold-felszabadítás ága is
        # látszódjon), majd a második — aki megelőztetett — újrapróbál a
        # most felszabadult slotra, és megerősít.
        ki("--- Hold-verseny a legkorábbi időpontra ---")
        first_round = order[:2]
        winner_code = None
        first_slot = targeted.get(first_round[0])
        first_start = targeted_start.get(first_round[0])
        if first_slot:
            hold_1 = _hold_try(conn, first_round[0], first_slot, first_start, ki)
            hold_2 = _hold_try(conn, first_round[1], first_slot, first_start, ki)

            if hold_1 is foglalas_repo.Result.SUCCESS:
                decision_1 = _decision(conn, first_round[0], first_slot, first_start, False, ki)
            else:
                decision_1 = hold_1

            if (
                hold_2 is foglalas_repo.Result.PREEMPTED
                and decision_1 is not foglalas_repo.Result.SUCCESS
            ):
                ki(f"  {first_round[1]}: újrapróbálkozik a most felszabadult időpontra.")
                hold_2 = _hold_try(conn, first_round[1], first_slot, first_start, ki)
                if hold_2 is foglalas_repo.Result.SUCCESS:
                    decision_2 = _decision(conn, first_round[1], first_slot, first_start, True, ki)
                    if decision_2 is foglalas_repo.Result.SUCCESS:
                        winner_code = first_round[1]
            elif hold_2 is foglalas_repo.Result.SUCCESS:
                decision_2 = _decision(conn, first_round[1], first_slot, first_start, True, ki)
                if decision_2 is foglalas_repo.Result.SUCCESS:
                    winner_code = first_round[1]
        ki("")

        # 3. fázis (csak 3 session esetén): a harmadik a saját (nem
        # kontesztált) legkorábbi szabad idejére próbálkozik, valódi
        # (mag-vezérelt) igen/nem válasszal.
        if sessions == 3:
            third = order[2]
            ki(f"--- {third}: önálló próbálkozás ---")
            matches = _search(conn, data, ki)
            if matches:
                slot_id, start, _end = matches[0]
                hold_3 = _hold_try(conn, third, slot_id, start, ki)
                if hold_3 is foglalas_repo.Result.SUCCESS:
                    yes = rng.choice([True, False])
                    decision_3 = _decision(conn, third, slot_id, start, yes, ki)
                    if decision_3 is foglalas_repo.Result.SUCCESS:
                        winner_code = third if winner_code is None else f"{winner_code}, {third}"
            else:
                ki(f"    {third}: nincs több szabad időpont.")
            ki("")

        ki("--- Végeredmény ---")
        final = foglalas_repo.free_slots_search(
            conn, org_id=data["szervezet_id"], shop_id=data["bolt_id"]
        )
        ki(f"Szabad időpont a végén: {len(final)}/{data['slot_szam']}.")
        ki(f"Nyert: {winner_code or '(senki — mindenki visszalépett vagy megelőzték)'}")

        return {
            "mag": seed,
            "sessziok": sessions,
            "sorrend": order,
            "nyertes": winner_code,
            "szabad_a_vegen": len(final),
            "slot_szam_osszesen": data["slot_szam"],
        }
    finally:
        conn.close()
        if own_tmp:
            Path(db_path).unlink(missing_ok=True)
            for kiterjesztes in ("-wal", "-shm"):
                Path(db_path + kiterjesztes).unlink(missing_ok=True)

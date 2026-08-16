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
    python -m mag.api.cli demo-verseny
    python -m mag.api.cli demo-verseny --sessziok 2 --mag 7
"""

from __future__ import annotations

import hashlib
import random
import tempfile
from collections.abc import Callable
from pathlib import Path

from mag.repo import foglalas_repo, migracio, muszak_repo, torzsadat_repo
from mag.slot import generator
from mag.slot._idomatek import hozzaad_perc
from mag.slot.blokk import FixBlokk

_MUSZAK_KEZDET = "2026-08-18T08:00:00Z"
_MUSZAK_VEG = "2026-08-18T09:00:00Z"
_SZUKOSSEG_KUSZOB = 3


def _vasarlo_kulcs(nev: str) -> str:
    """Demó vásárlóazonosító-HASH — nyers azonosító itt SOSEM létezett,
    ez a demó direktben egy már-hashelt (64 hex karakter) értéket állít
    elő egy olvasható névből, CLAUDE.md 2. invariánsával összhangban."""
    return hashlib.sha256(f"demo-vasarlo:{nev}".encode()).hexdigest()


def _elokeszit(conn) -> dict:
    migracio.migral(conn)
    szervezet_id = torzsadat_repo.szervezet_letrehoz(conn, nev="Verseny-demó", idozona="UTC")
    bolt_id = torzsadat_repo.bolt_letrehoz(conn, szervezet_id=szervezet_id, nev="Ügyifogyi demó")
    pult_id = torzsadat_repo.pult_letrehoz(
        conn, szervezet_id=szervezet_id, bolt_id=bolt_id, nev="Pult 1"
    )
    alkalmazott_id = torzsadat_repo.alkalmazott_letrehoz(
        conn, szervezet_id=szervezet_id, bolt_id=bolt_id, nev="Durranó"
    )
    szolgaltatas_id = torzsadat_repo.szolgaltatas_letrehoz(
        conn,
        szervezet_id=szervezet_id,
        bolt_id=bolt_id,
        nev="petárda",
        alap_idotartam_perc=10,
    )
    muszak_id = muszak_repo.muszak_letrehoz(
        conn,
        szervezet_id=szervezet_id,
        bolt_id=bolt_id,
        pult_id=pult_id,
        alkalmazott_id=alkalmazott_id,
        szolgaltatas_id=szolgaltatas_id,
        kezdet=_MUSZAK_KEZDET,
        veg=_MUSZAK_VEG,
        idotartam_perc=10,
        puffer_utana_perc=0,
        min_racs_perc=10,
        foglalhato_arany=1.0,
        blokk_szabaly={"szunetek": []},
    )
    muszak = muszak_repo.muszak_betoltese(conn, muszak_id)
    eredmeny = generator.general(muszak, FixBlokk())
    muszak_repo.blokkok_slotok_mentese(
        conn,
        muszak_id=muszak_id,
        szervezet_id=szervezet_id,
        blokkok=eredmeny.blokkok,
        slotok=eredmeny.slotok,
    )
    return {
        "szervezet_id": szervezet_id,
        "bolt_id": bolt_id,
        "szolgaltatas_id": szolgaltatas_id,
        "slot_szam": len(eredmeny.slotok),
    }


def _keres(conn, adat: dict, ki: Callable[[str], None]) -> list[tuple[str, str, str]]:
    talalatok = foglalas_repo.szabad_slotok_keresese(
        conn, szervezet_id=adat["szervezet_id"], bolt_id=adat["bolt_id"]
    )
    ki(f"    {len(talalatok)} szabad időpont a kért ablakban.")
    if 0 < len(talalatok) <= _SZUKOSSEG_KUSZOB:
        ki(
            f"    ⚠ szűkösségi figyelmeztetés ITT lépne be "
            f"(≤ {_SZUKOSSEG_KUSZOB} szabad hely maradt, homályosan jelezve a vásárlónak — "
            f"blueprint 7. szakasz)."
        )
    return talalatok


def _hold_probal(
    conn, session: str, slot_id: str, kezdet: str, ki: Callable[[str], None]
) -> foglalas_repo.Eredmeny:
    """Csak a hold-próbálkozás — a döntést (`_dontes`) tudatosan külön
    lépésként hívjuk, hogy két session hold-próbálkozása között valódi
    ütközés keletkezhessen (a második session AKKOR próbálkozik, amikor
    az első MÉG tartja a holdot — nem azután, hogy már eldöntötte és
    esetleg felszabadította)."""
    lejar = hozzaad_perc(_most_valodi(), 5)
    eredmeny = foglalas_repo.hold_letrehoz(conn, slot_id, session, lejar)
    if eredmeny is foglalas_repo.Eredmeny.SIKERES:
        ki(f"    {session}: hold megszerezve a {kezdet} időpontra.")
    else:
        ki(f"    {session}: hold {kezdet}-re → {eredmeny.value.upper()} (más már ott áll)")
    return eredmeny


def _dontes(
    conn, session: str, slot_id: str, kezdet: str, igen: bool, ki: Callable[[str], None]
) -> foglalas_repo.Eredmeny:
    """A session ELŐZŐLEG megszerzett holdjáról dönt: megerősíti (foglalás
    létrejön) vagy visszalép (a hold felszabadul, a slot újra szabad)."""
    valasz = "igen" if igen else "nem"
    ki(f"    {session}: biztosan lefoglaljam? → {valasz}")
    if not igen:
        hold_id = foglalas_repo.hold_lekerdezese(conn, slot_id=slot_id, session_id=session)
        foglalas_repo.hold_felszabadit(conn, hold_id)
        ki(f"    {session}: hold felszabadítva — a slot ({kezdet}) újra szabad.")
        return foglalas_repo.Eredmeny.MEGELOZTEK  # a hívó szemszögéből: nem lett foglalás

    vasarlo_kulcs = _vasarlo_kulcs(session)
    foglalas_eredmeny = foglalas_repo.foglalas_letrehoz(
        conn, slot_id, vasarlo_kulcs, f"idem-{session}-{slot_id}", session
    )
    if foglalas_eredmeny is foglalas_repo.Eredmeny.SIKERES:
        talalt = foglalas_repo.foglalas_lekerdezes_idempotencia_szerint(
            conn, f"idem-{session}-{slot_id}"
        )
        ki(f"    {session}: FOGLALÁS LÉTREJÖTT — kód: {talalt['foglalasi_kod']}")
    else:
        ki(f"    {session}: foglalás → {foglalas_eredmeny.value.upper()}")
    return foglalas_eredmeny


def _most_valodi() -> str:
    from mag.ido import most_iso

    return most_iso()


def futtat(
    *,
    sessziok: int = 3,
    mag: int = 42,
    db_utvonal: str | None = None,
    ki: Callable[[str], None] = print,
) -> dict:
    """A teljes verseny-demót lefuttatja, lépésenként kiírva `ki`-vel
    (alapból `print`). Visszaadja az összefoglalót is (tesztelhetőség
    végett) — a `sessziok` 2 vagy 3, a `mag` a session-sorrendet és a
    megerősítés-ágakat vezérli determinisztikusan."""
    if sessziok not in (2, 3):
        raise ValueError("sessziok csak 2 vagy 3 lehet")

    rng = random.Random(mag)
    sajat_tmp = db_utvonal is None
    db_utvonal = db_utvonal or tempfile.mktemp(prefix="demo_verseny_", suffix=".db")

    conn = migracio.kapcsolat_nyitas(db_utvonal)
    try:
        ki(f"=== Verseny-demó — {sessziok} session, mag={mag} ===")
        ki(f"(ideiglenes DB: {db_utvonal})\n")

        adat = _elokeszit(conn)
        ki(f"Műszak előkészítve: {adat['slot_szam']} slot, {_MUSZAK_KEZDET}–{_MUSZAK_VEG}.\n")

        sessionok = [f"session-{i + 1}" for i in range(sessziok)]
        sorrend = sessionok.copy()
        rng.shuffle(sorrend)
        ki(f"Sorrend (mag={mag} szerint): {', '.join(sorrend)}\n")

        # 1. fázis: mindenki keres, MIELŐTT bárki holdolna — mindenki
        # ugyanazt a legkorábbi szabad időpontot akarja (realisztikus
        # verseny: "mindenki a legkorábbi időpontot kéri").
        ki("--- Keresési fázis ---")
        celzott: dict[str, str] = {}
        celzott_kezdet: dict[str, str] = {}
        for session in sorrend:
            ki(f"  {session}: keres...")
            talalatok = _keres(conn, adat, ki)
            if not talalatok:
                ki(f"    {session}: nincs szabad időpont, kimarad.")
                continue
            slot_id, kezdet, _veg = talalatok[0]
            celzott[session] = slot_id
            celzott_kezdet[session] = kezdet
            ki(f"    {session}: a legkorábbit célozza ({kezdet}).")
        ki("")

        # 2. fázis: hold-verseny a kontesztált (legkorábbi) slotra, a
        # sorrend szerint. FONTOS: a második session AKKOR próbál
        # holdolni, amikor az első MÉG tartja a holdot — csak így
        # keletkezik valódi MEGELOZTEK. Csak ezután dönt az első (a
        # nyertes SZÁNDÉKOSAN visszalép, hogy a hold-felszabadítás ága is
        # látszódjon), majd a második — aki megelőztetett — újrapróbál a
        # most felszabadult slotra, és megerősít.
        ki("--- Hold-verseny a legkorábbi időpontra ---")
        elso_kor = sorrend[:2]
        nyertes_kod = None
        elso_slot = celzott.get(elso_kor[0])
        elso_kezdet = celzott_kezdet.get(elso_kor[0])
        if elso_slot:
            hold_1 = _hold_probal(conn, elso_kor[0], elso_slot, elso_kezdet, ki)
            hold_2 = _hold_probal(conn, elso_kor[1], elso_slot, elso_kezdet, ki)

            if hold_1 is foglalas_repo.Eredmeny.SIKERES:
                dontes_1 = _dontes(conn, elso_kor[0], elso_slot, elso_kezdet, False, ki)
            else:
                dontes_1 = hold_1

            if (
                hold_2 is foglalas_repo.Eredmeny.MEGELOZTEK
                and dontes_1 is not foglalas_repo.Eredmeny.SIKERES
            ):
                ki(f"  {elso_kor[1]}: újrapróbálkozik a most felszabadult időpontra.")
                hold_2 = _hold_probal(conn, elso_kor[1], elso_slot, elso_kezdet, ki)
                if hold_2 is foglalas_repo.Eredmeny.SIKERES:
                    dontes_2 = _dontes(conn, elso_kor[1], elso_slot, elso_kezdet, True, ki)
                    if dontes_2 is foglalas_repo.Eredmeny.SIKERES:
                        nyertes_kod = elso_kor[1]
            elif hold_2 is foglalas_repo.Eredmeny.SIKERES:
                dontes_2 = _dontes(conn, elso_kor[1], elso_slot, elso_kezdet, True, ki)
                if dontes_2 is foglalas_repo.Eredmeny.SIKERES:
                    nyertes_kod = elso_kor[1]
        ki("")

        # 3. fázis (csak 3 session esetén): a harmadik a saját (nem
        # kontesztált) legkorábbi szabad idejére próbálkozik, valódi
        # (mag-vezérelt) igen/nem válasszal.
        if sessziok == 3:
            harmadik = sorrend[2]
            ki(f"--- {harmadik}: önálló próbálkozás ---")
            talalatok = _keres(conn, adat, ki)
            if talalatok:
                slot_id, kezdet, _veg = talalatok[0]
                hold_3 = _hold_probal(conn, harmadik, slot_id, kezdet, ki)
                if hold_3 is foglalas_repo.Eredmeny.SIKERES:
                    igen = rng.choice([True, False])
                    dontes_3 = _dontes(conn, harmadik, slot_id, kezdet, igen, ki)
                    if dontes_3 is foglalas_repo.Eredmeny.SIKERES:
                        nyertes_kod = (
                            harmadik if nyertes_kod is None else f"{nyertes_kod}, {harmadik}"
                        )
            else:
                ki(f"    {harmadik}: nincs több szabad időpont.")
            ki("")

        ki("--- Végeredmény ---")
        vegso = foglalas_repo.szabad_slotok_keresese(
            conn, szervezet_id=adat["szervezet_id"], bolt_id=adat["bolt_id"]
        )
        ki(f"Szabad időpont a végén: {len(vegso)}/{adat['slot_szam']}.")
        ki(f"Nyert: {nyertes_kod or '(senki — mindenki visszalépett vagy megelőzték)'}")

        return {
            "mag": mag,
            "sessziok": sessziok,
            "sorrend": sorrend,
            "nyertes": nyertes_kod,
            "szabad_a_vegen": len(vegso),
            "slot_szam_osszesen": adat["slot_szam"],
        }
    finally:
        conn.close()
        if sajat_tmp:
            Path(db_utvonal).unlink(missing_ok=True)
            for kiterjesztes in ("-wal", "-shm"):
                Path(db_utvonal + kiterjesztes).unlink(missing_ok=True)

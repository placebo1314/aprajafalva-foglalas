"""Versenyhelyzeti (konkurencia-) tesztek a `mag/repo/foglalas_repo.py` rétegre.

Ezek NEM szekvenciális szimulációk: minden teszt valódi OS-szálakat indít,
mindegyiket saját SQLite-kapcsolattal (a `migracio.kapcsolat_nyitas()`
mindig ugyanarra a fájlra), és egy `threading.Barrier`-rel arra kényszeríti
őket, hogy a repo-függvényt ténylegesen egyszerre hívják meg — nem
`time.sleep`-pel próbálunk szinkronizálni, mert az villogó tesztet ad.

A cél a CLAUDE.md 1. sérthetetlen invariánsának bizonyítása: "Egy slotra
pontosan egy aktív foglalás lehet." A védelem — ADR-003 szerint — kizárólag
a `foglalas` tábla `ix_foglalas_slot_aktiv` parciális UNIQUE indexe és a
`hold` tábla `ix_hold_slot` UNIQUE indexe; nincs alkalmazásszintű zár vagy
számláló. Ezek a tesztek ezt közvetlenül igazolják, nem csak levezetik.

Motor-hordozhatóság (db-hordozhatosag skill, ADR-004): ezeknek a
teszteknek SQLite-on ÉS Postgresen is futniuk kellene (`python feladat.py
teszt-mindketto`). A jelen állapotban a `mag/repo/migracio.py` — a saját
docstringje szerint — "kizárólag SQLite-ot ismer", és a repóban nincs
Postgres-kapcsolati réteg, driver-függőség (`psycopg`) vagy `ADATTAR`
környezeti változót ténylegesen kiolvasó kód (a `feladat.py
teszt-mindketto` beállítja, de semmi nem olvassa). Ez azt jelenti, hogy
ma `ADATTAR=postgres` mellett is a SQLite-ág fut le — vagyis a "mindkét
motoron" elvárás jelenleg NEM teljesíthető ezen a rétegen additív
teszteléssel, ez a repo-réteg hiánya, nem a teszteké. Lásd a modul végén
és a jelentésben is.
"""

from __future__ import annotations

import threading
import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from core.repo import foglalas_repo, migracio
from core.repo.foglalas_repo import Result

_MOST = "2026-08-15T10:00:00Z"

# A versenyhelyzeti tesztek szálszáma. A feladat 20-50 közötti tartományt
# javasol; 30-at használunk — elég nagy ahhoz, hogy a busy_timeout-ot és a
# WAL-viselkedést ténylegesen próbára tegye, elég kicsi ahhoz, hogy a teszt
# CI-n is másodperceken belül lefusson.
_THREAD_COUNT = 30


def _uuid() -> str:
    return uuid.uuid4().hex


def _jovoben(minute: int = 5) -> str:
    """Valódi 'most'-hoz képest a jövőben lévő ISO-8601 időpont — a hold
    `lejar > letrejott` CHECK-je a tényleges rendszerórát (most_iso())
    használja, nem a fix _MOST teszt-konstanst."""
    return (datetime.now(UTC) + timedelta(minutes=minute)).strftime("%Y-%m-%dT%H:%M:%SZ")


# --- törzsadat --------------------------------------------------------------
#
# Ugyanaz a minta, mint a tesztek/egyseg/test_foglalas_repo.py-ban — itt
# szándékosan nem importáljuk onnan (egységteszt-fájlból konkurencia-tesztbe
# importálni rossz csatolást hozna létre), hanem egy saját, minimális
# builder-t tartunk fenn ezen a rétegen.


def _master_data_insert(conn) -> dict[str, str]:
    org_id = _uuid()
    conn.execute(
        "INSERT INTO szervezet (id, nev, idozona, letrehozva) VALUES (?, ?, ?, ?)",
        (org_id, "Aprajafalva", "Europe/Budapest", _MOST),
    )
    shop_id = _uuid()
    conn.execute(
        "INSERT INTO bolt (id, szervezet_id, nev, letrehozva) VALUES (?, ?, ?, ?)",
        (shop_id, org_id, "Törpilla boltja", _MOST),
    )
    counter_id = _uuid()
    conn.execute(
        "INSERT INTO pult (id, szervezet_id, bolt_id, nev, letrehozva) VALUES (?, ?, ?, ?, ?)",
        (counter_id, org_id, shop_id, "Pult 1", _MOST),
    )
    employee_id = _uuid()
    conn.execute(
        "INSERT INTO alkalmazott (id, szervezet_id, bolt_id, nev, letrehozva) "
        "VALUES (?, ?, ?, ?, ?)",
        (employee_id, org_id, shop_id, "Törpilla", _MOST),
    )
    service_id = _uuid()
    conn.execute(
        "INSERT INTO szolgaltatas "
        "(id, szervezet_id, bolt_id, nev, alap_idotartam_perc, letrehozva) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (service_id, org_id, shop_id, "kis petárda", 30, _MOST),
    )
    return {
        "szervezet_id": org_id,
        "bolt_id": shop_id,
        "pult_id": counter_id,
        "alkalmazott_id": employee_id,
        "szolgaltatas_id": service_id,
    }


def _shift_insert(conn, master: dict[str, str]) -> str:
    shift_id = _uuid()
    conn.execute(
        "INSERT INTO muszak "
        "(id, szervezet_id, bolt_id, pult_id, alkalmazott_id, szolgaltatas_id, "
        "kezdet, veg, idotartam_perc, puffer_utana_perc, min_racs_perc, "
        "foglalhato_arany, blokk_szabaly, allapot, letrehozva) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            shift_id,
            master["szervezet_id"],
            master["bolt_id"],
            master["pult_id"],
            master["alkalmazott_id"],
            master["szolgaltatas_id"],
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
    return shift_id


def _slot_insert(
    conn,
    master: dict[str, str],
    shift_id: str,
    start: str = "2026-08-18T08:00:00Z",
    end: str = "2026-08-18T08:30:00Z",
) -> str:
    slot_id = _uuid()
    conn.execute(
        "INSERT INTO slot (id, szervezet_id, muszak_id, kezdet, veg, letrehozva) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (slot_id, master["szervezet_id"], shift_id, start, end, _MOST),
    )
    return slot_id


@pytest.fixture
def db_path(tmp_path) -> str:
    """Fájlalapú SQLite adatbázis — NEM memóriában, mert a WAL/busy_timeout
    viselkedés csak fájlalapú adatbázison releváns (több valódi kapcsolat
    ugyanarra a fájlra, ahogy az éles rendszerben is történne)."""
    return str(tmp_path / "verseny.db")


@pytest.fixture
def one_slot(db_path) -> str:
    """Migrál, és beszúr egy törzsadatot + egy műszakot + egy slotot.
    A visszaadott slot_id-re épül minden verseny-teszt. A beszúráshoz
    használt kapcsolatot azonnal bezárjuk — a versenyhelyzet-tesztek a
    saját, önálló kapcsolataikat nyitják meg."""
    conn = migracio.conn_nyitas(db_path)
    try:
        migracio.migral(conn)
        master = _master_data_insert(conn)
        shift_id = _shift_insert(conn, master)
        slot_id = _slot_insert(conn, master, shift_id)
        return slot_id
    finally:
        conn.close()


# --- valódi szálas versenyfuttató -------------------------------------------


def _egyszerre_inditva(
    tasks: list[Callable[[], object]],
) -> tuple[list[object], list[BaseException]]:
    """`len(feladatok)` szálat indít, egy `threading.Barrier`-rel pontosan
    egyszerre engedve el őket a tényleges híváshoz — ez a determinisztikus
    verseny-előidézés, nem `time.sleep`.

    Minden feladat kivétele elkapva kerül vissza (nem propagálódik azonnal),
    hogy a hívó explicit ellenőrizhesse: a repo-rétegnek a versenyhelyzet
    egyetlen ágán sem szabadna kivételt dobnia."""
    n = len(tasks)
    barrier = threading.Barrier(n)
    results: list[object] = [None] * n
    errors: list[BaseException] = []
    error_lock = threading.Lock()

    def run(i: int, task: Callable[[], object]) -> None:
        barrier.wait()
        try:
            results[i] = task()
        except BaseException as exc:  # noqa: BLE001 - a teszt maga dönti el, mi számít hibának
            with error_lock:
                errors.append(exc)

    threads = [threading.Thread(target=run, args=(i, f)) for i, f in enumerate(tasks)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
    elo = [thread for thread in threads if thread.is_alive()]
    if elo:
        raise RuntimeError(f"{len(elo)} szál nem fejeződött be 30 másodpercen belül")
    return results, errors


# --- 1. Párhuzamos foglalás ugyanarra a slotra ------------------------------


def test_parhuzamos_booking_pontosan_one_success(db_path, one_slot):
    """N szál egyszerre foglalja ugyanazt a slotot, különböző
    idempotencia_kulccsal. Pontosan egynek szabad SIKERES-t kapnia, a
    többinek MEGELOZTEK-et — kivétel egyiknek sem, és a végén az
    adatbázisban pontosan egy aktív foglalás legyen erre a slotra.

    Minden szál a SAJÁT kapcsolatát nyitja meg — a sqlite3 modul egy
    kapcsolatot csak abban a szálban engedélyez, amelyikben megnyílt
    (`check_same_thread`), ezért a kapcsolatnyitás nem történhet a fő
    szálon a worker-szálak indítása előtt."""

    def _task(i: int) -> Result:
        conn = migracio.conn_nyitas(db_path)
        try:
            return foglalas_repo.booking_create(conn, one_slot, "a" * 64, _uuid(), f"session-{i}")
        finally:
            conn.close()

    tasks = [(lambda i=i: _task(i)) for i in range(_THREAD_COUNT)]
    results, errors = _egyszerre_inditva(tasks)

    assert errors == [], f"a repo réteg kivételt dobott versenyhelyzetben: {errors!r}"
    assert len(results) == _THREAD_COUNT
    assert all(e in (Result.SUCCESS, Result.PREEMPTED) for e in results)

    successes = [e for e in results if e is Result.SUCCESS]
    preceded = [e for e in results if e is Result.PREEMPTED]
    assert len(successes) == 1, "pontosan egy szálnak kell nyernie — ez a dupla foglalás invariáns"
    assert len(preceded) == _THREAD_COUNT - 1

    checker = migracio.conn_nyitas(db_path)
    try:
        active_count = checker.execute(
            "SELECT COUNT(*) FROM foglalas WHERE slot_id = ? AND allapot <> 'lemondva'",
            (one_slot,),
        ).fetchone()[0]
        assert active_count == 1, "dupla foglalás történt — sérült a CLAUDE.md 1. invariánsa"

        all_count = checker.execute(
            "SELECT COUNT(*) FROM foglalas WHERE slot_id = ?", (one_slot,)
        ).fetchone()[0]
        assert all_count == 1, "nem várt extra foglalás-sor keletkezett a slotra"
    finally:
        checker.close()


# --- 2. Hold-verseny --------------------------------------------------------


def test_parhuzamos_hold_pontosan_one_success(db_path, one_slot):
    """N szál egyszerre próbál holdot tenni ugyanarra a slotra, különböző
    session_id-vel. Pontosan egynek SIKERES-t kell kapnia, a végén pontosan
    egy hold sor legyen a slotra."""

    def _task(i: int) -> Result:
        conn = migracio.conn_nyitas(db_path)
        try:
            return foglalas_repo.hold_create(conn, one_slot, f"session-{i}", _jovoben())
        finally:
            conn.close()

    tasks = [(lambda i=i: _task(i)) for i in range(_THREAD_COUNT)]
    results, errors = _egyszerre_inditva(tasks)

    assert errors == [], f"a repo réteg kivételt dobott versenyhelyzetben: {errors!r}"
    assert all(e in (Result.SUCCESS, Result.PREEMPTED) for e in results)

    successes = [e for e in results if e is Result.SUCCESS]
    preceded = [e for e in results if e is Result.PREEMPTED]
    assert len(successes) == 1, "pontosan egy szálnak kell holdot nyernie egy slotra"
    assert len(preceded) == _THREAD_COUNT - 1

    checker = migracio.conn_nyitas(db_path)
    try:
        hold_count = checker.execute(
            "SELECT COUNT(*) FROM hold WHERE slot_id = ?", (one_slot,)
        ).fetchone()[0]
        assert hold_count == 1, "duplán holdolt slot — sérült a hold egyediségi garanciája"
    finally:
        checker.close()


def test_parhuzamos_hold_lejart_hold_after_pontosan_one_success(db_path, one_slot):
    """Ha a slotra már ül egy LEJÁRT hold, két szál egyszerre próbál új
    holdot tenni rá — a hold_letrehoz a beszúrás előtt törli a lejárt
    holdot, ezért pontosan egy szálnak kell nyernie, nem egyiknek sem
    szabad MEGELOZTEK-et kapnia a régi (lejárt) sor miatt."""
    preparer = migracio.conn_nyitas(db_path)
    try:
        (org_id,) = preparer.execute(
            "SELECT szervezet_id FROM slot WHERE id = ?", (one_slot,)
        ).fetchone()
        preparer.execute(
            "INSERT INTO hold (id, szervezet_id, slot_id, session_id, letrejott, lejar) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                _uuid(),
                org_id,
                one_slot,
                "session-regi",
                "2020-01-01T00:00:00Z",
                "2020-01-01T00:00:01Z",
            ),
        )
    finally:
        preparer.close()

    def _task(i: int) -> Result:
        conn = migracio.conn_nyitas(db_path)
        try:
            return foglalas_repo.hold_create(conn, one_slot, f"session-uj-{i}", _jovoben())
        finally:
            conn.close()

    tasks = [(lambda i=i: _task(i)) for i in range(2)]
    results, errors = _egyszerre_inditva(tasks)

    assert errors == [], f"a repo réteg kivételt dobott versenyhelyzetben: {errors!r}"
    successes = [e for e in results if e is Result.SUCCESS]
    preceded = [e for e in results if e is Result.PREEMPTED]
    assert len(successes) == 1, f"pontosan egy szálnak kell nyernie, kapott: {results!r}"
    assert len(preceded) == 1

    checker = migracio.conn_nyitas(db_path)
    try:
        rows = checker.execute(
            "SELECT session_id FROM hold WHERE slot_id = ?", (one_slot,)
        ).fetchall()
        assert len(rows) == 1, "a lejárt hold és/vagy a vesztes szál sora bent maradt"
        assert rows[0][0] != "session-regi", "a lejárt hold sora nem törlődött"
    finally:
        checker.close()


# --- 3. Idempotencia-ismétlés, párhuzamosan ---------------------------------


def test_parhuzamos_idempotent_repetition_each_success(db_path, one_slot):
    """Ugyanaz az idempotencia_kulcs N szálból, párhuzamosan, ugyanarra a
    slotra: mindegyiknek SIKERES-t kell adnia (soha nem MEGELOZTEK, soha
    nem kivétel), és a végén pontosan egy foglalás-sor legyen."""
    common_key = _uuid()

    def _task(i: int) -> Result:
        conn = migracio.conn_nyitas(db_path)
        try:
            return foglalas_repo.booking_create(
                conn, one_slot, "a" * 64, common_key, f"session-{i}"
            )
        finally:
            conn.close()

    tasks = [(lambda i=i: _task(i)) for i in range(_THREAD_COUNT)]
    results, errors = _egyszerre_inditva(tasks)

    assert errors == [], f"a repo réteg kivételt dobott versenyhelyzetben: {errors!r}"
    assert results == [Result.SUCCESS] * _THREAD_COUNT, (
        "az idempotens ismétlésnek MINDIG SIKERES-t kell adnia, sosem MEGELOZTEK-et — "
        f"kapott eredmények: {results!r}"
    )

    checker = migracio.conn_nyitas(db_path)
    try:
        all_count = checker.execute(
            "SELECT COUNT(*) FROM foglalas WHERE slot_id = ?", (one_slot,)
        ).fetchone()[0]
        assert all_count == 1, "az idempotens ismétlés duplázott — elveszett/duplázott foglalás"

        key_count = checker.execute(
            "SELECT COUNT(DISTINCT idempotencia_kulcs) FROM foglalas WHERE slot_id = ?",
            (one_slot,),
        ).fetchone()[0]
        assert key_count == 1
    finally:
        checker.close()


# --- motor-hordozhatóság dokumentálása ---------------------------------------


def test_migration_ma_only_sqlite_ot_tamogat_dokumentalt_hiany():
    """Ez a teszt NEM funkcionális elvárást bizonyít, hanem egy jelenlegi
    hiányt dokumentál, hogy ne merüljön feledésbe: a `db-hordozhatosag`
    skill és a CLAUDE.md szerint minden tesztnek SQLite-on ÉS Postgresen is
    futnia kellene (`python feladat.py teszt-mindketto`), de a
    `mag/repo/migracio.py` — a saját docstringje szerint — ma kizárólag
    SQLite-ot ismer, és a repóban nincs Postgres-kapcsolati kód vagy driver
    (`psycopg`) függőség. Ha ez a teszt egyszer pirosra vált (mert valaki
    hozzáadja a Postgres-támogatást), az jó hír — akkor ezt a tesztet és ezt
    a megjegyzést törölni kell, és a fenti verseny-tesztek `db_utvonal`
    fixture-jét ki kell egészíteni egy Postgres-ághoz kötött kapcsolattal.
    """
    source = Path(migracio.__file__).read_text(encoding="utf-8")
    assert "kizárólag SQLite-ot ismer" in source, (
        "a migracio.py leírása megváltozott — ha Postgres-támogatás került bele, "
        "a verseny-tesztek db_utvonal/kapcsolat fixture-jét ki kell egészíteni "
        "egy tényleges Postgres-ágra, hogy a 'teszt-mindketto' valóban két "
        "motort fedjen le, ne csak kétszer ugyanazt a SQLite-ágat."
    )

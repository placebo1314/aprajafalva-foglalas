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

from mag.repo import foglalas_repo, migracio
from mag.repo.foglalas_repo import Eredmeny

_MOST = "2026-08-15T10:00:00Z"

# A versenyhelyzeti tesztek szálszáma. A feladat 20-50 közötti tartományt
# javasol; 30-at használunk — elég nagy ahhoz, hogy a busy_timeout-ot és a
# WAL-viselkedést ténylegesen próbára tegye, elég kicsi ahhoz, hogy a teszt
# CI-n is másodperceken belül lefusson.
_SZALSZAM = 30


def _uuid() -> str:
    return uuid.uuid4().hex


def _jovoben(perc: int = 5) -> str:
    """Valódi 'most'-hoz képest a jövőben lévő ISO-8601 időpont — a hold
    `lejar > letrejott` CHECK-je a tényleges rendszerórát (most_iso())
    használja, nem a fix _MOST teszt-konstanst."""
    return (datetime.now(UTC) + timedelta(minutes=perc)).strftime("%Y-%m-%dT%H:%M:%SZ")


# --- törzsadat --------------------------------------------------------------
#
# Ugyanaz a minta, mint a tesztek/egyseg/test_foglalas_repo.py-ban — itt
# szándékosan nem importáljuk onnan (egységteszt-fájlból konkurencia-tesztbe
# importálni rossz csatolást hozna létre), hanem egy saját, minimális
# builder-t tartunk fenn ezen a rétegen.


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
def db_utvonal(tmp_path) -> str:
    """Fájlalapú SQLite adatbázis — NEM memóriában, mert a WAL/busy_timeout
    viselkedés csak fájlalapú adatbázison releváns (több valódi kapcsolat
    ugyanarra a fájlra, ahogy az éles rendszerben is történne)."""
    return str(tmp_path / "verseny.db")


@pytest.fixture
def egy_slot(db_utvonal) -> str:
    """Migrál, és beszúr egy törzsadatot + egy műszakot + egy slotot.
    A visszaadott slot_id-re épül minden verseny-teszt. A beszúráshoz
    használt kapcsolatot azonnal bezárjuk — a versenyhelyzet-tesztek a
    saját, önálló kapcsolataikat nyitják meg."""
    conn = migracio.kapcsolat_nyitas(db_utvonal)
    try:
        migracio.migral(conn)
        torzs = _torzsadat_beszur(conn)
        muszak_id = _muszak_beszur(conn, torzs)
        slot_id = _slot_beszur(conn, torzs, muszak_id)
        return slot_id
    finally:
        conn.close()


# --- valódi szálas versenyfuttató -------------------------------------------


def _egyszerre_inditva(
    feladatok: list[Callable[[], object]],
) -> tuple[list[object], list[BaseException]]:
    """`len(feladatok)` szálat indít, egy `threading.Barrier`-rel pontosan
    egyszerre engedve el őket a tényleges híváshoz — ez a determinisztikus
    verseny-előidézés, nem `time.sleep`.

    Minden feladat kivétele elkapva kerül vissza (nem propagálódik azonnal),
    hogy a hívó explicit ellenőrizhesse: a repo-rétegnek a versenyhelyzet
    egyetlen ágán sem szabadna kivételt dobnia."""
    n = len(feladatok)
    korlat = threading.Barrier(n)
    eredmenyek: list[object] = [None] * n
    hibak: list[BaseException] = []
    hiba_zar = threading.Lock()

    def fuss(i: int, feladat: Callable[[], object]) -> None:
        korlat.wait()
        try:
            eredmenyek[i] = feladat()
        except BaseException as exc:  # noqa: BLE001 - a teszt maga dönti el, mi számít hibának
            with hiba_zar:
                hibak.append(exc)

    szalak = [threading.Thread(target=fuss, args=(i, f)) for i, f in enumerate(feladatok)]
    for szal in szalak:
        szal.start()
    for szal in szalak:
        szal.join(timeout=30)
    meg_elo = [szal for szal in szalak if szal.is_alive()]
    if meg_elo:
        raise RuntimeError(f"{len(meg_elo)} szál nem fejeződött be 30 másodpercen belül")
    return eredmenyek, hibak


# --- 1. Párhuzamos foglalás ugyanarra a slotra ------------------------------


def test_parhuzamos_foglalas_pontosan_egy_sikeres(db_utvonal, egy_slot):
    """N szál egyszerre foglalja ugyanazt a slotot, különböző
    idempotencia_kulccsal. Pontosan egynek szabad SIKERES-t kapnia, a
    többinek MEGELOZTEK-et — kivétel egyiknek sem, és a végén az
    adatbázisban pontosan egy aktív foglalás legyen erre a slotra.

    Minden szál a SAJÁT kapcsolatát nyitja meg — a sqlite3 modul egy
    kapcsolatot csak abban a szálban engedélyez, amelyikben megnyílt
    (`check_same_thread`), ezért a kapcsolatnyitás nem történhet a fő
    szálon a worker-szálak indítása előtt."""

    def _feladat(i: int) -> Eredmeny:
        conn = migracio.kapcsolat_nyitas(db_utvonal)
        try:
            return foglalas_repo.foglalas_letrehoz(
                conn, egy_slot, "a" * 64, _uuid(), f"session-{i}"
            )
        finally:
            conn.close()

    feladatok = [(lambda i=i: _feladat(i)) for i in range(_SZALSZAM)]
    eredmenyek, hibak = _egyszerre_inditva(feladatok)

    assert hibak == [], f"a repo réteg kivételt dobott versenyhelyzetben: {hibak!r}"
    assert len(eredmenyek) == _SZALSZAM
    assert all(e in (Eredmeny.SIKERES, Eredmeny.MEGELOZTEK) for e in eredmenyek)

    sikeresek = [e for e in eredmenyek if e is Eredmeny.SIKERES]
    megelozottek = [e for e in eredmenyek if e is Eredmeny.MEGELOZTEK]
    assert len(sikeresek) == 1, "pontosan egy szálnak kell nyernie — ez a dupla foglalás invariáns"
    assert len(megelozottek) == _SZALSZAM - 1

    ellenorzo = migracio.kapcsolat_nyitas(db_utvonal)
    try:
        aktiv_szam = ellenorzo.execute(
            "SELECT COUNT(*) FROM foglalas WHERE slot_id = ? AND allapot <> 'lemondva'",
            (egy_slot,),
        ).fetchone()[0]
        assert aktiv_szam == 1, "dupla foglalás történt — sérült a CLAUDE.md 1. invariánsa"

        osszes_szam = ellenorzo.execute(
            "SELECT COUNT(*) FROM foglalas WHERE slot_id = ?", (egy_slot,)
        ).fetchone()[0]
        assert osszes_szam == 1, "nem várt extra foglalás-sor keletkezett a slotra"
    finally:
        ellenorzo.close()


# --- 2. Hold-verseny --------------------------------------------------------


def test_parhuzamos_hold_pontosan_egy_sikeres(db_utvonal, egy_slot):
    """N szál egyszerre próbál holdot tenni ugyanarra a slotra, különböző
    session_id-vel. Pontosan egynek SIKERES-t kell kapnia, a végén pontosan
    egy hold sor legyen a slotra."""

    def _feladat(i: int) -> Eredmeny:
        conn = migracio.kapcsolat_nyitas(db_utvonal)
        try:
            return foglalas_repo.hold_letrehoz(conn, egy_slot, f"session-{i}", _jovoben())
        finally:
            conn.close()

    feladatok = [(lambda i=i: _feladat(i)) for i in range(_SZALSZAM)]
    eredmenyek, hibak = _egyszerre_inditva(feladatok)

    assert hibak == [], f"a repo réteg kivételt dobott versenyhelyzetben: {hibak!r}"
    assert all(e in (Eredmeny.SIKERES, Eredmeny.MEGELOZTEK) for e in eredmenyek)

    sikeresek = [e for e in eredmenyek if e is Eredmeny.SIKERES]
    megelozottek = [e for e in eredmenyek if e is Eredmeny.MEGELOZTEK]
    assert len(sikeresek) == 1, "pontosan egy szálnak kell holdot nyernie egy slotra"
    assert len(megelozottek) == _SZALSZAM - 1

    ellenorzo = migracio.kapcsolat_nyitas(db_utvonal)
    try:
        hold_szam = ellenorzo.execute(
            "SELECT COUNT(*) FROM hold WHERE slot_id = ?", (egy_slot,)
        ).fetchone()[0]
        assert hold_szam == 1, "duplán holdolt slot — sérült a hold egyediségi garanciája"
    finally:
        ellenorzo.close()


def test_parhuzamos_hold_lejart_hold_utan_pontosan_egy_sikeres(db_utvonal, egy_slot):
    """Ha a slotra már ül egy LEJÁRT hold, két szál egyszerre próbál új
    holdot tenni rá — a hold_letrehoz a beszúrás előtt törli a lejárt
    holdot, ezért pontosan egy szálnak kell nyernie, nem egyiknek sem
    szabad MEGELOZTEK-et kapnia a régi (lejárt) sor miatt."""
    elokeszito = migracio.kapcsolat_nyitas(db_utvonal)
    try:
        (szervezet_id,) = elokeszito.execute(
            "SELECT szervezet_id FROM slot WHERE id = ?", (egy_slot,)
        ).fetchone()
        elokeszito.execute(
            "INSERT INTO hold (id, szervezet_id, slot_id, session_id, letrejott, lejar) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                _uuid(),
                szervezet_id,
                egy_slot,
                "session-regi",
                "2020-01-01T00:00:00Z",
                "2020-01-01T00:00:01Z",
            ),
        )
    finally:
        elokeszito.close()

    def _feladat(i: int) -> Eredmeny:
        conn = migracio.kapcsolat_nyitas(db_utvonal)
        try:
            return foglalas_repo.hold_letrehoz(conn, egy_slot, f"session-uj-{i}", _jovoben())
        finally:
            conn.close()

    feladatok = [(lambda i=i: _feladat(i)) for i in range(2)]
    eredmenyek, hibak = _egyszerre_inditva(feladatok)

    assert hibak == [], f"a repo réteg kivételt dobott versenyhelyzetben: {hibak!r}"
    sikeresek = [e for e in eredmenyek if e is Eredmeny.SIKERES]
    megelozottek = [e for e in eredmenyek if e is Eredmeny.MEGELOZTEK]
    assert len(sikeresek) == 1, f"pontosan egy szálnak kell nyernie, kapott: {eredmenyek!r}"
    assert len(megelozottek) == 1

    ellenorzo = migracio.kapcsolat_nyitas(db_utvonal)
    try:
        sorok = ellenorzo.execute(
            "SELECT session_id FROM hold WHERE slot_id = ?", (egy_slot,)
        ).fetchall()
        assert len(sorok) == 1, "a lejárt hold és/vagy a vesztes szál sora bent maradt"
        assert sorok[0][0] != "session-regi", "a lejárt hold sora nem törlődött"
    finally:
        ellenorzo.close()


# --- 3. Idempotencia-ismétlés, párhuzamosan ---------------------------------


def test_parhuzamos_idempotens_ismetles_mindegyik_sikeres(db_utvonal, egy_slot):
    """Ugyanaz az idempotencia_kulcs N szálból, párhuzamosan, ugyanarra a
    slotra: mindegyiknek SIKERES-t kell adnia (soha nem MEGELOZTEK, soha
    nem kivétel), és a végén pontosan egy foglalás-sor legyen."""
    kozos_kulcs = _uuid()

    def _feladat(i: int) -> Eredmeny:
        conn = migracio.kapcsolat_nyitas(db_utvonal)
        try:
            return foglalas_repo.foglalas_letrehoz(
                conn, egy_slot, "a" * 64, kozos_kulcs, f"session-{i}"
            )
        finally:
            conn.close()

    feladatok = [(lambda i=i: _feladat(i)) for i in range(_SZALSZAM)]
    eredmenyek, hibak = _egyszerre_inditva(feladatok)

    assert hibak == [], f"a repo réteg kivételt dobott versenyhelyzetben: {hibak!r}"
    assert eredmenyek == [Eredmeny.SIKERES] * _SZALSZAM, (
        "az idempotens ismétlésnek MINDIG SIKERES-t kell adnia, sosem MEGELOZTEK-et — "
        f"kapott eredmények: {eredmenyek!r}"
    )

    ellenorzo = migracio.kapcsolat_nyitas(db_utvonal)
    try:
        osszes_szam = ellenorzo.execute(
            "SELECT COUNT(*) FROM foglalas WHERE slot_id = ?", (egy_slot,)
        ).fetchone()[0]
        assert osszes_szam == 1, "az idempotens ismétlés duplázott — elveszett/duplázott foglalás"

        kulcs_szam = ellenorzo.execute(
            "SELECT COUNT(DISTINCT idempotencia_kulcs) FROM foglalas WHERE slot_id = ?",
            (egy_slot,),
        ).fetchone()[0]
        assert kulcs_szam == 1
    finally:
        ellenorzo.close()


# --- motor-hordozhatóság dokumentálása ---------------------------------------


def test_migracio_ma_kizarolag_sqlite_ot_tamogat_dokumentalt_hiany():
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
    forras = Path(migracio.__file__).read_text(encoding="utf-8")
    assert "kizárólag SQLite-ot ismer" in forras, (
        "a migracio.py leírása megváltozott — ha Postgres-támogatás került bele, "
        "a verseny-tesztek db_utvonal/kapcsolat fixture-jét ki kell egészíteni "
        "egy tényleges Postgres-ágra, hogy a 'teszt-mindketto' valóban két "
        "motort fedjen le, ne csak kétszer ugyanazt a SQLite-ágat."
    )

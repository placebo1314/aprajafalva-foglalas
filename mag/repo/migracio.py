"""Migrációs futtató a foglalási maghoz.

Sorszámozott `.sql` fájlokat olvas a `migraciok/` könyvtárból. Minden fájl
`-- up` és `-- down` szakaszra bomlik (lásd `db-hordozhatosag` skill,
migrációs sablon). A lefutott migrációkat a `sema_verzio` tábla tartja
nyilván, minden migráció egyetlen tranzakcióban fut.

Ez a modul kizárólag SQLite-ot ismer (ADR-004). A kapcsolat nyitásakor
kötelezően beállítja a hordozhatósági szabályok szerinti pragmákat, és az
írás mindig explicit `BEGIN IMMEDIATE`-del indul — sosem a sqlite3 modul
implicit tranzakciókezelésével, ezért a kapcsolat `isolation_level=None`
(autocommit) módban nyílik meg.
"""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

GYOKER = Path(__file__).resolve().parents[2]
MIGRACIOK_KONYVTAR = GYOKER / "migraciok"

_FAJLNEV_MINTA = re.compile(r"^(\d{4})_[a-z0-9_]+\.sql$")
_UP_MINTA = re.compile(r"^--\s*up\s*$", re.MULTILINE | re.IGNORECASE)
_DOWN_MINTA = re.compile(r"^--\s*down\s*$", re.MULTILINE | re.IGNORECASE)


class MigracioHiba(RuntimeError):
    """Migrációs fájl formátuma vagy futtatása hibás."""


@dataclass(frozen=True)
class Migracio:
    sorszam: str
    nev: str
    fajl: Path
    up_sql: str
    down_sql: str


def kapcsolat_nyitas(db_utvonal: str) -> sqlite3.Connection:
    """Kapcsolatot nyit, és beállítja a kötelező pragmákat.

    `isolation_level=None`: a sqlite3 modul nem nyit és nem zár tranzakciót
    magától — a `BEGIN IMMEDIATE` / `COMMIT` / `ROLLBACK` mindig explicit.
    """
    conn = sqlite3.connect(db_utvonal, isolation_level=None)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn


def _migraciok_beolvasasa() -> list[Migracio]:
    migraciok: list[Migracio] = []
    for fajl in sorted(MIGRACIOK_KONYVTAR.glob("*.sql")):
        illeszkedes = _FAJLNEV_MINTA.match(fajl.name)
        if not illeszkedes:
            raise MigracioHiba(
                f"Érvénytelen migrációs fájlnév: {fajl.name} "
                "(elvárt minta: 0001_nev.sql)"
            )
        sorszam = illeszkedes.group(1)
        up_sql, down_sql = _szakaszokra_bontas(fajl)
        migraciok.append(Migracio(sorszam, fajl.stem, fajl, up_sql, down_sql))

    latott: set[str] = set()
    for m in migraciok:
        if m.sorszam in latott:
            raise MigracioHiba(f"Duplikált migrációs sorszám: {m.sorszam}")
        latott.add(m.sorszam)
    return migraciok


def _szakaszokra_bontas(fajl: Path) -> tuple[str, str]:
    szoveg = fajl.read_text(encoding="utf-8")
    up_illeszkedes = _UP_MINTA.search(szoveg)
    down_illeszkedes = _DOWN_MINTA.search(szoveg)
    if not up_illeszkedes or not down_illeszkedes:
        raise MigracioHiba(f"{fajl.name}: hiányzik a '-- up' vagy '-- down' szakaszjelölő")
    if down_illeszkedes.start() < up_illeszkedes.start():
        raise MigracioHiba(f"{fajl.name}: a '-- down' a '-- up' előtt szerepel")

    up_sql = szoveg[up_illeszkedes.end() : down_illeszkedes.start()].strip()
    down_sql = szoveg[down_illeszkedes.end() :].strip()
    if not up_sql:
        raise MigracioHiba(f"{fajl.name}: üres 'up' szakasz")
    if not down_sql:
        raise MigracioHiba(f"{fajl.name}: üres 'down' szakasz — a down kötelező")
    return up_sql, down_sql


def _allitasokra_bontas(sql: str) -> list[str]:
    """SQL szöveget önálló utasításokra bont, sztringen/kommenten belüli
    pontosvesszőt figyelmen kívül hagyva."""
    allitasok: list[str] = []
    puffer = ""
    for sor in sql.splitlines(keepends=True):
        puffer += sor
        if sqlite3.complete_statement(puffer):
            csonkitott = puffer.strip()
            if csonkitott:
                allitasok.append(csonkitott)
            puffer = ""
    maradek = puffer.strip()
    if maradek:
        raise MigracioHiba(f"Befejezetlen SQL utasítás a szakasz végén: {maradek!r}")
    return allitasok


def _sema_verzio_biztositasa(conn: sqlite3.Connection) -> None:
    """A `sema_verzio` a migrációs rendszer saját nyilvántartása, nem
    domain-tábla — ezért nem migrációs fájlból jön, hanem itt, közvetlenül.
    Ez tudatos kivétel a "kézi sémamódosítás soha" elv alól (CLAUDE.md):
    a verziókövető táblának léteznie kell, mielőtt bármelyik migrációs
    fájlt le tudnánk olvasni ahhoz, hogy eldöntsük, melyik futott már —
    ő maga nem verziózható. Idempotens (`IF NOT EXISTS`) és determinisztikus,
    nem igényel ADR-t.
    """
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS sema_verzio (
            sorszam     TEXT PRIMARY KEY,
            nev         TEXT NOT NULL,
            lefutott    TEXT NOT NULL,
            CHECK (length(sorszam) = 4)
        )
        """
    )


def _lefutott_sorszamok(conn: sqlite3.Connection) -> set[str]:
    _sema_verzio_biztositasa(conn)
    return {sor[0] for sor in conn.execute("SELECT sorszam FROM sema_verzio")}


def _most_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def migral(conn: sqlite3.Connection) -> list[str]:
    """A még le nem futott migrációkat sorszám szerint, egyenként végrehajtja.

    Minden migráció saját `BEGIN IMMEDIATE` tranzakcióban fut: vagy teljesen
    lefut és bekerül a `sema_verzio`-ba, vagy hiba esetén minden változása
    visszagördül. Visszaadja a most lefuttatott migrációk sorszámát.
    """
    migraciok = _migraciok_beolvasasa()
    lefutott = _lefutott_sorszamok(conn)
    vegrehajtott: list[str] = []
    for m in migraciok:
        if m.sorszam in lefutott:
            continue
        conn.execute("BEGIN IMMEDIATE")
        try:
            for allitas in _allitasokra_bontas(m.up_sql):
                conn.execute(allitas)
            conn.execute(
                "INSERT INTO sema_verzio (sorszam, nev, lefutott) VALUES (?, ?, ?)",
                (m.sorszam, m.nev, _most_iso()),
            )
        except Exception:
            conn.execute("ROLLBACK")
            raise
        else:
            conn.execute("COMMIT")
            vegrehajtott.append(m.sorszam)
    return vegrehajtott


def visszagorget(conn: sqlite3.Connection, sorszamig: str | None = None) -> list[str]:
    """Visszagörgeti a lefutott migrációkat fordított sorrendben.

    `sorszamig` megadásakor csak addig görget vissza (azt a migrációt már
    nem vonja vissza); ha `None`, mindent visszagörget. Visszaadja a most
    visszagörgetett migrációk sorszámát, végrehajtási sorrendben.
    """
    migraciok = {m.sorszam: m for m in _migraciok_beolvasasa()}
    lefutott = sorted(_lefutott_sorszamok(conn), reverse=True)
    visszagorgetett: list[str] = []
    for sorszam in lefutott:
        if sorszamig is not None and sorszam <= sorszamig:
            break
        m = migraciok.get(sorszam)
        if m is None:
            raise MigracioHiba(f"Lefutott migráció fájlja hiányzik a migraciok/-ból: {sorszam}")
        conn.execute("BEGIN IMMEDIATE")
        try:
            for allitas in _allitasokra_bontas(m.down_sql):
                conn.execute(allitas)
            conn.execute("DELETE FROM sema_verzio WHERE sorszam = ?", (sorszam,))
        except Exception:
            conn.execute("ROLLBACK")
            raise
        else:
            conn.execute("COMMIT")
            visszagorgetett.append(sorszam)
    return visszagorgetett


def _fo() -> None:
    import sys

    if len(sys.argv) < 2:
        print("Használat: python -m mag.repo.migracio <db_utvonal> [--vissza [sorszamig]]")
        raise SystemExit(1)

    db_utvonal = sys.argv[1]
    conn = kapcsolat_nyitas(db_utvonal)
    try:
        if len(sys.argv) > 2 and sys.argv[2] == "--vissza":
            sorszamig = sys.argv[3] if len(sys.argv) > 3 else None
            eredmeny = visszagorget(conn, sorszamig)
            print(f"Visszagörgetve: {eredmeny}" if eredmeny else "Nincs mit visszagörgetni.")
        else:
            eredmeny = migral(conn)
            print(f"Lefuttatva: {eredmeny}" if eredmeny else "Minden migráció naprakész.")
    finally:
        conn.close()


if __name__ == "__main__":
    _fo()

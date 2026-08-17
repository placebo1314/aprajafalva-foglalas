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
from pathlib import Path

from core.ido import most_iso

ROOT = Path(__file__).resolve().parents[2]
MIGRATIONS_DIRECTORY = ROOT / "migrations"

_FILENAME_PATTERN = re.compile(r"^(\d{4})_[a-z0-9_]+\.sql$")
_UP_PATTERN = re.compile(r"^--\s*up\s*$", re.MULTILINE | re.IGNORECASE)
_DOWN_PATTERN = re.compile(r"^--\s*down\s*$", re.MULTILINE | re.IGNORECASE)


class MigrationError(RuntimeError):
    """Migrációs fájl formátuma vagy futtatása hibás."""


@dataclass(frozen=True)
class Migration:
    seq: str
    name: str
    file: Path
    up_sql: str
    down_sql: str


def conn_nyitas(db_path: str) -> sqlite3.Connection:
    """Kapcsolatot nyit, és beállítja a kötelező pragmákat.

    `isolation_level=None`: a sqlite3 modul nem nyit és nem zár tranzakciót
    magától — a `BEGIN IMMEDIATE` / `COMMIT` / `ROLLBACK` mindig explicit.
    """
    conn = sqlite3.connect(db_path, isolation_level=None)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn


def _migrations_read() -> list[Migration]:
    migrations: list[Migration] = []
    for file in sorted(MIGRATIONS_DIRECTORY.glob("*.sql")):
        illeszkedes = _FILENAME_PATTERN.match(file.name)
        if not illeszkedes:
            raise MigrationError(
                f"Érvénytelen migrációs fájlnév: {file.name} (elvárt minta: 0001_nev.sql)"
            )
        seq = illeszkedes.group(1)
        up_sql, down_sql = _into_segments_split(file)
        migrations.append(Migration(seq, file.stem, file, up_sql, down_sql))

    seen: set[str] = set()
    for m in migrations:
        if m.seq in seen:
            raise MigrationError(f"Duplikált migrációs sorszám: {m.seq}")
        seen.add(m.seq)
    return migrations


def _into_segments_split(file: Path) -> tuple[str, str]:
    szoveg = file.read_text(encoding="utf-8")
    up_match = _UP_PATTERN.search(szoveg)
    down_match = _DOWN_PATTERN.search(szoveg)
    if not up_match or not down_match:
        raise MigrationError(f"{file.name}: hiányzik a '-- up' vagy '-- down' szakaszjelölő")
    if down_match.start() < up_match.start():
        raise MigrationError(f"{file.name}: a '-- down' a '-- up' előtt szerepel")

    up_sql = szoveg[up_match.end() : down_match.start()].strip()
    down_sql = szoveg[down_match.end() :].strip()
    if not up_sql:
        raise MigrationError(f"{file.name}: üres 'up' szakasz")
    if not down_sql:
        raise MigrationError(f"{file.name}: üres 'down' szakasz — a down kötelező")
    return up_sql, down_sql


def _into_statements_split(sql: str) -> list[str]:
    """SQL szöveget önálló utasításokra bont, sztringen/kommenten belüli
    pontosvesszőt figyelmen kívül hagyva."""
    statements: list[str] = []
    buffer = ""
    for row in sql.splitlines(keepends=True):
        buffer += row
        if sqlite3.complete_statement(buffer):
            truncated = buffer.strip()
            if truncated:
                statements.append(truncated)
            buffer = ""
    maradek = buffer.strip()
    if maradek:
        raise MigrationError(f"Befejezetlen SQL utasítás a szakasz végén: {maradek!r}")
    return statements


def _schema_version_ensure(conn: sqlite3.Connection) -> None:
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


def _ran_seqs(conn: sqlite3.Connection) -> set[str]:
    _schema_version_ensure(conn)
    return {row[0] for row in conn.execute("SELECT sorszam FROM sema_verzio")}


def migral(conn: sqlite3.Connection) -> list[str]:
    """A még le nem futott migrációkat sorszám szerint, egyenként végrehajtja.

    Minden migráció saját `BEGIN IMMEDIATE` tranzakcióban fut: vagy teljesen
    lefut és bekerül a `sema_verzio`-ba, vagy hiba esetén minden változása
    visszagördül. Visszaadja a most lefuttatott migrációk sorszámát.
    """
    migrations = _migrations_read()
    ran = _ran_seqs(conn)
    executed: list[str] = []
    for m in migrations:
        if m.seq in ran:
            continue
        conn.execute("BEGIN IMMEDIATE")
        try:
            for statement in _into_statements_split(m.up_sql):
                conn.execute(statement)
            conn.execute(
                "INSERT INTO sema_verzio (sorszam, nev, lefutott) VALUES (?, ?, ?)",
                (m.seq, m.name, most_iso()),
            )
        except Exception:
            conn.execute("ROLLBACK")
            raise
        else:
            conn.execute("COMMIT")
            executed.append(m.seq)
    return executed


def rollback(conn: sqlite3.Connection, up_to_seq: str | None = None) -> list[str]:
    """Visszagörgeti a lefutott migrációkat fordított sorrendben.

    `sorszamig` megadásakor csak addig görget vissza (azt a migrációt már
    nem vonja vissza); ha `None`, mindent visszagörget. Visszaadja a most
    visszagörgetett migrációk sorszámát, végrehajtási sorrendben.
    """
    migrations = {m.seq: m for m in _migrations_read()}
    ran = sorted(_ran_seqs(conn), reverse=True)
    rolled_back: list[str] = []
    for seq in ran:
        if up_to_seq is not None and seq <= up_to_seq:
            break
        m = migrations.get(seq)
        if m is None:
            raise MigrationError(f"Lefutott migráció fájlja hiányzik a migraciok/-ból: {seq}")
        conn.execute("BEGIN IMMEDIATE")
        try:
            for statement in _into_statements_split(m.down_sql):
                conn.execute(statement)
            conn.execute("DELETE FROM sema_verzio WHERE sorszam = ?", (seq,))
        except Exception:
            conn.execute("ROLLBACK")
            raise
        else:
            conn.execute("COMMIT")
            rolled_back.append(seq)
    return rolled_back


def _fo() -> None:
    import sys

    # Lásd seed/betolt.py::_fo() azonos kommentje — Windowson a konzol
    # örökölt kódlapja nem mindig kódolja az ékezetes karaktereket.
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

    if len(sys.argv) < 2:
        print("Használat: python -m mag.repo.migracio <db_utvonal> [--vissza [sorszamig]]")
        raise SystemExit(1)

    db_path = sys.argv[1]
    conn = conn_nyitas(db_path)
    try:
        if len(sys.argv) > 2 and sys.argv[2] == "--vissza":
            up_to_seq = sys.argv[3] if len(sys.argv) > 3 else None
            result = rollback(conn, up_to_seq)
            print(f"Visszagörgetve: {result}" if result else "Nincs mit visszagörgetni.")
        else:
            result = migral(conn)
            print(f"Lefuttatva: {result}" if result else "Minden migráció naprakész.")
    finally:
        conn.close()


if __name__ == "__main__":
    _fo()

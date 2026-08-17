"""Mentés: `VACUUM INTO` pillanatkép.

Blueprint 9. szakasz, "Mentés és helyreállítás":

    óránkénti VACUUM INTO pillanatkép + WAL-másolat külön eszközre
    helyreállítási próba a tesztkészletben — az a mentés, amit sosem
    állítottak vissza, nem mentés

A „0 elveszett foglalás" invariáns (CLAUDE.md) idáig csak a konkurenciára
vonatkozott (ADR-003) — ez a modul a lemezre vonatkozó felét fedi.
`VACUUM INTO` egyetlen, önmagában konzisztens fájlt ad, a WAL-ban ülő, még
nem checkpointolt változásokkal együtt — nincs szükség külön
checkpoint-lépésre előtte.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from core.ido import most_iso
from core.repo.migracio import conn_nyitas


def snapshot_create(db_path: str | Path, target_path: str | Path) -> Path:
    """`VACUUM INTO` a `cel_utvonal`-ra. A cél nem létezhet előre — a
    `VACUUM INTO` maga is elutasítja a felülírást, ezt itt csak explicit
    hibaüzenettel ismételjük meg, hogy ne az SQLite nyers hibája jöjjön
    vissza."""
    target_path = Path(target_path)
    if target_path.exists():
        raise FileExistsError(f"A pillanatkép célja már létezik: {target_path}")
    target_path.parent.mkdir(parents=True, exist_ok=True)

    conn = conn_nyitas(str(db_path))
    try:
        conn.execute("VACUUM INTO ?", (str(target_path),))
    finally:
        conn.close()
    return target_path


def snapshot_name(prefix: str = "aprajafalva") -> str:
    """`<előtag>-<ISO-8601 UTC időbélyeg, kettőspont nélkül>.db` —
    fájlnévbe kettőspont nem való, a formázás azt aláhúzásra cseréli."""
    timestamp = most_iso().replace(":", "")
    return f"{prefix}-{timestamp}.db"


def restore(snapshot_path: str | Path, target_db_path: str | Path) -> Path:
    """A pillanatképet egyszerű fájlmásolással állítja vissza — a
    `VACUUM INTO` már egy önmagában konzisztens, nem-WAL fájlt ad, nincs
    szükség speciális helyreállítási logikára vagy nyitott kapcsolatra."""
    target_db_path = Path(target_db_path)
    target_db_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(str(snapshot_path), str(target_db_path))
    return target_db_path


def _fo() -> int:
    import sys

    sys.stdout.reconfigure(encoding="utf-8")
    if len(sys.argv) < 2 or sys.argv[1] not in ("ment", "visszaallit"):
        print(
            "Használat:\n"
            "  python -m mag.repo.mentes ment <db_utvonal> <cel_utvonal>\n"
            "  python -m mag.repo.mentes visszaallit <pillanatkep_utvonal> <cel_db_utvonal>"
        )
        return 1
    if sys.argv[1] == "ment":
        result = snapshot_create(sys.argv[2], sys.argv[3])
        print(f"Pillanatkép kész: {result}")
    else:
        result = restore(sys.argv[2], sys.argv[3])
        print(f"Visszaállítva: {result}")
    return 0


if __name__ == "__main__":
    import sys

    sys.exit(_fo())

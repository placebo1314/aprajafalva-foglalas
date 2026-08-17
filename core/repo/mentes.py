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

from mag.ido import most_iso
from mag.repo.migracio import kapcsolat_nyitas


def pillanatkep_keszit(db_utvonal: str | Path, cel_utvonal: str | Path) -> Path:
    """`VACUUM INTO` a `cel_utvonal`-ra. A cél nem létezhet előre — a
    `VACUUM INTO` maga is elutasítja a felülírást, ezt itt csak explicit
    hibaüzenettel ismételjük meg, hogy ne az SQLite nyers hibája jöjjön
    vissza."""
    cel_utvonal = Path(cel_utvonal)
    if cel_utvonal.exists():
        raise FileExistsError(f"A pillanatkép célja már létezik: {cel_utvonal}")
    cel_utvonal.parent.mkdir(parents=True, exist_ok=True)

    conn = kapcsolat_nyitas(str(db_utvonal))
    try:
        conn.execute("VACUUM INTO ?", (str(cel_utvonal),))
    finally:
        conn.close()
    return cel_utvonal


def pillanatkep_nev(elotag: str = "aprajafalva") -> str:
    """`<előtag>-<ISO-8601 UTC időbélyeg, kettőspont nélkül>.db` —
    fájlnévbe kettőspont nem való, a formázás azt aláhúzásra cseréli."""
    idobelyeg = most_iso().replace(":", "")
    return f"{elotag}-{idobelyeg}.db"


def visszaallit(pillanatkep_utvonal: str | Path, cel_db_utvonal: str | Path) -> Path:
    """A pillanatképet egyszerű fájlmásolással állítja vissza — a
    `VACUUM INTO` már egy önmagában konzisztens, nem-WAL fájlt ad, nincs
    szükség speciális helyreállítási logikára vagy nyitott kapcsolatra."""
    cel_db_utvonal = Path(cel_db_utvonal)
    cel_db_utvonal.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(str(pillanatkep_utvonal), str(cel_db_utvonal))
    return cel_db_utvonal


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
        eredmeny = pillanatkep_keszit(sys.argv[2], sys.argv[3])
        print(f"Pillanatkép kész: {eredmeny}")
    else:
        eredmeny = visszaallit(sys.argv[2], sys.argv[3])
        print(f"Visszaállítva: {eredmeny}")
    return 0


if __name__ == "__main__":
    import sys

    sys.exit(_fo())

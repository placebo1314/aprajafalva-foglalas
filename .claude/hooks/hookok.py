#!/usr/bin/env python3
"""Claude Code hookok az aprajafalvi időpontfoglaló projekthez.

Használat:  python hookok.py <ellenorzes>

Az ellenőrzések a bemeneti JSON-t a stdin-en kapják. A 2-es kilépőkód
blokkoló hibát jelez: a stderr tartalma visszakerül Claude-hoz.

Platformfüggetlen: nem kell hozzá bash, jq vagy egyéb külső eszköz.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

# --------------------------------------------------------------------------
# Segédfüggvények
# --------------------------------------------------------------------------


def bemenet() -> dict:
    """A hook JSON bemenete a stdin-ről. Hibás bemenet nem okoz összeomlást."""
    try:
        return json.loads(sys.stdin.read() or "{}")
    except (json.JSONDecodeError, ValueError):
        return {}


def projekt_gyoker() -> Path:
    return Path(os.environ.get("CLAUDE_PROJECT_DIR", ".")).resolve()


def erintett_fajl(adat: dict) -> Path | None:
    """A szerkesztett fájl útvonala, ha létezik."""
    utvonal = (adat.get("tool_input") or {}).get("file_path")
    if not utvonal:
        return None
    p = Path(utvonal)
    return p if p.is_file() else None


def relativ(p: Path) -> str:
    """Projektgyökérhez képesti útvonal, mindig / elválasztóval."""
    try:
        return p.resolve().relative_to(projekt_gyoker()).as_posix()
    except ValueError:
        return p.as_posix()


def szoveg(p: Path) -> str:
    return p.read_text(encoding="utf-8", errors="replace")


def blokkol(cim: str, reszletek: list[str], hivatkozas: str) -> None:
    """Blokkoló hiba: a 2-es kilépőkód miatt Claude látja a stderr-t."""
    print(f"{cim}\n", file=sys.stderr)
    for sor in reszletek:
        print(f"  - {sor}", file=sys.stderr)
    print(f"\n{hivatkozas}", file=sys.stderr)
    sys.exit(2)


def talalatok(tartalom: str, minta: str) -> list[str]:
    """Illeszkedő sorok sorszámmal, megjelenítéshez."""
    ki = []
    for i, sor in enumerate(tartalom.splitlines(), 1):
        if re.search(minta, sor, re.IGNORECASE):
            ki.append(f"{i}: {sor.strip()}")
    return ki


# --------------------------------------------------------------------------
# Ellenőrzések
# --------------------------------------------------------------------------


def modul_hatar() -> None:
    """A mag/ nem függhet az asszisztens/-től. Ez a modularitás valódi tesztje."""
    fajl = erintett_fajl(bemenet())
    if not fajl:
        return
    rel = relativ(fajl)
    tartalom = szoveg(fajl)
    hibak: list[str] = []

    if rel.startswith("mag/"):
        m = talalatok(tartalom, r"^\s*(from|import)\s+(asszisztens|felulet)\b")
        if m:
            hibak.append("A mag/ nem importálhat az asszisztens/ vagy felulet/ modulból:")
            hibak.extend(m)
        if talalatok(tartalom, r"(llama_cpp|ollama|openai|transformers|LLMSzolgaltato)"):
            hibak.append("A mag/ nem hívhat LLM-et. Az értelmezés az asszisztens/ dolga.")

    if rel.startswith("felulet/"):
        if talalatok(tartalom, r"(llama_cpp|ollama|openai\.)"):
            hibak.append("A felulet/ nem hívhat LLM-et közvetlenül, csak az asszisztens/-en át.")

    if hibak:
        blokkol(
            f"MODULHATÁR SÉRTÉS ({rel})",
            hibak,
            "Lásd CLAUDE.md / Modulhatárok. Ha indokolt a változtatás, ADR kell hozzá.",
        )


def tiltott_minta() -> None:
    """Titok vagy nyers személyes azonosító nem kerülhet a kódba."""
    fajl = erintett_fajl(bemenet())
    if not fajl:
        return
    rel = relativ(fajl)
    if rel.startswith(("tesztek/", "seed/", "docs/", ".claude/")):
        return

    tartalom = szoveg(fajl)
    hibak: list[str] = []

    if talalatok(tartalom, r"(PEPPER|SECRET|API_KEY|PASSWORD|TOKEN)\s*[:=]\s*[\"'][^\"']{6,}"):
        hibak.append(
            "Beégetett titok. A pepper és minden kulcs környezeti változóból "
            "vagy kulcstárolóból jön."
        )

    if not rel.startswith("adatvedelem/"):
        if talalatok(tartalom, r"nyers_azonosito|azonosito_nyers"):
            hibak.append(
                "Nyers azonosító az adatvedelem/ modulon kívül. "
                "Használd az adatvedelem.hash_azonosito() függvényt."
            )

    if hibak:
        blokkol(
            f"TILTOTT MINTA ({rel})",
            hibak,
            "Lásd CLAUDE.md invariáns 2. és az adatvedelem skillt.",
        )


SQL_MINTA = (
    r"\b(SELECT\s+.*\s+FROM\s|INSERT\s+INTO|UPDATE\s+.*\s+SET\s"
    r"|DELETE\s+FROM|CREATE\s+(TABLE|INDEX))"
)


def sql_hely() -> None:
    """Minden SQL a mag/repo/-ban van. Ez teszi a Postgres-váltást egynapossá."""
    fajl = erintett_fajl(bemenet())
    if not fajl or fajl.suffix != ".py":
        return
    rel = relativ(fajl)
    if rel.startswith(("mag/repo/", "migraciok/", "tesztek/", "seed/")):
        return

    m = talalatok(szoveg(fajl), SQL_MINTA)
    if m:
        blokkol(
            f"SQL A REPOSITORY RÉTEGEN KÍVÜL ({rel})",
            m + ["Minden lekérdezés a mag/repo/-ba tartozik."],
            "Lásd a db-hordozhatosag skillt.",
        )


HORDOZHATOSAG = [
    (r"AUTOINCREMENT", "AUTOINCREMENT tilos. Használj UUID-t (TEXT)."),
    (r"INTEGER\s+PRIMARY\s+KEY", "Egész elsődleges kulcs tilos. UUID TEXT kell."),
    (r"INSERT\s+OR\s+REPLACE", "INSERT OR REPLACE tilos. Használj ON CONFLICT-ot."),
    (r"INSERT\s+OR\s+IGNORE", "INSERT OR IGNORE tilos. Használj ON CONFLICT DO NOTHING-ot."),
    (r"strftime\s*\(", "strftime SQLite-specifikus. Az időszámítás az alkalmazásrétegben van."),
    (r"julianday\s*\(", "julianday SQLite-specifikus."),
    (r"datetime\s*\(\s*'now'", "datetime('now') SQLite-specifikus. Az időt az app adja át."),
    (r"WITHOUT\s+ROWID", "WITHOUT ROWID SQLite-specifikus."),
    (r"\bGLOB\b", "GLOB SQLite-specifikus. Használj LIKE-ot."),
]


def migracio_lint() -> None:
    """Ami ezen átmegy, az Postgresen is fut."""
    fajl = erintett_fajl(bemenet())
    if not fajl or fajl.suffix != ".sql":
        return

    tartalom = szoveg(fajl)
    hibak: list[str] = []

    for minta, uzenet in HORDOZHATOSAG:
        m = talalatok(tartalom, minta)
        if m:
            hibak.append(uzenet)
            hibak.extend(f"    {sor}" for sor in m)

    if re.search(r"CREATE\s+TABLE", tartalom, re.IGNORECASE) and not re.search(
        r"^\s*--\s*down", tartalom, re.IGNORECASE | re.MULTILINE
    ):
        hibak.append("Hiányzik a '-- down' szakasz. Minden migráció visszafordítható.")

    if hibak:
        blokkol(
            f"HORDOZHATÓSÁGI HIBA ({fajl.name})", hibak, "Lásd db-hordozhatosag skill / ADR-004."
        )


def formaz() -> None:
    """Formázás és lintelés. Sosem blokkol, csak rendet tart."""
    fajl = erintett_fajl(bemenet())
    if not fajl or fajl.suffix != ".py":
        return
    for parancs in (
        [sys.executable, "-m", "ruff", "format", str(fajl)],
        [sys.executable, "-m", "ruff", "check", "--fix", str(fajl)],
    ):
        try:
            subprocess.run(parancs, capture_output=True, timeout=30)
        except subprocess.TimeoutExpired:
            return
        except FileNotFoundError:
            return  # ruff nincs telepítve: csendben kihagyjuk


def teszt() -> None:
    """A turn végén háttérben futó tesztek. Bukásnál felébreszti Claude-ot.

    Négy védelem a végtelen hurok ellen — a hook 2-es kódja felébreszti
    Claude-ot, aki új fordulót zár, ami újra kiváltaná ezt a hookot:

    1. stop_hook_active: már egy hook-ébresztés miatt futunk, nem szólunk újra
    2. nincs tesztfájl: nincs mit bizonyítani
    3. pytest nincs telepítve: környezeti hiány, nem kódhiba
    4. pytest 5-ös kód (nem gyűjtött tesztet): nem bukás
    """
    adat = bemenet()
    if adat.get("stop_hook_active"):
        return

    gyoker = projekt_gyoker()
    if not (gyoker / "feladat.py").is_file():
        return

    tesztek = list((gyoker / "tesztek").rglob("test_*.py"))
    if not tesztek:
        return

    try:
        eredmeny = subprocess.run(
            [sys.executable, "feladat.py", "teszt"],
            cwd=gyoker,
            capture_output=True,
            text=True,
            timeout=280,
        )
    except (subprocess.TimeoutExpired, OSError):
        return

    kimenet = eredmeny.stdout + eredmeny.stderr

    if "No module named pytest" in kimenet:
        return  # környezeti hiány: a fejlesztő dolga, nem blokkoló
    if eredmeny.returncode in (0, 5):
        return  # 5 = nem gyűjtött tesztet

    print("A TESZTEK BUKTAK:\n" + "\n".join(kimenet.splitlines()[-40:]), file=sys.stderr)
    sys.exit(2)


def session_kezdet() -> None:
    """Rövid állapotkép a munkamenet elején. Tények, nem utasítások."""
    gyoker = projekt_gyoker()

    def git(*args: str) -> str:
        try:
            return subprocess.run(
                ["git", *args], cwd=gyoker, capture_output=True, text=True, timeout=5
            ).stdout.strip()
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return ""

    ag = git("rev-parse", "--abbrev-ref", "HEAD") or "nincs-git"
    valtozott = len([s for s in git("status", "--porcelain").splitlines() if s])
    migraciok = len(list((gyoker / "migraciok").glob("*.sql")))
    adrek = len(list((gyoker / "docs" / "adr").glob("*.md")))

    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "SessionStart",
                    "additionalContext": (
                        f"Repó állapota: ág={ag}, nem commitolt fájlok={valtozott}, "
                        f"migrációk={migraciok}, ADR-ek={adrek}."
                    ),
                }
            }
        )
    )


ELLENORZESEK = {
    "modul-hatar": modul_hatar,
    "tiltott-minta": tiltott_minta,
    "sql-hely": sql_hely,
    "migracio-lint": migracio_lint,
    "formaz": formaz,
    "teszt": teszt,
    "session-kezdet": session_kezdet,
}


def main() -> None:
    if len(sys.argv) < 2 or sys.argv[1] not in ELLENORZESEK:
        print(f"Használat: python hookok.py <{' | '.join(ELLENORZESEK)}>", file=sys.stderr)
        sys.exit(0)  # ismeretlen ellenőrzés nem blokkolhat munkát
    ELLENORZESEK[sys.argv[1]]()


if __name__ == "__main__":
    main()

# Aprajafalvi időpontfoglaló

Magyar nyelvű, lokálisan futó időpontfoglaló rendszer Aprajafalva három
boltjához. A vásárló hétköznapi magyar mondatokkal foglal — az LLM fordít,
a foglalást determinisztikus mag végzi.

## Dokumentáció

| Fájl | Mit tartalmaz |
|---|---|
| `CLAUDE.md` | alapelv, invariánsok, konvenciók — minden munkamenet ezzel indul |
| `docs/blueprint.md` | a teljes műszaki terv |
| `docs/roadmap.md` | mérföldkövek és az első lépések |
| `docs/KOMPONENSEK.md` | újrahasznosítható komponensek, licencekkel |
| `docs/adr/` | döntési feljegyzések kiváltó feltétellel |

## Előfeltételek

- **Python 3.11+** — a `python` parancsnak elérhetőnek kell lennie
- **git**
- opcionális: `pip install ruff pytest`

Nem kell hozzá: Node.js, make, bash, jq, WSL, Docker.
A projekt natívan fut Windowson, macOS-en és Linuxon.

## Indulás

```
python feladat.py seed        # demóadat: 3 bolt, Törpilla 3 pultja
python feladat.py teszt       # tesztkészlet
```

## Fejlesztői környezet

A repó Claude Code-hoz készült. A `.claude/` alatt:

- **skillek** — domain-tudás igény szerint betöltve
- **agentek** — `sema-orzo`, `konkurencia-teszto`, `eval-futtato`
- **hookok** — `hooks/hookok.py`, tiszta Python

A hookok kikényszerítik: modulhatár (a `mag/` nem importál az
`asszisztens/`-ből), SQL csak a `mag/repo/`-ban, migrációk hordozhatósága,
tiltott minták (nyers azonosító, beégetett titok).

### Ha `python` helyett `python3` a parancs

macOS-en és Linuxon gyakran `python3`. Ilyenkor a `.claude/settings.json`-ben
a `"command": "python"` értékeket cseréld `"python3"`-ra.

### A hookok kézi próbája

```
python .claude/hooks/hookok.py session-kezdet
```

## A két invariáns

- Egy slotra pontosan egy aktív foglalás lehet. **0 dupla foglalás.**
- Nyers vásárlóazonosító soha nem kerül lemezre, logba vagy trace-be.

Mindkettőt teszt bizonyítja, nem monitorozás.

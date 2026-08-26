# Aprajafalvi időpontfoglaló

Magyar nyelvű, lokálisan futó időpontfoglaló rendszer Aprajafalva három
boltjához. A vásárló hétköznapi magyar mondatokkal foglal — az LLM fordít,
a foglalást determinisztikus mag végzi.

## Dokumentáció

Ha most találkozol először a projekttel: **`docs/KISOKOS.md`** — telepítés,
első futtatás, mit próbálj ki, gyakori hibák. Ha ellenőrizni akarod, hogy
működik: **`docs/TESZTELES.md`**. Ha azt akarod tudni, hol tartunk: **`docs/ALLAPOT.md`**.

| Fájl | Mit tartalmaz |
|---|---|
| `CLAUDE.md` | alapelv, invariánsok, konvenciók — minden munkamenet ezzel indul |
| `docs/KISOKOS.md` | belépő laikusoknak — telepítés, első futtatás, gyakori hibák |
| `docs/ALLAPOT.md` | egy oldalas állapotjelentés: mérföldkövek, számok, nyitott döntések |
| `docs/TESZTELES.md` | hogyan ellenőrizd, hogy a rendszer működik — automata és kézi próbák |
| `docs/blueprint.md` | a teljes műszaki terv |
| `docs/roadmap.md` | mérföldkövek és az első lépések |
| `docs/domain.md` | a domain-fogalmak szótára (magyar), és a magyar↔angol kódnév-táblázat |
| `docs/KOMPONENSEK.md` | újrahasznosítható komponensek, licencekkel |
| `docs/ALTALANOSITAS.md` | mi javul elvileg, és mi marad ismert korlát — a strukturális javítás és a ráigazítás különbsége |
| `docs/adr/` | döntési feljegyzések kiváltó feltétellel |
| `docs/PLATFORM_TANULSAGOK.md` | mit tanulhatunk a Cal.com és a Vapi platformoktól — a saját terveink szemüvegén át |
| `docs/CLAUDE_KISOKOS.md` | gyakorlati jegyzet a Claude Code használatáról ebben a projektben |

## Előfeltételek

- **Python 3.11+** — a `python` parancsnak elérhetőnek kell lennie
- **git**
- opcionális: `pip install ruff pytest`

Nem kell hozzá: Node.js, make, bash, jq, WSL, Docker.
A projekt natívan fut Windowson, macOS-en és Linuxon.

## Indulás

```
python feladat.py seed          # demóadat: 3 bolt, Törpilla 3 pultja
python feladat.py teszt         # tesztkészlet
python -m ui.vasarlo            # vásárlói felület (koppintós + szöveges út)
python feladat.py vegigjatszas  # ugyanaz fej nélkül, végigjátszva
python feladat.py vegigjatszas --mod beszelheto   # …felolvasásra szánt kimenettel
```

A szöveges fülön **kimeneti mód-kapcsoló** van (M6, hang-előkészítés): a
`szöveges` a képernyőé, a `beszélhető` az, amit egy felolvasó kapna —
egész mondatok, kimondott számokkal („nyolc óra tizenöt"), fordulónként
legfeljebb két mondattal és egy kérdéssel. Hang még nincs; a mód épp
azért van, hogy hang nélkül is látni lehessen, mit HALLANA a vásárló.

A szöveges úthoz nem kötelező nyelvi modell: ha nincs beállítva
`APRAJAFALVA_LLM_MODELL`, vagy nem fut az Ollama, a felület csendben a
determinisztikus értelmezőre esik vissza. Hogy éppen melyik dolgozik, az
ablak tetején és a próba-naplóban is látszik — l. `docs/TESZTELES.md`,
"Beszélgetés-próba".

## Fejlesztői környezet

A repó Claude Code-hoz készült. A `.claude/` alatt:

- **skillek** — domain-tudás igény szerint betöltve
- **agentek** — `sema-orzo`, `konkurencia-teszto`, `eval-futtato`
- **hookok** — `hooks/hookok.py`, tiszta Python

A hookok kikényszerítik: modulhatár (a `core/` nem importál az
`assistant/`-ből), SQL csak a `core/repo/`-ban, migrációk hordozhatósága,
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

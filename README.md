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
| `docs/PROBA_JEGYZET.md` | öt perces használati sorrend: a két kimeneti mód, mit írj be, hogyan olvasd a naplót |
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
python feladat.py golden --halmaz beszedhelyzetek  # a harmadik golden halmaz
python feladat.py naplo --archival                 # a próba-napló lezárása, új naplóval
python -m tools.ablak_meres                        # az előzmény-ablak hosszmérése
python -m tools.vram_meres --modell qwen3.5:9b     # belefér-e a modell a VRAM-ba
python feladat.py hangproba                        # felolvasás: megvan-e a Piper és a hang
python feladat.py hangproba --meres                # mennyi a csend a mondat előtt
```

A felület indításkor **előmelegíti a modellt** (háttérszálon, egy
egytokenes hívással): az első éles próbában az első forduló 13,93 s
volt, a többi 3,5 s — a különbség a betöltés. A mód-sorban látszik,
mikor lett kész.

**Hangkimenet** (ADR-029): a beszélhető mód 2026-09-01 óta meg is
szólal, ha van Piper és magyar hangmodell — `python feladat.py
hangproba` megmondja, van-e, és ha nincs, mit kell telepíteni. Addig a
mód a képernyőn olvasható marad, és a felület ezt ki is írja: a csend és
a „nincs telepítve" korábban ugyanúgy nézett ki.

A hangmodell **betöltve marad, és indításkor melegszik** (ADR-033):
enélkül minden megszólalás új folyamatot indított és újratöltötte a
60 MB-os hangot — mondatonként 2,07 s csend a mondat hosszától
függetlenül. Betöltve tartva 0,2 s; `hangproba --meres` méri a saját
gépen. Az új megszólalás elhallgattatja a régit, tehát két forduló
hangja nem csúszik egymásra.

**Minden képernyőre kerülő és minden felolvasott időpont HELYI idő**
(ADR-033). A tárolás UTC marad (4. invariáns), a váltás egyetlen
ponton történik (`assistant/valasz/helyi_ido.py`), a szervezet
időzónája szerint. 2026-09-20 előtt a felület a nyers UTC-t mutatta,
`(UTC)` felirattal — a 8 órakor nyitó bolt időpontjai 7 óraként.

A szöveges fülön **kimeneti mód-kapcsoló** van (M6, hang-előkészítés): a
`szöveges` a képernyőé, a `beszélhető` az, amit egy felolvasó kapna —
egész mondatok, kimondott számokkal („nyolc óra tizenöt"), fordulónként
legfeljebb két mondattal és egy kérdéssel. Hang még nincs; a mód épp
azért van, hogy hang nélkül is látni lehessen, mit HALLANA a vásárló.

A szöveges úthoz nem kötelező nyelvi modell: ha nincs beállítva
`APRAJAFALVA_LLM_MODELL`, vagy nem fut az Ollama, a felület a
determinisztikus értelmezőre esik vissza. **Csendben viszont már nem**:
indításkor egy modális ablak megmondja, mi hiányzik és mit kell beírni,
és két gombot ad — „Folytatom tartalékággal" vagy „Kilépek". A napló
fordulónként rögzíti, volt-e konfigurált modell és melyik prompt-verzió
futott; a beszélgetés-riport fejlécében piros sáv jelzi, ha egyetlen
modellhívás sem történt. Részletek: `docs/TESZTELES.md`,
"Beszélgetés-próba".

Környezeti kapcsolók (mind a MÉRÉSÉRT vannak, nem üzemmódként):

| Változó | Mit állít | Alap |
|---|---|---|
| `APRAJAFALVA_LLM_MODELL` | Ollama modellnév | nincs (tartalék ág) |
| `APRAJAFALVA_ABLAK_FORDULO` | hány forduló megy át szó szerint (`0` = nincs ablak, ADR-025) | 4 |
| `APRAJAFALVA_PROMPT_VERZIO` | `v1` / `v2` rendszerprompt (ADR-026) | `v1` |
| `APRAJAFALVA_ONKONZISZTENCIA` | három futás, szavazás (ADR-021) | ki |
| `APRAJAFALVA_INDITO_ELLENORZES` | `ki` = nincs modális indítási ellenőrzés | be |
| `APRAJAFALVA_NUM_CTX` | modell-kontextusméret (ADR-027) | 8192 |
| `APRAJAFALVA_ALLAPOT_SOR` | állapotsor a promptban (ADR-028) | be |
| `APRAJAFALVA_PIPER` / `APRAJAFALVA_PIPER_HANG` | Piper és a magyar hang útvonala (ADR-029) | automatikus keresés |

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

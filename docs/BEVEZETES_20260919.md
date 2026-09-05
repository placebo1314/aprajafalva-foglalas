# A bevezetési rés — az első IDEGEN próba és ami utána maradt

**Dátum:** 2026-09-19 · **Modell:** `qwen3.5:9b`, `num_ctx=8192`, v1
prompt, 4 fordulós ablak · **ADR:** [032](adr/032-bevezetes-koszones-katalogus-es-a-kiut-kapuja.md)

## A próba

Az első próbát olyan ember végezte, aki **nem ismerte a rendszert**.
Négy forduló alatt jutott el a köszönéstől odáig, hogy menjen be a
boltba élőben — és közben a rendszer **egyetlen keresést sem futtatott**.

| | a vásárló | ami TÖRTÉNT | ami most történik |
|---|---|---|---|
| 1. | „helló." | „Ehhez még kellene tudnom: melyik boltba szeretnél menni." | köszönés + a három bolt, leírással |
| 2. | „milyenek vannak?" | „Úgy látom, így nem jutunk előre…" (kiút) | katalógus a törzsadatból |
| 3. | „másik napszakot." | „ne kínlódj vele tovább… menj be a boltba" | visszakérdezés a boltra |
| 4. | „de én mindenképp itt akarom." | *(ugyanaz még egyszer)* | visszakérdezés, bolt-gombokkal |

**A négy hiba egyetlen feltevésből következett**: hogy a vásárló ismeri
a boltokat. Aki megnevezte a boltot, annak minden rétegünk jól működött
— ezért nem is mutatta a hibát semmilyen mérés: **a golden set minden
esete olyan emberé volt, aki már tudta, mit akar.**

## Mi változott

| # | változás | hol |
|---|---|---|
| 1 | `KOSZONES` kategória a kapuőrben | `assistant/kapuor/` |
| 2 | `kinalat` eszköz — a boltok és szolgáltatásaik a törzsadatból | `assistant/tools/kinalat.py` |
| 3 | a zárt kérdés LEÍRÁST mutat („Szundi — altató"), nem slugot | `ui/vasarlo.py`, `assistant/valasz/` |
| 4 | a kiút csak KERESÉS után szólal meg | `assistant/orchestrator.py` |
| 5 | keresés nélkül a gombok: a három bolt + „Mit lehet itt?" | `ui/vasarlo.py` |
| 6 | `elso_talalkozas` golden réteg, 8 eset | `tests/golden/esetek/` |

A bolt- és szolgáltatásnevek **ragozva** kerülnek a mondatba
(`assistant/valasz/ragozas.py`): „a Szundiba altatóért, az Ügyifogyiba
petárdáért, a Törpillába boldogságért". Ez közelítés, nem morfológiai
elemző — a korlátait az ADR „Amit feladunk" szakasza és a
`tests/egyseg/test_ragozas.py` rögzíti.

## Amit a fej nélküli végigjátszás fogott meg — a javítás után

A hat változtatás átment a golden seten, a VÉGIGJÁTSZÁS mégis két
hibát mutatott. Mindkettő olyan, amit a golden set nem is láthat: nem
az ÉRTELMEZÉSRŐL szólnak, hanem arról, mit lát a képernyőn a vásárló.

**1. A katalógus megismételte önmagát.** Az „ismétlés → kiút"
beszélgetés második és harmadik fordulójára szó szerint ugyanaz a
felsorolás ment ki. Javítás: a bemutatkozás **legfeljebb egyszer** áll a
kiút helyébe (`Frusztracio.bemutatkozhat`).

**2. A keresés nélküli kiút mondata olyat ígért, amit nem kínált.** A
gombok — helyesen — üresek voltak, a mondat viszont felsorolta a három
dimenziót („másik napot, másik napszakot…"). Javítás: külön sablon
(`bevezetes_bolt`) és bolt-gombok.

A létra így négy fokú, és mind a négy fok MÁS:

```
1. visszakérdezés  →  zárt bolt-kérdés, gombok + „Mit lehet itt?"
2. katalógus       →  mi van itt egyáltalán
3. kiút            →  „Kezdjük a legelején: melyik boltba szeretnél menni?"
4. emberhez        →  „a boltban élőben is fel tudnak venni időpontot"
```

## A mérés

### Az új réteg

```
elso_talalkozas      100.0%  (n=8)  küszöb 90%  [TARTJA]
```

A négy próbaforduló SZÓ SZERINT benne van, a **helyes** válasszal — nem
azzal, ami történt. A 3. és 4. eset több elfogadható viselkedést mér
(visszakérdezés vagy katalógus), mert ott nincs egyetlen helyes válasz,
csak ártó és nem ártó — tiltott viszont a kitalált bolt és a kitalált
dátum.

Két ellenpróba őrzi a kategóriákat: a „Jó napot! Szeretnék időpontot a
Szundiba holnapra" **nem** köszönés (a kérés viszi a fordulót), a „Mit
lehet kapni a Törpillánál?" pedig **nem** katalógus (a vásárló
megnevezte a boltot → `bolt_info`).

### Beszédhelyzetek — 39 eset

| | eredmény |
|---|---|
| összesített | **94,9%** (2 bukás) |
| `elso_talalkozas` | 100% (n=8) |
| `koszones` / `kinalat` / `kiut_utan` | 100% / 100% / 100% |

A két bukás RÉGI és ismert (`meggondolas-02`, `kozbevetes-02`), nem
ehhez a körhöz tartozik.

### Regresszió a nyelvi halmazon — 85 eset, két futás

```
1. futás: 84.1%   2. futás: 84.1%   tartomány: 0.0 százalékpont
Előző futás: 84.1%  →  most: 84.1%  (+0.0 pont)
ÍTÉLET: a különbség a zajküszöbön BELÜL van — ez SZÓRÁS, nem hatás.
```

**Nem javulást állítunk, hanem azt, hogy nem rontottunk.** A hat
változtatás a kapuőrbe és a kiút kapujába nyúlt — mindkettő a nyelvi
halmaz minden esetének útjában áll, tehát a regresszió itt valódi
kockázat volt.

### A determinisztikus alapvonal

A `koszones` és a `kinalat` a **kapuőr** döntése, tehát modellhívás
nélkül is megy — a bevezetés nem függhet attól, fut-e az Ollama. A
csupasz szabályalapú értelmezőn az `elso_talalkozas` 50% (a többfordulós
és a `bolt_info`-s esetek buknak), a kaszkádon a köszönés és a katalógus
modell nélkül is helyes.

## Amit ez a kör NEM old meg

- **A ragozás közelítés marad.** A mai három boltnévre helyes; egy
  vegyes hangrendű új névnél („Csilingelő") már nem lenne az. Kiváltó
  feltétel az ADR-ben.
- **A katalógus egy fordulóval hosszabb út.** Aki tényleg elakadt, de
  még nem keresett, mostantól előbb kap egy felsorolást. Ez tudatos ár.
- **Az `elengedes` réteg 53%** — továbbra is a leggyengébb, és ehhez a
  körhöz semmi köze (l. `docs/ALTALANOSITAS.md` 2.9).

## Reprodukció

```
python feladat.py golden --ertelmezo forditott --halmaz beszedhelyzetek
python feladat.py golden --ertelmezo forditott --ismetles 2 --elozo <elozo>.json
python tools/vegigjatszas.py        # „első találkozás (idegen próba)" beszélgetés
python -m pytest tests/egyseg/test_kinalat.py tests/egyseg/test_ragozas.py
```

Nyers kimenetek: `spike/meres_20260919/`.

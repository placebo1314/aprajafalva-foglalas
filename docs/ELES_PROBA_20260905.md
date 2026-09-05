# Az első éles próba — mit talált, és mi lett belőle

**Dátum:** 2026-09-05 · **Modell:** `qwen3.5:9b` · **9 forduló, kézzel**
· Napló: `naplo/probak.jsonl`

Az első valódi, kézi próba kilenc fordulója **három hibát** talált. Mind
a három ugyanabból a hiányból jött: **a rendszernek nem volt neve arra,
amit a vásárló csinált.**

## A három hiba

| forduló | a vásárló | ami történt | ami kellett volna |
|---|---|---|---|
| 7. | „csak a választ beszéled?" | KERESÉS indult, és a lezárt foglalás állapota (`KESZ`) `AJANLAT_VAR`-ra romlott | rövid bemutatkozás, az állapot marad |
| 8. | „nekem mind jó. válasz te." | ÚJRA felajánlotta ugyanazt a három időpontot | válasszon a rendszer, és kérjen megerősítést |
| 9. | „a hét tizenötös" | a MÁSODIKAT választotta (07:00–**07:15**) | a HARMADIKAT (**07:15**–07:30) |

Plusz egy negyedik, ami nem hiba, csak fájt: **az első forduló 13,93 s
volt**, a többi 3,5 s körül — a modell betöltése.

## Ami ebből lett

### 1. A kapuőr negyedik kategóriája (ADR-030)

`META_KERDES` — a rendszerről szóló kérdés. Nem foglalási szándék, nem
tényválasz, és **nem is hatókörön kívüli**: erre VAN válaszunk. A modell
meg sem szólal (a kapuőr a modell előtt dönt), a válasz sablonból jön, és
a beszélgetés állapota nem mozdul.

A minta SZŰK: a „mit tudsz mondani a nyitvatartásról?" továbbra is
tényválasz, a „Szeretnék időpontot" továbbra is foglalás — ezt tíz
pozitív és öt ellenpróba őrzi (`test_kapuor.py`).

### 2. A döntés átadása (ADR-030)

`dontsd_el_te` — új irányítási érték az értelmező szerződésében. A
rendszer a **pontozó első jelöltjét** veszi (a jelöltek már abban a
sorrendben állnak, ADR-006), és megerősítést kér, **kimondott
időponttal**: a jelölt-gombok ilyenkor eltűnnek, tehát a mondatnak meg
kell mondania, miről van szó.

> A legjobb, amit találtam: 2026-12-21 07:15 (UTC). Lefoglaljam?

**A felismerés a modellé, a garancia a kapuké**: csak `AJANLAT_VAR`
állapotban és csak tényleges jelöltek mellett hajtjuk végre.

**Egy mondat kellett hozzá a promptban, és ezt mérni kellett.** Az első
változat (csak az eszközlistába felvéve) három megfogalmazásból egyet
ismert fel. A MINDEGY-blokk elnyelte: a „nekem mind jó" pontosan úgy
néz ki, mint egy mező-elengedés. A megkülönböztetés kimondása után:

| mondat | előtte | utána |
|---|---|---|
| „nekem mind jó. válassz te." | `szabad_idopontok` ✘ | `dontsd_el_te` ✔ |
| „amelyik neked jó" | `dontsd_el_te` ✔ | `dontsd_el_te` ✔ |
| „mindegy, foglalj egyet" | `szabad_idopontok` ✘ | `szabad_idopontok` ✘ |
| **ellenpróba:** „Bármelyik petárda jó, csak csütörtökön legyen" | `MINDEGY` ✔ | `MINDEGY` ✔ |

Az ellenpróba a fontos: a mező-elengedés MARADT mező-elengedés. A
harmadik megfogalmazás („mindegy, foglalj egyet") továbbra sem megy —
korlátként marad, nem toldozzuk kulcsszóval.

### 3. Modell-előmelegítés (ADR-030)

Indításkor, háttérszálon, egy egytokenes hívás tölti be a modellt; a
felület a mód-sorban kiírja, mikor lett kész („modell: kész (10,6 s)").
Mérve: az előmelegítés maga 10,65 s, utána a hívás 2,13 s.

Ugyanez a golden futtatóban és a végigjátszásban is fut — enélkül az
ELSŐ eset a betöltés idejét viseli, és a válaszidő-eloszlás olyan számot
mutat, ami éles beszélgetés közepén sosem fordul elő.

### 4. A 9. forduló GOLDEN ESET lett

A napló 9. fordulója (`elesbol-01-a-het-tizenotos`) bekerült a
beszédhelyzetek halmazba — és **a várt választ ember írta be, nem a
napló**: a rendszer akkor a másodikat választotta, a helyes válasz a
harmadik.

Ehhez a golden futtató is bővült: egy eset megadhatja, MIT ajánlottunk
fel (`felajanlott`), és a futtató ugyanabban az alakban teszi be a
beszélgetésbe, ahogy a felület — plusz az állapotsort is (ADR-028).
**Enélkül a jelöltre hivatkozó mondatok mérhetetlenek voltak**; ez a
korlát az ADR-028-ban még nyitottként szerepelt.

## A mérés — a három eset mostantól MEGY

`qwen3.5:9b`, beszédhelyzetek halmaz (31 eset):

| eset | mit mér | eredmény |
|---|---|---|
| `elesbol-01-a-het-tizenotos` | kimondott időpontra hivatkozás | **OK** (sorszám 3) |
| `elesbol-02-meta-kerdes` | „csak a választ beszéled?" | **OK** (`meta_valasz`) |
| `elesbol-03-valassz-te` | a döntés átadása | **OK** (`dontsd_el_te`) |
| **a halmaz egésze** | | **90,3%** (előtte 85,7%, 28 eseten) |

## Amit a nyelvi halmaz mond — és amit nem

| futás | nyelvi (55 eset) |
|---|---|
| a kör ELŐTT | 86,4% |
| a kör UTÁN, 1. futás | 82,7% |
| a kör UTÁN, 2. futás | 83,6% |

**Ezt nem lehet a változtatásra fogni, és nem is lehet felmenteni.** A
két futás közötti különbség (82,7 vs. 83,6) egyetlen eset, és a bukó
esetek listája is mozog: `koznyelvi-05`, `elengedes-03`,
`mintan_tul-09` váltakozva esik ki — ugyanaz az ingadozás, amit a
2026-09-01-i mérés is mutatott `temperature: 0` mellett.

Ami NEM mozog: `elengedes-01`, `elengedes-02`, `elengedes-05`,
`valtozatossag-04`, `mindegy-03`, `mindegy-07`, `mindegy-08` — ezek
minden futáson buknak, és ismert korlátok
(`docs/ALTALANOSITAS.md` 2.9b–2.9d).

**A becsületes összegzés:** a beszédhelyzetek halmazon mérhető javulás
(85,7% → 90,3%), a nyelvi halmazon a mozgás a szóráson belül van. Egy
harmadik-negyedik futás sem döntené el; ahhoz a halmazt kellene
növelni, nem a futásokat.

## Reprodukció

```
python feladat.py naplo --golden 9          # a 9. forduló mint golden-váz
python feladat.py golden --ertelmezo forditott --halmaz beszedhelyzetek
python -m pytest tests/egyseg/test_kapuor.py tests/egyseg/test_orchestrator.py
```

Nyers kimenetek: `spike/meres_20260905/vegso_*.{json,log}`,
`q9_besz_elesbol.{json,log}`.

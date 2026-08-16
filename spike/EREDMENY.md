# M-1 Spike — Eredmények

Ág: `spike/m-1`. Ez a változat kizárólag a `spike/*.json` fájlokból épül —
nincs benne újrafuttatás, és nincs benne olyan szám, aminek nincs
JSON-artifactja. Forrásfájlok:

- `eredmeny_qwen35_4b_nogondolkodas.json` (qwen3.5:4b, gondolkodás **ki**)
- `eredmeny_qwen35_9b.json` (qwen3.5:9b, gondolkodás **be**)
- `eredmeny_qwen35_9b_nogondolkodas.json` (qwen3.5:9b, gondolkodás **ki**)
- `latencia_qwen35_4b.json`, `latencia_qwen35_9b.json` (1 és 3 párhuzamos
  kérés; a szkript alapértelmezése `gondolkodas=True`, a JSON ezt nem
  tárolja explicit mezőként, de a mért idők nagyságrendje ezzel
  konzisztens)
- `sqlite_eredmeny.json` (3 és 10 egyidejű session)

**qwen3.5:4b, gondolkodással** (`be`) golden-set futáshoz nincs JSON fájl
a `spike/` alatt — nincs mit beolvasni, ezért ez a konfiguráció alább
mindenhol **nem mértük**-ként szerepel. A Racka-4B (ADR-013 ellenőrző
jelöltje) nem érhető el lokálisan, szintén nem mérhető.

## 1. Golden set — modellenként és gondolkodás-módonként, rétegekre bontva

| Modell | Gondolkodás | Összesített | Legrosszabb réteg | Átlagos válaszidő (szekvenciális) | Átlagos tokenszám/eset | Hívási hiba |
|---|---|---|---|---|---|---|
| qwen3.5:4b | be | — | — | — | — | **nem mértük** (nincs JSON) |
| qwen3.5:4b | ki | **18,2%** | egyszerűsített (0,0%) | 4,42 s | 59,9 | 0/22 |
| qwen3.5:9b | be | **54,5%** | szleng (16,7%) | 22,64 s | 45,9 | 0/22 |
| qwen3.5:9b | ki | **13,6%** | egyszerűsített (0,0%) | 5,19 s | 64,5 | 0/22 |

Réteg-bontás (a három elérhető JSON-ból, `retegek.kuszob` mező szerinti
küszöbökkel):

| Réteg | Küszöb | qwen3.5:4b (ki) | qwen3.5:9b (be) | qwen3.5:9b (ki) |
|---|---|---|---|---|
| köznyelvi | 98% | 20,0% NEM TARTJA | 40,0% NEM TARTJA | 0,0% NEM TARTJA |
| tájszólás | 90% | 25,0% NEM TARTJA | 75,0% NEM TARTJA | 25,0% NEM TARTJA |
| töredékes | 90% | 0,0% NEM TARTJA | 62,5% NEM TARTJA | 0,0% NEM TARTJA |
| szleng | 92% | 0,0% NEM TARTJA | 16,7% NEM TARTJA | 0,0% NEM TARTJA |
| egyszerűsített | 90% | 0,0% NEM TARTJA | 50,0% NEM TARTJA | 0,0% NEM TARTJA |
| kapuőr | (nincs küszöb) | 100,0% | 100,0% | 100,0% |

A mért három konfiguráció közül **egyik sem tartja** egyetlen küszöbölt
réteget sem. A kapuőr réteg (nem valós foglalási kérés felismerése) mindhárom
konfiguráción 100% — ez az egyetlen réteg, ami rendben van.

## 2. Válaszidő párhuzamosságban (1 és 3 szál, token/mondat)

Csak 1 és 3 szálon mértünk — az 5 szálas mérés **nem mértük** (nincs JSON,
a `latencia.py` docstringje szerint 8 GB VRAM mellett explicit kihagyva).

| Modell | Szál | p50 | p95 | Átlag | Hívási hiba | Token/mondat (átlag) | VRAM előtte→alatta |
|---|---|---|---|---|---|---|---|
| qwen3.5:4b | 1 | 71,73 s | 118,10 s | 71,39 s | 4/22 | 1441,4 | 6509→4055 MiB |
| qwen3.5:4b | 3 | 177,94 s | 182,04 s | 158,78 s | 10/22 | 635,9 | 4055→4055 MiB |
| qwen3.5:9b | 1 | 16,03 s | 95,70 s | 28,21 s | 0/22 | 56,9 | 4055→6507 MiB |
| qwen3.5:9b | 3 | 50,29 s | 88,12 s | 53,57 s | 0/22 | 54,1 | 6507→6509 MiB |

Blueprint §12 cél: szöveges asszisztens-válasz p95 < 2,5 s. Minden mért
pont ennek sokszorosa (6–73×), már 1 szálon is. A 4B hibaaránya 3 szálon a
duplájára nőtt (4/22 → 10/22), ami VRAM-kontenció jele, nem csak lassulás.

## 3. SQLite írási latencia session-számonként

`mag/repo/foglalas_repo.py`-val mérve, minden szál a saját slotjára ír.

| Session | n | p50 | p95 | Max | Hiba | ADR-004 kiváltó feltétel (p95 > 50 ms) |
|---|---|---|---|---|---|---|
| 3 | 3 | 18,66 ms | 35,45 ms | 35,45 ms | 0 | nem teljesül |
| 10 | 10 | 71,89 ms | 207,23 ms | 207,23 ms | 0 | **IGEN — teljesül** |

50 egyidejű session-re **nem mértük** ezúttal (nincs hozzá JSON a
`spike/` alatt; a `sqlite_iras.py` docstringje szerint ez amúgy sem v1 cél).

## 4. hun-date-parser pontossága

**Nem mértük** — legalábbis nincs hozzá JSON-artifact, amiből ez a
szakasz felépülhetne. A `spike/hun_date_meres.py` a `text2datetime`
kimenetét csak konzolra írja ki (`print`), nem perzisztálja `--json`
kapcsolóval, és a `spike/` alatt nincs ehhez tartozó eredményfájl. Mivel a
feladat kifejezetten tiltja az újrafuttatást, ezt a mérést itt nem tudom
JSON-ból rekonstruálni, és nem is becsülöm — a bukott esetek felsorolása
ezért is elmarad. (Ne keverd össze a 6. szakasszal: az ott szereplő
"dátum-hiba" osztályozás nem a hun-date-parser könyvtár mérése, hanem a
golden-futtatások mentett `indoklas` szövegeinek utólagos elemzése.)

## 5. A token/mondat különbség jelentése a modellválasztásra

A 2. szakasz `latencia_*.json`-jai szerint a **kisebb (4B) modell
~25×-ösen több tokent termel mondatonként, mint a nagyobb (9B)**: 1441,4
vs. 56,9 token/mondat 1 szálon, 635,9 vs. 54,1 token/mondat 3 szálon. Ez
ellentétes az intuícióval, és ez a mérés a `gondolkodas=True`
(alapértelmezett) beállítással futott.

Ez a különbség nem a szokásos "kisebb modell = kevesebb token"
tokenizer-hatékonyságról szól. A golden-set futásból (1. szakasz) tudjuk,
hogy a 4B modell gondolkodás **nélkül** is rosszabbul teljesít, mint a 9B
(18,2% vs. 54,5%); a latencia-mérésben pedig gondolkodással a 4B hibaaránya
is magasabb (4/22 → 10/22 3 szálon, a 9B-nél 0/22 mindkét szálszámon).
Együtt olvasva a két mérést: a 4B modellnél a gondolkodás bekapcsolása nem
csak lassabb válaszidőt, hanem magasabb hibaarányt is hoz, miközben a
gondolkodás nélküli pontossága is a 9B alatt marad.

**Következmény a modellválasztásra:** a 4B nyers paraméterszáma alapján
olcsóbbnak/gyorsabbnak tűnne, de a mért adatok szerint jelenleg egyik
konfigurációban sem éri meg — gondolkodással sokkal több tokent termel és
gyakrabban hibázik hívásban, gondolkodás nélkül pedig pontosságban marad
el a 9B mögött. A 9B jelenleg minden mért dimenzióban (pontosság,
token/mondat, hívási hibaarány) jobban áll, annak ellenére, hogy nagyobb
modell.

## 6. A dátumértelmezés kiemelésének becsült hatása

Módszer: a három elérhető golden-JSON-ban (qwen3.5:4b/ki, qwen3.5:9b/be,
qwen3.5:9b/ki) minden `pontszam < 1,0` esetet megnéztünk. Ahol az
`indoklas` az `"eszköz stimmel, paraméterek eltérnek: {A} != {B}"` mintát
követi, összevetettük az `A` (kapott) és `B` (elvárt) paraméter-szótárakat:

- **tisztán dátum-hiba**: kizárólag a `datum` / `datum_tol` / `datum_ig`
  mezők térnek el (érték vagy formátum), minden más mező egyezik vagy
  hiányzik a "más" oldalról is,
- **dátum + más hiba is**: a dátummezők mellett más paraméter is hiányzik
  vagy téves (pl. `szolgaltatas_id`, `napszak`, elgépelt `bolt_id`),
- **nem dátum jellegű**: rossz eszköz (`várt X, kapott Y`), elveszett
  visszakérdezés-állapot, kitalált dátum (`TILTOTT MINTA: kitalalt_datum`)
  vagy más, dátumtól független hiba.

Feltételezés: egy determinisztikus dátumparser a "tisztán dátum-hiba"
eseteket helyesen oldaná meg, minden mást változatlanul hagyva — a "dátum
+ más hiba is" eseteket **nem** javítaná, mert azokban a nem-dátum mező is
hibás marad.

| Konfiguráció | Bukott esetek | Tisztán dátum-hiba | Dátum + más hiba is | Nem dátum jellegű | Alap pontosság | Becsült pontosság dátumparserrel |
|---|---|---|---|---|---|---|
| qwen3.5:4b, gondolkodás nélkül | 18/22 | 2 | 3 | 13 | 18,2% | **27,3%** (+9,1 pp) |
| qwen3.5:9b, gondolkodással | 13/22 | 2 | 3 | 8 | 54,5% | **63,6%** (+9,1 pp) |
| qwen3.5:9b, gondolkodás nélkül | 19/22 | 2 | 5 | 12 | 13,6% | **22,7%** (+9,1 pp) |

qwen3.5:4b/gondolkodással **nem mértük** ebben a bontásban (nincs hozzá
JSON, lásd a bevezetőt).

**Értelmezés:** mindhárom mért konfiguráción **pontosan +9,1 százalékpont**
a becsült hatás (2 eset a 22-ből) — feltűnően egyenletes minta, ami arra
utal, hogy a golden set jelenlegi 22 esetes mérete mellett ez nagyjából
"2 eset ára", nem feltétlenül stabil arány. A dátumértelmezés kiemelése egy
determinisztikus parserbe (ahogy az M4 terve amúgy is előírja) valós, de
messze nem elég a 90%+ réteg-küszöbhöz. A bukott esetek nagyobbik része
**nem** dátumhiba, hanem rossz eszközválasztás vagy elveszett/hiányzó
visszakérdezés-állapot (8/13 a 9b/be-nél, 13/18 a 4b/ki-nél, 12/19 a
9b/ki-nél) — ezt a dátumparser önmagában nem oldja meg.

## Amit nem mértünk (JSON alapján)

- qwen3.5:4b, gondolkodással — golden set futás (nincs JSON a `spike/`
  alatt).
- 5 szálas válaszidő (nincs JSON).
- 50 egyidejű SQLite session (nincs JSON).
- hun-date-parser könyvtár közvetlen pontossága (a mérőszkript nem
  perzisztál JSON-t).
- Racka-4B (nincs lokálisan telepítve, nem futtatható).

Ez a fájl nem ADR — nem dönt, csak felsorolja, mit mutatnak a mentett
mérési artifactok. A tényleges döntés (SQLite/Postgres, modellválasztás,
roham-üzemmód) nyitott; ADR-t nem módosítottam.

# M-1 Spike — Eredmények

Mérve: 2026-08-16, ág: `spike/m-1`. Helyi Ollama, `qwen3.5:4b` és `qwen3.5:9b`
(mindkettő Apache-2.0). A Racka-4B (ADR-013 ellenőrző jelöltje) nem érhető el
lokálisan, nem mérhető.

Ez a fájl **nem ADR** — nem dönt, csak felsorolja, mit mértünk, melyik ADR
kiváltó feltétele teljesült, és mit javaslok. A tényleges döntés (SQLite
váltás, modellválasztás, roham-üzemmód) nyitott.

## 1. Teszt-készlet

`python feladat.py teszt` → **87 passed, 1 xfailed**. Tiszta.

## 2. Golden set — nyelvi pontosság (22 eset: 20 rétegzett + 2 kapuőr)

| Modell | Gondolkodás | Összesített | Leggyengébb réteg | Válaszidő (átlag, szekvenciális) | Hívási hibák |
|---|---|---|---|---|---|
| qwen3.5:4b | be | **40,9%** | szleng 16,7% | 66,89 s | 4/22 |
| qwen3.5:4b | ki | **18,2%** | egyszerűsített 0,0% | 4,42 s | 0/22 |
| qwen3.5:9b | be | **54,5%** | szleng 16,7% | 22,64 s | 0/22 |
| qwen3.5:9b | ki | **13,6%** | egyszerűsített 0,0% | 5,19 s | 0/22 |

Egyik cella sem tartja a blueprint §12 küszöbét (leggyengébb réteg > 90%).

**Megjegyzés a 4B/gondolkodással sorhoz:** ez a szám valós mérésből
származik (a futás konzol-kimenete rögzítve), de a hozzá tartozó JSON-fájl
felülíródott, mielőtt a `--nincs-gondolkodas` kapcsolót bevezettem — ezért
`spike/eredmeny_qwen35_4b.json` ma nem létezik, csak
`spike/eredmeny_qwen35_4b_nogondolkodas.json`,
`spike/eredmeny_qwen35_9b.json` és `spike/eredmeny_qwen35_9b_nogondolkodas.json`.
A hiányzó artifact miatt a 4B/be soron **nincs** tiszta dátum-hatás bontás
(lásd 7. szakasz).

Réteg-bontás (gondolkodással, a két elérhető teljes JSON-ból):

| Réteg | qwen3.5:4b (ki) | qwen3.5:9b (be) | qwen3.5:9b (ki) |
|---|---|---|---|
| köznyelvi | 20,0% | 40,0% | 0,0% |
| tájszólás | 25,0% | 75,0% | 25,0% |
| töredékes | 0,0% | 62,5% | 0,0% |
| szleng | 0,0% | 16,7% | 0,0% |
| egyszerűsített | 0,0% | 50,0% | 0,0% |
| kapuőr (nincs küszöb) | 100,0% | 100,0% | 100,0% |

(A 4B/be réteg-bontás a konzol-kimenetből: egyszerűsített 50,0%, köznyelvi
40,0%, szleng 16,7%, tájszólás 25,0%, töredékes 37,5%, kapuőr 100,0%.)

## 3. Tokenizer-hatékonyság — token/mondat

| Modell | Gondolkodással | Átlag token/mondat |
|---|---|---|
| qwen3.5:4b | be | **1441,4** |
| qwen3.5:9b | be | **56,9** |

**Ez ellentétes az intuícióval, és fontosabb, mint első ránézésre tűnik.**
A kisebb (4B) modell ~25×-ösen több tokent termel mondatonként, mint a
nagyobb (9B) — négy eset a 22-ből ~7680 tokenes, kontrollálatlan
gondolkodásba futott, és nem is adott érvényes JSON-t (ez a fenti "4/22
hívási hiba"). Ez nem a szokásos "kisebb modell = kevesebb token"
tokenizer-hatékonyság kérdése, hanem azt jelzi, hogy a 4B modell nálunk
instabil gondolkodási hosszal reagál a nehezebb magyar mondatokra, a 9B
nem. **Következmény a modellválasztásra:** a 4B nyers mérete alapján
olcsóbbnak/gyorsabbnak tűnne, de a mért viselkedés szerint jelenleg sem
nem gyorsabb, sem nem olcsóbb a 9B-nél — rosszabb pontosság mellett
drágább. Ha a 4B marad jelölt, ezt csak explicit `num_predict` korláttal
vagy a gondolkodás kikapcsolásával (ami viszont a pontosságot omlasztja
össze, lásd 2. szakasz) lehetne kordában tartani.

## 4. Válaszidő párhuzamosságban (1 és 3 szál, gondolkodással)

Csak 1 és 3 szálon mértünk — az 5 szálas mérést kihagytuk, mert 8 GB VRAM
mellett irreális.

| Modell | Szál | p50 | p95 | Hibák | VRAM előtte→alatta |
|---|---|---|---|---|---|
| qwen3.5:4b | 1 | 71,73 s | 118,10 s | 4/22 | 6509→4055 MiB |
| qwen3.5:4b | 3 | 177,94 s | 182,04 s | 10/22 | 4055→4055 MiB |
| qwen3.5:9b | 1 | 16,03 s | 95,70 s | 0/22 | 4055→6507 MiB |
| qwen3.5:9b | 3 | 50,29 s | 88,12 s | 0/22 | 6507→6509 MiB |

Blueprint §12 cél: asszisztens válasz (szöveg) p95 < 2,5 s. **Minden mért
pont ennek sokszorosa**, már 1 szálon is (6–38×). 4B-nél a hibaarány
3 szálon a duplájára nőtt (4/22 → 10/22) — ez VRAM-kontenció jele, nem
csak lassulás.

## 5. SQLite írási latencia (3 és 10 egyidejű session)

Valódi `mag/repo/foglalas_repo.py`-val mérve, minden szál a saját slotjára ír.

| Session | p50 | p95 | ADR-004 kiváltó feltétel (p95 > 50 ms) |
|---|---|---|---|
| 3 | 18,66 ms | 35,45 ms | nem |
| 10 | 71,89 ms | 207,23 ms | **IGEN** |

(Korábban, ezen a munkameneten belül, 50 session mellett is mértünk —
p95 = 4264,55 ms — de ez nem v1 cél, a fenti táblázat a mérvadó.)

## 6. hun-date-parser pontossága

11/22 golden-set eset tartalmaz dátumkifejezést. Ezekből **5/11 = 45,5%**
helyes (a blueprint §12 célja > 99%).

Bukott esetek: `koznyelvi-02` (nyitott intervallum, nincs explicit
dátumszó), `tajszolas-01` és `szleng-01` ("hónap" = holnap csapda),
`toredekes-04` és `egyszerusitett-04` (nincs explicit dátumszó, csak
"a héten" / kontextusból következő "ma"), `szleng-03` ("jövő csüt" rövidített
alak, jövő heti értelmezés).

## 7. A dátumértelmezés kiemelésének becsült hatása a pontosságra

Módszer: minden 1,0-nál gyengébben pontozott, "eszköz stimmel, paraméterek
eltérnek" esetnél szétválasztottuk, hogy a modell által adott és az elvárt
paraméterek között *kizárólag* a dátum-mezők (`datum`, `datum_tol`,
`datum_ig`) térnek-e el. Ha igen, feltételeztük, hogy egy tökéletes
determinisztikus dátumparser ezt a mezőt helyesen adta volna, minden mást
változatlanul hagyva a modell kimenetéből — és megnéztük, ez elég lett
volna-e az 1,0 ponthoz.

Ez csak arra a két konfigurációra készült el, ahol a teljes (nem csonkolt)
`indoklas` szöveg elérhető volt a mentett JSON-ból:

| Konfiguráció | Bukott esetek | Tisztán dátum-hiba | Dátum + más hiba is | Nem dátum jellegű | Becsült pontosság dátumparserrel |
|---|---|---|---|---|---|
| qwen3.5:9b, gondolkodással | 13/22 | 2 | 3 | 8 | 54,5% → **63,6%** (+9,1 pp) |
| qwen3.5:4b, gondolkodás nélkül | 18/22 | 2 | 3 | 13 | 18,2% → **27,3%** (+9,1 pp) |

A qwen3.5:4b/gondolkodással és a qwen3.5:9b/gondolkodás nélkül
konfigurációkra **nem mértük** ezt a bontást (a szükséges teljes indoklás-
szöveg nincs meg tisztán, lásd 2. szakasz megjegyzése) — nem pótoltuk
becsléssel.

**Értelmezés:** a dátumértelmezés kiemelése egy determinisztikus parserbe
(ahogy az M4 terve amúgy is előírja: "hun-date-parser + saját kiegészítés")
mindkét mért konfiguráción kb. **+9 százalékpontot** hozna — valós, de
messze nem elég a 90%+ réteg-küszöbhöz. A bukott esetek nagyobbik fele
(8/13, illetve 13/18) **nem** dátumhiba, hanem rossz eszközválasztás vagy
elveszett/hiányzó visszakérdezés — ezt a dátumparser önmagában nem oldja
meg.

## 8. ADR kiváltó feltételek — állapot

**ADR-004 (SQLite mint kezdeti adattár).** Kiváltó feltétel: p95 írási
latencia > 50 ms. **Teljesül** 10 egyidejű session mellett (207,23 ms), nem
teljesül 3-nál (35,45 ms). 10 egyidejű session egy falusi bolt forgalmánál
nem irreális szám egy foglalási nyitás pillanatában.

**ADR-010 (nincs roham-üzemmód).** Kiváltó feltétel: 5 egyidejű
beszélgetésnél a válaszidő SLO (p95 < 2,5 s szöveg) nem tartható semmilyen
belső paraméter-csökkentéssel. **5 szálon nem mértünk** (explicit kihagyva,
8 GB VRAM mellett irreális teszt lett volna) — a szigorú feltétel tehát
nincs közvetlenül bizonyítva. Viszont már **1 és 3 szálon** is minden mért
p95 érték a cél 6–73×-osa (16–182 s a 2,5 s ellenében), és 4B-nél a hibaarány
3 szálon megduplázódott. Ez erős közvetett jel, hogy a feltétel 5 szálon is
teljesülne — de ezt jelzem, nem állítom bizonyítottnak.

Egyik ADR-t sem módosítottam. A döntés (Postgres-váltás, modellváltás,
roham-üzemmód újragondolása) nyitott.

## 9. pyproject.toml

`pip install -e ".[dev]"` a flat-layout auto-discovery hibája miatt
korábban nem futott le ("Multiple top-level packages discovered"). Fix:
`[tool.setuptools.packages.find]` explicit `include` listával
(`mag*, seed*, asszisztens*, adatvedelem*, felulet*`). Ellenőrizve: telepítés
sikeres, `python feladat.py teszt` és `lint` változatlanul zöld utána is.

## 10. Amit nem mértünk

- 5 szálas válaszidő (explicit kihagyva, 8 GB VRAM).
- Racka-4B (nincs lokálisan telepítve).
- Dátum-hatás bontás a 4B/gondolkodással és 9B/gondolkodás nélkül
  konfigurációkon (a teljes indoklás-szöveg nem elérhető ezekhez tisztán).
- `spike/eredmeny_qwen35_4b.json` (gondolkodással) mint artifact-fájl —
  a szám megvan (2. szakasz), a fájl nem.

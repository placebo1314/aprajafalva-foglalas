# M-1 Spike — Eredmények

**Frissítés (lezárva):** a `spike/golden_futtato.py` javítva lett (séma
enum-kényszer `eszkoz`/`bolt_id`/`szolgaltatas_id`/`napszak`-ra, a
dátumformátum-ellentmondás feloldva a rendszerpromptban, nyers kimenet
mentése minden esethez, `reszleges_elfogadas` a `koznyelvi-02` és
`egyszerusitett-04` esetekre), és a javított mérőeszközzel **le is
futott** a qwen3.5:9b/gondolkodással mérés, kétszer. Az új szám **a
qwen3.5:9b/be sorban 47,7%, ez az aktuális alapszám** — a korábbi 54,5%
**elavult**, ARCHÍV referenciaként megmaradt a táblázatban, de a
döntéshez a 47,7%-ot kell nézni. Lásd az "1a. A javítás hatása" szakaszt
a teljes indoklásért — a csökkenés oka **nem** egyértelmű, és **nem**
írható le egyszerűen "szigorúbb mérésként"; lásd ott.

Ág: `spike/m-1`. Ez a változat kizárólag a `spike/*.json` fájlokból épül —
nincs benne újrafuttatás ezen a körön (a két qwen3.5:9b/be futás egy
korábbi körben történt, a fájlok már megvannak), és nincs benne olyan
szám, aminek nincs JSON-artifactja. Forrásfájlok:

- `eredmeny_qwen35_4b_nogondolkodas.json` (qwen3.5:4b, gondolkodás **ki**)
- `eredmeny_qwen35_9b.json` (qwen3.5:9b, gondolkodás **be**, **ELAVULT** —
  a javítás előtti mérőeszközzel készült)
- `eredmeny_qwen35_9b_javitott.json` (qwen3.5:9b, gondolkodás **be**, a
  javított mérőeszközzel — **ez az aktuális alapszám**)
- `eredmeny_qwen35_9b_javitott_v1_hibas.json` (ugyanaz, DE egy hibás
  séma-verzióval mérve — lásd "1a" szakasz, ez egy dokumentált incidens,
  nem használható eredményként)
- `eredmeny_qwen35_9b_nogondolkodas.json` (qwen3.5:9b, gondolkodás **ki**,
  a javítás előtti mérőeszközzel — erre nem futott új mérés)
- `latencia_qwen35_4b.json`, `latencia_qwen35_9b.json` (1 és 3 párhuzamos
  kérés; a szkript alapértelmezése `gondolkodas=True`, a JSON ezt nem
  tárolja explicit mezőként, de a mért idők nagyságrendje ezzel
  konzisztens)
- `sqlite_eredmeny.json` (3 és 10 egyidejű session)

**qwen3.5:4b, gondolkodással** (`be`) golden-set futáshoz nincs JSON fájl
a `spike/` alatt — nincs mit beolvasni, ezért ez a konfiguráció alább
mindenhol **nem mértük**-ként szerepel.

**Racka-4B (ADR-013 ellenőrző jelöltje):** nem érhető el lokálisan.
`ollama pull racka-4b` megpróbálva — `Error: pull model manifest: file
does not exist`, mert nincs a publikus Ollama-registryben (a modell
CC-BY-NC-SA-4.0, kapuzott — ez elvárt). A telepítéshez kézi GGUF-letöltés
kell (Hugging Face-ről, hitelesített hozzáféréssel) és utána helyi
`ollama create racka-4b -f Modelfile` egy a letöltött GGUF-ra mutató
Modelfile-lal — ez a spike keretein kívül eső, külön lépés, itt nem
végeztük el.

## 1. Golden set — modellenként és gondolkodás-módonként, rétegekre bontva

| Modell | Gondolkodás | Összesített | Legrosszabb réteg | Átlagos válaszidő (szekvenciális) | Átlagos tokenszám/eset | Hívási hiba |
|---|---|---|---|---|---|---|
| qwen3.5:4b | be | — | — | — | — | **nem mértük** (nincs JSON) |
| qwen3.5:4b | ki | **18,2%** | egyszerűsített (0,0%) | 4,42 s | 59,9 | 0/22 |
| qwen3.5:9b | be **(ELAVULT — javítás előtti mérőeszköz)** | ~~54,5%~~ | szleng (16,7%) | 22,64 s | 45,9 | 0/22 |
| **qwen3.5:9b** | **be (AKTUÁLIS — javított mérőeszköz)** | **47,7%** | szleng (16,7%) | 34,18 s | 54,7 | 0/22 |
| qwen3.5:9b | ki (javítás előtti mérőeszköz, nem mértük újra) | **13,6%** | egyszerűsített (0,0%) | 5,19 s | 64,5 | 0/22 |

A qwen3.5:9b/ki sorra **nem futott új mérés** ezen a körön (a feladat csak
a qwen3.5:9b/be-re és a Rackára kért mérést) — a 13,6% változatlanul a
javítás előtti mérőeszközzel készült, jelöletlenül elavult lehet, de ezt
nem ellenőriztük.

Réteg-bontás (`retegek.kuszob` mező szerinti küszöbökkel; a qwen3.5:9b/be
oszlop az AKTUÁLIS, javított mérésből):

| Réteg | Küszöb | qwen3.5:4b (ki) | qwen3.5:9b (be, aktuális) | qwen3.5:9b (ki, elavult mérőeszköz) |
|---|---|---|---|---|
| köznyelvi | 98% | 20,0% NEM TARTJA | 20,0% NEM TARTJA | 0,0% NEM TARTJA |
| tájszólás | 90% | 25,0% NEM TARTJA | 75,0% NEM TARTJA | 25,0% NEM TARTJA |
| töredékes | 90% | 0,0% NEM TARTJA | 50,0% NEM TARTJA | 0,0% NEM TARTJA |
| szleng | 92% | 0,0% NEM TARTJA | 16,7% NEM TARTJA | 0,0% NEM TARTJA |
| egyszerűsített | 90% | 0,0% NEM TARTJA | 50,0% NEM TARTJA | 0,0% NEM TARTJA |
| kapuőr | (nincs küszöb) | 100,0% | 100,0% | 100,0% |

A mért konfigurációk közül **egyik sem tartja** egyetlen küszöbölt
réteget sem. A kapuőr réteg (nem valós foglalási kérés felismerése)
mindegyik konfiguráción 100% — ez az egyetlen réteg, ami rendben van.

### 1a. A séma-javítás hatása a pontosságra — egy incidens és egy nyílt kérdés

**Incidens: az első javított séma hibás volt.** Az enum-kényszer első
verziójában a `parameterek` JSON-séma `properties`-ében CSAK a négy zárt
halmazú mező szerepelt (`bolt_id`, `szolgaltatas_id`, `napszak`, és a
felső szintű `eszkoz`), a többi mező (`datum_tol`, `datum_ig`, `datum`,
`foglalasi_kod`, `hianyzo_mezo`, stb.) nem. Ez a gyakorlatban úgy
viselkedett, mintha `additionalProperties: false` lenne: a modell **egy
futásban sem** adott vissza dátummezőt vagy más nem-felsorolt mezőt,
holott korábban rendszeresen megadta őket. Ezzel a hibás sémával mérve az
összesített pontosság **40,9%**-ra esett (`eredmeny_qwen35_9b_javitott_v1_hibas.json`)
— ezt NEM tekintjük érvényes mérésnek, csak dokumentált incidensnek. A
hibát a `parameterek` séma összes ismert mezőjének explicit felsorolásával
és `additionalProperties: true`-val javítottuk, majd újramértünk —
ez adta a fenti 47,7%-ot.

**Nyílt kérdés: miért lett a JAVÍTOTT séma is alacsonyabb (47,7%), mint az
eredeti, séma-kényszer nélküli mérés (54,5%)?** A feladat leírása szerint
ezt "a mérés szigorodásának" kellene tulajdonítani — **ez esetszintű
összevetésben nem ez a magyarázat**, és becsületesebb ezt kimondani, mint
egy kényelmes, de a saját adatunknak ellentmondó narratívát leírni.
Esetenkénti összevetés (`eredmeny_qwen35_9b.json` vs.
`eredmeny_qwen35_9b_javitott.json`) szerint a 22 esetből **pontosan 2**
pontszáma változott, mindkettő **romlott**, és egyik sem tipikus "a séma
most már kizárja a hibát" mintázat:

- `koznyelvi-05` (1,0 → 0,0): a régi mérésben a modell helyesen
  `visszakerdez`-t választott. Az újban `foglalas_athelyezes`-t, **üres**
  `foglalasi_kod`-dal (`{"foglalasi_kod": "", "uj_datum": "2026-08-19"}`).
  Ez rosszabb, mint egy egyszerű paraméter-eltérés — a modell magabiztosan
  hívott egy rossz eszközt, értelmetlen paraméterrel.
- `toredekes-01` (0,5 → 0,0): a régi mérésben a modell visszakérdezett
  (részleges elfogadás — ez ELFOGADOTT viselkedés a golden set szerint).
  Az újban közvetlenül `szabad_idopontok`-ot hívott, de a `napszak` mezőt
  kihagyta.

Mindkét eset arra utal, hogy a bővebb, explicit séma (különösen a
`foglalas_athelyezes` és a `szabad_idopontok` paramétereinek explicit
felsorolása) a modellt **magabiztosabb, közvetlenebb tooleszköz-választásra**
ösztönözte — ami itt, ezen a két bemeneten, rosszabb kimenetet
eredményezett, mint a korábbi visszakérdezés. A kiértékelő logika
(`kiertekel()`) NEM változott ebben a két esetben — sőt, összességében
**engedékenyebb** lett (2 új `reszleges_elfogadas` szabály került be), így
"szigorúbb mérés" mint magyarázat **nem áll meg**: azonos szabályokkal,
más modellkimenetre mértünk. Az ok a séma/prompt-változás által kiváltott
**valódi modellviselkedés-változás** ezen a két konkrét bemeneten, nem a
mérőeszköz szigorodása és nem is egy általános "a modell rosszabb lett"
állítás — mindössze 2 eset 22-ből.

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

**Megjegyzés (utólagos, a séma-javítás után):** az 5. és 6. szakasz az
ELAVULT qwen3.5:9b/be futásra (54,5%) épül, ezt itt nem számoltuk újra az
aktuális (47,7%) futásra. Az 1a. szakaszban kimutatott 2 eltérő eset
(`koznyelvi-05`, `toredekes-01`) egyike sem "tisztán dátum-hiba" — mindkettő
a "nem dátum jellegű" kategóriába esne az aktuális futáson is —, ezért a
lenti minőségi következtetés (a dátumparser önmagában nem old meg
mindent) feltehetően változatlan marad, de a pontos számok (13/22, 54,5%
→ 63,6%) az elavult mérésből származnak, nem lettek újraszámolva.

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
- qwen3.5:9b, gondolkodás nélkül — a javított mérőeszközzel nem futott
  újra ezen a körön, a 13,6% a javítás előtti mérésből maradt.
- 5 szálas válaszidő (nincs JSON).
- 50 egyidejű SQLite session (nincs JSON).
- hun-date-parser könyvtár közvetlen pontossága (a mérőszkript nem
  perzisztál JSON-t).
- Racka-4B — `ollama pull` nem működik (nincs a publikus registryben,
  kapuzott licenc); kézi GGUF-letöltés + `ollama create` szükséges, ezt
  nem végeztük el.

Ez a fájl nem ADR — nem dönt, csak felsorolja, mit mutatnak a mentett
mérési artifactok. A tényleges döntés (SQLite/Postgres, modellválasztás,
roham-üzemmód) nyitott; ADR-t nem módosítottam.

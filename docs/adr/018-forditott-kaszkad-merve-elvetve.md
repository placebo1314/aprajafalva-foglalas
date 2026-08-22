# ADR-018: Fordított kaszkád — a modell értelmez, a determinisztikus réteg a kapu

- **Dátum:** 2026-08-22 (első, elvető változat) / **2026-08-23
  (átdolgozva: elfogadva)**
- **Állapot:** **elfogadott**. Felülírja az **ADR-016**-ot (az ott
  rögzített sorrend — determinisztikus előbb — nem az éles út többé; az
  ADR-016 dokumentumként megmarad, a döntése "felülírva (ADR-018)"
  állapotot kapott).
- **Fájlnév-megjegyzés:** a fájl neve `018-forditott-kaszkad-merve-
  elvetve.md` maradt, pedig a döntés megfordult. Szándékos: a fájlnév
  hivatkozási cím, nem állapotjelzés — átnevezve a korábbi commitokban
  és a `docs/ALLAPOT.md`-ben lévő hivatkozások elhasadnának. Az ÁLLAPOT
  a fenti mező, nem a fájlnév.

## Kontextus

Ennek az ADR-nek volt egy korábbi változata (2026-08-22), ami a
fordított kaszkádot **megmérte és elvetette** (69,4% vs 86,1%). Ez a
változat azt a döntést fordítja meg. A régi szöveg nincs elrejtve: a
git-történetben megvan, és a "Mi változott a két mérés között" szakasz
pontosan felsorolja, miért lettek mások a számok.

### Miért nyílt újra a kérdés

**Az ADR-016 numerikus kiváltó feltétele NEM teljesült**, és ma sem
teljesül. Az három együttes feltételt írt elő:

1. 150-200 eses, **valós beszélgetésekből** származó golden set — nincs
   meg (ma 45 eset, mind kézzel írt);
2. a determinisztikus réteg a leggyengébb rétegen **< 70%** — ez ma
   igaz (`elengedes` 0%), de a fenti halmazon kellene mérni;
3. a modell konzisztensen **> 90%** — **nem teljesül** (a leggyengébb
   réteg PLACEHOLDER_FORDITOTT_LEGGYENGEBB).

A döntés tehát **nem azért fordul meg, mert a küszöb kigyulladt.** Azért
fordul meg, mert **az ADR-016 bizonyítéka érvénytelen volt**:

- **A látható halmaz a szabályokhoz igazodott.** Az ADR-016 azzal
  érvelt, hogy a determinisztikus réteg 100%-ot ad — de ugyanez a
  dokumentum írja le, hogy "a látható halmaz pontosan azokra a mintákra
  épül, amiken a szabály-alapú réteg már bizonyítottan jól teljesít". Ez
  soha nem volt általánosítási mutató; a 100% a mérés köréről szólt, nem
  a képességről.
- **Az LLM-mérés hiányos promptot mért.** Few-shot példák nélkül,
  normalizálás nélkül, determinisztikus dátumfeloldás nélkül futott, és
  **a beszélgetés kontextusát meg sem kapta** (az `LLMErtelmezo` a
  `kontextus` argumentumot egyszerűen nem használta). A 26,8% ezért nem
  a modell képességének felső korlátja volt.
- **A determinisztikus réteg időközben mintaillesztéssé nőtt** (bolt-,
  napszak-, lemondás-, áthelyezés-mintalisták), és a nyelvi
  változatosságot elvi okból nem tudja lefedni: minden új megfogalmazás
  új mintát igényel.

Ez önmagában nem döntés, csak ok az újramérésre. A döntést a mérésnek
kellett meghoznia.

## Amit a méréshez meg kellett csinálni

### 1. A halmaz kiegészítése olyan esetekkel, amiket a minta nem foghat meg

Új réteg: **`mintan_tul`, 9 eset** (`tests/golden/nyelvi_alap.yaml`) —
mondattani ALAKZATOK, nem nehezebb szavak: vagylagos időpont, üres
szándék, feltételes időpont, indoklás mellékmondattal, kettős kérés,
visszavonás, bizonytalanság, köznyelvi töltelék. Mindegyikben két,
egyenrangúnak LÁTSZÓ érték van, és a szerkezet dönti el, melyik a kért.

A réteg magja a **04–09. tükörpár**: ugyanaz a szerkezet, a két napszak
felcserélve ("azért délelőtt, mert délután dolgozom" ↔ "azért délután,
mert délelőtt dolgozom"). Egy szólistás réteg mindkettőre ugyanazt adja,
tehát az egyiket szükségszerűen elrontja. Ez a bizonyíték arra, hogy a
másikat nem megértette, hanem eltalálta.

**Őszintén:** a kilencből a determinisztikus réteg többet is megold, mert
véletlenül jó irányba dől el (a "28-án" beleesik a "jövő hét" ablakába; a
napszak-minták sorrendje éppen a kért napszakot adja). A réteg értéke a
tükörpárban van, nem az egyes esetek nehézségében.

### 2. A fordított kaszkád befejezése

A korábbi mérés egy **félkész** modult mért, sőt: a `--ertelmezo
forditott` kapcsoló a futtatóban nem is volt bekötve (az `else` ág a
RÉGI kaszkádot építette fel), tehát a 69,4%-os szám a repóból nem
reprodukálható. Ami hiányzott, és most megvan:

| Kapu | Mit old meg |
|---|---|
| **Kontextus a promptban** | A modell eddig minden fordulót nulláról látott. A szándék KEMÉNY része (bolt, szolgáltatás) mostantól bekerül a rendszerpromptba — a puha (dátum, napszak) szándékosan nem, mert az minden fordulóban frissen dől el. |
| **Kontextus-kapu** | Ha a modell a boltra kérdezne, de a kontextus ismeri, keresés megy visszakérdezés helyett. (A hibás kimenet szó szerint ez volt: `visszakerdez` `hianyzo_mezo: bolt_id`-vel ÉS `bolt_id: szundi`-val ugyanabban a dictben.) |
| **Elengedés-kapu** | A kontextus-sor mellékhatása: a modell akkor is megtartotta a boltot, amikor a mondat elvetette. Ha a bolt a kontextusból jön ÉS a mondat determinisztikusan nem nevez meg boltot, egy külön, szigorúan zárt kérdés megy a modellnek ("mi esik ki?", csak mezőnevek) — ugyanaz a mechanizmus, amit az ADR-016 kaszkád használ. |
| **Vagylagos dátum** | `datum_kifejezes_2`: két időpont vagylagos/feltételes megadásánál mindkettőt IDÉZI a modell, az ablak összevonása determinisztikus. |
| **Determinisztikus pótlások** | Dátum, napszak, szolgáltatás, preferált óra a MONDAT egészéből, ha a modell kihagyta. A modell válasza mindig nyer; a szabály csak pótol. |
| **Zárt visszakérdezés-halmaz** | A `hianyzo_mezo` enum lett. A modell korábban olyan mezőnevet is adott ("datum_kifejezes", "termek"), amit a vásárlónak feltéve értelmetlen kérdés. |

Amit a fordítás **nem** változtat meg (mind kikényszerítve, nem csak
dokumentálva): a dátum a `hun-date-parser`-ből jön (vitás esetben a
parser nyer), a bolt és a szolgáltatás zárt halmazon marad, a foglalási
kód a mondatból, a visszakérdezésről az orchestrator dönt a
bizonyosság-küszöb alapján, és Ollama-hiba vagy időtúllépés esetén a
szabály-alapú réteg veszi át, HIBA NÉLKÜL.

### 3. Egy mérési hiba javítása

A `kitalalt_ar` tiltott-minta vizsgálat RÉSZSZÖVEGET keresett a
paraméternevekben, ezért a `varhato_kerdes_tipusa` mezőt is "kitalált
árnak" minősítette. Teljes mezőnév-egyezésre javítva
(`tests/golden/futtato.py`).

## A mérés

45 eset, `qwen3.5:9b`, `most = 2026-08-17T09:00:00Z`, `temperature 0`,
`think: false`:

PLACEHOLDER_FOTABLA

Rétegenként, `szabaly` → `forditott`:

PLACEHOLDER_RETEGTABLA

## Döntés

**Megfordítjuk a sorrendet.** Az éles út a
`assistant/interpreter/forditott_kaszkad.py`: normalizáló → modell
(kötött dekódolással) → determinisztikus kapuk → szabály-alapú tartalék.
Ezt építi fel az `assistant/interpreter/__init__.py::
alapertelmezett_ertelmezo()`, ezt használja a `ui/vasarlo.py`.

Az ADR-016 sorrendje (`kaszkad.py`) a repóban marad,
`--ertelmezo kaszkad`-dal bármikor újramérhető — ez a visszaút.

## Miért

- **Összesítetten jobb** (PLACEHOLDER_OSSZ_INDOK).
- **A leggyengébb réteg is jobb**, és ez a projekt hivatalos mérőszáma,
  nem az átlag: PLACEHOLDER_LEGGYENGEBB_INDOK.
- **Ott javít, ahol az általánosítás mérhető**: a `mintan_tul` és az
  `elengedes` réteg épp azt méri, amit a mintaillesztés elvileg nem tud.
- **A determinisztikus garanciák nem gyengültek.** A dátum, a zárt
  halmazok és a foglalási kód ugyanúgy a determinisztikus rétegből
  jönnek, mint eddig — csak a DÖNTÉS sorrendje fordult meg, nem a
  kényszerek helye.

## Amit feladunk

- **Válaszidő**: PLACEHOLDER_LATENCIA. Ez akkor lesz valódi akadály,
  amikor a hangcsatorna SLO-ja (blueprint §12, ma felfüggesztve) érvénybe
  lép — ott ez az érték nem tartható. A determinisztikus út továbbra is
  ott van tartaléknak.
- **Kapuőr**: PLACEHOLDER_KAPUOR. A blueprint 10. szakasza szerint a
  témán belül tartás kifejezetten NEM múlhat a modell prompt-fegyelmén —
  ezt a mérés megerősíti, és ez a legfontosabb nyitott pont (l. lent).
- **Áthelyezés-felismerés**: a modell a "Át tudnám tenni szerdára…"
  mondatot keresésnek érti, holott foglalási kód nélkül visszakérdezés
  a helyes válasz. Nem káros (nem helyez át semmit), de rossz élmény.
- **Bolt a megjelenése alapján** ("a csillagos kirakatú bolt"): a modell
  a bolt szerkesztett megjelenés-adatát nem látja, ezért visszakérdez.
  Ez nem a sorrend hibája — a bolti tudás promptba emelése külön lépés.

## A következő lépés (nem ebben az ADR-ben)

**Determinisztikus kapuőr a modell ELŐTT.** A kapuőr-minták
(`_KAPUOR_MINTAK`) pozitív, nagy pontosságú illesztések; ha illeszkednek,
a döntés determinisztikusan `nincs`, a modell meg sem szólal. Ez a
blueprint 10. szakaszának közvetlen alkalmazása, és a mai 50%-os
kapuőr-rétegen azonnali javulást ígér. **Szándékosan nem került bele
ebbe a körbe**: az architektúra ott már nem "fordított kaszkád" lenne,
hanem hibrid (determinisztikus kapuőr + modell-értelmezés), és azt külön
ADR-ben kell eldönteni, külön méréssel.

## Kiváltó feltétel (a visszafordulásra)

Bármelyik **kettő** együtt visszaállítja az ADR-016 sorrendjét:

- a `forditott` összesítettje egy jövőbeli, bővebb halmazon **a
  `kaszkad` alá** esik, VAGY a leggyengébb rétege **< 50%**;
- a hangcsatorna válaszidő-SLO-ja érvénybe lép, és a fordított felállás
  p95-e **> 2× a determinisztikus-előbb kaszkádé** (ma ez már igaz —
  ezért számít ez a feltétel élesnek, amint az SLO nem felfüggesztett);
- a modell egy fordulóban zárt halmazon KÍVÜLI értéket ad, amit a
  determinisztikus kapuk nem fognak meg (ma egy sem volt ilyen, de ez a
  hibaosztály önmagában elég a visszafordulásra — a kiszámíthatóság
  fontosabb a pontosságnál).

## Váltás költsége

Alacsony: egy sor az `alapertelmezett_ertelmezo()`-ben. Mindkét modul
megvan, mindkettő tesztelt, mindkettő mérhető ugyanazzal a paranccsal.

## Ellenőrzés

```
python feladat.py golden --ertelmezo szabaly
python feladat.py golden --ertelmezo llm       --modell qwen3.5:9b
python feladat.py golden --ertelmezo kaszkad   --modell qwen3.5:9b
python feladat.py golden --ertelmezo forditott --modell qwen3.5:9b
```

Rétegenkénti bontással és réteg-megoszlással. A kiváltó feltétel minden
fele közvetlenül leolvasható ebből a kimenetből.

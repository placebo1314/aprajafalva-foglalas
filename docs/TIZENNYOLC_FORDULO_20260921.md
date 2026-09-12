# Tizennyolc forduló — öt szerkezeti hiba egy beszélgetésben

**Dátum:** 2026-09-21 · **Modell:** `qwen3.5:9b`, `num_ctx=8192`, v1
prompt · **ADR:** [035](adr/035-tizennyolc-fordulo.md)

## A próba

A barátunk lefoglalt egy időpontot. **Tizennyolc fordulóból**, és a
tizedikben azt írta: *„Így nem haladunk előre."*

| # | amit mondott | ami történt |
|---|---|---|
| 1 | „Örömöt szeretnék. Van nálatok? Mikor?" | melyik boltba szeretnél menni? |
| 3–7 | „Van késõbbi?", „10 után kéne.", „nem jó nekem ilyen korán.", „ez minden nap van?", „De melyik nap?" | **ötször ugyanaz a keresés**, ugyanazzal az ablakkal |
| 10 | „Így nem haladunk elõre." | **melyik boltba szeretnél menni?** |
| 11 | „de azt már megbeszéltük te láma." | kiút |
| 14 | „igen...ha máshogy nem megy." | új keresés, a választott időpont eldobva, majd „ne kínlódj vele tovább" |
| 18 | *(gombnyomás)* | foglalás létrejött |

**Egyetlen forduló sem volt önmagában hibás.** A keresés lefutott, a
visszakérdezés a hiányzó boltra kérdezett, a kiút a frusztrációra
reagált — minden válasz védhető, külön-külön. És épp ez a tanulság:
**minden mérőszámunk a FORDULÓRA nézett, egyik sem a beszélgetésre.**

## A hat javítás

| # | mi | hol |
|---|---|---|
| 1 | az állapotgép nem lép vissza `AJANLAT_VAR`-ból | `assistant/allapotgep.py` |
| 2 | `MEGEROSITES_VAR`-ban a séma háromértékű | `assistant/interpreter/llm_based.py` |
| 3 | `ajanlat_kerdes` — a jelöltekből felel, keresés nélkül | `assistant/tools/ajanlat_kerdes.py` |
| 4 | az ajánlat kimondja a napot, naponként csoportosítva | `assistant/valasz/` |
| 5 | a köznyelvi nevek a törzsadatban | 0005. migráció |
| 6 | mérőszám: az ÚT HOSSZA | `tools/naplo_elemzo.py`, riport |

### 1. Az állapotgép nem lép vissza

`AJANLAT_VAR` → `HIANYZO_ADAT` **tiltott átmenet**. Helyette:

> Az imént ezeket ajánlottam — Kedden, december huszonkettedikén: 8:00,
> 9:30 vagy 10:20. Melyik jó, vagy nézzek mást?

És a tiltott átmenet ezentúl **maradást** jelent, nem `INDULAS`-t: a
beszélgetésben az a legdrágább, ha elfelejtjük, hol tartunk.

Két további helyre is bekerült ugyanez a kapu, mert a végigjátszás
megmutatta, hogy máshonnan is elveszhet az ajánlat: a **bizonytalanság**
(„Ehhez még kellene tudnom: eszkoz" — értelmezhetetlen kérdés a
vásárlónak) és a **kétszer ugyanaz a keresés** (modellfüggetlen
kör-megszakító: ha a kérés minden paramétere egyezik az előzővel, nem
keresünk újra).

### 2. A hezitáló igen az igen

`MEGEROSITES_VAR`-ban a modell három értéket adhat: `igen` / `nem` /
`mas_kerdes`. Nem kulcsszólista — a „jó, legyen", „hát ha muszáj",
„rendben, csak végezzünk" végtelen sok alakban létezik. A hangulat
külön mezőbe mehet (`hangulat: kelletlen`), **a döntést nem
befolyásolja.**

Ehhez kellett egy másik javítás is: a frusztráció-figyelő eddig
kiúttá alakította a fordulót, ha a mondatban jel volt („nem megy") —
akkor is, ha a forduló SIKERÜLT. Egy sikerült fordulót nem lehet
kudarcnak minősíteni a hangulat miatt.

### 3. A rendszer beszél az ajánlatáról

Négy kérdésfajta, és kettő közülük **ablakot tol**:

```
„Van későbbi?"  →  a következő keresés a legkésőbbi ajánlat MÖGÖTT kezdődik
```

Enélkül ugyanazt találnánk meg megint — és ez ötször egymás után
megtörtént.

### 4. Az ajánlat kimondja a napot

```
előtte:  Ezeket az időpontokat találtam: 8:00, 9:30 vagy 10:20. Melyik jó?
most:    Kedden, december huszonkettedikén: 8:00, 9:30 vagy 10:20. Melyik jó?
```

A 7. forduló pontosan ezt kérdezte. Hangon a napnév a legkorábbi
időpont mellett hangzik el; ott továbbra is két időpont megy ki.

### 5. A köznyelvi nevek a törzsadatban

```sql
ALTER TABLE szolgaltatas ADD COLUMN koznyelvi_nevek TEXT NOT NULL DEFAULT '';
```

„öröm, nagy öröm, beszélgetés, vigasz" → boldogság → Törpilla. **Két
helyen használjuk, és mérve mindkettő kellett:**

| hova | mit ad | mérve |
|---|---|---|
| a beszélgetés elé | semmit | a modell adatnak látta, nem szótárnak |
| a RENDSZERPROMPTBA (a statikus boltsor helyére) | a „tűzijáték" eljut az Ügyifogyiig | **de** az „Örömöt szeretnék. Van nálatok?" mondatra `MINDEGY` boltot adott |
| determinisztikus KAPU (köznyelvi alak → slug) | az „öröm" eljut a Törpilláig | ez zárta be a rést |

Ugyanaz az elv, mint a dátumnál (ADR-011): a modell ÉRT, a
determinisztikus réteg FELOLD.

### 6. Az út hossza

`python feladat.py naplo`:

```
-- AZ ÚT HOSSZA (első kéréstől a foglalásig) --
  foglalással végződő beszélgetés: 5
  átlag: 6.4 forduló     leghosszabb: 18
  a cél alatt (5 forduló): 4 / 5
  ! 8292e38a  18 forduló
```

A riport fejlécében is, pirossal, ha a leghosszabb út a cél fölött van.

## Mérés

### A `tizennyolc` golden réteg (12 eset, a próba mondatai szó szerint)

| lépés | eredmény |
|---|---|
| a hat javítás előtt, csak az új esetekkel | **41,7%** |
| a kínálat a rendszerpromptban + köznyelvi kapu | **58,3%** |
| + a kapuőr „mi van veled" hibája, + a mérés állapot-mezője | **91,7%** |
| ugyanaz MÉG EGYSZER, változatlan kóddal | **83,3%** |

**A két utolsó szám ugyanazt a kódot méri.** Tizenkét eseten egyetlen
billenés 8,3 százalékpont — a réteg tehát ma a 90%-os küszöb KÖRÜL áll,
nem fölötte. A billenés mindkétszer ugyanaz a fajta volt: a helyes
eszköz (`ajanlat_kerdes`), rossz alkérdéssel (`van_korabbi` a
`van_kesobbi` helyett). **A kár ettől kicsi** — az ablak rossz irányba
tolódik, nem marad helyben —, de az eset így is bukik, és ez helyes:
a mérés ne legyen elnézőbb, mint a vásárló.

A második lépés két MÉRÉSI hibát is javított, nem csak a rendszert: a
golden eset `mit_kerdez` mezőt várt, a kaszkád `mit`-et adott; és a
`MEGEROSITES_VAR` állapotot az esetnek ki kell mondania, különben a
mérés a bő sémával futott volna — a szűkített sémát meg sem lehetett
volna mérni.

### A teljes beszédhelyzet-halmaz

51 eset (39 → 51), modellel: **96,1%** és **90,2%** két futáson. A
stabil bukás a régi, ismert `kozbevetes-02`; a `kozbevetes-01` és a
`meggondolas-02` futásonként billen.

### Végigjátszás: a tizennyolc forduló újra

A próba tíz mondatát a VALÓDI felületen végigjátszva, a javítások
után: **nincs visszakérdezés a boltra, nincs kiút, az állapot végig
`AJANLAT_VAR` marad**, az ablak tolódik, és a rendszer háromszor
felel az ajánlatáról kérdés helyett új keresés nélkül.

Ez a futás mutatott rá három olyan hibára, amit a golden set
szerkezetileg nem láthatott: a bizonytalanság-kapu „eszkoz"-kérdésére,
a jelölt nélküli `ajanlat_kerdes` hibaüzenetére, és arra, hogy a
frusztráció-figyelő egy SIKERES megerősítést is kiúttá alakított.

## Amit ez a kör NEM old meg

- **A köznyelvi szótár szóalakokat illeszt, nem tőket**: a
  „beszélgetés" bejegyzés nem fogja meg a „beszélgetni"-t. Ez a
  törzsadat dolga (vegye fel az admin), nem morfológiai elemzőé.
- **Az `ajanlat_emlekezteto` ismételhet**: háromszor értelmezhetetlen
  mondatra háromszor ugyanaz a lista. A frusztráció-figyelő ilyenkor
  is dolgozik, de az emlékeztetőnek nincs saját fokozata.
- **Az út hossza még nincs 5 alatt** a régi beszélgetéseken. Az új
  szám épp azért van, hogy ez látszódjon.

## Utóirat: a kiváltó feltétel MÁSNAP teljesült (2026-09-22)

Az ADR-035 ezt írta kiváltó feltételként:

> az `ajanlat_emlekezteto` elnyel egy valódi új kérést (a naplóban
> emlékeztető olyan mondatra, ami boltot vagy dátumot mondott) — ekkor
> a kapu túl széles

**Az első végigjátszáson teljesült.** A „csütörtök?" és az „Egy pénteki
nap kellene" mondatra ugyanaz a felsorolás ment ki, amit a vásárló épp
nem kért.

A javítás három lépcsős, és a sorrendjük a lényeg:

1. **Ha a mondat NAPOT mond, az kérés** — akkor is, ha a modell nem
   tudta eszközhívássá alakítani. A nap a mondatban van, a bolt a
   megőrzött kontextusban: ez elég egy kereséshez
   (`_kimondott_nap_kereses`).
2. **Ha ugyanaz a keresés jönne ki**, mint az előző, a kör-megszakító
   emlékeztet. Ez nem mond ellent az elsőnek: előbb megpróbáljuk
   teljesíteni a kérést, és csak a keresés szintjén derül ki, hogy
   ugyanoda jutnánk.
3. **Ami se nem választás, se nem nap**, arra megy az emlékeztető.

Ugyanez a futás fogott meg egy negyedik hibát is: a bizonytalanság-kapu
`hianyzo_mezo: "eszkoz"` értékéből **„Ehhez még kellene tudnom:
eszkoz."** lett a képernyőn. Az „eszkoz" a MI szavunk, nem a vásárlóé —
most azt kérdezi, amit egy pultos kérdezne („mit szeretnél pontosan").

### Az alkérdés determinisztikus lett

A `tizennyolc` réteg mindkét maradék bukása ugyanaz volt: a helyes
eszköz (`ajanlat_kerdes`), rossz alkérdéssel. Az irány és a nap-kérdés
viszont determinisztikusan LÁTSZIK a mondatban:

| mondat | felismerés |
|---|---|
| „van későbbi?", „10 után kéne" | `van_kesobbi` |
| **„nem jó nekem ilyen korán"** | `van_kesobbi` — a KORAI szó, mégis későbbi |
| „nem jó ilyen későn" | `van_korabbi` — a tükörpár |
| „ez minden nap van?", „melyik nap?" | `melyik_nap` |
| „kilenc jó lesz" | — (nincs irány, a modell dönt) |

A „korán" **hamis barát**: szó szerint a korait említi, a jelentése
mégis az, hogy későbbit kér. Egy szólistás megoldás pontosan fordítva
döntene — ezért a tagadás külön szabály, nem kivétel.

Ezzel a `tizennyolc` réteg **100%** (12/12), a beszédhelyzetek halmaz
**94,1%**. A három stabil bukás mind RÉGI és ismert
(`meggondolas-02`, `kozbevetes-01/02`), ehhez a körhöz nincs közük.

### Az út hossza, mérve

A próba tíz mondatát a VALÓDI felületen végigjátszva:

| | megerősítésig |
|---|---|
| az eredeti próba | **17 forduló** |
| a javítások után | **9 forduló** |

Még mindig a cél (5) fölött — de a maradék hossz már nem a rendszeré: a
vásárló hat feltáró kérdést tett fel, mielőtt napot mondott volna, és
mostantól mind a hatra MÁS és hasznos választ kap. Az 5 fordulós cél
arra vonatkozik, aki tudja, mit akar.

### A köznyelvi szótár határa — szerkezetivé téve

A szótár szavai hétköznapi magyar szavak („beszélgetés", „öröm",
„robbantás"), és a „jó beszélgetés volt, köszi" mondatban nincs
foglalási szándék. A teljes úton eddig sem lett belőle keresés (a
modell `nincs`-et ad, és az ág eldobja a paramétereket) — de az
VÉLETLEN védelem volt. Mostantól a szótár csak FOGLALÁSI eszközöknél
tölthet ki boltot, zárt eszközhalmazzal.

## Reprodukció

```
python -m pytest tests/egyseg/test_ajanlat_kerdes.py tests/egyseg/test_allapotgep.py
python feladat.py golden --ertelmezo forditott --halmaz beszedhelyzetek
python feladat.py naplo          # „AZ ÚT HOSSZA" szakasz
```

Nyers kimenetek: `spike/meres_20260921/`.

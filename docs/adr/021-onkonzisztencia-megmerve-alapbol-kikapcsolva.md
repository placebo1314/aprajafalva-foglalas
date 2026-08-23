# ADR-021: Önkonzisztencia — megépítve, megmérve, alapból kikapcsolva

- **Dátum:** 2026-08-23
- **Állapot:** elfogadott
- **Viszonya a többihez:** a blueprint 10. szakasza a kezdet óta
  előírja („Önkonzisztencia: az értelmező 3-5×, a JSON eszközhívások
  pontos egyenlőségvizsgálatával"), de sosem épült meg. A blueprint 12.
  szakaszának új, 15 másodperces kerete tette lehetővé a mérést: az
  engedi meg a fordulónkénti több modellhívást — **feltéve, hogy
  mérhető pontosságot hoz**.

## Kontextus

A blueprint két helyen is beszél róla, és mindkettő fontos:

> Önkonzisztencia: az értelmező 3-5×, a JSON eszközhívások pontos
> egyenlőségvizsgálatával. Szűkösségben és hangon ez elesik.

> **Kerülendő:** szabad szöveg súlyozott keverése, LLM-ek egymással
> beszélgetése.

A kettő együtt azt jelenti: a szavazás megengedett, de csak
STRUKTURÁLT kimeneten, pontos egyenlőséggel — nincs hasonlóság, nincs
küszöb, nincs részleges egyezés. Ez itt lehetséges, mert a kimenet zárt
halmazokból épül (`assistant/tools/semak.py`), tehát az azonosság
értelmes fogalom rajta.

A blueprint 12. szakasza (2026-08-23) ehhez adta meg a keretet: „Több
modellhívás is megengedett, ha mérhető pontosságot hoz. Az engedély
**feltételes**: a hívásszám növelése csak MÉRÉSSEL indokolható."

## Amit megépítettünk

`assistant/interpreter/onkonzisztencia.py` — egy `Ertelmezo`-t burkol,
háromszor futtatja, és a `{eszkoz, parameterek}` pár kulcs szerint
rendezett JSON-alakján szavaztat.

| Egyetértés | Mi történik |
|---|---|
| 3 / 3 | a válasz megy, VÁLTOZATLAN bizonyossággal |
| 2 / 3 | a többségi válasz megy, ×0,8 bizonyossággal |
| 1+1+1 | ZÁRT KÉRDÉS a szándékra |

Két tervezési döntés, mindkettő szándékos:

1. **Az első futás kanonikus** (`temperature: 0`) — pontosan az, amit a
   rendszer önkonzisztencia nélkül adna. A kikapcsolás így nem
   változtathat a kanonikus válaszon. A másik kettő mintavételes
   (`temperature: 0,7`), RÖGZÍTETT maggal, hogy a mérés megismételhető
   legyen.
2. **A bizonyosság csak GYENGÜLHET, sosem erősödhet.** Három azonos
   futás nem „bónusz": azt állítani, hogy ez több, mint amit a
   logprobok mutatnak, nincs mire alapozni.

A ×0,8 szorzó a HATÁRESETEKET billenti át, nem mindent: egy magabiztos
0,95 utána is 0,76 (az eszköz-küszöb 0,7 FÖLÖTT), egy amúgy is gyenge
0,74 viszont 0,592 (a kritikus mező 0,6-os küszöbe ALATT). A pontos
fordulópont 0,75, tesztben rögzítve.

## A mérés

`qwen3.5:9b`, `forditott` értelmező, `most = 2026-08-17T09:00:00Z`.

| | nyelvi halmaz (45 eset) | robusztussági halmaz (44 eset) |
|---|---|---|
| pontosság — **nélküle** | 83,3% | 100,0% |
| pontosság — **vele** | **83,3%** | **100,0%** |
| válaszidő / forduló — nélküle | 5,23 s | 3,62 s |
| válaszidő / forduló — **vele** | **8,54 s (+63%)** | **6,20 s (+71%)** |
| egyetértés-eloszlás | 3/3: 38, 2/3: 7, nincs többség: 0 | 3/3: 41, 2/3: 3, nincs többség: 0 |

**Esetenként összevetve: NULLA eset változott** a 45-ből. Nem
„nagyjából ugyanannyi" — egyetlen eset pontszáma sem mozdult egyik
irányba sem.

Ez utólag nem meglepő: a többségi válasz definíció szerint az, amit a
`temperature: 0`-s futás is adott (a mintavételes futások ritkán
kerülnek többségbe önmagukban), és a „nincs többség" ág egyszer sem
szólalt meg.

### Amit a mérés MÉGIS megmutatott

A 2/3 egyetértés **korrelál a hibázással**:

| | eset | ebből hibás |
|---|---|---|
| 3/3 egyetértés | 38 | 5 (13%) |
| 2/3 egyetértés | 7 | 3 (43%) |

A hét ingadozó eset: `tajszolas-02`, `toredekes-03`, `toredekes-04`,
`szleng-03`, `egyszerusitett-03`, `mintan_tul-05`, `mintan_tul-09`.
Ebből három bukott is (`tajszolas-02`, `toredekes-04`,
`mintan_tul-09`).

Tehát a jel NEM értéktelen — csak a hatása nem ott van, ahol a mérés
nézi.

### A mérés korlátja, kimondva

**A golden futtató az ÉRTELMEZŐT méri, az orchestrator
bizonyosság-kapuját nem.** A csökkentett bizonyosság élesben
visszakérdezéssé alakulhat — a mérésben viszont nincs, ami erre
reagáljon. A `tajszolas-02` pont ilyen: a `docs/ALLAPOT.md` már
rögzítette, hogy ott a modell 0,58-as bizonyossággal tippelt boltot, és
élesben ez a 0,6-os küszöb alatt zárt kérdéssé alakulna. A ×0,8-cal ez
0,46 lenne — még egyértelműbben.

**Ezért a „nulla javulás" pontos állítása ez:** az önkonzisztencia az
ESZKÖZHÍVÁST nem javítja. Hogy a belőle származó bizonyosság-jel javít-e
a beszélgetésen, ez a mérés nem tudja megmondani — ahhoz
orchestrator-szintű mérés kellene, ami ma nincs.

## Döntés

**Megépítjük, megtartjuk, és ALAPÉRTELMEZÉSBEN KIKAPCSOLVA hagyjuk.**

- `assistant/interpreter/__init__.py::ONKONZISZTENCIA_ALAPERTELMEZES = False`
- `APRAJAFALVA_ONKONZISZTENCIA=1` bekapcsolja, `=0` kikapcsolja —
  mindkét irány konfigurációs csere, nem kódmódosítás.
- A golden futtató `--onkonzisztencia` kapcsolóval bármikor újramérhető.

## Miért

- **A blueprint 12. szakaszának feltétele nem teljesült.** „A hívásszám
  növelése csak méréssel indokolható — mennyit javít, és mennyivel
  lassít." Megmértük: 0 pontot javít, 63-71%-kal lassít. A feltételes
  engedély feltétele tehát nem áll fenn.
- **Nem töröljük, mert a mérés nem teljes.** A jel korrelál a
  hibázással, és a hatása egy olyan kapun megy át, amit a mai mérés nem
  hajt meg. Egy kikapcsolt, tesztelt modul olcsóbb, mint egy újra
  megírandó.
- **A 15 s keret még tartaná** (8,54 s átlag) — tehát nem a keret
  tiltja, hanem az, hogy nincs miért fizetni érte.
- **Az egyetértés-eloszlás önmagában is hasznos.** A napló rögzíti
  (`naplo/probak.jsonl`, `egyetertes` mező), és a
  `python feladat.py naplo` kiírja: bekapcsolva a rendszer megmutatja,
  MELYIK fordulókon ingadozik a modell. Ez diagnosztikai eszköz akkor
  is, ha a döntést nem változtatja meg.

## Amit feladunk

- **Egy megépített, tesztelt kód, ami nem fut.** Ez halott kód
  kockázata: ami nem fut, az elromlik. Ellene a 16 egységteszt
  (`tests/egyseg/test_onkonzisztencia.py`) és az, hogy a
  `--onkonzisztencia` kapcsoló a mérésben bármikor bekapcsolható.
- **A „nincs többség" ág gyakorlatilag mérhetetlen maradt.** A 89
  mért fordulón egyszer sem szólalt meg. A viselkedése tesztből ismert,
  éles adatból nem.
- **Nem tudjuk, mit tenne a bizonyosság-jel élesben.** Ez a mérés
  hiánya, nem a modulé — l. fent, „A mérés korlátja".

## Kiváltó feltétel

Bármelyik bekapcsolja:

- **Orchestrator-szintű mérés készül** (a bizonyosság-kapuval együtt
  értékelő halmaz), és azon az önkonzisztencia mérhetően javít.
- **A „nincs többség" ág megszólal** valós használatban (a napló
  `egyetertes` mezőjében 1 érték jelenik meg) — az azt jelentené, hogy
  van olyan bemenet, amin a modell háromfelé megy, és ott a zárt kérdés
  egyértelműen jobb, mint a találgatás.
- **Modellváltás** (ADR-013 kiváltó feltétele) — egy kisebb vagy
  gyengébb modellnél az ingadozás gyakoribb lehet, és akkor a szavazás
  többet érhet. Újramérés kötelező, nem feltételezés.

## Váltás mire

Ha bekapcsoljuk és a válaszidő szűk lesz: **futásszám csökkentése
háromról kettőre** nem járható út (kettőből nincs többség), viszont a
mintavételes futások **párhuzamosítása már megvan**
(`OnkonzisztensErtelmezo(parhuzamos=True)`, alapértelmezés). A mért
+63% ezzel a párhuzamosítással együtt értendő — sorosan
lényegesen rosszabb lenne.

## Váltás költsége

Nulla kódmódosítás: `APRAJAFALVA_ONKONZISZTENCIA=1`. A burkoló a
determinisztikus úton (nincs konfigurált modell) magától egyszer
futtat, tehát a bekapcsolás ott sem jár költséggel.

## Ellenőrzés

```
python feladat.py golden --ertelmezo forditott
python feladat.py golden --ertelmezo forditott --onkonzisztencia
python feladat.py naplo          # az `egyetertes` eloszlás éles használatból
python -m pytest tests/egyseg/test_onkonzisztencia.py
```

Az első kettő különbsége adja a „mennyit javít / mennyivel lassít" pár
mindkét felét. A `--json` fájlban esetenként is benne van az egyetértés,
tehát utólag megállapítható, MELYIK eseten ingadozott a modell — nem
csak az, hogy hányon.

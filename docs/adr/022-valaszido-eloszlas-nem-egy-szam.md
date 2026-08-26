# ADR-022: A válaszidő-elvárás eloszlás, nem egy szám

- **Dátum:** 2026-08-26
- **Állapot:** elfogadott
- **Viszonya a többihez:** a blueprint 12. szakaszának 2026-08-23-i
  „átlag < 15 s" keretét váltja fel. Az ADR-021 (önkonzisztencia) épp
  ezen a kereten mérte magát — az ott közölt számok (8,54 s, 6,20 s)
  változatlanul érvényesek, csak mostantól máshoz mérjük őket.

## Kontextus

A 15 másodperces keret egyetlen számot adott: az ÁTLAGOT. Az első
teljes körű mérés után látszik, hogy ez a szám két különböző kérdésre
ugyanazt a választ adja:

| Felállás | átlag | mi a baj | mit kellene javítani |
|---|---|---|---|
| minden forduló 15 s | 15 s | a rendszer egyenletesen lassú | modell, prompt, hívásszám |
| 42 forduló 3 s + 2 forduló 250 s | 14,2 s | van egy patológiás ág | azt az EGY ágat |

A két sor ugyanazt az átlagot adja, ugyanúgy „tartja a keretet", és
teljesen más munkát kíván. **Ez nem elméleti példa:** a saját
méréseinkben pontosan ez a mintázat állt elő — a robusztussági halmaz
átlaga 3,62 s/forduló volt, miközben a `hosszu-01-tobb-tema` eset
15,18 s-ot mért (`docs/ALLAPOT.md`). Az átlag ezt elnyelte; a mérés
„tartja"-t írt ki, holott egy vásárló azon az egy eseten negyed percig
nézte a képernyőt.

A második hiányzó dolog az IRÁNY. Két küszöb pillanatfelvétel: a p50
maradhat hónapokig 9,8 s-on úgy, hogy közben minden héten romlik — a
küszöb a kilencedik héten szólal meg először, amikor már késő.

## Döntés

A tartalmi válasz elvárása **kétpontos eloszlás + tendencia**,
fordulónként:

| Pont | Elvárás | Mit véd | Kemény? |
|---|---|---|---|
| **p50** | **< 10 s** | a tipikus forduló, a beszélgetés ritmusa | igen |
| **p95** | **< 25 s** | a farok, a türelem felső határa | igen |
| **tendencia** | figyelve | a lassú elsodródás | **nem** |

- **A mérés alapegysége a FORDULÓ**, nem az eset és nem a beszélgetés. A
  vásárló fordulónként vár; egy háromfordulós eset összideje egyetlen
  mintaként hamisan nyújtaná meg a farkat.
- **A két küszöb együtt áll.** Egy 4 s-os p50 nem vásárolja meg a 40
  s-os p95-öt.
- **A tendencia nem küszöb.** A napló-elemző a napló első és második
  felének p50-jét veti össze, és `javul` / `romlik` / `stabil` /
  `keves_adat` irányt ír ki. A `romlik` nem bukás — kérdés, amit fel
  kell tenni.

### A tendencia paraméterei, és miért pont ezek

- **p50-en mérjük, nem átlagon.** A tendencia kérdése az, hogy a
  TIPIKUS forduló lett-e lassabb. Egyetlen kilógó forduló az átlagot
  egy 20 elemű félidőben látványosan mozgatja, a mediánt nem.
- **±20% a „stabil" sáv** (`TENDENCIA_SAVSZELESSEG`). Az Ollama
  futásonkénti szórása önmagában bőven ekkora — ugyanarra a mondatra
  15,18 s-ot és 6,36 s-ot is mértünk egyetlen kódváltozás nélkül
  (`docs/ALLAPOT.md`, „A válaszidőről őszintén"). Ennél szűkebb sávból
  tendenciát olvasni önámítás lenne.
- **Legalább 10 forduló kell** (`TENDENCIA_MIN_FORDULO`), különben az
  irány `keves_adat`. Ez nem hibaág: azt jelenti, hogy a kérdésre ebből
  a naplóból nem lehet felelni.

## Miért ezek a számok

Ezek **fejlesztési keretek, nem termékígéretek** — ugyanúgy, ahogy a 15
s az volt. A választás indoklása:

- **p50 = 10 s.** A mai mért medián nagyságrendje 3-5 s a szöveges úton.
  A 10 s tehát nem szorít, viszont megfogná, ha a tipikus forduló
  megduplázódna — ami pont az a változás, amit észre kell venni.
- **p95 = 25 s.** A ma ismert leglassabb valódi forduló 15,18 s volt (a
  632 karakteres, öt témájú mondat). A 25 s ezt beengedi, de a
  nagyságrendváltást (percek) nem.
- **A p95 nem 15 s**, mert akkor a mai ismert farok azonnal bukna, és
  egy már dokumentált, tudatosan vállalt korlátból
  (`docs/ALTALANOSITAS.md` 2.1) lenne piros teszt. Egy elvárás, amit az
  első naptól sértünk, nem elvárás, hanem zaj.

## Amit feladunk

- **A p95 = 25 s hangon tarthatatlan.** Egy hangbeszélgetésben 25
  másodperc csönd nem türelmi határ, hanem a hívás vége. Ez a szám a
  szöveges csatornáé, ahol a gépelés-jelző kitölti a várakozást; a
  hangcsatornán a kétlépcsős válasz (blueprint 7.) első lépcsője a
  valódi mérőszám. Ezt kimondjuk, és nem takarjuk el egy közös számmal.
- **A p95 egy 44 eses halmazon a második leglassabb esetet jelenti.**
  Ilyen mintanagyságnál a p95 nem stabil statisztika: egyetlen eset
  hozzáadása vagy elvétele érdemben mozdítja. A számot ezért
  „ezen a futáson" jelentjük, nem abszolút igazságként.
- **A tendencia a napló SORRENDJÉRE támaszkodik**, nem az időbélyegre.
  Ha valaki két, hetekkel korábbi próba naplóját egyben elemzi, a
  „félidő" fogalma elmosódik. A napló-elemző `--utolso N` kapcsolója a
  kézi megoldás erre.

## Kiváltó feltétel

Bármelyik újranyitja ezt a döntést:

- **A hangcsatorna bekötése** (M6, ASR/TTS). Ott a p95 = 25 s nem
  tartható; a hangra külön elvárás kell — a mai számokat NEM szabad
  átemelni.
- **A p50 tartósan a 10 s felett marad** két egymást követő teljes
  mérésen — akkor nem a küszöböt kell tágítani, hanem a rendszert
  gyorsítani (kisebb modell: ADR-013 kiváltó feltétele, vagy kevesebb
  modellhívás).
- **Az SLO-k felfüggesztésének feloldása** (M4 lezárása) — akkor ezek a
  fejlesztési keretek vagy valódi SLO-vá válnak, vagy helyet adnak
  neki.

## Váltás mire

Ha a két pont kevésnek bizonyul: p99 hozzávétele. Ezt ma NEM tesszük
meg, mert egy 44-89 eses halmazon a p99 pontosan a leglassabb esetet
jelenti — vagyis nem statisztika, hanem egy anekdota, aminek százalék
van a nevében.

## Váltás költsége

Két konstans (`tools/naplo_elemzo.py::P50_KERET_MASODPERC`,
`P95_KERET_MASODPERC`) és a blueprint 12. szakaszának egy táblasora. A
golden futtató ugyanezt a két konstanst importálja — egy helyen van
definiálva, hogy a két jelentés összehasonlítható maradjon.

## Ellenőrzés

```
python feladat.py naplo                       # p50 / p95 / tendencia éles naplóból
python feladat.py golden --halmaz robusztus --ertelmezo forditott
python -m pytest tests/egyseg/test_naplo_elemzo.py
```

A napló-elemző kiírja mindkét pontot a hozzájuk tartozó
[TARTJA/NEM TARTJA] jelöléssel, külön-külön — az összevont ítélet
elrejtené, hogy a rendszer a mediánon rendben van, csak a farka hosszú.

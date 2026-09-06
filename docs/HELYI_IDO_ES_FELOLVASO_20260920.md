# A rossz óra és a néma gomb — helyi idő és a felolvasó

**Dátum:** 2026-09-20 · **ADR:** [033](adr/033-helyi-ido-a-megjelenitesben-es-a-felolvaso.md)

## A legfontosabb szám

A rendszer **minden időpontot egy órával korábbinak mondott**, mint
ahogy van (nyáron kettővel). Nem néha, nem élesetben: mindig, mindkét
csatornán, a megerősítés-kérdésben is.

```
adatbázis:  2026-12-21T07:00:00Z        ← helyes, a bolt 8-kor nyit
gomb:       2026-12-21 07:00–07:10 (UTC)  ← ezt látta a vásárló
felolvasó:  „hét órakor"                  ← ezt hallotta
```

A CLAUDE.md 4. invariánsa két mondat, és eddig csak az elsőt tartottuk
be: *„Minden idő UTC-ben tárolódik… **helyi idő csak a megjelenítésnél
keletkezik**."* Az elsőnek volt bizonyítéka (séma, tesztek), a
másodiknak nem volt gazdája.

**Miért nem fogta meg semmilyen mérés.** Mert minden réteg önmagában
konzisztens volt: a gomb ugyanazt mutatta, amit a mondat mondott, és
amit az előzmény-sor a modellnek átadott. A golden set, a végigjátszás
és az egységtesztek mind a rendszert hasonlították önmagához. Ehhez a
való világ kellett: valaki, aki tudja, hogy a bolt nyolckor nyit.

## Mi változott

| # | változás | hol |
|---|---|---|
| 1 | `helyi_iso(iso, zona)` — EGY konverziós pont | `assistant/valasz/helyi_ido.py` |
| 2 | a zóna a törzsadatból, a hívó adja át | `ui/vasarlo.py`, `assistant/valasz/` |
| 3 | az „(UTC)" nem hagyja el a rendszert | gombok, mondatok |
| 4 | a mondat KIMONDJA az időpontokat, nem csak bevezeti | `ajanlat_mondat` |
| 5 | a hangmodell betöltve marad + indításkor melegszik | `assistant/hang.py` |
| 6 | a lejátszás megszakítható, minden mondat saját fájlba | `assistant/hang.py` |
| 7 | a végigjátszás beszélhető módban ELLENŐRIZ | `tools/vegigjatszas.py` |

A konverzió ugyanolyan ALAKÚ ISO-szöveget ad vissza, csak `Z` nélkül —
így a karakterpozíció szerint vágó formázók változatlanul működnek. **A
`Z` hiánya a jelzés, hogy ez már nem UTC.**

## A gomb nem beszél

A szöveges ajánlat-mondat eddig csak bevezette a jelölteket:

```
előtte:  Ezeket az időpontokat találtam — melyik jó?
         [2026-12-22 09:20–09:30] [2026-12-22 09:40–09:50] …

most:    Ezeket az időpontokat találtam: 9:20, 9:40 vagy 10:20. Melyik jó?
         [2026-12-22 09:20–09:30] [2026-12-22 09:40–09:50] …
```

A gombok megmaradtak — a mondat nem helyettük szól, hanem mellettük. A
gombfelirat ugyanis nem része a beszélgetésnek: nem olvasható vissza,
nem kerül az előzménybe, és aki felolvastatja a képernyőt, annak
egyszerűen nincs ott.

Hangon marad a legkorábbi + egy alternatíva: három felolvasott időpont
megjegyezhetetlen (`ajanlat_mondat` docstring).

## A felolvasó — mérve

`python feladat.py hangproba --meres`

| | előtte | most |
|---|---|---|
| késleltetés mondatonként | **2,07 s** | **0,09–0,23 s** |
| a hangmodell betöltése | mondatonként újra | egyszer, indításkor (1,52 s) |

A késleltetés a mondat hosszától FÜGGETLENÜL volt 2 másodperc — tehát
nem a szintézis lassú, hanem az indulás: minden megszólalásnál új
Python-folyamat, és újra betöltött 60 MB-os hangmodell. A modell 3,5 s
alatt válaszol; ha a hang még kettőt tesz rá, a vásárló azt hiszi, nem
történt semmi, és újra beszél.

Két további hiba, amit ugyanez a kör zárt le:

- **Két forduló hangja egymásra csúszott.** Most az új megszólalás
  elhallgattatja a régit. Windowson a szinkron `PlaySound`-ot MÉRVE nem
  szakítja meg egy másik szálból küldött `SND_PURGE` (mérés: 4,89 s a
  4,89-ből lejátszva) — ezért aszinkron lejátszás + megszakítható
  várakozás. Utána: 1,01 s után elhallgat.
- **Minden szintézis ugyanarra a fájlra írt**, arra, amit a lejátszó
  épp olvasott. Most mondatonként egyedi név.

## Az új ellenőrzés: HANG-KIFOGÁS

`python feladat.py vegigjatszas --mod beszelheto`

A végigjátszás eddig KIÍRTA a mondatokat, de nem ellenőrizte őket.
Mostantól fordulónként két dolgot néz:

1. **formai kapu** (`beszelheto.tiltott_jelek`) — az egységtesztek
   minden EGYES sablonra futtatják, de az összerakott fordulóra eddig
   senki;
2. **néma választás** — ha a forduló gombot rajzol, a kimondott
   szövegnek kérdésnek kell lennie. Gomb önmagában néma.

Amit szándékosan NEM néz: hogy minden gomb elhangzik-e. A teljesség itt
nem cél, az ELINDÍTHATÓSÁG igen.

Mai állás: **kifogás nincs** — 15 beszélgetés, minden megszólalás
átment a kapun, és ahol gomb volt, ott a mondat is kérdezett.

## Mérés

| halmaz | eredmény |
|---|---|
| egységtesztek | 1076 zöld (+27 ebben a körben) |
| beszédhelyzetek (39, modellel) | 92,3% |
| nyelvi (85, két futás) | 84,1% és 82,9% — az előzőhöz képest ±0,0 |

A nyelvi halmazon a futtató ítélete: *„a különbség a zajküszöbön BELÜL
van — ez SZÓRÁS, nem hatás"*. **Nem javulást állítunk, hanem azt, hogy
nem rontottunk** — a változtatás a mondatépítő rétegbe nyúlt, ami a
halmaz minden esetének útjában áll.

**Egy eset flippelt, és NEM ettől a körtől**: az `elesbol-03-valassz-te`
(„nekem mind jó, válassz te") ma 5/5-ben bukik, a 2026-09-19-i körben
kétszer is ment. Ellenőrizve a COMMITTELT fán, a változtatások nélkül:
ott is bukik 3/3-ban. Tehát nem regresszió, hanem a modell viselkedése
mozdult el két nap alatt — ugyanaz a jelenség, amit a
`SZORAS_KUSZOB_SZAZALEKPONT` kezel, csak eseti szinten: **egy eset
lehet stabilan jó az egyik munkamenetben és stabilan rossz a
másikban.**

Az `elesbol-01` eset felajánlott időpontjai átálltak helyi időre, és a
bemenete `„a hét tizenötös"` → `„a nyolc tizenötös"` lett. A mondat
SZERKEZETE — ez az, amit az eset mér — betűre ugyanaz; ha az órákat
hagynánk, olyan képernyőre hivatkozna, ami már nem létezik.

## Reprodukció

```
python -m pytest tests/egyseg/test_helyi_ido.py tests/egyseg/test_hang.py
python feladat.py hangproba --meres
python feladat.py vegigjatszas --mod mindketto
python feladat.py golden --ertelmezo forditott --halmaz beszedhelyzetek
```

Nyers kimenetek: `spike/meres_20260920/`.

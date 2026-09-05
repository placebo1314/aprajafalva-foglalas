# A nyelvi halmaz bővítése és az ismételt mérés protokollja

**Dátum:** 2026-09-12 · **Modell:** `qwen3.5:9b`, `num_ctx=8192`, v1
prompt, 4 fordulós ablak, `temperature 0`

## Miért nőtt a halmaz

A 2026-09-05-i kör után ez maradt nyitva: a nyelvi szám futásról
futásra 2-4 pontot mozgott, és **egy futásból nem lehetett megmondani,
hogy egy változtatás javított-e**. Az ok a rétegek MÉRETE volt:

| réteg | eset (előtte) | egy billenő eset ára |
|---|---|---|
| `elengedes` | 5 | **20 százalékpont** |
| `tajszolas` | 4 | **25 százalékpont** |
| `toredekes` | 4 | **25 százalékpont** |

Egy ötelemű rétegen a szám többet mond a szerencséről, mint a
rendszerről. A bővítés célja tehát nem a nehezítés, hanem a
**stabilitás**.

## Mi került bele — 30 új eset

| réteg | előtte | most | mit mérnek az újak |
|---|---|---|---|
| `elengedes` | 5 | **15** | a bolt elengedése MÁS helyzetben (ajándék, kísérő, tudáshiány); a MINDEGY visszavonása mindkét irányba; névmási visszautalás; négy ellenpróba |
| `tajszolas` | 4 | **14** | ö-zés, í-zés, „hun/bót", régies felszólítás, nyelvjárási TÉNYKÉRDÉS és LEMONDÁS (eddig csak foglalás volt), egy köznyelvi ellenpróba |
| `toredekes` | 4 | **14** | táviratstílus, félbehagyott mondat, javítgatás menet közben, egyszavas válasz, írásjel nélküli folyam, ismételt szó, egy „nincs mit értelmezni" ellenpróba |

**Nem a meglévők átfogalmazásai**: mindegyik más beszédhelyzetből jön —
más szerep (kísérő, ajándékozó, telefonáló), más beszédaktus
(ténykérdés, lemondás, javítás), más hangalak.

Összesen: **55 → 85 eset**, a teljes golden set **184 eset**
(nyelvi 85, robusztussági 68, beszédhelyzetek 31).

## Az ismételt mérés protokollja (`--ismetles`)

```
python feladat.py golden --ertelmezo forditott --ismetles 2
python feladat.py golden --ertelmezo forditott --elozo elozo_futas.json
```

A futtató mostantól kiírja a **futásonkénti tartományt**, és
összehasonlításkor ítéletet mond:

```
=== ISMÉTELHETŐSÉG ===
  1. futás: 84.1%
  2. futás: 86.5%
  tartomány: 2.4 százalékpont
  Zajküszöb: 3.0 százalékpont (a 3 pontos alapérték és a mért tartomány közül a nagyobb)
  Előző futás: 86.4%  →  most: 84.1%  (-2.3 pont)
  ÍTÉLET: a különbség a zajküszöbön BELÜL van — ez SZÓRÁS, nem hatás.
  A jelentés ne állítson se javulást, se romlást.
```

A küszöb `SZORAS_KUSZOB_SZAZALEKPONT = 3.0` VAGY a ténylegesen mért
tartomány — amelyik nagyobb. Két futás tartománya alsó becslés a zajra,
tehát nem szabad vele alálicitálni a korábbi tapasztalatnak.

**Az ítélet a JSON-ba is bekerül** (`osszefoglalo.ismetelhetoseg`), tehát
egy későbbi jelentés sem hivatkozhat rá másképp.

## A bővítés hatása a szórásra — mérve

| | 55 eset (2026-09-05) | 85 eset (2026-09-12) |
|---|---|---|
| két futás | 82,7% és 83,6% | 84,1% és 86,5% |
| tartomány | 0,9 pont | 2,4 pont |
| **billenő eset** | 2 (a napi szélső értékek 3,7 pontot fogtak át) | **2** |
| **billenő arány** | 2/55 = **3,6%** | 2/85 = **2,4%** |

**A billenő esetek SZÁMA nem csökkent — az arányuk igen.** Ez volt a
cél: ugyanaz a két ingadozó eset (`koznyelvi-05`, `elengedes-03`) most
kisebb súlyt visz. A tartomány önmagában nem hasonlítható (két mintából
becsült szám), a billenő arány igen.

Amit ez NEM old meg: két futás továbbra is kevés a pontos zajbecsléshez.
A protokoll ezért nem a tartományra épít egyedül, hanem a 3 pontos
alapértékre is.

## A két nyitott bukás lezárva (ADR-031)

| eset | 2026-09-05 | most |
|---|---|---|
| `mindegy-07` (a MINDEGY visszavonása) | bukott mind a 4 modellen | **OK** |
| `elengedes-05` (szolgáltatás átmentése) | bukott mind a 4 modellen | **OK** |
| `elengedes-10/11` (visszavonás mindkét irányba) | — | **OK** |
| `elengedes-12/13` (visszautalás) | — | **OK** |

A javítás determinisztikus kapu, nem prompt — a promptos kísérlet
2026-09-05-én mérve megbukott.

## A rétegek mai állása (85 eset, 1. futás)

| réteg | eredmény | | réteg | eredmény |
|---|---|---|---|---|
| alkudozas | 100% | | szleng | 100% |
| egyszerusitett | 100% | | tajszolas | 93% |
| toredekes | 100% | | mintan_tul | 94% |
| kapuor | 100% | | koznyelvi | 80% |
| valtozatossag | 80% | | mindegy | 75% |
| **elengedes** | **47%** | | | |

Az `elengedes` továbbra is a leggyengébb — de most 15 eseten mérve,
tehát a szám a rendszerről szól, nem egy billenésről. A bukások
egyfélék: **a modell ragaszkodik a korábbi bolthoz**, amikor a vásárló
elengedi (`elengedes-01/02/06/07/08`) vagy másikat nevez meg
(`elengedes-14`). Ez ismert korlát (`docs/ALTALANOSITAS.md` 2.9), és
mostantól hat eset méri, nem kettő.

## Reprodukció

```
python feladat.py golden --ertelmezo forditott --ismetles 2 --json uj.json
python feladat.py golden --ertelmezo forditott --elozo uj.json
python -m pytest tests/egyseg/test_forditott_kaszkad.py -k "mindegy or visszautalas"
```

Nyers kimenetek: `spike/meres_20260912/nyelvi_85.{json,log}`.

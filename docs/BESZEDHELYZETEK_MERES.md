# A beszédhelyzetek halmaz első mérése

**Dátum:** 2026-08-31 · **Halmaz:** `tests/golden/beszedhelyzetek.yaml`,
23 eset, 9 réteg · **Értelmező:** `forditott` · **Ablak:** 4 forduló ·
**Prompt:** v1

```
python feladat.py golden --halmaz beszedhelyzetek                    # determinisztikus alapvonal
APRAJAFALVA_LLM_MODELL=qwen3.5:9b python feladat.py golden \
  --ertelmezo forditott --halmaz beszedhelyzetek
```

## Mit mér ez a halmaz

A `nyelvi_alap.yaml` azt méri, HOGYAN mondja a vásárló (köznyelv,
tájszólás, szleng, töredék); ez azt, hogy MILYEN HELYZETBEN beszél. A
mondatok felszíne köznyelvi — a nehézség a beszédhelyzetben van:

| réteg | a helyzet | példa |
|---|---|---|
| `masnak` | nem magának foglal | „Az anyámnak kellene időpont a Szundiba holnapra." |
| `felteteles` | feltételes tervezés | „Ha esik, akkor inkább szerdán…" |
| `osszehasonlitas` | boltok összevetése | „Melyik boltban van hamarabb hely?" |
| `korabbi_foglalas` | hivatkozás azonosítás nélkül | „Ugyanoda, mint múltkor." |
| `tobb_idopont` | két időpont egy kérésben | „Kellene kettő, egymás után." |
| `udvariassag` | a beszélgetés vége | „Köszönöm szépen, viszlát!" |
| `meggondolas` | teljes visszavonás | „Mégsem kell, elnézést." |
| `kozbevetes` | közbekérdezés foglalás közben | „És meddig tart ez egyáltalán?" |
| `szohasznalat` | szokatlan ige | „bejelentkeznék", „lestoppolnék" |

**A várt viselkedés sokszor a visszakérdezés vagy az udvarias
elhárítás.** Öt eset kifejezetten olyan kérést tartalmaz, amit a v1
rendszer nem tud teljesíteni (boltok összehasonlítása, két időpont
egyszerre, korábbi foglalás azonosítás nélkül, jogosultsági
szabály-kérdés). Ezeknél a helyes válasz nem az, hogy valamit mégis
csinálunk.

## Eredmények

| réteg | szabály-alapú | `qwen3.5:9b` | `qwen3:8b` |
|---|---|---|---|
| masnak | 100,0% | **100,0%** | 100,0% |
| felteteles | 50,0% | **100,0%** | 50,0% |
| osszehasonlitas | 100,0% | **100,0%** | 100,0% |
| korabbi_foglalas | 100,0% | **100,0%** | 50,0% |
| tobb_idopont | 100,0% | **100,0%** | 100,0% |
| udvariassag | 0,0% | **100,0%** | 100,0% |
| meggondolas | 0,0% | **100,0%** | 0,0% |
| kozbevetes | 33,3% | 66,7% | 100,0% |
| szohasznalat | 100,0% | **100,0%** | 100,0% |
| **összesített** | **69,6%** | **95,7%** | **82,6%** |

Válaszidő (`qwen3.5:9b`, 28 forduló): p50 3,63 s, p95 3,92 s, max 3,96 s.

## Amit a számok mögött érdemes látni

**1. A szokatlan szóhasználat NEM volt nehéz — se a modellnek, se a
szabályoknak.** Mind az öt eset („bejelentkeznék", „sorszámot kérnék",
„beugranék", „lestoppolnék", „föliratkoznék") 100%. A magyarázat
kijózanító: a szándékot ezekben a mondatokban nem az IGE hordozza,
hanem a bolt és a nap — és azokat a determinisztikus réteg is
megtalálja. A réteg attól még jó, hogy könnyű: ha egy jövőbeli
egyszerűsítés a szándékfelismerést igelistára szűkítené, ez a réteg
bukna elsőként.

**2. Az udvariassági kör és a meggondolás a determinisztikus réteg vak
foltja** (0% mindkettőn), a modellé nem (100%). Ez a két réteg méri a
legtisztábban, mit ad a modell a szólistához képest: a „Köszönöm
szépen, viszlát!" és a „Mégsem kell, elnézést" tele van olyan szóval,
amit egy mintaillesztő nem tud hova tenni — a jelentésük viszont
egyértelmű: ne csinálj semmit.

**3. Az egyetlen `qwen3.5:9b` bukás a `kozbevetes-02`.** A mondat
„Amúgy hol van pontosan a bolt?" — a modell `bolt_info` (cím) helyett
keresést indított, a boltot helyesen hozva a beszélgetésből:

```json
{"eszkoz": "szabad_idopontok",
 "parameterek": {"bolt_id": "szundi", "szolgaltatas_id": "altato",
                 "datum_tol": "2026-08-17T09:00:00Z",
                 "datum_ig": "2026-08-23T23:59:59Z", "napszak": "barmikor"},
 "bizonyossag": {"eszkoz": 0.885, "bolt_id": 0.9999}}
```

A hiba szerkezete tanulságos: a bolt-azonosítás tökéletes (0,9999), az
ESZKÖZ-választás bizonytalanabb (0,885) — a modell a foglalási
szándékot vitte tovább egy tényválasz-kérdésre. Ugyanez a réteg a
`qwen3:8b`-nél 100%: itt a nagyobb modell rontott el valamit, amit a
kisebb eltalált. Egyetlen esetből ebből nem következik semmi az
egyikről sem — a réteg n=3, és egy eset 33 százalékpont.

**4. A `qwen3:8b` a meggondolást rontja el rendszeresen** (0/2): a
„Mégsem kell, elnézést" után visszakérdez. Ez nem pontatlanság, hanem
udvariatlanság: a rendszer nyaggatja a vásárlót, aki épp azt mondta,
hogy nem kér semmit.

## Ismert korlát: a mérés az ÉRTELMEZÉST méri, nem a mondatot

A halmaz a `{eszkoz, parameterek}` alakot pontozza, tehát a
`udvariassag` rétegen azt méri, hogy a rendszer `nincs`-et ad — nem
azt, hogy udvarias-e a válasz, amit a vásárló lát. A mai válasz erre a
kapuőr elhárító mondata („Ez a kérdés nem foglalással kapcsolatos…"),
ami egy „Köszönöm, viszlát!"-ra **helyes, de nem szép**. A javítása a
válaszrétegé (`assistant/valasz/`), és külön lépés — ide azért került
be, hogy ne felejtődjön el: a 100% ezen a rétegen az értelmezés 100%-a,
nem a beszélgetésé.

## Reprodukció

Nyers kimenetek: `spike/meres_20260831/besz_v1.{json,log}` (9b),
`besz_v2.{json,log}` (9b, v2 prompt), `besz_v3.{json,log}` (9b, v3),
`q8_besz_v1.{json,log}` (8b).

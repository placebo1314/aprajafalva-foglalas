# A csúszó előzmény-ablak mérése

**Dátum:** 2026-08-31 · **Modell:** `qwen3.5:9b` (Ollama, `temperature 0`,
`think: false`) · **Értelmező:** `forditott` · **Prompt:** `v1` ·
**Gép:** RTX 4060 Laptop, 8 GB VRAM

A döntés az ADR-025-ben van, ez a mérés maga: **mennyivel rövidül a
prompt, és romlik-e tőle a pontosság.**

Két külön kérdés, két külön mérés — és ez nem formaság: a hossz-mérés
egy húsz fordulós beszélgetésen fut (ott számít az ablak), a
pontosság-mérés a golden seten (ahol a leghosszabb eset három fordulós).
Egyik sem helyettesíti a másikat.

## 1. Hossz — `python -m tools.ablak_meres`

Fixture: 20 forduló, 40 sor (`tools/ablak_meres.py::BESZELGETES`) — egy
döcögő, valósághű menet: alkudozás, két üres keresés, egy elengedett
mező, témaváltás. A mért 21. mondat egy sorszámos hivatkozás („akkor a
másodikat kérem"), mert pont ez az a fajta mondat, ami miatt az utolsó
fordulóknak szó szerint kell átmenniük.

| ablak | beszélgetés-rész (karakter) | ebből − | teljes prompt | ebből − |
|---|---|---|---|---|
| nincs (alapvonal) | 1872 | 0,0% | 6649 | 0,0% |
| 8 forduló | 850 | 54,6% | 6047 | 9,1% |
| **4 forduló (éles)** | **477** | **74,5%** | **5674** | **14,7%** |
| 2 forduló | 366 | 80,4% | 5563 | 16,3% |
| 1 forduló | 261 | 86,1% | 5458 | 17,9% |

Ugyanez a `v2` rendszerprompttal (ADR-026), ahol az állandó tag maga is
kisebb:

| ablak | teljes prompt | ebből − |
|---|---|---|
| nincs | 4356 | 0,0% |
| **4 (éles)** | **3381** | **22,4%** |
| 1 | 3165 | 27,3% |

**Miért két oszlop.** A beszélgetés-részre hat az ablak — ott a
rövidülés 74,5%. A teljes promptban viszont ott a rendszerprompt is,
ami minden híváshoz megy, és hígítja az arányt. Csak az egyik számot
kiírni mindkét irányban félrevezetne: „74%-kal rövidebb prompt" hamis,
„mindössze 15%" viszont eltakarja, hogy a NÖVEKVŐ rész zsugorodott 74%-kal.
Húsz forduló fölött a különbség nő, mert az alapvonal tovább nő, az
ablakos változat nem.

**Az összefoglaló sor, ahogy a modell látja** (ablak=4, a fenti
fixture-ön):

```
Összefoglaló (16 korábbi forduló): bolt=ugyifogyi; szolgáltatás=nagy_petarda;
napszak=delutan; eddig keresett napok: 2026-08-19, 2026-08-20, 2026-08-21;
üresen tért vissza 2 keresés
```

16 forduló → egy sor. A négy megtartott forduló szó szerint követi.

### Mibe kerül maga az ablakolás

Az összefoglaló determinisztikusan készül: a levágott vásárlói
mondatokat a szabály-alapú értelmező olvassa el. Ez idő — de mennyi?

```
ablakolás 20 fordulós előzményen: 14,5 ms / hívás
```

Egy modellhívás ugyanezen a gépen 3,6–3,8 s. Az ablakolás tehát a
forduló idejének **0,4%-a**, és felülről korlátos: a felület
legfeljebb 60 sort ad át (`_ELOZMENY_SOROK`), tehát a szám nem nő a
beszélgetéssel a végtelenségig. Egy modellhívásos összefoglaló ehelyett
másodperceket vinne — pont azt, amit az ablak megspórol.

## 2. Pontosság — `python feladat.py golden --ertelmezo forditott`

51 eset, nyelvi halmaz, ugyanaz a modell és kód, csak az
`APRAJAFALVA_ABLAK_FORDULO` változik:

| ablak | összesített | alkudozas | mintan_tul | elengedes | mindegy | p50 |
|---|---|---|---|---|---|---|
| nincs (alapvonal) | 90,2% | 100% | 100% | 33,3% | 83,3% | 3,67 s |
| **4 (éles)** | **90,2%** | 100% | 100% | 33,3% | 83,3% | 3,68 s |
| 1 (agresszív) | 90,2% | 100% | 100% | 33,3% | 83,3% | 3,64 s |

**Rétegenként is azonos, mind a tizenegy rétegen.** Nem kerekítés: a
bukott esetek is ugyanazok.

### Ezt őszintén kell kimondani: mit mér ez, és mit nem

- **Az `ablak=4` sor nem bizonyít semmit**, mert az ablak be sem kapcsol:
  a nyelvi halmaz leghosszabb esete háromfordulós, tehát négy forduló
  alatt marad. A 90,2% ott ugyanaz a szám, ugyanabból a lefutásból.
- **Az `ablak=1` sor bizonyít.** Ott a tömörítés a kétfordulós eseteken
  IS bekapcsol (ellenőrizve: a `mintan_tul-06-visszavonas` esetben a
  modell egy összefoglaló sort kap az első forduló helyett) — és a
  pontosság nem mozdul. Az az eset ráadásul épp visszahivatkozik az
  első fordulóra („mégsem, inkább maradjunk a keddnél"), és továbbra is
  helyes marad.
- **Amit egyik sem mér: a húsz fordulós beszélgetést.** Olyan golden
  esetünk nincs, és kitalálni hamisítás lenne. A hossz-mérés fixture-je
  húsz fordulós, de arra nincs elfogadott helyes válasz — csak
  promptot mérünk rajta, pontosságot nem.

Ebből az következik, hogy **az ablak mérete nem feltevés, hanem a mérés
határa**: 1 és 4 között nem tudunk különbséget kimutatni a mai
halmazon, ezért a 4 marad — a szélesebb ablak a kockázatosabb
hivatkozásokat (sorszám, visszavonás) is szó szerint viszi, és a
mért ára nulla.

## 3. Mikor kellene ezt újramérni

Az ADR-025 kiváltó feltételei szerint. Gyakorlatilag: amint van legalább
öt olyan golden eset, ami HAT fordulónál hosszabb — akkor az `ablak=4`
sor is mérni fog, nem csak jelen lenni. A `naplo/probak.jsonl`-ből
készülő rejtett halmaz (`python feladat.py naplo --golden <sor>`) ennek a
természetes forrása: a valódi beszélgetések hosszabbak, mint a kézzel
írt tesztesetek.

## Reprodukció

```
python -m tools.ablak_meres
python -m tools.ablak_meres --modell qwen3.5:9b        # valódi tokenszám is
APRAJAFALVA_LLM_MODELL=qwen3.5:9b APRAJAFALVA_ABLAK_FORDULO=0 \
  python feladat.py golden --ertelmezo forditott
APRAJAFALVA_LLM_MODELL=qwen3.5:9b APRAJAFALVA_ABLAK_FORDULO=1 \
  python feladat.py golden --ertelmezo forditott
```

Nyers kimenetek: `spike/meres_20260831/ablak_ki.{json,log}`,
`ablak_4.{json,log}`, `ablak_1.{json,log}`.

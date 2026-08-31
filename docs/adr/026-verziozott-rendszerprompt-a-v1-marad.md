# ADR-026: Verziózott rendszerprompt — és a v1 marad, mert az A/B ezt mondta

- **Dátum:** 2026-08-31
- **Állapot:** elfogadott

## Kontextus

A rendszerprompt (`assistant/interpreter/llm_based.py`) eddig egyetlen,
verziószám nélküli szöveg volt. Két baj következett ebből:

1. **Nem lehetett A/B-zni.** Egy prompt-változtatás előtti és utáni
   mérés csak úgy volt összehasonlítható, ha a régi szöveget kézzel
   visszamásoljuk — vagyis a régi verzió a git-történetben él, nem
   futtatható alakban.
2. **A naplóból nem derült ki, mivel futott a forduló.** Egy hét múlva
   egy furcsa válaszról nem lehetett megmondani, melyik prompt adta.

Közben felmerült, hogy a promptot a „mért gyakorlatok" szerint kellene
átépíteni: kritikus megkötések elöl, kevés de sokféle példa,
tömörítés — és hogy ez javítana.

## Döntés

**A rendszerprompt verziózott** (`PROMPTOK`, `PELDAKESZLETEK`,
`APRAJAFALVA_PROMPT_VERZIO`), a verzió **bekerül a próba-naplóba**
(`prompt_verzio` mező) — **és az éles verzió a `v1` marad**, mert a
mérés szerint az átépített változat nem javít.

Három verzió él egymás mellett, mind futtatható:

| verzió | szerkezet | példák | hossz |
|---|---|---|---|
| **v1 (éles)** | megkötések a prompt közepén | 15 | 4758 karakter |
| v2 | megkötések elöl, tömör | 6 | 2465 |
| v3 | megkötések elöl, tömör | 15 | 3819 |

## A mérés (részletesen: `docs/PROMPT_AB.md`)

`qwen3.5:9b`, `forditott`, 51 eses nyelvi halmaz:

| verzió | összesített | p50 | mit mutat |
|---|---|---|---|
| **v1** | **90,2%** | 3,68 s | — |
| v2 | 75,5% | 3,80 s | −14,7 pont |
| v3 | 89,2% | 3,66 s | −1,0 pont (zaj) |

Beszédhelyzetek (23 eset): v1 95,7% → v2 87,0%.

**A v2/v3 páros szétválasztja a két változtatást**: a v3 ugyanaz a
tömör szerkezet, de a TELJES példakészlettel. Ebből:

- **a példák elhagyása −13,7 pont** — és pontosan azokon a rétegeken
  esik, amiknek a példáját kivettük (tájszólás 100→50, töredékes
  100→50, szleng 100→33);
- **a szerkezet átrendezése −1,0 pont**, ami az 51 eses halmazon fél
  esetnyi, tehát zaj.

## Miért

- **A verziózás önmagában is megéri**, függetlenül attól, melyik verzió
  éles: enélkül nem lett volna ez a mérés, és a naplóból nem derülne ki,
  mivel futott egy forduló.
- **A v1 marad, mert nem javít semmi.** Ez a saját szabályunk („ha nem
  javít, ne vezesd be"), és most magunkra kellett alkalmazni: a v2/v3
  átépítés a mi ötletünk volt, jól hangzott, és a mérés megcáfolta.
- **A rövidebb prompt nem gyorsabb.** 48%-kal kevesebb rendszerprompt
  (v2) mellett a p50 nem javult (3,68 → 3,80 s). Ezen a méreten a
  válaszidőt a generálás viszi, nem a prompt beolvasása — a tömörítés
  tehát ma nem latencia-eszköz.

## Amit feladunk

- **Két nem használt prompt karbantartását.** A v2 és a v3 a repóban
  marad, és minden séma-változásnál (új mező, új eszköz) rájuk is
  gondolni kell. Ez valódi teher — cserébe a mérés megismételhető, és a
  következő modellváltásnál nem nulláról kell újrakezdeni.
- **A „szép prompt" ígéretét.** A v1 hosszabb és rendezetlenebb; tudjuk,
  hogy tömörebben is le lehetne írni ugyanazt. Amíg a mérés nem
  igazolja, hogy ez bármit ad, az esztétika nem elég indok.

## Kiváltó feltétel

Bármelyik önmagában újranyitja a döntést:

- **modellváltás.** A példák súlya modellfüggő — egy másik modellnél a
  v3 (tömör szerkezet, teljes példakészlet) nyerhet. A
  modell-összehasonlítás része legyen mindhárom verzió mérése.
- a v3 két KÖVETKEZŐ mérésen is legalább **3 százalékponttal** jobb, mint
  a v1 (egy futás különbsége zaj, kettőé már nem az);
- a prompt beolvasása mérhetően belassul (pl. sokkal hosszabb
  előzmény-összefoglaló vagy több példa miatt), és a `prompt_eval`
  ideje a teljes válaszidő **30%-a fölé** kerül — ekkor a tömörítés
  latencia-eszközzé válik, és a v3 ingyen nyereség lesz.

## Váltás mire

`ALAP_PROMPT_VERZIO = "v3"` — egy sor. A példakészlet nem változik, csak
a köré írt szöveg.

## Váltás költsége

Egy konstans és egy újramérés. A kockázat az, hogy a v3 `mintan_tul`
vesztesége (100% → 83,3%) nem zaj, hanem valódi — ezt a váltás előtt
két futással kell megnézni, nem eggyel.

## Ellenőrzés

```
APRAJAFALVA_PROMPT_VERZIO=v1 python feladat.py golden --ertelmezo forditott
APRAJAFALVA_PROMPT_VERZIO=v2 python feladat.py golden --ertelmezo forditott
APRAJAFALVA_PROMPT_VERZIO=v3 python feladat.py golden --ertelmezo forditott
python feladat.py naplo        # a "Modell és prompt" blokk fordulónként
```

# Rendszerprompt A/B — v1 vs. v2 (vs. v3)

**Dátum:** 2026-08-31 · **Modell:** `qwen3.5:9b` · **Értelmező:**
`forditott` · **Ablak:** 4 forduló · **Halmaz:** nyelvi (51 eset) és
beszédhelyzetek (23 eset) · `temperature 0`, `think: false`

## Mit mértünk

A v2 a „mért prompt-gyakorlatok" szerint épült át, **három
változtatással egyszerre**:

1. a kritikus megkötések a prompt ELEJÉRE (számozott lista: ne találj
   ki adatot, zárt halmazok, dátum a parserből, időpont csak az utolsó
   mondatból, MINDEGY) — a v1-ben ezek a prompt közepén és végén álltak;
2. **kevesebb, de egymástól távolabbi példa**: 15 → 6, a legjellemzőbb
   esettel a végén;
3. tömörítés: ami nem hordoz döntést, kimaradt.

Prompt-hossz (a példákkal együtt, összefoglaló-útmutató nélkül):

| verzió | karakter | v1-hez képest |
|---|---|---|
| v1 | 4758 | — |
| v2 | 2465 | −48,2% |
| v3 | 3819 | −19,7% |

## Az eredmény: a v2 ROSSZABB, ezért nem vezetjük be

Nyelvi halmaz, 51 eset:

| réteg | v1 | v2 | különbség |
|---|---|---|---|
| koznyelvi | 80,0% | **100,0%** | +20,0 |
| tajszolas | 100,0% | 50,0% | **−50,0** |
| toredekes | 100,0% | 50,0% | **−50,0** |
| szleng | 100,0% | 33,3% | **−66,7** |
| egyszerusitett | 100,0% | 75,0% | −25,0 |
| alkudozas | 100,0% | 100,0% | 0 |
| elengedes | 33,3% | 33,3% | 0 |
| mindegy | 83,3% | 83,3% | 0 |
| mintan_tul | 100,0% | 83,3% | −16,7 |
| valtozatossag | 80,0% | 80,0% | 0 |
| kapuor | 100,0% | 100,0% | 0 |
| **összesített** | **90,2%** | **75,5%** | **−14,7** |
| p50 válaszidő | 3,68 s | 3,80 s | +0,12 s |

Beszédhelyzetek halmaz, 23 eset: **95,7% → 87,0%** (−8,7).

**Döntés: marad a v1** (`ALAP_PROMPT_VERZIO = "v1"`). A v2 a repóban
marad, `APRAJAFALVA_PROMPT_VERZIO=v2`-vel bármikor újramérhető — ez a
mérés visszaútja, nem holt kód.

## Ami ebből tanulság, és nem csak eredmény

**1. A stílus-példák nem díszek — ők tartják a stílusrétegeket.**
A három legnagyobb esés (tájszólás, töredékes, szleng) pontosan az a
három réteg, aminek a példáját kivettük. A „sokféleség > darabszám"
elv itt megbukott, mert a példák nem ugyanazt tanították más szavakkal:
a `csütörtök… boldogság… lehetne?` mintája nem levezethető egy
köznyelvi példából. A v2 kommentárja ezt előre megkockáztatta („a
stílust a modell nyelvi tudása hozza") — a mérés megcáfolta.

**2. A megkötések előrehozása ÖNMAGÁBAN javított.** A `koznyelvi`
réteg 80% → 100%: a v1-ben elmaradó `koznyelvi-02`
(„Mikor tudok legkorábban menni Törpillához?" → `legkozelebbi_idopont`)
a v2-ben helyes lett. Ez az egyetlen réteg, ami javult — és épp az,
amelyiknek a hibája instrukció-jellegű volt, nem stílusbeli.

**3. A rövidebb prompt NEM lett gyorsabb.** 48%-kal kevesebb
rendszerprompt mellett a p50 3,68 s → 3,80 s, azaz nem mérhető javulás
(inkább zaj). Ez a Vapi-tanulság („a prompt hossza latencia") határa
ezen a méreten: a mai promptok teljes hossza 3–5 ezer karakter, és a
válaszidőt a GENERÁLÁS viszi, nem a prompt beolvasása. Ebből az
következik, hogy **a prompt tömörítése ma nem latencia-eszköz** — ha a
hangcsatorna SLO-ja szorít, máshol kell keresni (rövidebb kimenet,
kisebb modell, gyorsabb dekódolás).

## v3 — a két változtatás szétválasztva

A v2 két dolgot változtatott egyszerre, tehát a −14,7 pontból nem derül
ki, melyik ártott. A v3 az egyiket visszaveszi: **a v2 tömör,
megkötés-előre szerkezete + a v1 teljes, 15 elemű példakészlete.**

| verzió | szerkezet | példák | hossz | nyelvi | p50 |
|---|---|---|---|---|---|
| v1 | megkötések középen | 15 | 4758 | **90,2%** | 3,68 s |
| v2 | megkötések elöl, tömör | 6 | 2465 | 75,5% | 3,80 s |
| v3 | megkötések elöl, tömör | 15 | 3819 | **89,2%** | 3,66 s |

Rétegenként, v1 → v3:

| réteg | v1 | v3 | különbség |
|---|---|---|---|
| koznyelvi | 80,0% | **100,0%** | +20,0 |
| mintan_tul | 100,0% | 83,3% | −16,7 |
| tajszolas / toredekes / szleng | 100% | 100% | 0 |
| egyszerusitett / alkudozas | 100% | 100% | 0 |
| elengedes / mindegy / valtozatossag | 33,3 / 83,3 / 80,0% | ugyanaz | 0 |
| **összesített** | **90,2%** | **89,2%** | **−1,0** |

**Ez válaszolja meg a kérdést: a példák hiánya ártott, nem a
szerkezet.** A v3 ugyanazzal a tömör, megkötés-előre szerkezettel fut,
mint a v2, de a teljes példakészlettel — és visszakapja a
stílusrétegeket (tájszólás, töredékes, szleng mind 100%). A −14,7
pontból tehát **−13,7 pont a példák számlájára megy, −1,0 a
szerkezetére** — az utóbbi az 51 eses halmazon fél esetnyi különbség,
azaz zaj.

## Akkor miért nem vezetjük be a v3-at?

Mert **nem javít**, és a rövidebb prompt ezen a méreten nem hoz
sebességet sem (p50 3,66 s vs. 3,68 s — mérési zaj). Marad a szabály,
amit magunknak írtunk: *ha nem javít, ne vezesd be.* Egy 19,7%-kal
rövidebb prompt önmagában nem érték, csak akkor, ha valamit ad — időt,
pontosságot vagy érthetőséget.

Ami a v3 mellett szólna: a `koznyelvi` réteg 80% → 100%. Ami ellene: a
`mintan_tul` 100% → 83,3%. A kettő kioltja egymást, és mindkettő egy-egy
eset — ennyi különbségre nem cserélünk éles promptot.

**A v2 és a v3 a repóban marad**, `APRAJAFALVA_PROMPT_VERZIO`-val
futtatható. Nem holt kód: ez a mérés visszaútja, és a következő
modellváltásnál (ahol a példák súlya más lehet) újra kell futtatni
mindhármat.

## Reprodukció

```
APRAJAFALVA_LLM_MODELL=qwen3.5:9b APRAJAFALVA_PROMPT_VERZIO=v1 \
  python feladat.py golden --ertelmezo forditott
APRAJAFALVA_LLM_MODELL=qwen3.5:9b APRAJAFALVA_PROMPT_VERZIO=v2 \
  python feladat.py golden --ertelmezo forditott
APRAJAFALVA_LLM_MODELL=qwen3.5:9b APRAJAFALVA_PROMPT_VERZIO=v3 \
  python feladat.py golden --ertelmezo forditott
```

Nyers kimenetek: `spike/meres_20260831/ablak_4.{json,log}` (= v1),
`prompt_v2.{json,log}`, `prompt_v3.{json,log}`, `besz_v1.{json,log}`,
`besz_v2.{json,log}`, `besz_v3.{json,log}`.

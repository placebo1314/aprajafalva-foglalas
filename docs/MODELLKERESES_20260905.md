# Újabb modellek keresése — 2026-09-05

**Gép:** RTX 4060 Laptop, 8188 MB VRAM · **Ollama:** 0.33.2 ·
**Értelmező:** `forditott`, v1 prompt, `num_ctx=8192`, 4 fordulós ablak,
`temperature 0` · **Halmazok:** nyelvi (55 eset), beszédhelyzetek
(28 eset) — mindkettő BŐVÍTVE ebben a körben

## Mi változott a mezőnyben

Az eddigi jelöltjeink (`qwen3.5`, `qwen3`, `gemma3`, `qwen2.5`) közül a
legújabb is hónapokkal ezelőtti. A könyvtár azóta mozgott:

| család | mai legkisebb változat | belefér 8 GB-ba? |
|---|---|---|
| **Gemma 4** (2026. április) | `e2b-it-qat` 4,3 GB, `e4b-it-qat` 6,1 GB, `12b-it-qat` 7,2 GB | igen / igen / részben |
| Qwen3.6 | 27B, 17 GB | **nem** |
| Qwen3.8 | 27B | **nem** |
| Nemotron-3.5-Lightning | 30B-A3B, 23 GB | **nem** |

A 2026-os nagy modellek java 27B-nél kezdődik — azok ezen a kártyán nem
mérhetők tisztességesen. **A Gemma 4 az egyetlen új család, aminek van
8 GB alatti, komoly változata**, és ráadásul **Apache-2.0** licencű
(a Gemma 3 még saját Gemma-feltételekkel jött) — tehát az ADR-013
kikötését is teljesíti, nem csak ellenőrző jelölt lehetne.

## A mérés

| modell | betöltve / VRAM | kiszervezés | nyelvi (55) | leggyengébb réteg | beszédhelyzetek (28) | leggyengébb réteg | együtt | p50 |
|---|---|---|---|---|---|---|---|---|
| **`qwen3.5:9b`** (éles) | 5368 MB / 5368 | nincs | **86,4%** | `elengedes` **40%** | 85,7% | `felteteles` 50% | 86,1% | **3,84 s** |
| `gemma4:12b-it-qat` | 8144 MB / 5740 | **30% CPU** | 83,6% | `elengedes` 20% | **96,4%** | `korabbi_foglalas` 50% | **88,0%** | 6,07 s |
| `gemma4:e4b-it-qat` | 2947 MB / 2947 | nincs | 67,3% | `elengedes` 40% | 89,3% | `szohasznalat` 40% | 74,7% | 3,11 s |
| `gemma4:e2b-it-qat` | 1707 MB / 1707 | nincs | 65,5% | `alkudozas` 33% | 80,4% | `felteteles` 50% | 70,5% | 2,73 s |

## A kép, amit ez ad — és amiért NEM váltunk

**1. A két halmaz ellentétesen rangsorol.** A `gemma4:12b` a
beszédhelyzeteken 96,4% (a valaha mért legjobb szám ezen a halmazon),
a `qwen3.5:9b` viszont a nyelvi halmazon jobb 2,8 ponttal. A két
halmaz mást mér: a nyelvi a magyar mondat FELSZÍNÉT (tájszólás, szleng,
töredék), a beszédhelyzetek a HELYZET megértését (kinek foglal, mit
von vissza, mire kérdez rá). **A Gemma 4 a pragmatikában erősebb, a
magyar nyelvi rétegekben gyengébb.**

**2. A projekt mérőszáma a leggyengébb réteg, nem az átlag** (blueprint
7.). Azon a `qwen3.5:9b` nyer: `elengedes` 40% vs. 20%. Az átlag a
`gemma4:12b`-nek kedvez (88,0 vs. 86,1) — de az átlag mögött épp az a
réteg gyengül, ami a beszélgetés-értés magja.

**3. A 12B ára idő: p50 6,07 s vs. 3,84 s (+58%)**, mert a 8144 MB-os
modell 30%-a a CPU-ra kerül. Ez a hangcsatorna felé nézve a fontosabb
szám: a `docs/ALLAPOT.md` szerinti kétpontos elvárás (p50 < 10 s) még
tartja, de a tartalék elfogy.

**4. A kis Gemmák nem jelöltek.** Az `e4b` és az `e2b` a nyelvi
halmazon 67,3% és 65,5% — a mai szintnél 19-21 ponttal rosszabb. Amit
viszont megmutatnak: **a beszédhelyzeteken az `e4b` (89,3%) jobb, mint
a nálánál háromszor nagyobb `qwen3.5:9b` (85,7%)**. Egy 3 GB-os modell,
ami a pragmatikát jobban érti — ez a tokenizálás/tanítás különbsége,
nem a méreté.

**Döntés: marad a `qwen3.5:9b`.** Az ADR-013 kiváltó feltétele (>5
százalékpont javulás a leggyengébb rétegen) nem teljesült.

## Amikor ez a döntés megfordul

- **Nagyobb kártyán azonnal újramérendő.** A `gemma4:12b` kiszervezés
  nélkül más szám lenne, és ma a mezőny legjobb pragmatikáját hozza.
- **Ha a beszédhelyzetek halmaz súlya nő** (mert a valódi
  beszélgetésekben az a jellemző hibaforrás), a rangsor megfordul.
- **Ha megjelenik 8 GB alatti Qwen3.6/Gemma 4 mid-size változat** — ma
  a Qwen3.6 legkisebbje 17 GB.

## A bővített halmazok két új hibát találtak — és egy javítás megbukott

A nyelvi halmaz négy, a beszédhelyzetek öt esettel bővült ebben a
körben. Kettő azonnal talált:

**1. A MINDEGY ragadós** (`mindegy-07`): aki elengedett egy mezőt
(„Bármelyik petárda jó"), az nem tudja visszavonni („mégis inkább a
nagyot kérem") — a rendszer marad a `MINDEGY`-nél. **Mind a négy mért
modellen ugyanígy.**

Megpróbáltuk prompttal javítani (egy mondat a v1 promptban: *„Az
elengedés VISSZAVONHATÓ: … FELÜLÍRJA a korábbi MINDEGY-et"*), és
megmértük:

| | nyelvi (55) | `mindegy-07` |
|---|---|---|
| alap (szabály nélkül) | 86,4% | bukik |
| szabállyal, 1. futás | 85,5% | **továbbra is bukik** |
| szabállyal, 2. futás | 83,6% | **továbbra is bukik** |

**A szabályt ezért NEM vezettük be** (a saját szabályunk: ha nem javít,
ne vezesd be). A célzott eset nem fordult meg, az összesített szám nem
javult. A determinisztikus javítás (mondatbeli konkrét érték felülírja
a MINDEGY-et) sem járható ma: a szabály-alapú réteg a „nagyot" alakot
nem oldja fel (`nagy` nem illeszkedik a toldalékolt alakra), és a
mintát kitágítani ráigazítás lenne — a „nagyon sietek" mondatból lenne
tőle petárdaméret. A bukás így KORLÁTKÉNT marad
(`docs/ALTALANOSITAS.md` 2.9d).

**2. A szolgáltatás nem él túl egy fordulót** (`elengedes-05`): az
„és csütörtökön ugyanez?" mondatnál a bolt átjön, a szolgáltatás nem.
Szintén mind a négy modellen. Ez nem hibás foglalás, csak tágabb
keresés — korlátként rögzítve (`docs/ALTALANOSITAS.md` 2.9c).

## Ami a mérésből MELLÉKESEN kiderült

A `gemma4:e4b` első hívása 15,9 s volt (hideg betöltés), a melegek
2,8-3,1 s. A `vram_meres` a második hívástól mér — enélkül a betöltés
ideje a modellre íródna.

## Reprodukció

```
APRAJAFALVA_LLM_MODELL=gemma4:12b-it-qat python feladat.py golden \
  --ertelmezo forditott --halmaz nyelvi
APRAJAFALVA_LLM_MODELL=gemma4:12b-it-qat python feladat.py golden \
  --ertelmezo forditott --halmaz beszedhelyzetek
python -m tools.vram_meres --modell gemma4:12b-it-qat --num-ctx 8192
```

Nyers kimenetek: `spike/meres_20260905/*.{json,log}`.

# Kontextusméret, VRAM és kiszervezés — a mérés

**Dátum:** 2026-09-01 · **Gép:** RTX 4060 Laptop, **8188 MB VRAM** ·
**Ollama:** 0.33.2 · **Értelmező:** `forditott`, v1 prompt, 4 fordulós
ablak · **Halmaz:** nyelvi (51 eset)

A kiinduló feltevés az volt, hogy **a csendes CPU-visszaesés lehet a
gyökérok**: ha a kontextus nem fér a VRAM-ba, a modell egy része a CPU-n
fut, és ez nemcsak lassít, hanem a strukturált kimenetet is ronthatja.
Ez a dokumentum azt írja le, mi ebből igaz ezen a gépen.

## 1. Mi volt a kontextusméret eddig? 8192 — véletlenül a jó érték

A hívás nem adott meg `num_ctx`-et, tehát a szolgáltató alapértelmezése
döntött. Az Ollama 0.33.2 ma **8192**-t ad:

```
NAME          SIZE      PROCESSOR    CONTEXT
qwen3.5:9b    5.6 GB    100% GPU     8192
```

**Kiszervezés tehát nem volt.** A feltevés gyökérok-változata ezen a
gépen nem igazolódott — de az érték nem a miénk volt: verziófüggő, és az
`OLLAMA_CONTEXT_LENGTH` bármikor felülírja. Mostantól explicit
(ADR-027), és az érték ugyanaz a 8192, tehát **a beállítás önmagában
nem javított semmit** (l. a 2. pontot). Ez nem kudarc: egy mérés akkor
ér valamit, ha megismételhető.

## 2. Az explicit `num_ctx` A/B — nincs különbség, és ez a jó hír

| beállítás | kontextus | kiszervezés | pontosság | p50 |
|---|---|---|---|---|
| implicit (2026-08-31-i mérés) | 8192 | 100% GPU | 90,2% | 3,67 s |
| **explicit `num_ctx=8192`** | 8192 | 100% GPU | **90,2%** | 3,67 s |

Rétegenként is azonos. Ez a várt eredmény: ugyanazt kértük, amit eddig
kaptunk — csak most már tudjuk is, hogy azt kaptuk.

*(A későbbi, ismételt futások 91,2%-ot adtak — az egy pont különbség a
prompthoz idő közben hozzáadott `jelolt_valasztas` sorból és a
futásonkénti szórásból jön, l. a 3. pontot.)*

## 3. Mi történik, ha TÉNYLEG nem fér be? — kiszervezés kikényszerítve

Ugyanaz a modell, `num_ctx=65536`:

| | `num_ctx=8192` | `num_ctx=65536` |
|---|---|---|
| betöltött méret | 5368 MB | 8123 MB |
| ebből VRAM-ban | 5368 MB (**100%**) | 5206 MB (**64%**) |
| kiszervezve CPU-ra | — | **36%** |
| rövid hívás (meleg) | **3,10 s** | **4,17 s** |

**A LATENCIA-hatás valódi és ismételhető: +35%.**

A pontosságra viszont **kétszer futtattuk mindkét beállítást**, és a
kép megfordult:

| futás | `num_ctx=8192` (nincs kiszervezés) | `num_ctx=65536` (36% CPU) |
|---|---|---|
| 1. mérés | 90,2% | 86,3% (**−3,9**) |
| 2. mérés | 91,2% | 91,2% (**0,0**) |

**Az első mérés különbsége nem reprodukálódott.** A második futásban a
kiszervezett konfiguráció PONTOSAN ugyanazt adta, mint a kontroll —
esetre pontosan ugyanazokkal a bukásokkal.

### Amit ebből le lehet vonni, és amit nem

A bukások összevetése esetenként:

| eset | ctx8192 #1 | ctx8192 #2 | ctx65536 #1 | ctx65536 #2 |
|---|---|---|---|---|
| `elengedes-01`, `elengedes-02`, `valtozatossag-04`, `mindegy-03` | bukik | bukik | bukik | bukik |
| `koznyelvi-05` | bukik | — | bukik | — |
| `koznyelvi-01` | — | — | **bukik** | — |
| `elengedes-03` | — | — | **bukik** | — |
| `mintan_tul-05` | — | fél pont | — | fél pont |

- **Négy eset MINDIG bukik** — ezek valódi, ismert korlátok, nem
  memóriakezelés.
- **A kiszervezéshez köthető két extra bukás egyszer jelentkezett, és
  egyszer nem.** Egy futásból „a kiszervezés rontja a pontosságot"
  következtetést levonni túlzás lett volna — a második futás megcáfolta.
- **A `temperature: 0` NEM jelent futásonkénti azonosságot.** Ugyanaz a
  kód, ugyanaz a modell, ugyanaz a beállítás két futáson 1-2 esetnyit
  ingadozik (`koznyelvi-05` és `mintan_tul-05` váltakozása). Ez a
  projektben eddig is dokumentált tapasztalat (ADR-019: 2-4 pont
  szórás), és pont ezért kell két futás egy 4 pontos különbséghez.

**A becsületes összegzés tehát:** ezen a gépen, 36%-os kiszervezés
mellett a strukturált kimenetre és a pontosságra **nem tudtunk hatást
kimutatni**; a mérhető ár az idő (+35%). A séma-kényszerítés végig
tartott: JSON parse-hiba egyetlen futásban sem volt.

## 4. A nagy modellek — 8,5 és 10,3 GB egy 8,2 GB-os kártyán

Előre rögzítve: **mindkettő biztosan kiszervez**, tehát a várt eredmény
rosszabb. A mérés azért érdekes, mert megmutatja, MENNYIVEL — és mert a
„rosszabb" nem ugyanaz a kettőnél.

| modell | betöltve | VRAM-ban | kiszervezés | pontosság | golden p50 |
|---|---|---|---|---|---|
| **`qwen3.5:9b`** (éles) | 5368 MB | 5368 MB | **nincs** | **90,2%** | **3,67 s** |
| `qwen3:8b` | 5900 MB | 5900 MB | nincs | 71,6% | 3,33 s |
| `gemma3:12b` | 8507 MB | 5038 MB | **41% CPU** | 88,2% | 7,39 s |
| `qwen2.5:14b` | 10277 MB | 6049 MB | **41% CPU** | 70,6% | 8,61 s |

*(A `gemma3:27b` szándékosan kimaradt: 17,4 GB, több mint kétszerese a
kártyának.)*

**Amit ez mond:**

1. **A kiszervezés ára elsősorban IDŐ.** A `gemma3:12b` 88,2%-ot ért el
   — mindössze 2 ponttal a mai éles modell alatt —, de **kétszer lassabb**
   (7,39 s vs. 3,67 s p50). Egy hangcsatornán ez a különbség dönt, nem a
   két pont.
2. **A méret nem képesség.** A `qwen2.5:14b` a legnagyobb modell a
   mezőnyben, és a második legrosszabb eredményt adta (70,6%). Ez
   generációs különbség (qwen2.5 vs. qwen3.5), nem memóriakezelés — a
   `qwen3:8b` kiszervezés NÉLKÜL adott hasonlóan gyenge 71,6%-ot.
3. **A szakirodalmi elvárás NEM igazolódott a pontosságon.** A
   kiszervezés az ismételt mérésben nem rontott (l. a 3. pontot), és a
   `gemma3:12b` 41%-os kiszervezéssel is 88,2%-ot adott. Amit a
   kiszervezés biztosan visz, az az idő — a `gemma3:12b`-nél kétszeres
   válaszidő, a `qwen2.5:14b`-nél 2,3-szoros.

**Egy futás modellenként**, tehát a 2 pontos különbségek (90,2 vs. 88,2)
a fentiek szerint zajon belül vannak. A 20 pontos különbségek (70,6 és
71,6) nem.

## Reprodukció

```
python -m tools.vram_meres --modell qwen3.5:9b --num-ctx 8192
python -m tools.vram_meres --modell qwen3.5:9b --num-ctx 65536
python -m tools.vram_meres --modell gemma3:12b --num-ctx 8192
APRAJAFALVA_NUM_CTX=65536 APRAJAFALVA_LLM_MODELL=qwen3.5:9b \
  python feladat.py golden --ertelmezo forditott
```

Nyers kimenetek: `spike/meres_20260901/*.{json,log}` (a `*_vram.json`
fájlok a kiszervezés-mérésé).

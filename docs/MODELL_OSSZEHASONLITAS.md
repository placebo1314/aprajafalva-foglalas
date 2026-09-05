# Modell-összehasonlítás: `qwen3.5:9b` vs. `qwen3:8b`

**Dátum:** 2026-08-31 · **Gép:** RTX 4060 Laptop, **8 GB VRAM** ·
**Értelmező:** `forditott` (ADR-018) · **Ablak:** 4 forduló (ADR-025) ·
**Prompt:** v1 · `temperature 0`, `think: false`, Ollama

> **2026-09-05-i kiegészítés.** A mezőny a Gemma 4 családdal bővült
> (`12b-it-qat`, `e4b-it-qat`, `e2b-it-qat`), és a golden halmazok is
> bővültek — az összehasonlítás mostantól **55 + 28 eseten** fut, öt
> modellel. A számok és a döntés (marad a `qwen3.5:9b`):
> `docs/MODELLKERESES_20260905.md`. A LÉNYEG: a `gemma4:12b` a
> beszédhelyzeteken 96,4%-ot ad (a valaha mért legjobbat), de a nyelvi
> halmazon és a leggyengébb rétegen alulmarad, és 58%-kal lassabb.
>
> **2026-09-01-i kiegészítés.** A mezőny két nagy modellel bővült
> (`gemma3:12b`, `qwen2.5:14b`), amik a 8 GB-os kártyán biztosan
> kiszerveznek — a számok és a kiszervezés hatása:
> `docs/NUM_CTX_ES_VRAM.md`. Az összefoglaló négy modellre:
>
> | modell | kiszervezés | pontosság | golden p50 |
> |---|---|---|---|
> | **`qwen3.5:9b`** (éles) | nincs | **90,2%** | **3,67 s** |
> | `gemma3:12b` | 41% CPU | 88,2% | 7,39 s |
> | `qwen3:8b` | nincs | 71,6% | 3,33 s |
> | `qwen2.5:14b` | 41% CPU | 70,6% | 8,61 s |
>
> A döntés nem változott: marad a `qwen3.5:9b`. A `gemma3:12b`
> meglepően közel került pontosságban (−2,0 pont), de kétszer lassabb —
> hangcsatornán ez a különbség dönt, nem a két pont.

## Miért ez a kihívó

A jelenlegi éles modell a `qwen3.5:9b`. A kihívónak három feltételt
kellett teljesítenie:

1. **Beleférjen 8 GB VRAM-ba.** Ez zárta ki elsőre a `gemma3:12b`-t
   (8,15 GB) és a `qwen2.5:14b`-t (8,99 GB): a CPU-ra kicsorgó rétegek
   a válaszidőt megnövelik, tehát az nem tiszta modell-összehasonlítás,
   hanem hardver-mérés is egyben. **2026-09-01-én mégis megmértük
   mindkettőt** — épp azért, hogy a „biztosan rosszabb" ne feltevés
   maradjon: a számok fent, a kiszervezés hatásának elemzése a
   `docs/NUM_CTX_ES_VRAM.md`-ben.
2. **Apache-2.0 licenc**, mert az ADR-013 szerint az ELSŐDLEGES modell
   csak ilyen lehet. Ez zárta ki a `llama3.1:8b`-t (Llama Community
   License) — az legfeljebb ellenőrző jelölt lehetne, éles út nem.
3. **Hasonló méret**, hogy a különbség a modellről szóljon: a
   `qwen3:8b` 5,23 GB-os letöltés, tehát a `qwen3.5:9b` (6,59 GB)
   valódi párja.

## Pontosság

Nyelvi halmaz, 51 eset:

| réteg | `qwen3.5:9b` | `qwen3:8b` | különbség |
|---|---|---|---|
| koznyelvi | 80,0% | 80,0% | 0 |
| tajszolas | 100,0% | 25,0% | **−75,0** |
| toredekes | 100,0% | 75,0% | −25,0 |
| szleng | 100,0% | 66,7% | −33,3 |
| egyszerusitett | 100,0% | 50,0% | **−50,0** |
| alkudozas | 100,0% | 83,3% | −16,7 |
| elengedes | 33,3% | 33,3% | 0 |
| mindegy | 83,3% | 83,3% | 0 |
| mintan_tul | 100,0% | 83,3% | −16,7 |
| valtozatossag | 80,0% | 80,0% | 0 |
| kapuor | 100,0% | 100,0% | 0 |
| **összesített** | **90,2%** | **71,6%** | **−18,6** |
| **leggyengébb réteg** | `elengedes` 33,3% | `tajszolas` 25,0% | |

Beszédhelyzetek halmaz, 23 eset:

| | `qwen3.5:9b` | `qwen3:8b` |
|---|---|---|
| összesített | **95,7%** | 82,6% |
| leggyengébb réteg | `kozbevetes` 66,7% | `meggondolas` 0,0% |

A `qwen3:8b` bukásai a beszédhelyzeteken beszédesek: a **meggondolás**
mindkét esetét elrontja (a „Mégsem kell, elnézést" után visszakérdez,
ahelyett hogy elengedné a beszélgetést — vagyis nyaggatja a vásárlót,
aki épp azt mondta, nem kér semmit), és a feltételes tervezésnél csak az
egyik napot viszi be az ablakba.

## Válaszidő

Fordulónkénti eloszlás (ADR-022: nem egy szám), a nyelvi halmaz 67
fordulóján:

| modell | p50 | p95 | átlag | max |
|---|---|---|---|---|
| `qwen3.5:9b` | 3,67 s | 4,14 s | 3,46 s | 4,25 s |
| `qwen3:8b` | 3,33 s | 3,81 s | 3,21 s | 9,61 s |

A `qwen3:8b` **0,34 s-mal gyorsabb a p50-en (−9%)**, viszont a maximuma
9,61 s — egyetlen kiugró forduló, de a p95 keretén belül maradó
eloszlásnál ez a farok az, ami hangcsatornán hallható lenne.

## VRAM

`/api/ps` szerint, közvetlenül a mérés után (a teljes modell a GPU-n,
CPU-ra kicsorgás nélkül):

| modell | letöltés | betöltve (VRAM) | 8 GB-ból marad |
|---|---|---|---|
| `qwen3.5:9b` | 6,59 GB | **5368 MB** | ~2,6 GB |
| `qwen3:8b` | 5,23 GB | **5900 MB** | ~2,1 GB |

**A kisebb letöltés NAGYOBB VRAM-ot foglal.** Ez nem mérési hiba: a
betöltött méret a kvantálástól és a KV-cache foglalásától függ, nem a
fájl méretétől. Vagyis a `qwen3:8b` a mi 8 GB-os keretünkben nem is ad
mozgásteret cserébe.

## Döntés

**Marad a `qwen3.5:9b`.** A kihívó mindhárom tengelyen rosszabb vagy
egyenlő: 18,6 ponttal gyengébb a nyelvi halmazon, 13,1 ponttal a
beszédhelyzeteken, több VRAM-ot foglal, és a 9%-os p50-nyereséget egy
9,6 s-os kiugrás kíséri. Az ADR-013 kiváltó feltétele (>5 százalékpont
javulás a leggyengébb rétegen) nem teljesült — ellenkező irányban
teljesült.

**A prompt-verzió nem mentette meg:** a `qwen3:8b` a v2 prompttal 68,6%
(v1: 71,6%), tehát a v2 nála is ront (l. `docs/PROMPT_AB.md`).

## Amit ez a mérés NEM mond meg

- **Nem mondja meg, hogy a `qwen3.5:9b` a legjobb választás.** Csak azt,
  hogy a mai keretben (8 GB, Apache-2.0, hasonló méret) nem találtunk
  jobbat. Egy 12–14B-os modell nagyobb VRAM-mal más eredményt adhat —
  azt ezen a gépen nem lehet tisztességesen megmérni.
- **Nem méri a magyar tokenizálást külön.** A Racka-4B tokenizer-előnye
  (ADR-013) továbbra is nyitott kérdés, licenc-okból nem éles jelölt.
- **Egy futás modellenként.** A `temperature 0` mellett is van
  futásonkénti szórás (ADR-019 tapasztalata szerint 2–4 pont a 45 eses
  halmazon) — a 18,6 pontos különbség ezen jóval kívül van, a 3 pontos
  prompt-különbségek viszont nem feltétlenül.

## Reprodukció

```
APRAJAFALVA_LLM_MODELL=qwen3.5:9b python feladat.py golden --ertelmezo forditott
APRAJAFALVA_LLM_MODELL=qwen3:8b   python feladat.py golden --ertelmezo forditott
APRAJAFALVA_LLM_MODELL=qwen3:8b   python feladat.py golden --ertelmezo forditott \
  --halmaz beszedhelyzetek
curl -s http://localhost:11434/api/ps        # VRAM, közvetlenül a futás után
```

Nyers kimenetek: `spike/meres_20260831/ablak_4.{json,log}` (9b, nyelvi),
`q8_nyelvi_v1.{json,log}`, `q8_nyelvi_v2.{json,log}`,
`besz_v1.{json,log}` (9b, beszédhelyzetek), `q8_besz_v1.{json,log}`.

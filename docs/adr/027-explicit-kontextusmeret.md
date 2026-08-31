# ADR-027: Explicit kontextusméret (`num_ctx`) — mert az alapértelmezés nem a miénk

- **Dátum:** 2026-09-01
- **Állapot:** elfogadott

## Kontextus

A modellhívás eddig NEM adott meg `num_ctx`-et, tehát a szolgáltató
alapértelmezése döntött. Ez a szám azonban nem a miénk, és nem is
állandó:

- az Ollama 0.33.2 ma **8192**-t ad, korábbi verziók 2048-at vagy
  4096-ot adtak;
- az `OLLAMA_CONTEXT_LENGTH` környezeti változó bármikor felülírja;
- modellenként a Modelfile is állíthatja.

Egy néma kontextusméret-változásnak két következménye van, és a második
alattomos: a hosszú beszélgetés eleje csendben kicsúszik az ablakból, a
nagyobb KV-cache pedig **VRAM-ból is kiszoríthatja a modellt** — a
CPU-ra kicsorgó rétegek pedig lassítanak, és a szakirodalom szerint a
strukturált kimenet minőségét is ronthatják.

Ez volt a felvetés: **a csendes CPU-visszaesés lehet a gyökérok** a
mérési ingadozások mögött.

## Döntés

**A `num_ctx` explicit, és a mai értéke 8192**
(`llm_based.ALAP_NUM_CTX`), környezetből felülírva
(`APRAJAFALVA_NUM_CTX`) — a méréshez, nem üzemmódként.

Mellé egy eszköz, ami megmondja, van-e kiszervezés:
`python -m tools.vram_meres --modell <név> --num-ctx <n>` — három
forrásból dolgozik (`/api/ps`, `nvidia-smi`, válaszidő), mert egyik sem
elég önmagában.

## A mérés — és amit MEGCÁFOLT

### 1. Van-e ma kiszervezés? NINCS.

`qwen3.5:9b`, kért `num_ctx=8192`:

```
Betöltve:      5368 MB, ebből VRAM 5368 MB
Kiszervezés:   100% GPU
Tényleges kontextus: 8192 (kért: 8192)
Válaszidő (meleg): 3,10 s
```

**A gyökérok-feltevés tehát ezen a gépen nem igazolódott**: a mai
konfiguráció teljes egészében a GPU-n fut, és az Ollama alapértelmezése
véletlenül pontosan az az érték, amit mi is kérünk. Az explicit
beállítás így ma **nem javít semmit** — attól még helyes, mert a
következő Ollama-frissítés vagy egy örökölt környezeti változó ezt
elronthatja, és akkor a mérés a modellre fogná.

### 2. Mi történik, ha TÉNYLEG nem fér be?

Ugyanaz a modell, `num_ctx=65536`:

```
Betöltve:      8123 MB, ebből VRAM 5206 MB
Kiszervezés:   64% GPU / 36% CPU — KISZERVEZÉS
Válaszidő (meleg): 4,17 s   (8192-nél: 3,10 s)
```

A golden seten (51 eset, `forditott`, v1 prompt), **kétszer futtatva
mindkét beállítást**:

| futás | `num_ctx=8192` (100% GPU) | `num_ctx=65536` (36% CPU) |
|---|---|---|
| 1. | 90,2% | 86,3% |
| 2. | 91,2% | 91,2% |

**A pontosság-romlás NEM reprodukálódott.** Az első futás −3,9 pontja
két eset volt; a második futásban a kiszervezett konfiguráció esetre
pontosan ugyanazt adta, mint a kontroll. A `temperature: 0` ezen a
felálláson nem jelent futásonkénti azonosságot (1-2 eset ingadozik), és
egy 4 pontos különbséghez ezért kell két futás.

**Ami viszont reprodukálható: a latencia.** Rövid hívásokon 3,10 s →
4,17 s (+35%), a golden p50-en 3,67 s → 4,4 s.

**A séma-kényszerítés végig tartott**: JSON parse-hiba egyetlen
futásban sem volt, a kiszervezés a strukturált kimenetet nem törte el.

## Miért

- **Ami nem a miénk, azt nem tudjuk reprodukálni.** Egy mérés akkor ér
  valamit, ha egy hónap múlva ugyanaz jön ki — és egy szolgáltatói
  alapértelmezés nem ilyen.
- **A 8192 négyszeres ráhagyás.** A leghosszabb tényleges promptunk
  (rendszerprompt + összefoglaló + négy forduló) 1600 token körül van.
- **A kiszervezés mostantól MÉRHETŐ, nem sejthető.** Ez a döntés
  legfontosabb hozadéka: nem a `num_ctx` beállítása, hanem az, hogy meg
  tudjuk mondani, mikor csorog ki a modell — és hogy a „biztosan ez a
  gyökérok" feltevést meg lehessen cáfolni, ha nem az.

## Amit feladunk

- **A hosszú kontextust.** 8192 tokennél hosszabb beszélgetés esetén az
  eleje kiesik — de a csúszó előzmény-ablak (ADR-025) miatt oda sem
  jutunk el: a prompt négy fordulónál nem nő tovább.
- **Egy újabb kapcsolót** (`APRAJAFALVA_NUM_CTX`), amit karban kell
  tartani.

## Kiváltó feltétel

- a `tools.vram_meres` kiszervezést mutat a napi konfiguráción (pl. egy
  nagyobb modellre váltás után) — ekkor a `num_ctx`-et vagy a modellt
  kell csökkenteni, és a döntés újranyílik;
- a prompt tartósan 4000 token fölé nő (mérve, nem becsülve) — ekkor a
  8192 ráhagyása elfogy;
- az Ollama alapértelmezése 8192 fölé nő ÉS a kártya nagyobb lesz —
  ekkor az explicit érték már csak korlátoz.

## Ellenőrzés

```
python -m tools.vram_meres --modell qwen3.5:9b --num-ctx 8192
python -m tools.vram_meres --modell qwen3.5:9b --num-ctx 65536   # kiszervezés
APRAJAFALVA_NUM_CTX=8192  python feladat.py golden --ertelmezo forditott
APRAJAFALVA_NUM_CTX=65536 python feladat.py golden --ertelmezo forditott
```

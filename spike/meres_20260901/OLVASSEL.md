# 2026-09-01-i mérési sorozat — nyers kimenetek

| Kérdés | Jelentés |
|---|---|
| Van-e csendes CPU-visszaesés, és számít-e? | `docs/NUM_CTX_ES_VRAM.md` (ADR-027) |
| Segít-e az állapotsor a modellnek? | `docs/ALLAPOTSOR_MERES.md` (ADR-028) |
| Jobb-e egy nagyobb modell 8 GB-on? | `docs/NUM_CTX_ES_VRAM.md` 4. szakasz |

Minden golden futás: `forditott` értelmező, 4 fordulós ablak,
`temperature 0`, `think: false`, nyelvi halmaz (51 eset).

| fájl | modell | num_ctx | prompt | mit mér |
|---|---|---|---|---|
| `ctx8192_kontroll` | qwen3.5:9b | 8192 | v1 | kontroll (100% GPU) |
| `ctx8192_kontroll_2` | qwen3.5:9b | 8192 | v1 | ugyanaz, ISMÉTELVE |
| `ctx65536_offload` | qwen3.5:9b | 65536 | v1 | kikényszerített kiszervezés (36% CPU) |
| `ctx65536_offload_2` | qwen3.5:9b | 65536 | v1 | ugyanaz, ISMÉTELVE |
| `ctx8192_prompt_v3` | qwen3.5:9b | 8192 | v3 | a prompt A/B kontrollja rögzített num_ctx-szel |
| `gemma3_12b` | gemma3:12b | 8192 | v1 | 8,5 GB egy 8,2 GB-os kártyán |
| `qwen25_14b` | qwen2.5:14b | 8192 | v1 | 10,3 GB egy 8,2 GB-os kártyán |
| `vegigjatszas_allapotsor_be` / `_ki` | qwen3.5:9b | 8192 | v1 | az állapotsor A/B-je a VALÓDI úton |

A `*_vram.json` fájlok a kiszervezés-mérésé (`tools/vram_meres.py`):
betöltött méret, VRAM-ban lévő rész, tényleges kontextus, válaszidők.

**A két ISMÉTLÉS a sorozat lényege.** Az első futás 3,9 pontos
különbséget mutatott a kiszervezett konfiguráció rovására; a második
futásban a különbség eltűnt (91,2% vs. 91,2%, esetre pontosan ugyanazok
a bukások). Egy futásból tehát nem lehetett volna következtetni — és
ez a `temperature: 0` melletti futásonkénti szórás mértékét is
megmutatta.

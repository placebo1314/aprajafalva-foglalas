# 2026-09-05-i mérési sorozat — nyers kimenetek

**Kérdés:** van-e a mai (2026-os) modellmezőnyben jobb jelölt a
`qwen3.5:9b`-nél 8 GB VRAM-on? Az értelmezés és a döntés:
`docs/MODELLKERESES_20260905.md`.

Minden futás: `forditott` értelmező, `num_ctx=8192`, 4 fordulós ablak,
v1 prompt, `temperature 0`, állapotsor KI (a golden mérési úton úgysem
jelenik meg).

| fájl | modell | halmaz |
|---|---|---|
| `q9_nyelvi` / `q9_besz` | qwen3.5:9b (éles) | nyelvi (55) / beszédhelyzetek (28) |
| `g412b_nyelvi` / `g412b_besz` | gemma4:12b-it-qat | ugyanaz |
| `g4e4b_nyelvi` / `g4e4b_besz` | gemma4:e4b-it-qat | ugyanaz |
| `g4e2b_nyelvi` / `g4e2b_besz` | gemma4:e2b-it-qat | ugyanaz |
| `*_vram.json` | — | betöltött méret, VRAM, kiszervezés, válaszidők |
| `q9_nyelvi_mindegyszabaly_1/2` | qwen3.5:9b | a MINDEGY-felülírás prompt-szabály A/B-je (MEGBUKOTT) |
| `vegigjatszas_probak_be` | qwen3.5:9b | a bővített állapotsor-próbák a VALÓDI úton |

**A halmazok ebben a körben bővültek**, tehát ezek a számok NEM
hasonlíthatók közvetlenül a `spike/meres_20260901/` értékeihez: ott a
nyelvi halmaz 51 esetes volt, itt 55.

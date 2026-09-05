# 2026-09-12-i mérés — nyers kimenet

| fájl | mit mér |
|---|---|
| `nyelvi_85.{json,log}` | a BŐVÍTETT nyelvi halmaz (85 eset), KÉT futás — `qwen3.5:9b`, v1 prompt, `num_ctx=8192`, 4 fordulós ablak, állapotsor KI |

Az értelmezés: `docs/HALMAZ_BOVITES_20260912.md`.

**A két futás (84,1% és 86,5%) különbsége a zajküszöbön belül van**, tehát
a korábbi számokhoz képest se javulás, se romlás nem állítható — ezt a
futtató maga írja ki (`--ismetles 2`), és a JSON is tartalmazza
(`osszefoglalo.ismetelhetoseg`).

Ami MÉRHETŐ: a négy javított eset (`mindegy-07`, `elengedes-05`,
`elengedes-10/11/12/13`) mindkét futáson megy — ezek korábban mind a
négy megmért modellen buktak.

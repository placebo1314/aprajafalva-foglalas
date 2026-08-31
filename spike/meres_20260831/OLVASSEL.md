# 2026-08-31-i mérési sorozat — nyers kimenetek

Ez a könyvtár a mérések NYERS anyaga. Az értelmezésük a `docs/`-ban van:

| Kérdés | Jelentés |
|---|---|
| Mennyivel rövidít a csúszó előzmény-ablak? | `docs/ABLAK_MERES.md` (ADR-025) |
| Javít-e az átépített rendszerprompt? | `docs/PROMPT_AB.md` (ADR-026) |
| Van-e jobb modell 8 GB VRAM-ban? | `docs/MODELL_OSSZEHASONLITAS.md` |
| Mit tud a rendszer a beszédhelyzetekkel? | `docs/BESZEDHELYZETEK_MERES.md` |

Minden futás: `forditott` értelmező, `temperature 0`, `think: false`,
Ollama, RTX 4060 Laptop (8 GB VRAM).

| fájl | modell | halmaz | ablak | prompt |
|---|---|---|---|---|
| `ablak_ki` | qwen3.5:9b | nyelvi | nincs (alapvonal) | v1 |
| `ablak_4` | qwen3.5:9b | nyelvi | 4 (éles) | v1 |
| `ablak_1` | qwen3.5:9b | nyelvi | 1 | v1 |
| `prompt_v2` | qwen3.5:9b | nyelvi | 4 | v2 |
| `prompt_v3` | qwen3.5:9b | nyelvi | 4 | v3 |
| `besz_v1` / `besz_v2` / `besz_v3` | qwen3.5:9b | beszédhelyzetek | 4 | v1 / v2 / v3 |
| `q8_nyelvi_v1` / `q8_nyelvi_v2` | qwen3:8b | nyelvi | 4 | v1 / v2 |
| `q8_besz_v1` | qwen3:8b | beszédhelyzetek | 4 | v1 |
| `vegigjatszas_modellel` | qwen3.5:9b | — (fej nélküli végigjátszás) | 4 | v1 |
| `vegigjatszas_modellel_javitas_utan` | ugyanaz, az írásbeli megerősítés javítása UTÁN | | |

A `.log` a futás teljes kimenete (esetenkénti pontszám, réteg-küszöbök,
válaszidő-eloszlás, a végén a VRAM-foglalás), a `.json` az eseten­kénti
nyers modellkimenet — ebből lehet utólag megnézni, MIT adott a modell,
nem csak azt, hogy hibázott.

**A két végigjátszás-napló a lényeges pár:** az elsőben az „igen,
foglald le" mondatból új keresés lett és a foglalás megszakadt, a
másodikban ugyanaz a mondat `orchestrator:megerosites` rétegen fut le,
és a menet a foglalási kóddal zárul.

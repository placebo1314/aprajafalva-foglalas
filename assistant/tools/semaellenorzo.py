"""Minimális séma-ellenőrző az `assistant/tools/semak.py` sémáihoz.

**Nem általános célú JSON-séma-validátor.** Csak azt a részhalmazt
támogatja, amit ez a projekt ténylegesen használ (eszkoz-szerzodes skill):
`type: object`, `properties`, `required`, `enum`, `additionalProperties`,
`format: date-time`. Ha egy séma ezen túlmutató kényszert igényelne, azt
itt kell bővíteni — nem egy külső csomaggal (a projekt nem vezet be új
függőséget egy ilyen szűk, jól körülhatárolt igényhez).

Éles (LLM-es) kötött dekódolásnál ez a réteg redundáns lenne (a GBNF/
XGrammar már eleve csak érvényes kimenetet enged) — itt azért kell, mert
a determinisztikus (`assistant/interpreter/rule_based.py`) és a
koppintós UI-út is ugyanezeken a sémákon keresztül hívja az eszközöket,
kötött dekódolás nélkül.
"""

from __future__ import annotations

from datetime import datetime


def ellenoriz(sema: dict, adat: dict) -> list[str]:
    """A hibák listája, emberi (fejlesztői, NEM felhasználói) szöveggel —
    üres lista = érvényes. A hívó (`assistant/tools/hiba.py`) ezt sosem
    adja vissza szó szerint a felhasználónak, csak a hiba TÉNYÉT jelzi
    egy zárt `uzenet_kulcs`-csal."""
    if not isinstance(adat, dict):
        return ["a paraméterek nem objektum"]

    hibak: list[str] = []
    properties: dict = sema.get("properties", {})
    required: list[str] = sema.get("required", [])
    additional_ok: bool = sema.get("additionalProperties", True)

    for mezo in required:
        if mezo not in adat:
            hibak.append(f"hiányzó kötelező mező: {mezo}")

    if not additional_ok:
        for kulcs in adat:
            if kulcs not in properties:
                hibak.append(f"ismeretlen mező: {kulcs}")

    for kulcs, ertek in adat.items():
        mezo_sema = properties.get(kulcs)
        if mezo_sema is None:
            continue
        hibak.extend(_mezo_ellenoriz(kulcs, ertek, mezo_sema))

    return hibak


def _mezo_ellenoriz(kulcs: str, ertek: object, mezo_sema: dict) -> list[str]:
    hibak: list[str] = []
    tipus = mezo_sema.get("type")

    if tipus == "string" and not isinstance(ertek, str):
        hibak.append(f"{kulcs}: 'string' típus kellene, kapott {type(ertek).__name__}")
        return hibak
    if tipus == "integer" and not isinstance(ertek, int):
        hibak.append(f"{kulcs}: 'integer' típus kellene, kapott {type(ertek).__name__}")
        return hibak
    if tipus == "number" and not isinstance(ertek, (int, float)):
        hibak.append(f"{kulcs}: 'number' típus kellene, kapott {type(ertek).__name__}")
        return hibak

    enum = mezo_sema.get("enum")
    if enum is not None and ertek not in enum:
        hibak.append(f"{kulcs}: érvénytelen érték ({ertek!r}), várt egyike: {enum}")

    if mezo_sema.get("format") == "date-time" and isinstance(ertek, str):
        try:
            datetime.fromisoformat(ertek.replace("Z", "+00:00"))
        except ValueError:
            hibak.append(f"{kulcs}: nem érvényes ISO-8601 dátum-idő: {ertek!r}")

    return hibak

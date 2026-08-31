"""ÍRÁSBELI IGEN ÉS NEM — „igen, foglald le", „mégse kell".

**Mért hiba, nem elméleti hiányosság** (2026-08-31, `python feladat.py
vegigjatszas`, `qwen3.5:9b`): a szöveges úton a foglalás a HARMADIK
lépésnél szakadt meg. A keresés jó, a sorszámos választás jó („a
másodikat kérem" → megerősítés-kérés), aztán:

```
> igen, foglald le
    réteg:       llm
    eszköz:      szabad_idopontok
    jelöltek:    ['2026-12-23 07:00–07:10 (UTC)', …]
    Az azonosító-mező eltűnt — írásban itt szakad meg az út.
```

A modell a megerősítést ÚJ KERESÉSNEK értette, a felület pedig
kirajzolta az új jelölteket — a folyamatban lévő megerősítés (és vele a
kiválasztott időpont) eltűnt a képernyőről. Ugyanez a tartalék ágon is
megtörtént, tehát nem modellhiba: a rendszer állapotgépe nem is
KÉRDEZTE meg, hogy éppen megerősítésre vár-e.

## Miért determinisztikus réteg, és miért a modell ELŐTT

Ugyanaz az érv, mint a sorszámos hivatkozásnál
(`assistant/sorszam.py`): ha a rendszer épp azt kérdezte, hogy
„biztosan lefoglaljam ezt az időpontot?", akkor a válasz ZÁRT halmaz —
igen, nem, vagy valami más. Nincs mit értelmeztetni rajta, viszont van
mit elrontani: egy félreértett „igen" a rossz időpontot foglalná le, egy
félreértett „mégse" pedig eldobná a jót.

Ez a réteg CSAK akkor szólal meg, ha a session ténylegesen
megerősítésre vár (`_SessionAllapot.allapot == "megerositesre_var"`).
Minden más helyzetben az „igen" önmagában semmit nem jelent, és a
mondat a szokásos úton megy tovább.

## Amit szándékosan NEM ismer fel

- **„igen" egy hosszabb, önálló kérés belsejében**: „igen, de inkább
  szerdán lenne jó" — ott a mondat MÁSIK kérést hordoz, és azt az
  értelmezőnek kell látnia. A minták ezért a mondat EGÉSZÉRE
  illeszkednek, nem részszövegre.
- **A bizonytalan választ**: „talán", „lehet", „hát nem tudom". Ezek
  nem igenek és nem nemek; maradjon a kérdés nyitva.
- **Az azonosítót.** Az „igen" nem foglal — a foglaláshoz vásárlói
  kulcs kell (CLAUDE.md 2. invariáns: nyers azonosító nem kerül
  lemezre, csak hash), és azt a felület kéri be. Az igenlő válasz tehát
  ÚJRA feltett megerősítés-kérdés, nem foglalás.
"""

from __future__ import annotations

import re

from assistant.interpreter.normalizalo import normalizal

IGEN = "igen"
NEM = "nem"

# A MONDAT EGÉSZÉRE illeszkedő minták — nem részszöveg-keresés. Az
# „igen, de inkább szerdán" nem igenlés, hanem új kérés, és a
# részszöveg-keresés ezt elnyelné.
#
# A záró udvariassági szavak („köszönöm", „légyszi", „kérlek") és a
# foglalás-igék („foglald le", „mehet") a MINTÁN BELÜL vannak, mert
# ezek az igenlés természetes kísérői — nem külön kérések.
_UDVARIASSAG = r"(?:[,.]?\s*(?:köszönöm|köszi|legyszi|légyszi|kérlek|kérem|szépen))*"
_FOGLALAS_IGE = r"(?:foglald le|foglalja le|foglaljuk|lefoglalom|lefoglalhatod|mehet|jöhet)"

_IGEN_MINTAK = (
    re.compile(rf"^(?:igen|ja|aha|persze|naná|nyilván|ok|oké|okés|rendben){_UDVARIASSAG}[.!]?$"),
    re.compile(rf"^(?:jó|jó lesz|jöhet|megfelel|az jó|ez jó|tökéletes){_UDVARIASSAG}[.!]?$"),
    re.compile(rf"^(?:igen[,.]?\s*)?{_FOGLALAS_IGE}{_UDVARIASSAG}[.!]?$"),
    re.compile(rf"^(?:igen|ja|persze|rendben|ok|oké)[,.]?\s*{_FOGLALAS_IGE}{_UDVARIASSAG}[.!]?$"),
)

_NEM_MINTAK = (
    re.compile(rf"^(?:nem|nem kérem|nem kell|mégse|mégsem|inkább ne){_UDVARIASSAG}[.!]?$"),
    re.compile(rf"^(?:mégse|mégsem)[,.]?\s*(?:kérem|kell|akarom|foglald){_UDVARIASSAG}[.!]?$"),
    re.compile(rf"^(?:hagyjuk|felejtsd el|mindegy, hagyjuk){_UDVARIASSAG}[.!]?$"),
)


def megerosito_valasz(mondat: str) -> str | None:
    """`IGEN`, `NEM`, vagy `None`, ha a mondat egyik sem.

    A `None` a leggyakoribb és a legfontosabb visszatérési érték: azt
    jelenti, hogy a mondat valami MÁS (új kérés, kérdés, kifogás), és a
    szokásos értelmezési úton kell mennie. Ez a réteg nem elnyelni akar
    fordulókat, hanem egyetlen, zárt kérdésre adott választ felismerni."""
    also = normalizal(mondat).strip().lower()
    if not also:
        return None
    if any(minta.match(also) for minta in _IGEN_MINTAK):
        return IGEN
    if any(minta.match(also) for minta in _NEM_MINTAK):
        return NEM
    return None

"""RAGOZÁS — a törzsadatból jövő NEVEK toldalékolása (ADR-032).

A bolt- és szolgáltatásnevek az adatbázisból jönnek, a mondat viszont a
sablonból: „a **Szundiba** **altatóért**". A kettő között valakinek
ragoznia kell — és ez a modul csinálja, determinisztikusan.

**Miért nem a sablonba írjuk be a kész alakokat.** Mert akkor egy
admin-oldali átnevezés után a rendszer mást mondana, mint amit a
törzsadat tartalmaz (blueprint 10.: a bolti tudás egyetlen forrása a
tábla). A ragozás ára viszont az, hogy KÖZELÍTÉS — l. „Amit nem tud".

## Amit tud

- **Hangrendi illeszkedés** a `-ba/-be` ragnál: ha a szóban van hátsó
  magánhangzó (a á o ó u ú), a rag hátsó (`-ba`), különben elülső
  (`-be`). Ez a magyar hangrend leggyakoribb, szabályos esete.
- **Tővégi nyúlás**: a szóvégi `a` → `á`, `e` → `é` a rag előtt
  („Törpilla" → „Törpillába", „petárda" → „petárdáért").
- **Határozott névelő**: magánhangzóval kezdődő szó előtt `az`
  („az Ügyifogyi"), egyébként `a`.

## Amit NEM tud

Nem morfológiai elemző. A vegyes hangrendű jövevényneveket a
leggyakoribb szabály szerint kezeli (van benne hátsó magánhangzó →
hátsó rag), ami a mai három boltnévre helyes, de egy jövőbeli
„Csilingelő" névnél már nem lenne az. **Ez tudatos korlát**: egy teljes
magyar morfológiai könyvtár behúzása (`emmorph`, `huntag`) aránytalan
lenne három szóért — de ha a boltok száma nő, ez a modul az első hely,
amit ki kell dobni.

A `-ért` rag SZÁNDÉKOSAN nem hangrendfüggő: a magyarban ez a néhány
invariáns rag egyike („altatóért", „boldogságért").
"""

from __future__ import annotations

_HATSO_MAGANHANGZOK = set("aáoóuú")
_MAGANHANGZOK = set("aáeéiíoóöőuúüű")

# Szóvégi nyúlás a rag előtt.
_NYULAS = {"a": "á", "e": "é"}


def _hatso_hangrend(szo: str) -> bool:
    return any(betu in _HATSO_MAGANHANGZOK for betu in szo.lower())


def _tovegi_nyulas(szo: str) -> str:
    if not szo:
        return szo
    utolso = szo[-1].lower()
    if utolso in _NYULAS:
        return szo[:-1] + _NYULAS[utolso]
    return szo


def nevelo(szo: str) -> str:
    """`"a"` vagy `"az"` — a szó kezdőhangja szerint."""
    return "az" if szo and szo[0].lower() in _MAGANHANGZOK else "a"


def hova(szo: str) -> str:
    """`-ba` / `-be`: „Szundi" → „Szundiba", „Törpilla" → „Törpillába"."""
    return _tovegi_nyulas(szo) + ("ba" if _hatso_hangrend(szo) else "be")


def ert(szo: str) -> str:
    """`-ért` (invariáns rag): „altató" → „altatóért", „petárda" →
    „petárdáért"."""
    return _tovegi_nyulas(szo) + "ért"


def nevelovel(szo: str) -> str:
    """Névelővel együtt: „a Szundi", „az Ügyifogyi"."""
    return f"{nevelo(szo)} {szo}"

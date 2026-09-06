"""HELYI IDŐ — az egyetlen hely, ahol UTC-ből helyi idő lesz.

A rendszer minden időpontot **UTC-ben** tárol, ISO-8601 szövegként
(CLAUDE.md 4. invariáns). Ugyanannak az invariánsnak a második fele
viszont sokáig papíron maradt: *„helyi idő csak a megjelenítésnél
keletkezik"* — és a megjelenítés nem csinálta meg.

**Amit ez a mulasztás okozott** (2026-09-20, kézi próba): a demóadat
boltjai 8 órakor nyitnak helyi idő szerint, a slot `2026-12-21T07:00:00Z`
alakban áll az adatbázisban — és a vásárló ezt látta a gombon:

    2026-12-21 07:00–07:10 (UTC)

...a felolvasó pedig azt mondta neki, hogy „hét órakor". Télen egy, nyáron
két óra tévedés, MINDEN időponton, mindkét csatornán. Nem a formázás
volt csúnya: **rossz időpontot mondtunk.**

## A szerződés

`helyi_iso(iso, zona)` ugyanolyan ALAKÚ ISO-szöveget ad vissza, csak a
zóna szerinti falióra-idővel és `Z` nélkül:

    "2026-12-21T07:00:00Z" + "Europe/Budapest"  →  "2026-12-21T08:00:00"

Ez szándékos: a formázók (`assistant/valasz/szamok.py`) karakterpozíció
szerint vágnak (`iso[11:16]`), tehát a konverzió UTÁN is változatlanul
működnek. Egyetlen ponton váltunk, nem tíz formázóban.

**A `Z` eltűnése a jelzés, hogy ez már nem UTC.** Aki ilyen szöveget kap,
azt már csak kiírni szabad — visszaírni az adatbázisba soha.

## A zóna hiánya

`zona=None` esetén a bemenet változatlanul jön vissza. Ez nem
elnézés, hanem a hívó dolga: a zóna a szervezet törzsadata
(`core/repo/torzsadat_repo.py::org_load`), és a felület be tudja
szerezni. A `None` az az eset, amikor NINCS szervezet (üres adatbázis) —
ott nincs is mit megjeleníteni.
"""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


def helyi_iso(iso: str, zona: str | None) -> str:
    """UTC ISO-8601 → ugyanolyan alakú, de HELYI idejű ISO (`Z` nélkül).

    Ismeretlen zónanévnél a bemenetet adja vissza: egy elgépelt
    időzóna-törzsadat miatt nem maradhat el a megjelenítés. A hiba így
    látható marad (rossz óra), de nem néma kivétel a felület közepén."""
    if not iso or not zona:
        return iso
    try:
        cel = ZoneInfo(zona)
    except (ZoneInfoNotFoundError, ValueError):
        return iso
    pillanat = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    return pillanat.astimezone(cel).strftime("%Y-%m-%dT%H:%M:%S")


def helyi_ora_perc(iso: str, zona: str | None) -> str:
    """Csak az óra és a perc, helyi idő szerint: `"08:00"`."""
    return helyi_iso(iso, zona)[11:16]


def helyi_datum(iso: str, zona: str | None) -> str:
    """Csak a dátum, helyi idő szerint: `"2026-12-21"`.

    Nem ugyanaz, mint az `iso[:10]`: egy `23:30Z` kezdetű időpont
    Budapesten már a KÖVETKEZŐ napra esik."""
    return helyi_iso(iso, zona)[:10]

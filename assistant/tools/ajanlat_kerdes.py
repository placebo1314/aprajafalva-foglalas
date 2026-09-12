"""`ajanlat_kerdes` — KÉRDÉS A MÁR FELAJÁNLOTT IDŐPONTOKRÓL (ADR-035).

**Mért hiány** (2026-09-11, idegen próba, 18 forduló): a vásárló öt
egymás utáni fordulóban a felajánlott időpontokról kérdezett, és a
rendszer mind az ötször ÚJRA KERESETT — ugyanazzal az ablakkal,
ugyanazzal az eredménnyel:

| forduló | amit kérdezett | ami történt |
|---|---|---|
| 3. | „Van késõbbi?" | ugyanaz a keresés, ugyanaz a 8:00 |
| 4. | „10 után kéne." | ugyanaz |
| 5. | „nem jó nekem ilyen korán." | ugyanaz |
| 6. | „ez minden nap van?" | ugyanaz |
| 7. | „akkor a legkésõbbit. De melyik nap?" | ugyanaz |

**A hiba nem a keresésben volt, hanem abban, hogy kerestünk.** A
válasz ott volt a kezünkben: a jelöltek listájában. Aki azt kérdezi,
„melyik nap?", annak nem új keresés kell, hanem felelet.

## A négy kérdésfajta

- `melyik_nap` — „melyik nap?", „ez mikor van?"
- `van_kesobbi` — „van későbbi?", „nem jó ilyen korán", „10 után kéne"
- `van_korabbi` — „van korábbi?", „délelőtt nem megy?"
- `mikor_van` — „a másodikat mikorra?" (egy KONKRÉT jelöltről)

Az első és a negyedik a jelöltekből felel, keresés nélkül. A második
és a harmadik viszont **ablakot TOL**: ha a vásárló későbbit kér, a
következő keresés a legkésőbbi ajánlat UTÁN kezdődik — különben
ugyanazt találnánk meg újra, és pontosan ez történt ötször egymás
után.

## Amit NEM csinál

Nem foglal, nem választ, nem módosít semmit. Tiszta függvény a
jelöltek listáján: ugyanaz a bemenet mindig ugyanazt a választ adja.
A holdok érintetlenek maradnak — a vásárló kérdezett, nem döntött.
"""

from __future__ import annotations

from datetime import datetime, timedelta

# A KÉRDÉSFAJTÁK zárt halmaza. A modell ezt adja vissza (`mit` mező),
# és mint minden zárt halmaznál: ami nincs benne, az nem születhet meg.
MELYIK_NAP = "melyik_nap"
VAN_KESOBBI = "van_kesobbi"
VAN_KORABBI = "van_korabbi"
MIKOR_VAN = "mikor_van"

KERDESFAJTAK = (MELYIK_NAP, VAN_KESOBBI, VAN_KORABBI, MIKOR_VAN)

# Mennyivel toljuk az ablakot a legkésőbbi ajánlat után. Egy perc elég:
# a slot-határok percre esnek, és a cél nem az ugrás, hanem hogy a
# következő keresés ne ugyanazt a listát adja vissza.
_TOLAS_PERC = 1


def _ido(iso: str) -> datetime:
    return datetime.fromisoformat(iso.replace("Z", "+00:00"))


def hivas(parameterek: dict, *, jeloltek: list[dict]) -> dict:
    """A felajánlott jelöltekből válaszol — keresés nélkül.

    Nem adatbázist kérdez, mint a többi eszköz: a jelöltek a session
    állapotában vannak (`_SessionAllapot.aktualis_jeloltek`), és épp az
    a lényeg, hogy ne menjünk értük újra a slot-táblához. Ezért a
    `conn` sem paramétere.

    A visszaadott dict `sikeres` kulcsa a többi eszköz szerződését
    követi; az `uj_ablak_tol` csak akkor van benne, ha a kérdés
    ELTOLJA a keresést (későbbi/korábbi)."""
    mit = parameterek.get("mit")
    if mit not in KERDESFAJTAK:
        return {"sikeres": False, "uzenet_kulcs": "ismeretlen_ajanlat_kerdes"}
    if not jeloltek:
        return {"sikeres": False, "uzenet_kulcs": "nincs_mire_kerdezni"}

    kezdetek = [j["kezdet"] for j in jeloltek if j.get("kezdet")]
    if not kezdetek:
        return {"sikeres": False, "uzenet_kulcs": "nincs_mire_kerdezni"}

    if mit == MELYIK_NAP:
        # A NAPOK, az ajánlat sorrendjében. Nem halmaz: a sorrend a
        # pontozóé (ADR-006), és a vásárlónak is az a sorrend a
        # természetes, amit az imént látott.
        napok: list[str] = []
        for kezdet in kezdetek:
            if kezdet[:10] not in napok:
                napok.append(kezdet[:10])
        return {"sikeres": True, "mit": mit, "napok": napok, "kezdetek": kezdetek}

    if mit == MIKOR_VAN:
        sorszam = parameterek.get("sorszam")
        if not isinstance(sorszam, int) or not 1 <= sorszam <= len(jeloltek):
            # TARTOMÁNYON KÍVÜL: nem kerekítünk (ugyanaz az elv, mint a
            # jelöltválasztásnál) — inkább nincs válasz, mint rossz.
            return {"sikeres": False, "uzenet_kulcs": "nincs_ilyen_jelolt"}
        jelolt = jeloltek[sorszam - 1]
        return {"sikeres": True, "mit": mit, "sorszam": sorszam, "jelolt": jelolt}

    # VAN_KESOBBI / VAN_KORABBI — a kérdés egyben KÉRÉS is: a
    # következő keresés ablaka eltolódik, különben ugyanazt találnánk.
    if mit == VAN_KESOBBI:
        legkesobbi = max(kezdetek)
        uj_tol = _ido(legkesobbi) + timedelta(minutes=_TOLAS_PERC)
        return {
            "sikeres": True,
            "mit": mit,
            "uj_ablak_tol": uj_tol.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "hatar": legkesobbi,
        }

    legkorabbi = min(kezdetek)
    uj_veg = _ido(legkorabbi) - timedelta(minutes=_TOLAS_PERC)
    return {
        "sikeres": True,
        "mit": mit,
        "uj_ablak_ig": uj_veg.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "hatar": legkorabbi,
    }

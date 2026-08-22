"""Egységes eredmény- és hibaformátum minden `assistant/tools/` eszközhez
(eszkoz-szerzodes skill, "Hibaágak"):

```json
{"sikeres": false, "ok": "megeloztek", "uzenet_kulcs": "slot_elfogyott", "alternativak": [...]}
```

Az `ok` egy zárt halmazból jön (lásd `Ok`), gépi olvasható — ebből dönt az
orchestrator, nem szabad szövegből. Az `uzenet_kulcs` a válaszsablonra
mutat: **az eszköz nem fogalmaz magyar mondatot**, azt a `valasz` modul
teszi majd (M5), amíg az nincs megírva, az `ui/vasarlo.py` egy statikus
szótárral fordítja emberi szövegre.
"""

from __future__ import annotations

from enum import Enum


class Ok(Enum):
    """Zárt hiba-okok — az eszkoz-szerzodes skill mintája plusz a
    ténylegesen szükséges kiegészítések (áthelyezés, lekérdezés,
    séma-validáció)."""

    MEGELOZTEK = "megeloztek"
    NINCS_SZABAD_HELY = "nincs_szabad_hely"
    SZABALY_TILTJA = "szabaly_tiltja"
    HITELESITES_SZUKSEGES = "hitelesites_szukseges"
    ERVENYTELEN_KOD = "ervenytelen_kod"
    ERVENYTELEN_PARAMETER = "ervenytelen_parameter"
    NINCS_ILYEN_FOGLALAS = "nincs_ilyen_foglalas"
    MAR_LEMONDVA = "mar_lemondva"
    ISMERETLEN_BOLT = "ismeretlen_bolt"
    ISMERETLEN_SZOLGALTATAS = "ismeretlen_szolgaltatas"


def sikeres_eredmeny(**mezok: object) -> dict:
    """A hívó adja meg az eszközspecifikus mezőket (pl. `jeloltek`,
    `foglalasi_kod`) — ez a függvény csak az egységes `sikeres: true`
    borítékot teszi rájuk."""
    return {"sikeres": True, **mezok}


def hiba_eredmeny(
    ok: Ok, uzenet_kulcs: str, alternativak: list | None = None, **tovabbi_mezok: object
) -> dict:
    """`alternativak` majdnem mindig legyen nem-üres — a vesztes ág is
    legyen kellemes (eszkoz-szerzodes skill). Ahol a hívó ténylegesen nem
    tud alternatívát ajánlani (pl. érvénytelen paraméter), üres listát ad.

    `tovabbi_mezok`: eszközspecifikus kiegészítés a borítékhoz (pl.
    `szabad_idopontok` `alternativ_dimenzio`-ja — blueprint 1. szakasz,
    "Kapjon őszinte választ... ha nincs hely, alternatíva jöjjön": nem
    elég azt mondani, hogy nincs hely, azt is meg kell mondani, MELYIK
    dimenzióban van)."""
    return {
        "sikeres": False,
        "ok": ok.value,
        "uzenet_kulcs": uzenet_kulcs,
        "alternativak": alternativak or [],
        **tovabbi_mezok,
    }

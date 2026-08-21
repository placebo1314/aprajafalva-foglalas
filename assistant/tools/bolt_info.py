"""`bolt_info` — a "Bolti tudás" eszköze (docs/blueprint.md 10. szakasz):
nyitvatartás, cím, időtartam, megjelenés, termékleírás, ár. Azonosítás
nem kell — ez a kapuőr második kategóriája, "engedélyezett tényválasz,
zárt listából".

**A bolt-szintű tény mindig szerkesztett adat, sosem modellgenerálás** —
ez az eszköz kikeresi, nem kitalálja. A `megjelenes` (`bolt` tábla), a
`termekleiras`/`ar` (`szolgaltatas` tábla) valódi DB-oszlop
(migrations/0004_bolt_szolgaltatas_tudas.sql), üres stringgel, ha nincs
kitöltve — ez NEM hiba, azt jelenti, hogy erre a mezőre nincs még
szerkesztett válasz. A cím/nyitvatartás MA statikus, kódba írt adat
(`assistant/tools/katalogus.py::BOLT_INFO_STATIKUS` — a `bolt` táblának
nincs ilyen oszlopa).

**Az "ar" séma-szinten (v2) lekérdezhető, de a kapuőr MA mégis elutasítja**
— a golden set `kapuor-02` esete ("Mennyibe kerül a nagy petárda?" →
`nincs`, tiltott minta: `kitalalt_ar`) a kapuőr-réteg döntése, nem ennek
az eszköznek a korlátja. Ez a séma csak a lekérdezési KÉPESSÉGET rögzíti
— ha az ártájékoztatás valaha engedélyezetté válna, az a kapuőr
(`assistant/interpreter/rule_based.py`) döntése, ADR-rel, nem csendes
viselkedésváltás."""

from __future__ import annotations

from assistant.tools import hiba, katalogus, semaellenorzo, semak
from core.repo import torzsadat_repo

_SZOLGALTATAS_MEZOK = {
    "idotartam": ("idotartam_perc", "alap_idotartam_perc"),
    "termek": ("termekleiras", "termekleiras"),
    "ar": ("ar", "ar"),
}


def hivas(conn, parameterek: dict, *, org_id: str) -> dict:
    sema = semak.SEMAK["bolt_info"][semak.legutobbi_verzio("bolt_info")]
    hibak = semaellenorzo.ellenoriz(sema, parameterek)
    if hibak:
        return hiba.hiba_eredmeny(hiba.Ok.ERVENYTELEN_PARAMETER, "ervenytelen_kereses")

    bolt_slug = parameterek["bolt_id"]
    bolt_id = katalogus.bolt_id_felold(conn, org_id, bolt_slug)
    if bolt_id is None:
        return hiba.hiba_eredmeny(hiba.Ok.ISMERETLEN_BOLT, "ismeretlen_bolt")

    mit = parameterek["mit"]

    if mit in _SZOLGALTATAS_MEZOK:
        kimeneti_kulcs, forras_kulcs = _SZOLGALTATAS_MEZOK[mit]
        szolgaltatasok = torzsadat_repo.services_list(conn, shop_id=bolt_id)
        return hiba.sikeres_eredmeny(
            szolgaltatasok=[
                {"nev": s["nev"], kimeneti_kulcs: s[forras_kulcs]} for s in szolgaltatasok
            ]
        )

    if mit == "megjelenes":
        bolt = torzsadat_repo.shop_load(conn, bolt_id)
        return hiba.sikeres_eredmeny(megjelenes=bolt["megjelenes"] if bolt else "")

    statikus = katalogus.BOLT_INFO_STATIKUS.get(bolt_slug, {})
    return hiba.sikeres_eredmeny(**{mit: statikus.get(mit)})

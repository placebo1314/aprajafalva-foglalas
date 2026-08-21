"""`bolt_info` — nyitvatartás, cím, időtartam (eszkoz-szerzodes skill
táblázata: "nyitvatartás, cím, időtartam", azonosítás nem kell).

Ez az EGYETLEN engedélyezett tényválasz-eszköz azonosítás nélkül — az ár
NEM tartozik ide (golden set, `kapuor-02`: "Mennyibe kerül a nagy
petárda?" → `nincs`, tiltott minta: `kitalalt_ar`). Ha egy jövőbeli
igény miatt az ár is engedélyezett tényválasz lenne, az séma-verzióváltás
(v2) és ADR, nem csendes bővítés.

A cím/nyitvatartás MA statikus, kódba írt adat (lásd
`assistant/tools/katalogus.py::BOLT_INFO_STATIKUS` — a `bolt` táblának
nincs ilyen oszlopa). Az időtartam a ténylegesen regisztrált
szolgáltatások alapértelmezett időtartama, valódi DB-adatból."""

from __future__ import annotations

from assistant.tools import hiba, katalogus, semaellenorzo, semak
from core.repo import torzsadat_repo


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
    if mit == "idotartam":
        szolgaltatasok = torzsadat_repo.services_list(conn, shop_id=bolt_id)
        return hiba.sikeres_eredmeny(
            szolgaltatasok=[
                {"nev": s["nev"], "idotartam_perc": s["alap_idotartam_perc"]}
                for s in szolgaltatasok
            ]
        )

    statikus = katalogus.BOLT_INFO_STATIKUS.get(bolt_slug, {})
    return hiba.sikeres_eredmeny(**{mit: statikus.get(mit)})

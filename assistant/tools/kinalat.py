"""`kinalat` — MI VAN ITT EGYÁLTALÁN: a boltok és a szolgáltatásaik,
rövid leírással (ADR-032).

**Mért hiány** (2026-09-05, első IDEGEN próba, négy forduló): a rendszer
feltételezte, hogy a vásárló ismeri a boltokat. A „helló" mondatra azt
kérdezte, melyik boltba szeretne menni; a „milyenek vannak?" kérdésre
pedig — mert az megint nem tartalmazott boltnevet — az ismétlés-figyelő
kiutat ajánlott, majd elküldte a vásárlót a boltba, élőben.

Négy forduló alatt jutott el a köszönéstől odáig, hogy „ne kínlódj vele
tovább". Nem azért, mert rossz kérdést tett fel — hanem mert olyat
kérdezett, amire nem volt válaszunk.

## Mit ad vissza

Boltonként: a slug, a NÉV, és a bolt szolgáltatásai (név, rövid
leírás, időtartam). `bolt_id` megadásakor CSAK azt a boltot — ha a
beszélgetésből már tudjuk, hova megy a vásárló, a másik kettő
felsorolása zaj lenne.

**Minden adat az adatbázisból jön** (`core/repo/torzsadat_repo.py`), nem
a kódból: a bolt neve, a szolgáltatás neve és a termékleírás egyaránt
szerkesztett törzsadat (blueprint 10., „Bolti tudás — szerkesztett adat,
nem modell-tudás"). Ha az admin átírja a leírást, ez a válasz is
változik — külön kódmódosítás nélkül.

**Az ÁR nem megy ki.** Ugyanaz a kimeneti tiltás, mint a `bolt_info`
`termek` ágán (blueprint 7. és 10.): az ár ezen a csatornán nem
engedélyezett tényválasz, és a tiltást nem elég az útvonal elején
érvényesíteni.
"""

from __future__ import annotations

from assistant.tools import hiba, katalogus, semaellenorzo, semak
from core.repo import torzsadat_repo

# A leírás RÖVID alakja a felsoroláshoz. A teljes termékleírás több
# mondat (l. `seed/betolt.py`) — egy katalógusban az első mondat elég,
# a részletet a `bolt_info` adja, ha a vásárló rákérdez.
_LEIRAS_MAX_MONDAT = 1


def _rovid_leiras(termekleiras: str) -> str:
    """A termékleírás ELSŐ mondata. Üres leírásból üres string — a
    „nincs megadva" nem hiba, csak azt jelenti, hogy erre a mezőre nincs
    szerkesztett válasz."""
    if not termekleiras:
        return ""
    mondatok = [resz.strip() for resz in termekleiras.split(".") if resz.strip()]
    return ". ".join(mondatok[:_LEIRAS_MAX_MONDAT]) + "." if mondatok else ""


def hivas(conn, parameterek: dict, *, org_id: str) -> dict:
    sema = semak.SEMAK["kinalat"][semak.legutobbi_verzio("kinalat")]
    hibak = semaellenorzo.ellenoriz(sema, parameterek)
    if hibak:
        return hiba.hiba_eredmeny(hiba.Ok.ERVENYTELEN_PARAMETER, "ervenytelen_kereses")

    bolt_slug = parameterek.get("bolt_id")
    if bolt_slug and bolt_slug != katalogus.MINDEGY:
        bolt_id = katalogus.bolt_id_felold(conn, org_id, bolt_slug)
        if bolt_id is None:
            return hiba.hiba_eredmeny(hiba.Ok.ISMERETLEN_BOLT, "ismeretlen_bolt")
        slugok = {bolt_slug: bolt_id}
    else:
        # A SORREND a katalógusé (`katalogus.BOLT_NEVEK`), nem az
        # adatbázisé: a felsorolás sorrendje a vásárlónak szól, és
        # állandónak kell lennie — egy átnevezés nem rendezheti át.
        slugok = {
            slug: azonosito
            for slug in katalogus.BOLT_NEVEK
            if (azonosito := katalogus.bolt_id_felold(conn, org_id, slug)) is not None
        }

    boltok = []
    for slug, bolt_id in slugok.items():
        bolt = torzsadat_repo.shop_load(conn, bolt_id)
        boltok.append(
            {
                "bolt_id": slug,
                "nev": bolt["nev"] if bolt else katalogus.BOLT_NEVEK.get(slug, slug),
                "szolgaltatasok": [
                    {
                        "nev": szolgaltatas["nev"],
                        "leiras": _rovid_leiras(szolgaltatas["termekleiras"]),
                        "idotartam_perc": szolgaltatas["alap_idotartam_perc"],
                    }
                    for szolgaltatas in torzsadat_repo.services_list(conn, shop_id=bolt_id)
                ],
            }
        )

    if not boltok:
        return hiba.hiba_eredmeny(hiba.Ok.ISMERETLEN_BOLT, "ismeretlen_bolt")
    return hiba.sikeres_eredmeny(boltok=boltok)

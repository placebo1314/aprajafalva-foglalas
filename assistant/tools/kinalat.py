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

# Hány köznyelvi alak megy a modellnek szolgáltatásonként. Minden szó
# latencia (`docs/PLATFORM_TANULSAGOK.md`), és a lista eleje a
# leggyakoribb — a bolt sorrendje szándék, nem véletlen.
_KOZNYELVI_MAX = 4


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
                        # AHOGY A VÁSÁRLÓ KÉRI (0005. migráció). A
                        # katalógus-válaszban nem jelenik meg — a
                        # felsorolás a bolt SAJÁT szavaival szól —,
                        # a modellnek szóló kínálat-sorba viszont
                        # ez a fontos rész (`prompt_sor`).
                        "koznyelvi_nevek": szolgaltatas["koznyelvi_nevek"],
                    }
                    for szolgaltatas in torzsadat_repo.services_list(conn, shop_id=bolt_id)
                ],
            }
        )

    if not boltok:
        return hiba.hiba_eredmeny(hiba.Ok.ISMERETLEN_BOLT, "ismeretlen_bolt")
    return hiba.sikeres_eredmeny(boltok=boltok)


def prompt_sor(conn, *, org_id: str) -> str | None:
    """A KÍNÁLAT egyetlen sorban, a modellnek (ADR-035).

        Kínálat: szundi: altató (alvás, álom, altatófőzet); ugyifogyi:
        petárda (tűzijáték, durranás, rakéta); torpilla: boldogság
        (öröm, nagy öröm, beszélgetés)

    **Miért nem a rendszerpromptba égetve.** Mert adat: a bolt tudja,
    milyen szóval kérik nála a szolgáltatást, nem mi. Az első idegen
    próba nyitómondata ezen bukott el — „Örömöt szeretnék. Van
    nálatok?" —, és a rendszer azt kérdezte vissza, melyik boltba
    szeretne menni. Az „öröm" azóta a `szolgaltatas.koznyelvi_nevek`
    oszlopban áll (0005. migráció): ha egy bolt holnap más szóval is
    árulja, az admin írja be, nem mi írjuk át a promptot.

    A SLUG megy ki, nem a bolt neve: a modellnek a slugot kell
    visszaadnia (arra van enum a sémában), és a kettő között nem
    hagyunk fordítási lépést.

    `None`, ha nincs mit mondani — üres törzsadatnál a hallgatás a
    pontos állítás."""
    eredmeny = hivas(conn, {"session_id": "prompt"}, org_id=org_id)
    if not eredmeny["sikeres"]:
        return None
    reszek = []
    for bolt in eredmeny["boltok"]:
        for szolgaltatas in bolt["szolgaltatasok"]:
            nevek = szolgaltatas.get("koznyelvi_nevek") or []
            koznyelvi = f" ({', '.join(nevek[:_KOZNYELVI_MAX])})" if nevek else ""
            reszek.append(f"{bolt['bolt_id']}: {szolgaltatas['nev']}{koznyelvi}")
    if not reszek:
        return None
    return "Kínálat: " + "; ".join(reszek)


def koznyelvi_szotar(conn, *, org_id: str) -> dict[str, str]:
    """KÖZNYELVI ALAK → bolt slug, a törzsadatból (ADR-035).

    A `prompt_sor` a modellnek szól; ez a determinisztikus kapunak. Ha
    a modell nem jutott el az „örömtől" a Törpilláig — és mérve nem
    mindig jut el —, a kapu eljut.

    A szolgáltatás SAJÁT neve is bekerül („boldogság"), nem csak a
    köznyelvi alakok: ugyanaz a felhasználás, és a hívónak nem kell két
    szótárat kezelnie. Ütközésnél az ELSŐ bolt nyer (a katalógus
    sorrendje szerint) — egy szó, ami két boltra is illik, nem szótár
    kérdése, hanem törzsadat-hiba, és a bolt döntse el, ne mi."""
    eredmeny = hivas(conn, {"session_id": "szotar"}, org_id=org_id)
    if not eredmeny["sikeres"]:
        return {}
    szotar: dict[str, str] = {}
    for bolt in eredmeny["boltok"]:
        for szolgaltatas in bolt["szolgaltatasok"]:
            nevek = [szolgaltatas["nev"], *(szolgaltatas.get("koznyelvi_nevek") or [])]
            for nev in nevek:
                szotar.setdefault(nev.strip().lower(), bolt["bolt_id"])
    return szotar

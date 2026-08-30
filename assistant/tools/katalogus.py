"""Zárt azonosító-halmazok az eszközsémákhoz (eszkoz-szerzodes skill,
"Zárt halmazok mindenhol, ahol lehet").

A JSON-sémák enumjai stabil **slug**-okat várnak (pl. `"torpilla"`), nem a
DB UUID-okat — ezt a séma-verzió (v1) rögzíti, séma-verzióváltás nélkül
nem bővül szabadon. A slug → valódi azonosító feloldás NÉV szerint
történik a `torzsadat_repo`-n keresztül, nem egy előre kiszámolt
UUID-listával — így bármelyik, a névkonvenciót követő adatbázison
(seed vagy teszt) működik, nem csak a `seed/betolt.py` determinisztikus
UUID-jeivel.

**A golden set finomabb szolgáltatás-szintet feltételez** (kis/nagy
petárda, nagy öröm), mint a jelenlegi seed-adat egyetlen szolgáltatása
boltonként (`docs/domain.md`, "Szolgáltatás ≠ variáns" — ez a
megkülönböztetés a variáns szintjén ütemezési hatás nélküli). Ezért a
`kis_petarda` és `nagy_petarda` slug egyaránt az Ügyifogyi egyetlen
"petárda" szolgáltatására mutat, a `nagy_orom` pedig a Törpilla
"boldogság" szolgáltatására. Ha ez valaha valódi, ütemezési hatású
megkülönböztetéssé válik, az új szolgáltatás-sorokat és séma-verziót
igényel — ADR kell hozzá, nem csendes bővítés.
"""

from __future__ import annotations

from core.repo import torzsadat_repo

# A „MINDEGY" SZENTINEL — a vásárló ELENGEDTE ezt a mezőt.
#
# **Három állapot van, nem kettő**, és a különbség viselkedésbeli:
#
# | Érték | Jelentés | Mit tesz a rendszer |
# |---|---|---|
# | hiányzik / `None` | nem tudjuk | KÉRDEZ |
# | `MINDEGY` | a vásárló elengedte | NEM kérdez többé, mindenben keres |
# | konkrét slug | tudjuk | arra szűkít |
#
# Enélkül a „mindegy melyik pult" válasz ugyanaz volt, mint a hallgatás:
# a mező üresen maradt, a rendszer pedig újra rákérdezett — arra, amit a
# vásárló épp az imént engedett el. A `None` és a „mindegy" ÖSSZEMOSÁSA
# volt a hiba, nem a kérdés maga.
#
# Zárt halmazbeli érték (a sémák enumjában is szerepel), tehát a modell
# is használhatja — a felismerése nyelvi feladat, nem kulcsszólista
# (`assistant/interpreter/llm_based.py` rendszerprompt).
MINDEGY = "MINDEGY"

# slug -> a torzsadat_repo-ban tárolt pontos bolt-név.
BOLT_NEVEK: dict[str, str] = {
    "szundi": "Szundi",
    "ugyifogyi": "Ügyifogyi",
    "torpilla": "Törpilla",
}

# slug -> (bolt_slug, a torzsadat_repo-ban tárolt pontos szolgáltatás-név).
SZOLGALTATAS_NEVEK: dict[str, tuple[str, str]] = {
    "altato": ("szundi", "altató"),
    "kis_petarda": ("ugyifogyi", "petárda"),
    "nagy_petarda": ("ugyifogyi", "petárda"),
    "nagy_orom": ("torpilla", "boldogság"),
}

# bolt_slug -> szolgaltatas_slug, azokra a boltokra, ahol a szolgáltatás
# egyértelmű (egyetlen katalógus-bejegyzés tartozik hozzá) — ezekre a
# szolgáltatás automatikusan kitölthető, ha a bolt ismert (golden set,
# koznyelvi-02 megjegyzése: "A boltnak egy szolgáltatása van, ezért a
# szolgáltatás egyértelmű"). Ügyifogyi szándékosan kimarad: két slug
# (kis/nagy petárda) tartozik hozzá, a méret nem következik a boltból.
BOLT_EGYERTELMU_SZOLGALTATAS: dict[str, str] = {
    "szundi": "altato",
    "torpilla": "nagy_orom",
}

BOLT_SLUGOK = frozenset(BOLT_NEVEK)
SZOLGALTATAS_SLUGOK = frozenset(SZOLGALTATAS_NEVEK)

# A `bolt` tábla (migrations/0001_alapsema.sql) NEM tartalmaz cím vagy
# nyitvatartás oszlopot — ez a `bolt_info` eszköznek kellő adat MA sehol
# nincs modellezve. Amíg nincs rá önálló migráció és admin-szerkesztő
# felület (ADR kell hozzá, ha a valós működtetés ezt igényli), ez egy
# dokumentáltan STATIKUS, kódba írt v1 helyőrző — nem a `torzsadat_repo`-n
# keresztül jön, mert nincs mögötte tábla.
BOLT_INFO_STATIKUS: dict[str, dict[str, str]] = {
    "szundi": {"cim": "Aprajafalva, Pihenő utca 1.", "nyitvatartas": "H-Szo 20:00-06:00"},
    "ugyifogyi": {"cim": "Aprajafalva, Durranó tér 3.", "nyitvatartas": "H-V 08:00-20:00"},
    "torpilla": {"cim": "Aprajafalva, Fő utca 7.", "nyitvatartas": "H-Szo 08:00-16:00"},
}


def bolt_id_felold(conn, org_id: str, slug: str) -> str | None:
    """A slug-hoz tartozó valódi `bolt.id`, vagy `None`, ha a slug nem
    érvényes, vagy a névvel nincs bolt ebben a szervezetben."""
    nev = BOLT_NEVEK.get(slug)
    if nev is None:
        return None
    for bolt in torzsadat_repo.shops_list(conn, org_id=org_id):
        if bolt["nev"] == nev:
            return bolt["id"]
    return None


def szolgaltatas_id_felold(conn, org_id: str, slug: str) -> str | None:
    """A slug-hoz tartozó valódi `szolgaltatas.id`, vagy `None`, ha a
    slug nem érvényes, a bolt nem található, vagy a névvel nincs
    szolgáltatás abban a boltban."""
    bejegyzes = SZOLGALTATAS_NEVEK.get(slug)
    if bejegyzes is None:
        return None
    bolt_slug, szolgaltatas_nev = bejegyzes
    bolt_id = bolt_id_felold(conn, org_id, bolt_slug)
    if bolt_id is None:
        return None
    for szolgaltatas in torzsadat_repo.services_list(conn, shop_id=bolt_id):
        if szolgaltatas["nev"] == szolgaltatas_nev:
            return szolgaltatas["id"]
    return None

"""Ajánlatpontozó — ADR-006, blueprint 6. szakasz.

```
pontszám = w1 * (1 - tényleges_lefedettség)
         + w2 * (1 - várható_lefedettség)
         korlátozva: csak a kért ablakon belül
         kizárva:    szabad sáv, blokkolt idő
```

Ez NEM ugyanaz, mint `foglalas_repo.free_slots_search()` — az puszta,
rendezetlen listázás (a CLI `keres` parancsának), ez itt pontoz és
rangsorol, és **csak ez adhat jelöltet az asszisztensnek** (a
`szabad_idopontok` eszköz erre épül, nem a nyers listázásra).

A szabad sáv és a blokkolt idő kizárása nem itt történik: a slotgenerátor
(`core/slot/blokk.py`) ezeket eleve NEM alakítja slottá — a `slot` tábla
már csak ténylegesen foglalható időt tartalmaz, ezért a `free_slots_search`
eredménye erről a szempontról már tiszta (ADR-011).

`tényleges_lefedettség`: a jelölt slot testvér-slotjainak (ugyanaz a
műszak) hányad része foglalt vagy holdolt — ezt a `slot_statuses_list()`
adja meg készen.

`várható_lefedettség`: a szándékindexből (`szandekindex.py`) — hány MÁS
aktív session érdeklődik ugyanarra a bolt+nap+napszak sávra, egy
irányszám-alapú normalizálással (v1: nincs történeti adat, sem admin
felületről jelölt "népszerű sáv" mező — ez a becslés ennyire durva marad
addig, lásd ADR-006 "Kiváltó feltétel").
"""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from core.api import szandekindex
from core.repo import foglalas_repo, torzsadat_repo

# Az illesztés korlát, nem súly (ADR-006) — ezek a súlyok csak a MÁR a
# kért ablakon belülre szűrt jelöltek közti sorrendet finomítják.
W1_TENYLEGES = 0.6
W2_VARHATO = 0.4

# Napszak-sávok HELYI óra szerint, félig-nyitva [kezdő, záró).
_NAPSZAK_SAVOK = {
    "delelott": (6, 12),
    "delutan": (12, 18),
    "este": (18, 23),
}

# Ha ennyi vagy ennél több MÁS session mutat azonos szándékot, a várható
# lefedettség 1.0-nak (teljesen "várhatóan lefedett") számít — irányszám,
# nincs mögötte mérés (lásd a modul docstringjét).
_VARHATO_TELITETTSEG_KUSZOB = 3


def _helyi_ora(kezdet_iso: str, zona: ZoneInfo) -> int:
    utc_ido = datetime.fromisoformat(kezdet_iso.replace("Z", "+00:00"))
    return utc_ido.astimezone(zona).hour


def _napszaknak_megfelel(kezdet_iso: str, napszak: str, zona: ZoneInfo) -> bool:
    if napszak == "barmikor":
        return True
    sav = _NAPSZAK_SAVOK.get(napszak)
    if sav is None:
        return True
    ora = _helyi_ora(kezdet_iso, zona)
    return sav[0] <= ora < sav[1]


def find_candidates(
    conn,
    *,
    org_id: str,
    shop_id: str,
    service_id: str | None = None,
    datum_tol: str,
    datum_ig: str,
    napszak: str = "barmikor",
    session_id: str,
    limit: int = 3,
) -> list[dict]:
    """1-3 pontozott jelöltet ad vissza, kezdet szerint NEM rendezve,
    hanem pontszám szerint csökkenően — a hívó (`szabad_idopontok` eszköz)
    dolga, hogy holdot tegyen rájuk, mielőtt felajánlja őket (CLAUDE.md
    6. invariáns: "csak olyan időpontot mutatunk, amit tartani is tudunk").

    Visszatérési érték elemenként: `{"slot_id", "kezdet", "veg",
    "pontszam"}`. Üres lista = nincs a kért ablakban szabad, a napszaknak
    megfelelő időpont — ez NEM hiba, a hívó dönt az `alternativak`
    kereséséről (pl. napszak nélkül, vagy tágabb dátumablakkal)."""
    org = torzsadat_repo.org_load(conn, org_id)
    zona = ZoneInfo(org["idozona"]) if org else ZoneInfo("UTC")

    nyers = foglalas_repo.free_slots_search(
        conn, org_id=org_id, shop_id=shop_id, service_id=service_id
    )
    jeloltek = [
        (slot_id, kezdet, veg)
        for slot_id, kezdet, veg in nyers
        if datum_tol <= kezdet <= datum_ig and _napszaknak_megfelel(kezdet, napszak, zona)
    ]
    if not jeloltek:
        return []

    lefedettseg_cache: dict[str, float] = {}
    eredmeny = []
    for slot_id, kezdet, veg in jeloltek:
        slot = foglalas_repo.slot_load(conn, slot_id)
        shift_id = slot["muszak_id"]
        if shift_id not in lefedettseg_cache:
            lefedettseg_cache[shift_id] = _tenyleges_lefedettseg(conn, shift_id)
        tenyleges = lefedettseg_cache[shift_id]

        nap = kezdet[:10]
        hasonlo = szandekindex.hasonlo_szandekok_szama(
            bolt_id=shop_id, nap=nap, napszak=napszak, kizart_session_id=session_id
        )
        varhato = min(1.0, hasonlo / _VARHATO_TELITETTSEG_KUSZOB)

        pontszam = W1_TENYLEGES * (1 - tenyleges) + W2_VARHATO * (1 - varhato)
        eredmeny.append({"slot_id": slot_id, "kezdet": kezdet, "veg": veg, "pontszam": pontszam})

    eredmeny.sort(key=lambda jelolt: (-jelolt["pontszam"], jelolt["kezdet"]))
    return eredmeny[:limit]


def _tenyleges_lefedettseg(conn, shift_id: str) -> float:
    """A műszak slotjainak hányad része foglalt vagy holdolt. Üres
    műszaknál (0 slot — pl. kivétel nap, elméletileg nem fordulhat elő,
    hisz a jelölt maga is ebből a műszakból jött) 0.0-t ad, hogy ne
    osszunk nullával."""
    statuszok = foglalas_repo.slot_statuses_list(conn, shift_id=shift_id)
    if not statuszok:
        return 0.0
    foglalt_vagy_holdolt = sum(1 for s in statuszok if s["allapot"] != "szabad")
    return foglalt_vagy_holdolt / len(statuszok)


def earliest_free(
    conn,
    *,
    org_id: str,
    shop_id: str,
    service_id: str | None = None,
    tol_iso: str,
    ig_iso: str,
    napszak: str = "barmikor",
) -> dict | None:
    """A LEGKORÁBBI szabad slot a megadott ablakban — `{"slot_id",
    "kezdet", "veg"}`, vagy `None`, ha nincs.

    **Nem pontoz, és ez szándékos.** Az ajánlatpontozó (ADR-006) akkor
    kell, amikor a vásárló VÁLASZT néhány jelölt közül: ott számít, hogy
    melyik slot töri szét kevésbé a napot. A "mikor tudok legkorábban
    menni?" kérdésnek viszont egyetlen, objektív helyes válasza van — a
    legkorábbi —, és ott a pontozás nemhogy nem segít, hanem torzítana:
    egy jobban pontozott, de KÉSŐBBI időpontot ajánlana a kérdésre, ami
    nem arra kérdezett.

    A `free_slots_search` már kezdet szerint rendezve ad vissza, és
    kizárja az érvényes holdokat és aktív foglalásokat — az első
    napszaknak megfelelő találat a válasz."""
    org = torzsadat_repo.org_load(conn, org_id)
    zona = ZoneInfo(org["idozona"]) if org else ZoneInfo("UTC")

    for slot_id, kezdet, veg in foglalas_repo.free_slots_search(
        conn, org_id=org_id, shop_id=shop_id, service_id=service_id
    ):
        if tol_iso <= kezdet <= ig_iso and _napszaknak_megfelel(kezdet, napszak, zona):
            return {"slot_id": slot_id, "kezdet": kezdet, "veg": veg}
    return None

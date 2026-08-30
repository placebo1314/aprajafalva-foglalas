"""`legkozelebbi_idopont` — "mikor tudok legkorábban menni?", EGY
időpont, holddal.

**Miért külön eszköz, és nem a `szabad_idopontok` egy tág ablakkal.**
A kettő más kérdésre válaszol:

- `szabad_idopontok`: "mikor mehetek szerdán?" → néhány JELÖLT, amik
  közül a vásárló választ; a sorrendet az ajánlatpontozó adja (ADR-006),
  mert ott az számít, melyik időpont töri szét kevésbé a napot.
- `legkozelebbi_idopont`: "mikor tudok legkorábban menni?" → EGY válasz,
  és annak egyetlen objektív helyes értéke van: a legkorábbi szabad
  slot. Itt a pontozás nem segítene, hanem TORZÍTANA — egy jobban
  pontozott, de későbbi időpontot adna arra a kérdésre, ami nem arra
  kérdezett.

A vásárló 3. igénye (blueprint 1. szakasz: "gyorsan végezzen — a gyakori
eset két fordulóból") ezen az úton teljesül a legjobban: egy kérdés, egy
konkrét időpont, mehet a megerősítés.

**A hold ugyanúgy kötelező** (CLAUDE.md 6. invariáns: "csak olyan
időpontot mutatunk, amit tartani is tudunk"): a visszaadott slotra
azonnal hold kerül, mielőtt a hívó látná — ugyanaz a szerződés, mint a
`szabad_idopontok`-nál, és a hívónak (orchestrator) itt sem kell külön
hold-hívást indítania. A `jeloltek` kulcs alatt EGY elemmel tér vissza,
hogy a hívó ugyanazon az ágon tudja kezelni, mint a keresést.

**Horizont.** Dátumablakot szándékosan nem kér: a kérdésben nincs. A
`most`-tól `_HORIZONT_NAP` napig néz előre — enélkül egy üres naptárú
boltnál a "legkorábbi" kérdés a végtelenbe futna. A horizont értéke
üzemeltetési döntés, nem domain-igazság: ha egy bolt ennél messzebbre
hirdet meg időpontot, ezt a számot kell emelni.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from assistant.tools import hiba, katalogus, semaellenorzo, semak, szabad_idopontok
from core.api import ajanlatpontozo
from core.repo import foglalas_repo

# Meddig nézünk előre a "legkorábbi" kérdésre. Hatvan nap: két hónapnál
# messzebbre egy falusi bolt nem hirdet meg beosztást (a demóadat egy
# hétre szól), és egy ennél távolabbi találat válaszként amúgy sem
# lenne hasznos ("legkorábban fél év múlva" nem válasz, hanem elutasítás).
_HORIZONT_NAP = 60

# Ugyanaz a hold-élettartam, mint a `szabad_idopontok`-nál — a vásárló
# szempontjából a kettő ugyanaz a helyzet (kap egy időpontot, amire
# rábólinthat), tehát nem indokolt eltérő TTL.
_HOLD_TTL_MASODPERC = 120


def hivas(conn, parameterek: dict, *, org_id: str) -> dict:
    """`org_id`: melyik szervezetben keresünk — ezt a hívó
    (orchestrator) adja meg, nem az eszköz sémájának paramétere (l.
    `szabad_idopontok.hivas` azonos indoklása)."""
    sema = semak.SEMAK["legkozelebbi_idopont"][semak.legutobbi_verzio("legkozelebbi_idopont")]
    hibak = semaellenorzo.ellenoriz(sema, parameterek)
    if hibak:
        return hiba.hiba_eredmeny(hiba.Ok.ERVENYTELEN_PARAMETER, "ervenytelen_kereses")

    bolt_id = katalogus.bolt_id_felold(conn, org_id, parameterek["bolt_id"])
    if bolt_id is None:
        return hiba.hiba_eredmeny(hiba.Ok.ISMERETLEN_BOLT, "ismeretlen_bolt")

    szolgaltatas_slug = parameterek.get("szolgaltatas_id")
    szolgaltatas_id = None
    if szolgaltatas_slug is not None:
        szolgaltatas_id = katalogus.szolgaltatas_id_felold(conn, org_id, szolgaltatas_slug)
        if szolgaltatas_id is None:
            return hiba.hiba_eredmeny(hiba.Ok.ISMERETLEN_SZOLGALTATAS, "ismeretlen_szolgaltatas")

    most_iso = parameterek["most"]
    most_dt = datetime.fromisoformat(most_iso.replace("Z", "+00:00")).replace(tzinfo=None)
    horizont_iso = f"{(most_dt + timedelta(days=_HORIZONT_NAP)).date().isoformat()}T23:59:59Z"

    jelolt = ajanlatpontozo.earliest_free(
        conn,
        org_id=org_id,
        shop_id=bolt_id,
        service_id=szolgaltatas_id,
        tol_iso=most_iso,
        ig_iso=horizont_iso,
        napszak=parameterek.get("napszak", "barmikor"),
    )
    if jelolt is None:
        # ŐSZINTESÉG-ÁG, ugyanaz a megkülönböztetés, mint a
        # `szabad_idopontok`-nál: az üres naptár NEM szűkösség
        # (blueprint 7. szakasz, "Szűkösség jelzése").
        # MÁSIK BOLT: ugyanaz a kérdés, mint a `szabad_idopontok`-nál —
        # a „nincs" válasz igaz, de haszontalan, ha nem mondja meg, hol
        # VAN (`szabad_idopontok._masik_bolt_ahol_van`).
        masik = szabad_idopontok.masik_bolt_ahol_van(
            conn,
            org_id=org_id,
            kiveve_bolt_id=bolt_id,
            datum_tol=most_iso,
            datum_ig=horizont_iso,
            napszak=parameterek.get("napszak", "barmikor"),
        )
        if not foglalas_repo.published_slots_exist(
            conn, org_id=org_id, shop_id=bolt_id, service_id=szolgaltatas_id, tol_iso=most_iso
        ):
            return hiba.hiba_eredmeny(
                hiba.Ok.NINCS_MEGHIRDETETT_IDOPONT,
                "nincs_meghirdetett_idopont",
                masik_bolt=masik,
            )
        return hiba.hiba_eredmeny(
            hiba.Ok.NINCS_SZABAD_HELY, "nincs_szabad_hely_az_ablakban", masik_bolt=masik
        )

    lejar = (datetime.now(UTC) + timedelta(seconds=_HOLD_TTL_MASODPERC)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    eredmeny = foglalas_repo.hold_create(conn, jelolt["slot_id"], parameterek["session_id"], lejar)
    if eredmeny is not foglalas_repo.Result.SUCCESS:
        # Valaki épp most szerezte meg a pontozás és a hold között —
        # normál verseny-ág (ADR-003), nem rendszerhiba.
        return hiba.hiba_eredmeny(hiba.Ok.MEGELOZTEK, "jeloltek_kozben_elfogytak")

    return hiba.sikeres_eredmeny(
        jeloltek=[{"slot_id": jelolt["slot_id"], "kezdet": jelolt["kezdet"], "veg": jelolt["veg"]}],
        hold_lejar=lejar,
        legkozelebbi=True,
    )

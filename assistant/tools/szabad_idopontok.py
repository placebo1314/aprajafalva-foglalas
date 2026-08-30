"""`szabad_idopontok` — keresés, pontozott jelöltek + hold
(eszkoz-szerzodes skill táblázata: "keresés, pontozott jelöltek + hold",
azonosítás nem kell — böngészéshez semmi nem szükséges, blueprint
8. szakasz).

A visszaadott jelöltekre AZONNAL hold kerül, mielőtt a hívó látná őket —
ez teszi lehetővé a CLAUDE.md 6. invariánsát ("csak olyan időpontot
mutatunk, amit tartani is tudunk"). A hívónak (orchestrator) NEM kell
külön hold-hívást indítania.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from assistant.tools import hiba, katalogus, semaellenorzo, semak
from core.api import ajanlatpontozo
from core.repo import foglalas_repo

# Hold-élettartam a jelölteken — foglalasi-mag skill: "TTL alapból 2-5
# perc, torlódásnál rövidebb". A v1 a rövidebbik szélet választja, hogy
# egy elfelejtett/elhagyott session gyorsan felszabadítsa a slotot.
_HOLD_TTL_MASODPERC = 120


def _hold_lejar(most: datetime) -> str:
    return (most + timedelta(seconds=_HOLD_TTL_MASODPERC)).strftime("%Y-%m-%dT%H:%M:%SZ")


def _het_vege_iso(datum_iso: str) -> str:
    """A `datum_iso` naptári napját tartalmazó hét vasárnapjának napvégi
    időpontja — ugyanaz a "hét vége" fogalom, mint `assistant/
    interpreter/rule_based.py::_het_vege`, csak itt tetszőleges dátumra,
    nem csak `most`-ra."""
    dt = datetime.fromisoformat(datum_iso.replace("Z", "+00:00")).replace(tzinfo=None)
    napok_vasarnapig = 6 - dt.weekday()
    vege = (dt + timedelta(days=napok_vasarnapig)).date()
    return f"{vege.isoformat()}T23:59:59Z"


# A három tágítási dimenzió, a kért ablakhoz legközelebbitől a
# legtávolabbiig. A `napszak` a kért napon belül enged, a `nap` a
# folyó héten belül, a `het` a következő hétre lép.
TAGITASI_DIMENZIOK = ("napszak", "nap", "het")


def tagitott_ablak(
    dimenzio: str, *, datum_tol: str, datum_ig: str, napszak: str
) -> dict[str, str] | None:
    """Egy tágítási dimenzióhoz megadja a MEGFELELŐ keresési ablakot —
    `{"datum_tol", "datum_ig", "napszak"}`, vagy `None`, ha ez a
    tágítás ebben a helyzetben nem értelmezhető (pl. `napszak` tágítás,
    amikor a kérés eleve "barmikor" volt).

    **Egyetlen forrás**: ugyanezt használja az `_alternativ_dimenzio`
    annak eldöntésére, hogy VAN-e alternatíva, és az orchestrator arra,
    hogy a felajánlott gombra ténylegesen ugyanazt a keresést futtassa
    le. Ha a kettő szétdriftelne, a gomb mást mutatna, mint amit a
    rendszer ígért."""
    if dimenzio == "napszak":
        if napszak == "barmikor":
            return None
        return {"datum_tol": datum_tol, "datum_ig": datum_ig, "napszak": "barmikor"}

    het_vege = _het_vege_iso(datum_tol)
    if dimenzio == "nap":
        if datum_ig >= het_vege:
            return None
        return {"datum_tol": datum_tol, "datum_ig": het_vege, "napszak": napszak}

    if dimenzio == "het":
        kovetkezo_vege_dt = datetime.fromisoformat(het_vege.replace("Z", "+00:00")).replace(
            tzinfo=None
        ) + timedelta(days=7)
        return {
            "datum_tol": het_vege,
            "datum_ig": f"{kovetkezo_vege_dt.date().isoformat()}T23:59:59Z",
            "napszak": napszak,
        }
    return None


def masik_bolt_ahol_van(
    conn,
    *,
    org_id: str,
    kiveve_bolt_id: str,
    datum_tol: str,
    datum_ig: str,
    napszak: str,
) -> dict | None:
    """Melyik MÁSIK boltban van szabad időpont ugyanebben az ablakban —
    `{"bolt_id": slug, "legkorabbi": iso}` vagy `None`.

    **Miért kell.** A „nincs meghirdetett időpont" válasz igaz, de
    haszontalan: nem mondja meg, hol VAN. A vásárló 5. igénye (blueprint
    1.) épp ez: *„ha nincs hely, alternatíva jöjjön"* — és az
    `_alternativ_dimenzio` ezt eddig csak a NAPTÁRON belül nézte (másik
    napszak, nap, hét), a boltok között nem.

    **A szolgáltatás-szűrő szándékosan kimarad** a másik boltnál: a
    szolgáltatás bolt-specifikus (az „altató" csak a Szundié), tehát a
    kért szolgáltatással szűrve sosem találnánk semmit. Az ajánlat a
    BOLTRÓL szól, nem a szolgáltatásról.

    **Nem foglal holdot, és a `legkorabbi` időpontot NEM mondjuk ki.**
    A CLAIM ennyi: „ott van szabad időpont" — ugyanaz a fajta állítás,
    mint az `_alternativ_dimenzio`-é, és ugyanúgy egy tényleges
    kereséssel igazolt. Konkrét időpontot csak holddal szabad mutatni
    (CLAUDE.md 6. invariáns), az pedig akkor keletkezik, amikor a
    vásárló ténylegesen odalép. A `legkorabbi` mező a naplóé és a
    jelentésé — abból látszik, MIÉRT ajánlottuk épp azt a boltot."""
    talalatok = []
    for slug in sorted(katalogus.BOLT_SLUGOK):
        masik_id = katalogus.bolt_id_felold(conn, org_id, slug)
        if masik_id is None or masik_id == kiveve_bolt_id:
            continue
        jelolt = ajanlatpontozo.earliest_free(
            conn,
            org_id=org_id,
            shop_id=masik_id,
            service_id=None,
            tol_iso=datum_tol,
            ig_iso=datum_ig,
            napszak=napszak,
        )
        if jelolt is not None:
            talalatok.append({"bolt_id": slug, "legkorabbi": jelolt["kezdet"]})
    if not talalatok:
        return None
    # A LEGKORÁBBI nyer: ha két boltban is van, az az érdekes, ahol
    # hamarabb sorra kerül.
    return min(talalatok, key=lambda t: t["legkorabbi"])


def _alternativ_dimenzio(
    conn,
    *,
    org_id: str,
    bolt_id: str,
    szolgaltatas_id: str | None,
    datum_tol: str,
    datum_ig: str,
    napszak: str,
    session_id: str,
) -> str | None:
    """Ha a kért ablakra nincs jelölt, megmondja, MELYIK dimenzió
    tágításával van — a blueprint 1. szakasz ("Kapjon őszinte választ —
    ha nincs hely, alternatíva jöjjön") és a szándék-rétegzés közös
    nevezője: nem elég azt mondani, hogy nincs hely, azt is meg kell
    mondani, min érdemes lazítani. Csak PRÓBÁL (`find_candidates`, hold
    nélkül) — nem foglal le és nem zárol semmit.

    A három dimenzió **nem egyenrangú** — a `nap` és a `het` próba a
    kért `napszak`-ot VÁLTOZATLANUL hagyja, csak a dátumablakot tágítja
    (pl. "péntek délelőtt jövő héten": a napszak — délelőtt — itt kemény,
    csak a hét puha, l. blueprint 5. szakasz). Csak a `napszak` dimenzió
    próbája engedi el magát a napszak-kötöttséget. Anélkül ez a
    megkülönböztetés hamis pozitívot adna: egy máshol, más napszakban
    szabad időpontot "nap"/"het" alternatívaként ajánlana, holott az a
    vásárló tényleges (napszak-)kérésének nem felel meg.

    Sorrend, a kért ablakhoz legközelebbitől a legtávolabbiig:
    `napszak` (ugyanaz a nap/ablak, más napszak) → `nap` (ugyanazon a
    héten, más nap, UGYANAZ a napszak) → `het` (a következő héten,
    UGYANAZ a napszak). `None`, ha egyik tágítás sem hoz találatot —
    ekkor tényleg nincs mit ajánlani."""

    def van_jelolt(*, datum_tol: str, datum_ig: str, napszak: str) -> bool:
        return bool(
            ajanlatpontozo.find_candidates(
                conn,
                org_id=org_id,
                shop_id=bolt_id,
                service_id=szolgaltatas_id,
                datum_tol=datum_tol,
                datum_ig=datum_ig,
                napszak=napszak,
                session_id=session_id,
                limit=1,
            )
        )

    for dimenzio in TAGITASI_DIMENZIOK:
        ablak = tagitott_ablak(dimenzio, datum_tol=datum_tol, datum_ig=datum_ig, napszak=napszak)
        if ablak is not None and van_jelolt(**ablak):
            return dimenzio
    return None


def hivas(conn, parameterek: dict, *, org_id: str) -> dict:
    """`org_id`: melyik szervezetben keresünk — ezt a hívó (orchestrator)
    adja meg, nem az eszköz sémájának paramétere: a v1 hatókör egyetlen
    szervezettel (Aprajafalva) számol, ezt nem a mondatból kell
    kiolvasni."""
    sema = semak.SEMAK["szabad_idopontok"][semak.legutobbi_verzio("szabad_idopontok")]
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

    jeloltek = ajanlatpontozo.find_candidates(
        conn,
        org_id=org_id,
        shop_id=bolt_id,
        service_id=szolgaltatas_id,
        datum_tol=parameterek["datum_tol"],
        datum_ig=parameterek["datum_ig"],
        napszak=parameterek.get("napszak", "barmikor"),
        session_id=parameterek["session_id"],
    )
    if not jeloltek:
        datum_tol = parameterek["datum_tol"]
        datum_ig = parameterek["datum_ig"]
        napszak = parameterek.get("napszak", "barmikor")

        # ŐSZINTESÉG-ÁG: ha a boltnak EGYÁLTALÁN nincs meghirdetett
        # slotja, az nem szűkösség — a bolt nem vitte fel a beosztást.
        # A kettő összemosása telinek mutatna egy üres naptárat
        # (blueprint 7. szakasz, "Szűkösség jelzése": csak akkor
        # jelezzünk szűkösséget, ha IGAZ).
        if not foglalas_repo.published_slots_exist(
            conn,
            org_id=org_id,
            shop_id=bolt_id,
            service_id=szolgaltatas_id,
            tol_iso=datum_tol,
        ):
            return hiba.hiba_eredmeny(
                hiba.Ok.NINCS_MEGHIRDETETT_IDOPONT,
                "nincs_meghirdetett_idopont",
                alternativ_dimenzio=None,
                masik_bolt=masik_bolt_ahol_van(
                    conn,
                    org_id=org_id,
                    kiveve_bolt_id=bolt_id,
                    datum_tol=datum_tol,
                    datum_ig=datum_ig,
                    napszak=napszak,
                ),
            )

        dimenzio = _alternativ_dimenzio(
            conn,
            org_id=org_id,
            bolt_id=bolt_id,
            szolgaltatas_id=szolgaltatas_id,
            datum_tol=datum_tol,
            datum_ig=datum_ig,
            napszak=napszak,
            session_id=parameterek["session_id"],
        )
        return hiba.hiba_eredmeny(
            hiba.Ok.NINCS_SZABAD_HELY,
            "nincs_szabad_hely_az_ablakban",
            alternativ_dimenzio=dimenzio,
            # MÁSIK BOLT csak akkor, ha a boltON BELÜL nincs mit
            # ajánlani. A sorrend nem esztétika: a vásárló ezt a boltot
            # kérte, tehát előbb a napszakot/napot/hetet tágítjuk, és
            # csak azután javasoljuk, hogy menjen máshova.
            masik_bolt=(
                None
                if dimenzio
                else masik_bolt_ahol_van(
                    conn,
                    org_id=org_id,
                    kiveve_bolt_id=bolt_id,
                    datum_tol=datum_tol,
                    datum_ig=datum_ig,
                    napszak=napszak,
                )
            ),
        )

    lejar = _hold_lejar(datetime.now(UTC))
    holdolt = []
    for jelolt in jeloltek:
        eredmeny = foglalas_repo.hold_create(
            conn, jelolt["slot_id"], parameterek["session_id"], lejar
        )
        if eredmeny is foglalas_repo.Result.SUCCESS:
            holdolt.append(
                {"slot_id": jelolt["slot_id"], "kezdet": jelolt["kezdet"], "veg": jelolt["veg"]}
            )
        # PREEMPTED: valaki épp most szerezte meg köztünk a pontozás és a
        # hold-kísérlet között — kihagyjuk, ez nem hiba (ADR-003 szerint
        # normál verseny-ág), csak eggyel kevesebb jelölt marad.

    if not holdolt:
        return hiba.hiba_eredmeny(hiba.Ok.MEGELOZTEK, "jeloltek_kozben_elfogytak")

    return hiba.sikeres_eredmeny(jeloltek=holdolt, hold_lejar=lejar)

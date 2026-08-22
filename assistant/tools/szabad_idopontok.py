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
    ha nincs hely, alternatíva jöjjön") és a szándék-rétegzés
    (`assistant/orchestrator.py::kovetkezo_kontextus`) közös nevezője:
    nem elég azt mondani, hogy nincs hely, azt is meg kell mondani, min
    érdemes lazítani. Csak PRÓBÁL (`find_candidates`, hold nélkül) — nem
    foglal le és nem zárol semmit.

    Sorrend, a kért ablakhoz legközelebbitől a legtávolabbiig:
    `napszak` (ugyanaz a nap/ablak, más napszak) → `nap` (ugyanazon a
    héten, más nap) → `het` (a következő héten). `None`, ha egyik
    tágítás sem hoz találatot — ekkor tényleg nincs mit ajánlani."""

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

    if napszak != "barmikor" and van_jelolt(
        datum_tol=datum_tol, datum_ig=datum_ig, napszak="barmikor"
    ):
        return "napszak"

    het_vege = _het_vege_iso(datum_tol)
    if datum_ig < het_vege and van_jelolt(
        datum_tol=datum_tol, datum_ig=het_vege, napszak="barmikor"
    ):
        return "nap"

    kovetkezo_het_vege_dt = datetime.fromisoformat(het_vege.replace("Z", "+00:00")).replace(
        tzinfo=None
    ) + timedelta(days=7)
    kovetkezo_het_ig = f"{kovetkezo_het_vege_dt.date().isoformat()}T23:59:59Z"
    if van_jelolt(datum_tol=het_vege, datum_ig=kovetkezo_het_ig, napszak="barmikor"):
        return "het"

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

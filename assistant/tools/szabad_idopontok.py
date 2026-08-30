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


# A LAZÍTÁSI SORREND — bolton belül, a kért ablakhoz legközelebbitől a
# legtávolabbiig (ADR-024).
#
# **A bolt szándékosan NINCS köztük.** A bolt nem cserélhető dimenzió,
# hanem maga a termék: Aprajafalva három boltja három különböző dolgot
# árul (altató / petárda / boldogság), tehát aki petárdát kér, annak a
# boldogság-bolt nem alternatíva, hanem MÁS KÉRÉSRE adott válasz.
#
# - `napszak` — más időpont a KÉRT ablakban: a napszak-kötöttséget
#   engedjük el, a nap marad.
# - `nap` — ugyanazon a héten másik nap, UGYANAZZAL a napszakkal.
# - `kesobb` — tágabb ablak: a kért ablak VÉGE utáni legkorábbi szabad
#   időpont, akár hetekkel később ("a legkorábbi szabad időpont
#   december huszonharmadikán van"). Ez az egyetlen dimenzió, ami nem
#   ablakot tágít, hanem elhagyja az ablak fogalmát —
#   `legkozelebbi_idopont`-tal fut, tehát holddal, tehát a konkrét
#   dátum kimondható (CLAUDE.md 6. invariáns).
# - `varians` — más változat a bolton BELÜL (kis/nagy petárda): a
#   szolgáltatás-szűrést engedjük el. Csak akkor van értelme, ha a
#   vásárló KONKRÉT terméket kért; ha már `MINDEGY`, nincs mit
#   elengedni, mert minden változatot nézünk.
#
# **A `pult` (más pult ugyanabban a boltban) azért nincs a listán, mert
# nincs mit lazítani rajta**: a keresés MA SEM szűkít pultra — sem az
# ajánlatpontozó (`core/api/ajanlatpontozo.py`), sem a repo
# (`foglalas_repo.free_slots_search`: a szűrés bolt és szolgáltatás
# szerint megy, a `pult` csak a slot generálásában szerepel). Egy
# mindig üresen visszatérő ág itt hazugság lenne. Ha valaha
# szűkítenénk pultra, a helye a `nap` és a `kesobb` közé kerül.
LAZITAS_DIMENZIOK = ("napszak", "nap", "kesobb", "varians")

# Meddig nézünk előre a `kesobb` dimenzióban — ugyanaz a horizont, mint
# a `legkozelebbi_idopont` eszközé, mert ugyanaz a kérdés. Nem
# importáljuk onnan: az a modul EBBŐL importál (`_bolt_es_szolgaltatas`,
# `napszak_ertek`), a fordítottja körkörös lenne.
_KESOBB_HORIZONT_NAP = 60


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

    if dimenzio == "nap":
        het_vege = _het_vege_iso(datum_tol)
        if datum_ig >= het_vege:
            return None
        return {"datum_tol": datum_tol, "datum_ig": het_vege, "napszak": napszak}

    # `kesobb` és `varians` NEM ablaktágítás — l. `lazitas_terve`.
    return None


def lazitas_terve(
    dimenzio: str,
    *,
    datum_tol: str,
    datum_ig: str,
    napszak: str,
    szolgaltatas_szures: bool,
) -> dict | None:
    """Egy lazítási dimenzióhoz megadja, MIT kell futtatni:
    `{"eszkoz": ..., "parameterek": {...}}`, vagy `None`, ha ez a
    lazítás ebben a helyzetben nem értelmezhető.

    **Egyetlen forrás** (ugyanaz az elv, mint korábban a
    `tagitott_ablak`-é, csak most a nem-ablak dimenziókra is): ebből
    dönti el az `_alternativ_dimenzio`, hogy VAN-e mit ajánlani, és
    ugyanebből futtatja az orchestrator a felajánlott gombot. Ha a kettő
    szétdriftelne, a gomb mást mutatna, mint amit a rendszer ígért.

    `szolgaltatas_szures`: szűkít-e MA a keresés konkrét szolgáltatásra.
    Ha nem (hiányzik vagy `MINDEGY`), a `varians` dimenzió értelmetlen —
    nincs mit elengedni."""
    if dimenzio in ("napszak", "nap"):
        ablak = tagitott_ablak(dimenzio, datum_tol=datum_tol, datum_ig=datum_ig, napszak=napszak)
        if ablak is None:
            return None
        return {"eszkoz": "szabad_idopontok", "parameterek": ablak}

    if dimenzio == "kesobb":
        # A kért ablak VÉGÉTŐL nézve a legkorábbi — az eszköz `most`
        # paramétere itt nem rendszeridő, hanem a keresés kezdőpontja
        # (a séma szerint is csak ennyi a dolga).
        return {
            "eszkoz": "legkozelebbi_idopont",
            "parameterek": {"most": datum_ig, "napszak": napszak},
        }

    if dimenzio == "varians":
        if not szolgaltatas_szures:
            return None
        return {
            "eszkoz": "szabad_idopontok",
            "parameterek": {
                "datum_tol": datum_tol,
                "datum_ig": datum_ig,
                "napszak": napszak,
                "szolgaltatas_id": katalogus.MINDEGY,
            },
        }
    return None


def _alternativ_dimenzio(
    conn,
    *,
    org_id: str,
    bolt_id: str | None,
    szolgaltatas_id: str | None,
    datum_tol: str,
    datum_ig: str,
    napszak: str,
    session_id: str,
) -> str | None:
    """Ha a kért ablakra nincs jelölt, megmondja, MELYIK dimenzió
    mentén van — a blueprint 1. szakasz ("Kapjon őszinte választ — ha
    nincs hely, alternatíva jöjjön"): nem elég azt mondani, hogy nincs
    hely, azt is meg kell mondani, min érdemes engedni. Csak PRÓBÁL
    (`find_candidates` / `earliest_free`, hold nélkül) — nem foglal le
    és nem zárol semmit.

    A sorrend és a dimenziók jelentése a `LAZITAS_DIMENZIOK`-nál van
    leírva; a lépés tartalmát a `lazitas_terve` adja, hogy a próba és a
    felajánlott gomb ugyanaz legyen.

    A dimenziók **nem egyenrangúak** — a `nap` és a `kesobb` próba a
    kért `napszak`-ot VÁLTOZATLANUL hagyja, csak az időben lép (pl.
    "péntek délelőtt": a délelőtt itt kemény, csak a nap puha, l.
    blueprint 5. szakasz). Csak a `napszak` dimenzió engedi el magát a
    napszak-kötöttséget. Anélkül ez a megkülönböztetés hamis pozitívot
    adna: egy más napszakban szabad időpontot "nap"/"kesobb"
    alternatívaként ajánlana, holott az a vásárló tényleges kérésének
    nem felel meg.

    `None`, ha egyik lazítás sem hoz találatot — ekkor tényleg nincs
    mit ajánlani."""

    def van_jelolt(parameterek: dict) -> bool:
        return bool(
            ajanlatpontozo.find_candidates(
                conn,
                org_id=org_id,
                shop_id=bolt_id,
                # A `varians` terve MINDEGY-et ad, ami itt a szűrés
                # elhagyását jelenti (l. `_bolt_es_szolgaltatas`).
                service_id=(
                    None
                    if parameterek.get("szolgaltatas_id") == katalogus.MINDEGY
                    else szolgaltatas_id
                ),
                datum_tol=parameterek["datum_tol"],
                datum_ig=parameterek["datum_ig"],
                napszak=parameterek["napszak"],
                session_id=session_id,
                limit=1,
            )
        )

    def van_kesobb(parameterek: dict) -> bool:
        tol = parameterek["most"]
        tol_dt = datetime.fromisoformat(tol.replace("Z", "+00:00")).replace(tzinfo=None)
        ig = f"{(tol_dt + timedelta(days=_KESOBB_HORIZONT_NAP)).date().isoformat()}T23:59:59Z"
        return (
            ajanlatpontozo.earliest_free(
                conn,
                org_id=org_id,
                shop_id=bolt_id,
                service_id=szolgaltatas_id,
                tol_iso=tol,
                ig_iso=ig,
                napszak=parameterek["napszak"],
            )
            is not None
        )

    for dimenzio in LAZITAS_DIMENZIOK:
        terv = lazitas_terve(
            dimenzio,
            datum_tol=datum_tol,
            datum_ig=datum_ig,
            napszak=napszak,
            szolgaltatas_szures=szolgaltatas_id is not None,
        )
        if terv is None:
            continue
        probal = van_kesobb if terv["eszkoz"] == "legkozelebbi_idopont" else van_jelolt
        if probal(terv["parameterek"]):
            return dimenzio
    return None


def _bolt_es_szolgaltatas(conn, org_id: str, parameterek: dict):
    """`(bolt_id | None, szolgaltatas_id | None, hiba | None)` — a két
    zárt halmazbeli mező feloldása, a MINDEGY szentinel kezelésével.

    **A `MINDEGY` nem ismeretlen érték, hanem ELENGEDETT mező**
    (`katalogus.MINDEGY`): a vásárló azt mondta, „mindegy melyik". A
    feloldás eredménye ilyenkor `None`, ami a lekérdező rétegben
    pontosan azt jelenti, hogy nincs szűrés erre a mezőre
    (`foglalas_repo.free_slots_search` már így is működik) — tehát
    MINDEN boltban, illetve minden szolgáltatásra keresünk.

    A hiányzó mező (`None` a bemenetben) NEM ugyanez: az a hívó dolga,
    hogy kérdezzen rá; ide csak akkor jut el, ha a séma megengedi."""
    bolt_slug = parameterek.get("bolt_id")
    bolt_id = None
    if bolt_slug is not None and bolt_slug != katalogus.MINDEGY:
        bolt_id = katalogus.bolt_id_felold(conn, org_id, bolt_slug)
        if bolt_id is None:
            return None, None, hiba.hiba_eredmeny(hiba.Ok.ISMERETLEN_BOLT, "ismeretlen_bolt")

    szolgaltatas_slug = parameterek.get("szolgaltatas_id")
    szolgaltatas_id = None
    if szolgaltatas_slug is not None and szolgaltatas_slug != katalogus.MINDEGY:
        szolgaltatas_id = katalogus.szolgaltatas_id_felold(conn, org_id, szolgaltatas_slug)
        if szolgaltatas_id is None:
            return (
                None,
                None,
                hiba.hiba_eredmeny(hiba.Ok.ISMERETLEN_SZOLGALTATAS, "ismeretlen_szolgaltatas"),
            )
    return bolt_id, szolgaltatas_id, None


def napszak_ertek(parameterek: dict) -> str:
    """A napszak, a MINDEGY szentinelt „barmikor"-ra fordítva — a kettő
    a KERESÉS szempontjából ugyanaz, csak a szándék más: a „bármikor" a
    rendszer alapértelmezése, a MINDEGY a vásárló kimondott döntése.
    A megkülönböztetés a kontextusban számít (nem kérdezünk rá újra),
    a szűrésben nem."""
    napszak = parameterek.get("napszak", "barmikor")
    return "barmikor" if napszak == katalogus.MINDEGY else napszak


def hivas(conn, parameterek: dict, *, org_id: str) -> dict:
    """`org_id`: melyik szervezetben keresünk — ezt a hívó (orchestrator)
    adja meg, nem az eszköz sémájának paramétere: a v1 hatókör egyetlen
    szervezettel (Aprajafalva) számol, ezt nem a mondatból kell
    kiolvasni."""
    sema = semak.SEMAK["szabad_idopontok"][semak.legutobbi_verzio("szabad_idopontok")]
    hibak = semaellenorzo.ellenoriz(sema, parameterek)
    if hibak:
        return hiba.hiba_eredmeny(hiba.Ok.ERVENYTELEN_PARAMETER, "ervenytelen_kereses")

    bolt_id, szolgaltatas_id, felold_hiba = _bolt_es_szolgaltatas(conn, org_id, parameterek)
    if felold_hiba is not None:
        return felold_hiba

    jeloltek = ajanlatpontozo.find_candidates(
        conn,
        org_id=org_id,
        shop_id=bolt_id,
        service_id=szolgaltatas_id,
        datum_tol=parameterek["datum_tol"],
        datum_ig=parameterek["datum_ig"],
        napszak=napszak_ertek(parameterek),
        session_id=parameterek["session_id"],
    )
    if not jeloltek:
        datum_tol = parameterek["datum_tol"]
        datum_ig = parameterek["datum_ig"]
        napszak = napszak_ertek(parameterek)

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

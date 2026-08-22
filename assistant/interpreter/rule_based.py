"""Determinisztikus (szabály-alapú) `Ertelmezo` implementáció.

Ez az **alapvonal, ami fölé egy jövőbeli LLM-es értelmezőnek kerülnie
kell** — nem azért íródott, hogy tökéletes legyen, hanem hogy legyen
mihez mérni (roadmap M4: "modellválasztás méréssel"). A golden set
`--ertelmezo szabaly` módja ezt méri (`spike/golden_futtato.py`).

A feldolgozás sorrendje (mindegyik az előzőt kizárva):

1. kapuőr — nem foglalással kapcsolatos kérés (időjárás, ár) → `nincs`
2. tényválasz-szándék (nyitvatartás/cím/megjelenés/termék) → `bolt_info`
   ("ár" a séma szintjén létezik, de ide sosem jut el — a kapuőr korábban
   elkapja, l. 1. pont)
3. lemondás-szándék → `foglalas_lemondas`, vagy `visszakerdez` kód nélkül
4. áthelyezés-szándék → `visszakerdez` (a v1 nem keres új időpontot
   automatikusan egy mondatból — lásd `assistant/orchestrator.py`
   hatókör-korlátja)
5. alapértelmezett: keresési szándék → `szabad_idopontok`, vagy
   `visszakerdez`, ha a bolt nem azonosítható

A `visszakerdez` ág **csak ténylegesen kinyert adatot** tesz a
válaszba — sosem alapértelmezést/tartalék-ablakot (azok csak a
`szabad_idopontok` ág végén kerülnek be, amikor a hívónak MINDENKÉPP
kell valamilyen dátumablak)."""

from __future__ import annotations

import re
from datetime import datetime, timedelta

from hun_date_parser import text2datetime

from assistant.interpreter import ErtelmezesKontextus
from assistant.interpreter.normalizalo import normalizal
from assistant.tools import katalogus

_KAPUOR_MINTAK = re.compile(r"milyen id[őo]\b|id[őo]j[áa]r[áa]s|mennyibe ker[üu]l|mibe ker[üu]l")
_NYITVATARTAS_MINTA = re.compile(r"nyitva|nyitvatart[áa]s|mikor nyit|mikor z[áa]r")
_CIM_MINTA = re.compile(r"\bhol van\b|merre van|\bc[íi]m\b")
_MEGJELENES_KOZVETLEN_MINTA = re.compile(r"n[ée]z\s*ki|ismerem\s*fel|ismerni\s*fel")
_MEGJELENES_MILYEN_MINTA = re.compile(r"\bmilyen\b")
_MEGJELENES_TARGY_MINTA = re.compile(r"bolt|kirakat|c[ée]g[ée]r|homlokzat")
_TERMEK_MINTA = re.compile(
    r"mit\s*[áa]rul|milyen\s*term[ée]k|mit\s*lehet\s*kapni|mit\s*lehet\s*venni|mit\s*kapni"
)
_LEMONDAS_MINTA = re.compile(r"le\s*szeretn[ée]m\s*mondani|\blemond")
_ATHELYEZES_MINTA = re.compile(r"[áa]thelyez|[áa]t\s*tudn[áa]m\s*tenni|[áa]ttenni|[áa]t\s*tenni")
_KOD_MINTA = re.compile(r"\b[A-Z0-9]{6,10}\b")

# Legalább egy tényleges NAP-jelző szónak szerepelnie kell ahhoz, hogy a
# hun_date_parser eredményét elfogadjuk — l. _datum_ablak_explicit
# docstringje: önmagában álló napszak-szó (pl. bare "délelőtt") nélküle
# hamis pozitívot ad.
_NAP_JELZO_MINTA = re.compile(
    r"\bma\b|\bholnap|hétf[őo]|\bkedd|szerd[áa]|csütörtök|péntek|szombat|vasárnap"
)

_BOLT_MINTAK: list[tuple[re.Pattern, str]] = [
    (re.compile(r"szundi|altat[óo]"), "szundi"),
    (re.compile(r"ügyifogyi|ugyifogyi|pet[áa]rd"), "ugyifogyi"),
    (re.compile(r"törpill|torpill|boldogs[áa]g"), "torpilla"),
]

_NAPSZAK_MINTAK: list[tuple[re.Pattern, str]] = [
    (re.compile(r"délel[őo]tt|reggel"), "delelott"),
    (re.compile(r"délut[áa]n"), "delutan"),
    (re.compile(r"\beste\b"), "este"),
]

# A golden set konvenciója: egynapos ablaknál, ha van explicit napszak,
# a datum_ig órára vágódik, a datum_tol naphatáron marad (lásd
# tajszolas-01, szleng-01, toredekes-03).
_NAPSZAK_VEGORA = {"delelott": 11, "delutan": 17, "este": 22}

_PREFERALT_ORA_MINTA = re.compile(r"\b(\d{1,2})\s*(?:óra|körül)")


def _kapuor_talalat(also: str) -> bool:
    return _KAPUOR_MINTAK.search(also) is not None


def _megjelenes_kerdes(also: str) -> bool:
    if _MEGJELENES_KOZVETLEN_MINTA.search(also):
        return True
    # "milyen" és a tárgy (bolt/kirakat/...) nem feltétlenül szomszédos
    # szavak ("Milyen a Szundi kirakata?") — külön keresett, nem egy
    # összefüggő mintaként.
    return bool(_MEGJELENES_MILYEN_MINTA.search(also) and _MEGJELENES_TARGY_MINTA.search(also))


def _bolt_info_mezo(also: str) -> str | None:
    if _NYITVATARTAS_MINTA.search(also):
        return "nyitvatartas"
    if _CIM_MINTA.search(also):
        return "cim"
    if _megjelenes_kerdes(also):
        return "megjelenes"
    if _TERMEK_MINTA.search(also):
        return "termek"
    return None


def _bolt_azonositas(also: str) -> str | None:
    for minta, slug in _BOLT_MINTAK:
        if minta.search(also):
            return slug
    return None


def _szolgaltatas_azonositas(also: str, bolt_id: str | None) -> str | None:
    if bolt_id != "ugyifogyi":
        return None
    if re.search(r"\bnagy\b", also):
        return "nagy_petarda"
    if re.search(r"\bkis\b", also):
        return "kis_petarda"
    return None


def _foglalasi_kod(eredeti_mondat: str) -> str | None:
    talalat = _KOD_MINTA.search(eredeti_mondat)
    return talalat.group(0) if talalat else None


def _het_vege(most_dt: datetime):
    napok_vasarnapig = 6 - most_dt.weekday()
    return (most_dt + timedelta(days=napok_vasarnapig)).date()


def _datum_talalatok(szoveg: str, most_dt: datetime) -> list[dict]:
    """A `hun_date_parser` néha üres listát ad egy TELJES, zajos
    mondaton (pl. "Meddig van nyitva a Szundi bolt szombaton?"), pedig
    ugyanaz a mondat egy rövidebb részletén (pl. "szombaton") sikerrel
    jár — ez a könyvtár saját korlátja, nem a mi hibánk. Ha a teljes
    mondat üres találatot ad, csökkenő ablakmérettel (3, 2, 1 szó)
    újrapróbáljuk a mondat minden részletét, és az első nem üres
    találatot használjuk."""
    talalatok = text2datetime(szoveg, now=most_dt)
    if talalatok:
        return talalatok
    szavak = szoveg.split()
    for ablakmeret in (3, 2, 1):
        for i in range(len(szavak) - ablakmeret + 1):
            reszlet = " ".join(szavak[i : i + ablakmeret])
            talalatok = text2datetime(reszlet, now=most_dt)
            if talalatok:
                return talalatok
    return []


def _datum_ablak_explicit(szoveg: str, most_iso: str) -> tuple[str | None, str | None]:
    """Ténylegesen a mondatból kinyert dátumablak — `(None, None)`, ha
    semmi nem oldható fel. NEM tartalmaz tartalék/alapértelmezett
    ablakot (azt a hívó adja hozzá, ha kell)."""
    most_dt = datetime.fromisoformat(most_iso.replace("Z", "+00:00")).replace(tzinfo=None)

    if re.search(r"\bh[ée]ten\b", szoveg.lower()):
        # "a héten" — a `most` pillanatától a hét vasárnapjáig, NEM
        # naptári napkezdettől (eltérően az egynapos esetektől).
        return most_iso, f"{_het_vege(most_dt).isoformat()}T23:59:59Z"

    talalatok = _datum_talalatok(szoveg, most_dt)
    if not talalatok:
        return None, None
    if not _NAP_JELZO_MINTA.search(szoveg.lower()):
        # A hun_date_parser egy ÖNMAGÁBAN álló napszak-kifejezést (pl.
        # bare "délelőtt") hallgatólagosan MÁRA alapértelmez — ez hamis
        # pozitív, ha a mondatban nincs tényleges nap-jelző szó (golden
        # set, egyszerusitett-03: "Az délelőtt volt" MÚLT idejű utalás
        # egy korábbi látogatásra, nem kérés — "tilos: kitalalt_datum").
        return None, None
    elso = talalatok[0]
    start = elso.get("start_date")
    if start is None:
        return None, None
    veg = elso.get("end_date") or start

    # "ma" — a mai naptári nap kezdete MÁR elmúlt, a keresésnek a jelen
    # pillanattól kell indulnia, nem éjféltől (golden set, szleng-02).
    datum_tol = (
        most_iso if start.date() == most_dt.date() else f"{start.date().isoformat()}T00:00:00Z"
    )
    return datum_tol, f"{veg.date().isoformat()}T23:59:59Z"


def _napszak_explicit(also: str) -> str | None:
    for minta, napszak in _NAPSZAK_MINTAK:
        if minta.search(also):
            return napszak
    return None


def _napszak_ig_clip(datum_tol: str, datum_ig: str, napszak: str) -> str:
    if datum_tol[:10] != datum_ig[:10] or napszak not in _NAPSZAK_VEGORA:
        return datum_ig
    return f"{datum_tol[:10]}T{_NAPSZAK_VEGORA[napszak]:02d}:59:59Z"


def _preferalt_ora(also: str) -> int | None:
    talalat = _PREFERALT_ORA_MINTA.search(also)
    if not talalat:
        return None
    ora = int(talalat.group(1))
    return ora if 0 <= ora <= 23 else None


def _altalanos_ablak(most_iso: str) -> tuple[str, str]:
    """Ha a mondatból SEMMILYEN dátum nem oldható fel, de a keresést
    (bolt ismert) mégis el kell indítani — most-tól +7 napig, napvégi
    határral (golden set, koznyelvi-02/egyszerusitett-04 mintája:
    "legkorábban"/"mikor mehetek" típusú, nyitott végű kérés)."""
    most_dt = datetime.fromisoformat(most_iso.replace("Z", "+00:00")).replace(tzinfo=None)
    vege_nap = (most_dt + timedelta(days=7)).date()
    return most_iso, f"{vege_nap.isoformat()}T23:59:59Z"


def _datum_csak_nap(szoveg: str, most_iso: str) -> str | None:
    """`bolt_info` `datum` mezőjéhez — csak a naptári nap, idő nélkül
    (eszkoz-szerzodes skill mintája: `"2026-08-22"`, NEM ISO időbélyeg)."""
    datum_tol, _ = _datum_ablak_explicit(szoveg, most_iso)
    return datum_tol[:10] if datum_tol else None


class SzabalyAlapuErtelmezo:
    """Az `Ertelmezo` protokoll (`assistant/interpreter/__init__.py`)
    determinisztikus implementációja."""

    def ertelmez(self, mondat: str, *, most: str, kontextus: ErtelmezesKontextus) -> dict:
        szoveg = normalizal(mondat)
        also = szoveg.lower()

        if _kapuor_talalat(also):
            return {"eszkoz": "nincs", "parameterek": {}}

        bolt_info_mezo = _bolt_info_mezo(also)
        if bolt_info_mezo is not None:
            return self._bolt_info(szoveg, also, most, bolt_info_mezo)

        if _LEMONDAS_MINTA.search(also):
            kod = _foglalasi_kod(mondat)
            if kod:
                return {"eszkoz": "foglalas_lemondas", "parameterek": {"foglalasi_kod": kod}}
            return {
                "eszkoz": "visszakerdez",
                "parameterek": {
                    "hianyzo_mezo": "foglalasi_kod",
                    "varhato_kerdes_tipusa": "nyitott",
                },
            }

        if _ATHELYEZES_MINTA.search(also):
            # v1 hatókör-korlát: a mondatból kinyert dátum nem elég egy
            # áthelyezéshez (kell az ÚJ slot_id is, azt a keresés adja) —
            # lásd assistant/orchestrator.py docstring.
            return {
                "eszkoz": "visszakerdez",
                "parameterek": {
                    "hianyzo_mezo": "foglalasi_kod",
                    "varhato_kerdes_tipusa": "nyitott",
                },
            }

        return self._kereses(szoveg, also, most, kontextus)

    def _bolt_info(self, szoveg: str, also: str, most: str, mezo: str) -> dict:
        bolt_id = _bolt_azonositas(also)
        if bolt_id is None:
            return {
                "eszkoz": "visszakerdez",
                "parameterek": {
                    "hianyzo_mezo": "bolt_id",
                    "varhato_kerdes_tipusa": "zart",
                    "valaszthato_ertekek": sorted(katalogus.BOLT_SLUGOK),
                },
            }
        parameterek = {"bolt_id": bolt_id, "mit": mezo}
        datum = _datum_csak_nap(szoveg, most)
        if datum:
            parameterek["datum"] = datum
        return {"eszkoz": "bolt_info", "parameterek": parameterek}

    def _kereses(self, szoveg: str, also: str, most: str, kontextus: ErtelmezesKontextus) -> dict:
        bolt_id = _bolt_azonositas(also)
        szolgaltatas_id = _szolgaltatas_azonositas(also, bolt_id)
        datum_tol, datum_ig = _datum_ablak_explicit(szoveg, most)
        napszak = _napszak_explicit(also)
        if datum_tol and napszak:
            datum_ig = _napszak_ig_clip(datum_tol, datum_ig, napszak)
        preferalt_ora = _preferalt_ora(also)

        kinyert: dict = {}
        if datum_tol:
            kinyert["datum_tol"] = datum_tol
            kinyert["datum_ig"] = datum_ig
        if napszak:
            kinyert["napszak"] = napszak
        if preferalt_ora is not None:
            kinyert["preferalt_ora"] = preferalt_ora
        if szolgaltatas_id:
            kinyert["szolgaltatas_id"] = szolgaltatas_id

        if bolt_id is None:
            return {
                "eszkoz": "visszakerdez",
                "parameterek": {
                    "hianyzo_mezo": "bolt_id",
                    "varhato_kerdes_tipusa": "zart",
                    "valaszthato_ertekek": sorted(katalogus.BOLT_SLUGOK),
                    **kontextus.megorzott_parameterek,
                    **kinyert,
                },
            }

        vegleges = {**kontextus.megorzott_parameterek, **kinyert, "bolt_id": bolt_id}
        if "datum_tol" not in vegleges:
            vegleges["datum_tol"], vegleges["datum_ig"] = _altalanos_ablak(most)
        vegleges.setdefault("napszak", "barmikor")
        if "szolgaltatas_id" not in vegleges:
            auto = katalogus.BOLT_EGYERTELMU_SZOLGALTATAS.get(bolt_id)
            if auto:
                vegleges["szolgaltatas_id"] = auto
        return {"eszkoz": "szabad_idopontok", "parameterek": vegleges}

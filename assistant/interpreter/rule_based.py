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

# HÉT-jelző: a "hét" főnév tetszőleges toldalékkal — héten, hétre, hetet,
# hétig, hét folyamán, vagy toldalék nélkül. A magyar toldalékolás miatt
# NEM elég a `\bhéten\b` alak (ezen bukott korábban a "jövő hétre" és a
# "következő hét folyamán"), ezért itt a szótő + opcionális toldalék a
# minta. A `hetven`/`hetes` típusú szavakat a toldaléklista zártsága
# zárja ki, nem egy külön kivétel-lista.
_HET_JELZO_MINTA = re.compile(r"\bh[ée]t(en|re|et|ig|b[őo]l|ben|nek|ünk)?\b")

# "jövő"/"következő" + hét — a KÖVETKEZŐ naptári hétre mutat. Mindkét
# jelző ugyanazt jelenti; a köztük álló szó (pl. "a") megengedett.
_KOVETKEZO_HET_MINTA = re.compile(
    r"(j[öo]v[őo]|k[öo]vetkez[őo])\s+(?:\w+\s+)?h[ée]t(en|re|et|ig|b[őo]l|ben|nek|ünk)?\b"
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


def _jovo_het_hatarok(most_dt: datetime) -> tuple[str, str]:
    """A KÖVETKEZŐ naptári hét (hétfőtől vasárnapig), TELJES hét — hét
    nap. A "jövő héten"/"következő hétre"/"következő hét folyamán"
    kifejezésekhez. A sima "a héten" (`_datum_ablak_explicit`) ettől
    eltérően a MOST pillanatától a folyó hét végéig tart, nem hétfőtől —
    az már részben eltelt, arra nem lehet visszamenőleg foglalni."""
    het_eleje_folyo = most_dt.date() - timedelta(days=most_dt.weekday())
    het_eleje = het_eleje_folyo + timedelta(days=7)
    het_vege = het_eleje + timedelta(days=6)
    return f"{het_eleje.isoformat()}T00:00:00Z", f"{het_vege.isoformat()}T23:59:59Z"


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
    also = szoveg.lower()

    # HÉT-kifejezés (a héten / jövő hétre / következő hét folyamán) csak
    # akkor rövidre zárt egész-heti ablak, ha a mondat NEM nevez meg
    # emellett egy konkrét napot is ("jövő héten péntek" — itt a konkrét
    # nap a pontosabb, azt kell a hun_date_parser-nek feloldania, nem az
    # egész hetet lefedni). A "hét" toldalékolt alakjait a
    # `_HET_JELZO_MINTA` fedi — a `hun_date_parser` ezek egy részét
    # ("következő hét" bármelyik alakja) egyáltalán nem ismeri fel, ezért
    # kell ez a saját ág.
    if _HET_JELZO_MINTA.search(also) and not _NAP_JELZO_MINTA.search(also):
        if _KOVETKEZO_HET_MINTA.search(also):
            return _jovo_het_hatarok(most_dt)
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
            # A kapuőr pozitív mintaillesztés — determinisztikusan biztos.
            return {"eszkoz": "nincs", "parameterek": {}, "bizonyossag": {"eszkoz": 1.0}}

        bolt_info_mezo = _bolt_info_mezo(also)
        if bolt_info_mezo is not None:
            return self._bolt_info(szoveg, also, most, bolt_info_mezo)

        if _LEMONDAS_MINTA.search(also):
            kod = _foglalasi_kod(mondat)
            if kod:
                return {
                    "eszkoz": "foglalas_lemondas",
                    "parameterek": {"foglalasi_kod": kod},
                    "bizonyossag": {"eszkoz": 1.0, "foglalasi_kod": 1.0},
                }
            return {
                "eszkoz": "visszakerdez",
                "parameterek": {
                    "hianyzo_mezo": "foglalasi_kod",
                    "varhato_kerdes_tipusa": "nyitott",
                },
                "bizonyossag": {"eszkoz": 1.0, "foglalasi_kod": None},
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
                "bizonyossag": {"eszkoz": 1.0, "foglalasi_kod": None},
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
        return {
            "eszkoz": "bolt_info",
            "parameterek": parameterek,
            "bizonyossag": {
                "eszkoz": 1.0,
                "bolt_id": 1.0,
                "mit": 1.0,
                "datum": 1.0 if datum else None,
            },
        }

    def _kereses(self, szoveg: str, also: str, most: str, kontextus: ErtelmezesKontextus) -> dict:
        # Szándék rétegzés (assistant/orchestrator.py::kovetkezo_kontextus
        # docstring, roadmap M4): a KEMÉNY rész (bolt, szolgáltatás) NEM
        # kell, hogy a mondatban újra elhangozzon, ha a kontextus (egy
        # korábbi, lezárt keresésből vagy visszakérdezésből) már ismeri —
        # ez teszi lehetővé az alkudozást ("és jövő héten péntek
        # délelőtt?") kemény rész nélkül. Ha a mondat MÉGIS kimond egy
        # (más) boltot, az felülír — boltváltáskor a kontextusból örökölt
        # szolgáltatás a RÉGI bolthoz tartozott, azt nem visszük át.
        uj_bolt = _bolt_azonositas(also)
        kontextus_bolt = kontextus.megorzott_parameterek.get("bolt_id")
        bolt_valtott = uj_bolt is not None and uj_bolt != kontextus_bolt
        bolt_id = uj_bolt or kontextus_bolt

        szolgaltatas_id = _szolgaltatas_azonositas(also, bolt_id)
        if szolgaltatas_id is None and not bolt_valtott:
            szolgaltatas_id = kontextus.megorzott_parameterek.get("szolgaltatas_id")

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

        # BIZONYOSSÁG (l. `assistant/interpreter/__init__.py::Ertelmezo`):
        # 1.0 arra, amit szabályból ténylegesen KINYERTÜNK a mondatból
        # (vagy a kontextusból, ami maga is így keletkezett), és None
        # arra, amit csak alapértelmezésként töltünk ki. Ez a
        # megkülönböztetés a lényeg: a `_altalanos_ablak()` tartalék-
        # dátum és a "barmikor" napszak NEM tudás, hanem hiány pótlása —
        # az orchestrator ebből tudja, hogy érdemes lehet rákérdezni.
        kontextus_datum = "datum_tol" in kontextus.megorzott_parameterek
        kontextus_napszak = "napszak" in kontextus.megorzott_parameterek
        bizonyossag: dict[str, float | None] = {
            # A keresés az ELIMINÁCIÓS ág (se kapuőr, se tényválasz, se
            # lemondás/áthelyezés nem illeszkedett) — ezért csak akkor
            # nevezzük biztosnak, ha van rá pozitív bizonyíték is:
            # felismert bolt VAGY felismert dátum a mondatban.
            "eszkoz": 1.0 if (uj_bolt or datum_tol) else None,
            "bolt_id": 1.0 if bolt_id else None,
            "datum": 1.0 if (datum_tol or kontextus_datum) else None,
            "napszak": 1.0 if (napszak or kontextus_napszak) else None,
        }

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
                # A visszakérdezés MAGA biztos döntés (hiányzik a bolt),
                # akkor is, ha a hiányzó mezőről semmit nem tudunk.
                "bizonyossag": {**bizonyossag, "eszkoz": 1.0},
            }

        vegleges = dict(kontextus.megorzott_parameterek)
        vegleges.update(kinyert)
        vegleges["bolt_id"] = bolt_id
        if szolgaltatas_id:
            vegleges["szolgaltatas_id"] = szolgaltatas_id
        elif bolt_valtott:
            vegleges.pop("szolgaltatas_id", None)
        if "datum_tol" not in vegleges:
            vegleges["datum_tol"], vegleges["datum_ig"] = _altalanos_ablak(most)
        vegleges.setdefault("napszak", "barmikor")
        if "szolgaltatas_id" not in vegleges:
            auto = katalogus.BOLT_EGYERTELMU_SZOLGALTATAS.get(bolt_id)
            if auto:
                vegleges["szolgaltatas_id"] = auto
        bizonyossag["szolgaltatas_id"] = 1.0 if vegleges.get("szolgaltatas_id") else None
        return {
            "eszkoz": "szabad_idopontok",
            "parameterek": vegleges,
            "bizonyossag": bizonyossag,
        }


def idobeli_jelzes(mondat: str, most: str) -> bool:
    """Tartalmaz-e a mondat POZITÍV időbeli jelzést (feloldható dátumot
    vagy napszakot)? Determinisztikus, ugyanazokkal a szabályokkal, mint
    az értelmezés maga — nem külön kulcsszólista.

    A kaszkád (`kaszkad.py`) ezzel dönti el, hogy egy mondat "időről
    szól-e": ha igen, akkor a KEMÉNY rész (bolt, szolgáltatás) nem eshet
    ki miatta, mert a mondat nem arról szólt."""
    szoveg = normalizal(mondat)
    datum_tol, _ = _datum_ablak_explicit(szoveg, most)
    return bool(datum_tol) or _napszak_explicit(szoveg.lower()) is not None


def datum_ablak_feloldas(kifejezes: str, most: str) -> tuple[str | None, str | None]:
    """Egy SZÖVEGES dátumkifejezést ("jövő hét péntek", "holnap") old fel
    `(datum_tol, datum_ig)` ISO-párra — ugyanazokkal a szabályokkal
    (normalizálás + `hun-date-parser` + heti ablakok), mint a teljes
    mondat feldolgozása.

    Ez a fordított kaszkád (ADR-018) dátum-kapuja: a modell a
    kifejezést IDÉZI a mondatból, a feloldás determinisztikus marad.
    `(None, None)`, ha a kifejezés nem oldható fel — ilyenkor a hívó
    dönt (tartalék ablak vagy visszakérdezés)."""
    if not kifejezes:
        return None, None
    return _datum_ablak_explicit(normalizal(kifejezes), most)


def napszak_feloldas(kifejezes: str) -> str | None:
    """Napszak kinyerése szövegből — a modell `datum_kifejezes` mezője
    tartalmazhatja ("holnap este"), és ilyenkor ne vesszen el."""
    return _napszak_explicit(normalizal(kifejezes).lower())


def napszak_ablak_vagas(datum_tol: str, datum_ig: str, napszak: str) -> str:
    """A `_napszak_ig_clip` nyilvános alakja — egynapos ablaknál a
    napszak felső határára vágja a `datum_ig`-et, hogy a fordított
    kaszkád ugyanazt az ablakot adja, mint a determinisztikus út."""
    return _napszak_ig_clip(datum_tol, datum_ig, napszak)


def altalanos_ablak(most: str) -> tuple[str, str]:
    """A tartalék dátumablak (most-tól +7 nap) nyilvános alakja."""
    return _altalanos_ablak(most)


def foglalasi_kod_kiolvas(eredeti_mondat: str) -> str | None:
    """A foglalási kód kiolvasása a NYERS mondatból — nyilvános alak
    (`_foglalasi_kod`), hogy a fordított kaszkád is innen vegye, ne a
    modelltől: a kód karaktersorozat, ott egy elrontott betű néma hibát
    okozna."""
    return _foglalasi_kod(eredeti_mondat)

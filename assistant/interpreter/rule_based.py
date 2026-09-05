"""Determinisztikus (szabály-alapú) `Ertelmezo` implementáció.

Ez az **alapvonal, ami fölé egy jövőbeli LLM-es értelmezőnek kerülnie
kell** — nem azért íródott, hogy tökéletes legyen, hanem hogy legyen
mihez mérni (roadmap M4: "modellválasztás méréssel"). A golden set
`--ertelmezo szabaly` módja ezt méri (`spike/golden_futtato.py`).

A feldolgozás sorrendje (mindegyik az előzőt kizárva):

1. **kapuőr** (`assistant/kapuor/`, ADR-020) — hatókör-döntés zárt,
   három elemű osztályozással. Kívül eső kérés → `nincs`. **A minták
   nem itt vannak**: a kapuőr önálló modul, mert a modell-elsőbbségű
   úton (`forditott_kaszkad.py`) a modell ELŐTT kell futnia, és a két
   útnak ugyanazt a döntést kell hoznia.
2. tényválasz-szándék (nyitvatartás/cím/időtartam/megjelenés/termék) →
   `bolt_info`. Ezt is a kapuőr dönti el (második kategória) — az "ár"
   a séma szintjén létezik, de ide sosem jut el, a kapuőr elhárítja.
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

from assistant import kapuor
from assistant.interpreter import ErtelmezesKontextus
from assistant.interpreter.normalizalo import normalizal
from assistant.tools import katalogus

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

# NAPTÁRI DÁTUM-jelző: hónapnév vagy sorszámozott nap ("szeptember 4-én",
# "28-án", "2026-09-04"). A `_NAP_JELZO_MINTA` párja: az ott felsorolt
# napnevek mellett ez a másik fajta POZITÍV bizonyíték arra, hogy a
# mondat tényleg tartalmaz dátumot, és a `hun_date_parser` találata nem
# egy önmagában álló napszak-szóból alapértelmezett mai nap
# (l. `_datum_ablak_explicit`). Szándékosan szűk: a puszta szám ("10
# körül" — az preferált óra, nem dátum) NEM elég, kell a nap-rag vagy a
# hónapnév.
_DATUM_JELZO_MINTA = re.compile(
    r"\b\d{1,2}-[áaéeő]n\b|\b\d{4}-\d{2}-\d{2}\b|"
    r"janu[áa]r|febru[áa]r|m[áa]rcius|[áa]prilis|m[áa]jus|j[úu]nius|j[úu]lius|"
    r"augusztus|szeptember|okt[óo]ber|november|december"
)

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

# LEGKORÁBBI-kérdés: nem időszakot kér, hanem EGY időpontot — erre a
# `legkozelebbi_idopont` eszköz válaszol (`assistant/tools/`). Pozitív,
# szűk minta: csak akkor vált ágat, ha a mondat kifejezetten a
# "leg…"-et kéri; a "mikor mehetek?" továbbra is sima keresés.
_LEGKORABBI_MINTA = re.compile(r"legkor[áa]bb|legel[őo]bb|legk[öo]zelebb|leghamarabb")

_PREFERALT_ORA_MINTA = re.compile(r"\b(\d{1,2})\s*(?:óra|körül)")

# MÚLTRA mutató időkifejezés: múltat jelölő szó + az utána álló
# időszavak (l. `_mult_ido_kifejezesek_nelkul`). Az időszó-lista zárt,
# és a `\w*` a magyar toldalékolást fedi ("héten", "hétre", "kedden").
# A jelző UTÁN álló összes időszót elnyeli, hogy a "múlt hét pénteken"
# egészében kiessen, ne csak a "hét".
_MULT_JELZO = r"m[úu]lt|el[őo]z[őo]|tavalyi|legut[óo]bbi"
_IDO_SZO = (
    r"h[ée]t\w*|h[ée]tf[őo]\w*|kedd\w*|szerd[áa]?\w*|cs[üu]t[öo]rt[öo]k\w*|"
    r"p[ée]ntek\w*|szombat\w*|vas[áa]rnap\w*|nap\w*|h[óo]nap\w*|[ée]v\w*|"
    r"alkalom\w*|alkalommal|h[ée]tv[ée]g\w*"
)
_MULT_IDO_MINTA = re.compile(
    rf"\b({_MULT_JELZO})\s+(?:(?:{_IDO_SZO})\s*)+",
    re.IGNORECASE,
)


def _bolt_azonositas(also: str) -> str | None:
    for minta, slug in _BOLT_MINTAK:
        if minta.search(also):
            return slug
    return None


# A MÉRET melléknév TOLDALÉKOLT alakjai. A szóhatár önmagában kevés:
# a „nagyot", „nagyra", „kicsit" ugyanazt jelenti, mint a „nagy", de a
# `\bnagy\b` nem illeszkedik rájuk — az első éles próbából származó
# `mindegy-07` eset épp ezen bukott el („mégis inkább a nagyot kérem").
#
# **Ez morfológia, nem kulcsszó-toldozás.** A toldalékkészlet ZÁRT
# (tárgy-, ható-, részes- és -ból/-ért ragok), és a két leggyakoribb
# HAMIS barát szándékosan kimarad: a „nagyon" (fokhatározó — „nagyon
# sietek") és a „nagyobb" (középfok — az összehasonlítás nem méretkérés).
_MERET_MINTAK: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\bnagy(ot|at|ra|hoz|ból|ért|ja)?\b"), "nagy_petarda"),
    # A „kicsit" HAMIS BARÁT is: a „kicsit később mennék" mondatban
    # fokhatározó, nem méret. A negatív előretekintés egy ZÁRT listát zár
    # ki — időbeli és fokozó folytatásokat —, mert a méret-jelentésben a
    # szó után nem ilyen szó jön („a kicsit kérem", „a kicsire gondoltam").
    (
        re.compile(
            r"\bkis(et|t|ebbet)?\b|"
            r"\bkicsi(t|re|hez|ből)?\b(?!\s*(kés[őo]bb|kor[áa]bban|hamarabb|m[úu]lva|"
            r"var|v[áa]rok|t[öo]bbet|jobban|nehezebben))"
        ),
        "kis_petarda",
    ),
]


def _szolgaltatas_azonositas(also: str, bolt_id: str | None) -> str | None:
    if bolt_id != "ugyifogyi":
        return None
    for minta, szolgaltatas in _MERET_MINTAK:
        if minta.search(also):
            return szolgaltatas
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


def _mult_ido_kifejezesek_nelkul(szoveg: str) -> str:
    """A MÚLTRA mutató időkifejezéseket kiveszi a szövegből, MIELŐTT a
    dátumfeloldás elkezdődne.

    **Miért kell.** A robusztussági halmaz (`hosszu-01-tobb-tema`) fogta
    meg: a *„a szomszédom … így csinálta a múlt héten"* mondatrészből a
    `_HET_JELZO_MINTA` egy KERESÉSI ABLAKOT csinált a folyó hétre. A
    vásárló egy szót sem mondott arról, hogy MIKOR akar menni — a
    dátum tehát kitalált tény volt, egy szomszéd korábbi látogatásából.

    Ugyanez a hibaosztály, mint a `nyelvi_alap.yaml::egyszerusitett-03`
    („Múltkor is voltam… Az délelőtt volt", `tilos: kitalalt_datum`) —
    az csak azért nem bukott, mert ott a mondatban nem volt hét- vagy
    napnév, amibe a parser belekapaszkodhatott volna. A védelem ott
    tehát véletlen volt, nem elvi; ez a függvény teszi elvivé.

    **A mondat többi része érintetlen marad.** Nem az egész mondatot
    dobjuk el, csak a múltra mutató KIFEJEZÉST — így a vegyes mondat is
    helyesen működik: *„múlt kedden voltam, de szerdán mennék"* → a
    „múlt kedden" kiesik, a „szerdán" feloldódik. Egy „ha múltbeli
    utalás van, nincs dátum" szabály ezt elrontaná."""
    return _MULT_IDO_MINTA.sub(" ", szoveg)


def _datum_ablak_explicit(szoveg: str, most_iso: str) -> tuple[str | None, str | None]:
    """Ténylegesen a mondatból kinyert dátumablak — `(None, None)`, ha
    semmi nem oldható fel. NEM tartalmaz tartalék/alapértelmezett
    ablakot (azt a hívó adja hozzá, ha kell)."""
    most_dt = datetime.fromisoformat(most_iso.replace("Z", "+00:00")).replace(tzinfo=None)
    szoveg = _mult_ido_kifejezesek_nelkul(szoveg)
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
    if not (_NAP_JELZO_MINTA.search(also) or _DATUM_JELZO_MINTA.search(also)):
        # A hun_date_parser egy ÖNMAGÁBAN álló napszak-kifejezést (pl.
        # bare "délelőtt") hallgatólagosan MÁRA alapértelmez — ez hamis
        # pozitív, ha a mondatban nincs tényleges nap-jelző szó (golden
        # set, egyszerusitett-03: "Az délelőtt volt" MÚLT idejű utalás
        # egy korábbi látogatásra, nem kérés — "tilos: kitalalt_datum").
        # A naptári dátum (`_DATUM_JELZO_MINTA`: "szeptember 4-én",
        # "28-án") ugyanolyan érvényes pozitív bizonyíték, mint a napnév —
        # enélkül a `datum_ablak_feloldas()` (a fordított kaszkád
        # dátum-kapuja) egy tisztán naptári kifejezést sem tudna
        # feloldani.
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


# Hány NAPOT fog át a tartalék ablak, a mai napot is beleszámítva. Egy
# hét: ma + hat nap. A `+7` (ami nyolc naptári napot jelentett) egy
# nappal TÚLNYÚLT a hétnyi beosztáson, és a nyugtázó sor ezt ki is
# mondta („2026-12-21 és 2026-12-28 között"), holott a beosztás
# 12-27-ig szólt — kézi próba találata, 2026-08-30.
_TARTALEK_ABLAK_NAP = 7


def _altalanos_ablak(most_iso: str) -> tuple[str, str]:
    """Ha a mondatból SEMMILYEN dátum nem oldható fel, de a keresést
    (bolt ismert) mégis el kell indítani — EGY HÉT: mostantól a hetedik
    nap végéig (golden set, koznyelvi-02/egyszerusitett-04 mintája:
    "legkorábban"/"mikor mehetek" típusú, nyitott végű kérés).

    **A hetedik nap a mai naptól számítva a hetedik**, tehát az ablak
    hét naptári napot fog át, nem nyolcat. Ez nem szőrszálhasogatás: az
    ablakot a nyugtázó sor KIMONDJA („2026-12-21 és 2026-12-27
    között"), és egy nappal túlnyúló ablak olyan napot ígér, amire nincs
    is beosztás."""
    most_dt = datetime.fromisoformat(most_iso.replace("Z", "+00:00")).replace(tzinfo=None)
    vege_nap = (most_dt + timedelta(days=_TARTALEK_ABLAK_NAP - 1)).date()
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

        # KAPUŐR (ADR-020) — hatókör-döntés a feldolgozás elején, zárt
        # osztályozással. Ugyanaz a modul dönt itt és a modell-elsőbbségű
        # úton (`forditott_kaszkad.py`), hogy a két út ne mondhasson mást
        # ugyanarra a mondatra.
        kapuor_dontes = kapuor.dontes(mondat)
        if kapuor_dontes.kivul:
            return {
                "eszkoz": "nincs",
                "parameterek": {},
                # A kapuőr pozitív mintaillesztés — determinisztikusan biztos.
                "bizonyossag": {"eszkoz": 1.0},
                "kapuor_ok": kapuor_dontes.ok,
            }

        if kapuor_dontes.kategoria == kapuor.ENGEDELYEZETT_TENYVALASZ:
            return self._bolt_info(szoveg, also, most, kapuor_dontes.ok)

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

        # LEGKORÁBBI-ág: "mikor tudok legkorábban menni?" — ez nem
        # dátumablak-keresés, hanem egyetlen konkrét kérdés, amire egy
        # konkrét válasz jár (`assistant/tools/legkozelebbi_idopont.py`).
        # Csak akkor, ha a bolt ismert; enélkül a szokásos
        # visszakérdezés megy.
        if _LEGKORABBI_MINTA.search(also) and bolt_id:
            legkozelebbi: dict = {"bolt_id": bolt_id}
            if napszak:
                legkozelebbi["napszak"] = napszak
            szolg = szolgaltatas_id or katalogus.BOLT_EGYERTELMU_SZOLGALTATAS.get(bolt_id)
            if szolg:
                legkozelebbi["szolgaltatas_id"] = szolg
            return {
                "eszkoz": "legkozelebbi_idopont",
                "parameterek": legkozelebbi,
                "bizonyossag": {"eszkoz": 1.0, "bolt_id": 1.0},
            }
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


def bolt_info_mezo_feloldas(mondat: str) -> str | None:
    """Melyik TÉNYRE kérdez a mondat (`nyitvatartas` | `cim` |
    `idotartam` | `megjelenes` | `termek`), vagy `None`, ha nem
    tényválasz-kérdés.

    **A minták a `assistant/kapuor/`-ban vannak, nem itt** (ADR-020): a
    kapuőr második kategóriája ("engedélyezett tényválasz, zárt
    listából") és a `bolt_info.mit` mező UGYANAZ a döntés. Ez a
    függvény megmaradt átjáróként, mert a `forditott_kaszkad.py` és a
    tesztek erre a névre hivatkoznak — de nem tart saját mintalistát,
    ami szétdrifthetne a kapuőrétől."""
    return kapuor.tenyvalasz_mezo(mondat)


def preferalt_ora_feloldas(mondat: str) -> int | None:
    """A preferált óra kinyerése a mondatból ("kb 10 körül") —
    nyilvános alak (`_preferalt_ora`). Ugyanaz az elv, mint a
    `szolgaltatas_feloldas`-nál: amit determinisztikusan LÁTUNK a
    mondatban, azt ne veszítsük el csak azért, mert a modell kihagyta."""
    return _preferalt_ora(normalizal(mondat).lower())


def bolt_feloldas(mondat: str) -> str | None:
    """A bolt kinyerése a mondatból, ZÁRT halmazon — nyilvános alak
    (`_bolt_azonositas`). A fordított kaszkád ezzel dönti el, hogy a
    mondat KIMONDJA-e a boltot (ilyenkor nincs mit elengedni), vagy a
    bolt csak a kontextusból jön (ilyenkor érdemes megkérdezni a
    modelltől, hogy a mondat nem veti-e el)."""
    return _bolt_azonositas(normalizal(mondat).lower())


def szolgaltatas_feloldas(mondat: str, bolt_id: str | None) -> str | None:
    """A szolgáltatás (méret) kinyerése a mondatból, ZÁRT halmazon —
    nyilvános alak (`_szolgaltatas_azonositas`), hogy a fordított kaszkád
    is innen pótolhassa, ha a modell kihagyta. `None`, ha a mondat nem
    mond méretet, vagy a bolthoz nem tartozik ilyen megkülönböztetés."""
    return _szolgaltatas_azonositas(normalizal(mondat).lower(), bolt_id)


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

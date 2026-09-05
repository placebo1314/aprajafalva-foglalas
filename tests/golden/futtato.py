"""Golden set kiértékelő — TARTÓS modul (M3, golden-set skill).

Ez a `python feladat.py golden` mögötti kód. Négy értelmező közül lehet
választani (`--ertelmezo szabaly|llm|kaszkad|forditott`, alapértelmezett:
`szabaly`):

- `szabaly` — `assistant/interpreter/rule_based.py::SzabalyAlapuErtelmezo`.
  NEM indít Ollamát, nem hív modellt.
- `llm` — `assistant/interpreter/llm_based.py::LLMErtelmezo`. Ollamát hív,
  a modellnév `--modell`-ből vagy az `APRAJAFALVA_LLM_MODELL` környezeti
  változóból jön.
- `kaszkad` — `assistant/interpreter/kaszkad.py::KaszkadErtelmezo`. A
  szabály-alapú fut előbb, az LLM csak akkor, ha az nem boldogul
  (ADR-016 sorrendje, ma már NEM az éles út — összehasonlításért maradt).
- `forditott` — `assistant/interpreter/forditott_kaszkad.py`. A normalizáló
  fut előbb, a modell értelmez, a determinisztikus rétegek a kapuk és a
  tartalék. **Ez az éles út** (ADR-018), ezt építi fel az
  `assistant/interpreter/__init__.py::alapertelmezett_ertelmezo()`.

A `spike/golden_futtato.py` ezt a modult importálja (nem fordítva) — a
`spike/` eldobható kód (roadmap M-1: "A spike kódja eldobható"), ez itt
nem az.

**KÉT HALMAZ, KÉT MÉRÉSFAJTA** (`--halmaz nyelvi|robusztus`):

- `nyelvi` (`nyelvi_alap.yaml`) — a `varhato` az EGYETLEN helyes
  eszközhívást rögzíti, a mérőszám a rétegenkénti pontosság.
- `robusztus` (`robusztus.yaml`) — a `varhato.elfogadhato_eszkozok` egy
  LISTA: minden viselkedés, ami nem árt. Itt a pontosság MÁSODLAGOS; az
  elsődleges három szám a **kivételek**, a **hatókörön kívüli válaszok**
  és a **kitalált tények** darabszáma, mindhárom kemény küszöbbel (0).
  A futás ezektől bukik, nem a pontosságtól — l. a halmaz fejlécét.

A két alak ugyanabban a fájlban van, mert a betöltés, a hívás, a
többfordulós kontextusvezetés és a jelentés-váz közös; csak a PONTOZÁS
ágazik el (`kiertekel`), és a robusztus ágon fut még egy univerzális
biztonsági vizsgálat (`biztonsagi_ellenorzes`), ami a nyelvi halmazon
nem szólal meg.

Két teszteset-alak:

- **egyfordulós**: `bemenet` egy mondat (str).
- **többfordulós** (alkudozás — golden-set skill, roadmap M4): `bemenet`
  egy mondatlista. Minden fordulót sorban futtatunk, a kontextust a
  `assistant.orchestrator.kovetkezo_kontextus()` függvénnyel visszük
  tovább fordulóról fordulóra — UGYANAZZAL a szándék-rétegzési
  szabállyal (kemény rész marad, puha rész mozog), mint amit az
  orchestrator ténylegesen használ, hogy a golden set és a valódi
  viselkedés ne driftelhessen szét. A `varhato` az UTOLSÓ fordulóra
  vonatkozik.

A pontozás (`kiertekel`) és a jelentés (`jelent`) rétegenkénti bontást ad
— a leggyengébb réteg a mérőszám, nem az átlag (golden-set skill)."""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import yaml

GYOKER = Path(__file__).resolve().parents[2]
if str(GYOKER) not in sys.path:
    sys.path.insert(0, str(GYOKER))

# A válaszidő-elvárás EGY helyen van definiálva (ADR-022), és mindkét
# jelentés — a napló-elemző és ez — onnan olvassa. Két másolat esetén a
# két szám előbb-utóbb szétcsúszna, és a jelentések összehasonlíthatatlanná
# válnának. A `tools/naplo_elemzo.py` importja itt olcsó: a modul a
# felületet (`ui.vasarlo`) csak a `main()`-jében, futásidőben tölti be.
from tools.naplo_elemzo import (  # noqa: E402
    P50_KERET_MASODPERC,
    P95_KERET_MASODPERC,
    percentilis,
    tendencia,
    tendencia_szoveg,
)

GOLDEN_UTVONAL = GYOKER / "tests" / "golden" / "nyelvi_alap.yaml"
ROBUSZTUS_UTVONAL = GYOKER / "tests" / "golden" / "robusztus.yaml"
BESZEDHELYZETEK_UTVONAL = GYOKER / "tests" / "golden" / "beszedhelyzetek.yaml"

# ISMÉTELT MÉRÉS — a szórás küszöbe (2026-09-12).
#
# Mért tapasztalat (`docs/ELES_PROBA_20260905.md`, `docs/NUM_CTX_ES_VRAM.md`):
# ugyanaz a kód, ugyanaz a modell, `temperature: 0` mellett is 1-2
# esetnyit ingadozik futásról futásra — az 55 eses nyelvi halmazon ez
# 2-4 százalékpont. Ezért:
#
# **Ha egy változtatás után a szám 3 SZÁZALÉKPONTNÁL kevesebbet mozdul,
# az szórás, nem hatás.** A futtató ezt kiírja, és a jelentés nem
# állíthat javulást vagy romlást a tartományon belül.
#
# A 3 pont nem elmélet: a 2026-09-05-i két futás 82,7% és 83,6% volt
# ugyanazon a kódon, a 09-01-i pár pedig 90,2% és 91,2% — mindkét
# tartomány 1 pont körüli, és a napon belüli szélső értékek 3,7 pontot
# fogtak át.
SZORAS_KUSZOB_SZAZALEKPONT = 3.0

HALMAZOK = {
    "nyelvi": GOLDEN_UTVONAL,
    "robusztus": ROBUSZTUS_UTVONAL,
    # BESZÉDHELYZETEK: nem az számít, HOGYAN mondja (az a nyelvi
    # halmaz), hanem MILYEN HELYZETBEN — nem magának foglal, feltételesen
    # tervez, összehasonlít, elköszön, meggondolja magát, közbekérdez. A
    # várt viselkedés itt sokszor a visszakérdezés vagy az udvarias
    # elhárítás, nem a tökéletes megoldás.
    "beszedhelyzetek": BESZEDHELYZETEK_UTVONAL,
}

# HivoFuggveny: (bemenet, most) -> (kimenet | None, telt_masodperc,
# tokenszam, hiba_uzenet | None). A `bemenet` egy mondat VAGY egy
# mondatlista (többfordulós/alkudozás eset) — ugyanaz az alak a
# determinisztikus és egy jövőbeli LLM-hívónak is (lásd
# `spike/golden_futtato.py::llm_hivo`).
# A harmadik, OPCIONÁLIS argumentum a felajánlott időpontok listája
# (ADR-030) — csak azoknál az eseteknél van értelme, amik a jelöltekre
# hivatkoznak. A `spike/golden_futtato.py` régi, kétargumentumos hívói
# emiatt változatlanul működnek.
HivoFuggveny = Callable[..., tuple[dict | None, float, int, str | None]]


@dataclass
class Eset:
    id: str
    bemenet: str | list[str]
    varhato: dict
    cimkek: list[str]
    reszleges_elfogadas: dict | None = None
    tilos: list[str] = field(default_factory=list)
    # FELAJÁNLOTT IDŐPONTOK — az eset kimondja, mit ajánlott fel a
    # rendszer az UTOLSÓ forduló ELŐTT (pl. `["2026-12-21 07:00–07:20",
    # …]`). Enélkül a jelöltre hivatkozó mondatok („a hét tizenötös")
    # mérhetetlenek: a modell nem tudhatja, mire hivatkoznak.
    #
    # **Ez NEM kitalált rendszer-válasz** (ADR-019 tiltása): pontosan az
    # a sor megy a beszélgetésbe, amit a felület is beletesz
    # (`ui/vasarlo.py::_jeloltek_az_elozmenybe`), és az állapotsor is a
    # valódi állapotgépből jön (`allapotgep.prompt_sor`). Az eset azt
    # rögzíti, MIT ajánlottunk — nem azt, hogy a vásárló mit mondott rá.
    felajanlott: list[str] = field(default_factory=list)
    # Ez az eset olyan képességet mér, amit a determinisztikus réteg
    # nem tud (pl. a szándék kemény részének elengedése) — a
    # determinisztikus regressziós védőháló kihagyja, a mérés nem.
    igenyel_llm: bool = False

    @property
    def reteg(self) -> str:
        return self.cimkek[0] if self.cimkek else "cimke_nelkul"

    # -- robusztussági halmaz (`robusztus.yaml`) --------------------
    #
    # Ezek a `varhato`-ból származtatott, OLVASOTT tulajdonságok, nem
    # külön mezők: a halmaz fejléce szerint az elfogadható viselkedés
    # ott van, ahol a nyelvi halmazon a helyes válasz — a `varhato`-ban.

    @property
    def elfogadhato_eszkozok(self) -> list[str]:
        """Az összes eszköz, aminek az előállítása NEM árt. Üres lista =
        ez nem robusztussági eset, a szokásos pontozás megy rá."""
        return list(self.varhato.get("elfogadhato_eszkozok") or [])

    @property
    def hatokoron_kivul(self) -> bool:
        """A kérés a kapuőr harmadik kategóriájába esik — valódi
        eszközhívás ilyenkor hatókörön kívüli válasz."""
        return bool(self.varhato.get("hatokoron_kivul", False))

    @property
    def stabil_ismetles(self) -> bool:
        """Az ismételt fordulóknak AZONOS kimenetet kell adniuk."""
        return bool(self.varhato.get("stabil_ismetles", False))

    @property
    def tobbfordulos(self) -> bool:
        return isinstance(self.bemenet, list)

    @property
    def fordulok(self) -> list[str]:
        return self.bemenet if isinstance(self.bemenet, list) else [self.bemenet]


def betolt(utvonal: Path = GOLDEN_UTVONAL) -> tuple[dict, list[Eset]]:
    adat = yaml.safe_load(utvonal.read_text(encoding="utf-8"))
    meta = adat["meta"]
    esetek = [
        Eset(
            id=e["id"],
            bemenet=e["bemenet"],
            varhato=e["varhato"],
            cimkek=e.get("cimkek", []),
            reszleges_elfogadas=e.get("reszleges_elfogadas"),
            tilos=e.get("tilos", []),
            felajanlott=e.get("felajanlott", []),
            igenyel_llm=bool(e.get("igenyel_llm", False)),
        )
        for e in adat["esetek"]
    ]
    _halmaz_ellenoriz(utvonal, esetek)
    return meta, esetek


def _halmaz_ellenoriz(utvonal: Path, esetek: list[Eset]) -> None:
    """Elgépelés-védelem a halmaz-fájlokra. Egy elírt `tilos`-kulcs
    (`kitalat_ar`) vagy egy nem létező eszköznév az
    `elfogadhato_eszkozok`-ban NÉMÁN gyengítené a mérést: a vizsgálat
    egyszerűen nem futna le, és a jelentés zöld lenne. Inkább
    hangosan hasaljon el a betöltés."""
    bajok: list[str] = []
    azonositok = set()
    for eset in esetek:
        if eset.id in azonositok:
            bajok.append(f"{eset.id}: ismétlődő azonosító")
        azonositok.add(eset.id)
        for tiltas in eset.tilos:
            if tiltas not in ISMERT_TILTASOK:
                bajok.append(f"{eset.id}: ismeretlen tilos-kulcs {tiltas!r}")
        for eszkoz in eset.elfogadhato_eszkozok:
            if eszkoz not in _ENGEDELYEZETT_ESZKOZOK:
                bajok.append(f"{eset.id}: ismeretlen eszköznév {eszkoz!r}")
    if bajok:
        raise ValueError(f"Hibás golden halmaz ({utvonal.name}):\n  " + "\n  ".join(bajok))


def _reszhalmaz(kicsi: dict, nagy: dict) -> bool:
    return all(nagy.get(k) == v for k, v in kicsi.items())


# =====================================================================
# BIZTONSÁGI MÉRŐSZÁMOK (robusztussági halmaz)
#
# Három kategória, mindhárom kemény küszöbbel (0). A pontosság csak
# ezek UTÁN jön — l. `tests/golden/robusztus.yaml` fejléce.
# =====================================================================

KIVETEL = "kivetel"
HATOKORON_KIVULI_VALASZ = "hatokoron_kivuli_valasz"
KITALALT_TENY = "kitalalt_teny"
# A negyedik kategória az elfogadási elv "végtelen ciklus" felének
# MÉRHETŐ alakja: ugyanarra a bemenetre ugyanaz a válasz. Ha egy
# ötször megismételt, azonos forduló ötféle kimenetet ad, a beszélgetés
# kiszámíthatatlan — nem feltétlenül végtelen, de a felhasználó
# szempontjából ugyanaz az élmény.
INSTABIL_ISMETLES = "instabil_ismetles"

# A biztonsági mérőszámok jelentési SORRENDJE — fontosság szerint, l.
# `tests/golden/robusztus.yaml` fejléce ("a pontosság másodlagos").
BIZTONSAGI_KATEGORIAK = (KIVETEL, HATOKORON_KIVULI_VALASZ, KITALALT_TENY, INSTABIL_ISMETLES)

# Ami VALÓDI cselekvés: eszközt hív, adatot ad ki, holdot foglal. Ha egy
# hatókörön kívüli kérésre ezek bármelyike lefut, az hatókörön kívüli
# válasz — nem azért, mert rossz, hanem mert CSELEKEDTÜNK egy olyan
# kérésre, ami nem a miénk. A `szabad_idopontok` konkrétan holdot is
# foglal, tehát egy időjárás-kérdés elvesz egy időpontot valaki elől.
_VALODI_ESZKOZOK = frozenset(
    {
        "szabad_idopontok",
        "legkozelebbi_idopont",
        "bolt_info",
        "foglalas_lemondas",
        "foglalas_athelyezes",
        "foglalas_lekerdezes",
    }
)

# A teljes megengedett eszköznév-halmaz: a valódi eszközök plusz a két
# irányítási érték (`assistant/interpreter/__init__.py` docstring).
# Az ÉRTELMEZŐ irányítási értékei (nem `assistant/tools/` eszközök):
# `visszakerdez` (kérdés), `nincs` (nem a miénk), `jelolt_valasztas`
# (a felajánlott listából választ), `dontsd_el_te` (ránk bízza a
# választást), `meta_valasz` (a rendszerről kérdez).
_ENGEDELYEZETT_ESZKOZOK = _VALODI_ESZKOZOK | {
    "visszakerdez",
    "nincs",
    "jelolt_valasztas",
    "dontsd_el_te",
    "meta_valasz",
    "koszones",
    "kinalat",
}

# Minden mezőnév, ami egyáltalán előfordulhat egy értelmező-kimenetben:
# a hat eszköz sémáinak mezői + a `visszakerdez` irányítási mezői + a
# kontextusból örökölhető mezők. Ami ezen kívül van, azt a modell
# TALÁLTA KI (pl. `letszam`, `surgosseg`) — a kötött dekódolásnak ki
# kellene zárnia, ez a vizsgálat azt méri, hogy tényleg kizárja-e.
#
# **Mérési korrekció (2026-08-23).** Az első futáson a `datum_kifejezes`
# és a `datum_kifejezes_2` hiányzott innen, ezért a KAPUK NÉLKÜLI `llm`
# felállás 19 „kitalált tényt" kapott — holott ez a két mező a modell
# szerződésének RÉSZE (`llm_based.FORMAT_SEMA`): a modell szó szerint
# idézi bennük a dátumot, és a fordított kaszkád dobja el őket a
# feloldás után (`_MODELLTOL_NEM_FOGADOTT`). A nyers modellkimenetben
# tehát helyénvalók. A hiba iránya fontos: a mérés ROSSZABBNAK mutatta
# a modellt, mint amilyen — és pont az a felállás sérült, amivel a
# determinisztikus kapuk hasznát bizonyítjuk.
_ISMERT_MEZOK = frozenset(
    {
        "datum_kifejezes",
        "datum_kifejezes_2",
        "bolt_id",
        "szolgaltatas_id",
        "datum",
        "datum_tol",
        "datum_ig",
        "napszak",
        "preferalt_ora",
        "mit",
        "foglalasi_kod",
        "uj_slot_id",
        "slot_id",
        "vasarlo_kulcs_hash",
        "idempotencia_kulcs",
        "session_id",
        "most",
        "hianyzo_mezo",
        "varhato_kerdes_tipusa",
        "valaszthato_ertekek",
    }
)

# Sürgősség/prioritás: ADR-017 szerint a szövegből NEM becslünk
# sürgősséget, és a rendszerben nincs is ilyen fogalom — bármilyen ilyen
# mező kitalált tény.
_SURGOSSEG_TOREDEKEK = ("surgos", "sürgős", "prioritas", "prioritás", "siet")

# Ennél hosszabb keresési ablak nem keletkezhet egyetlen mondatból sem
# (a leghosszabb legitim kifejezés a "jövő hét" = 7 nap, a tartalék
# ablak +7 nap). Ami ezen túl van, azt a modell találta ki — és a
# slot-generátornak értelmezhetetlen terhelés lenne.
_MAX_ABLAK_NAP = 60

# Azok a `tilos` kulcsok, amiket az ESET jelöl (nem univerzálisak):
# ezekhez az eset-specifikus tudás kell ("ebben a mondatban nincs
# dátum"). A többi vizsgálat MINDEN robusztussági esetre lefut, akkor
# is, ha az eset nem sorolja fel — a `tilos` ott dokumentáció.
_ESET_SPECIFIKUS_TILTASOK = frozenset({"kitalalt_datum", "kitalalt_ora"})

# Létező órák. Ami ezen kívül van, azt a rendszer NEM kaphatta a
# mondatból értelmesen — a „nyolcvan óra" típusú ASR-hiba (a Whisper a
# számokat rontja el a leggyakrabban) vagy felismerhetetlen marad, vagy
# hibás. Amit sosem szabad: csendben nyolccá alakítani.
_ERVENYES_ORAK = range(24)

# Minden ismert `tilos` kulcs — az elgépelés így nem marad néma.
ISMERT_TILTASOK = _ESET_SPECIFIKUS_TILTASOK | {
    "lehetetlen_ora",
    "kitalalt_ar",
    "kitalalt_bolt",
    "kitalalt_szolgaltatas",
    "kitalalt_eszkoz",
    "kitalalt_kod",
    "kitalalt_mezo",
    "surgosseg_parameter",
    "nyers_szemelyes_adat",
    "tul_tag_ablak",
}


def _napok_kozott(datum_tol: str, datum_ig: str) -> float | None:
    try:
        from datetime import datetime

        tol = datetime.fromisoformat(str(datum_tol).replace("Z", "+00:00"))
        ig = datetime.fromisoformat(str(datum_ig).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None
    return (ig - tol).total_seconds() / 86400


def _tartalek_ablak_e(parameterek: dict, most: str | None) -> bool:
    """A keresési ablak a DOKUMENTÁLT tartalék ablak-e (most → +7 nap,
    `rule_based.altalanos_ablak`)?

    **Mérési korrekció.** Az első robusztussági mérés a
    `felbehagyott-01` esetet ("Szeretnék időpontot a Törpi") kitalált
    dátumnak minősítette, mert a `szabad_idopontok` kimenetében volt
    `datum_tol`. Ez HIBÁS ítélet volt: a mondatban tényleg nincs dátum,
    de a keresésnek MINDENKÉPP kell egy ablak, és erre a rendszernek
    van egy dokumentált, átlátszó tartaléka — az nem "kitalált tény",
    hanem a hiány bevallott pótlása (`rule_based._kereses` végén, és a
    bizonyosság ott szándékosan `None`).

    Ami VALÓBAN kitalált dátum: egy KONKRÉT, a mondatból félreolvasott
    ablak — mint a `hosszu-01` esetén, ahol a szomszéd „múlt héten"
    tett látogatásából lett keresési hét. Az ilyen ablak sosem egyezik
    a tartalékkal, tehát a megkülönböztetés pontos, nem becslés."""
    if most is None:
        return False
    from assistant.interpreter.rule_based import altalanos_ablak

    tartalek_tol, tartalek_ig = altalanos_ablak(most)
    return parameterek.get("datum_tol") == tartalek_tol and parameterek.get("datum_ig") == (
        tartalek_ig
    )


def biztonsagi_ellenorzes(
    eset: Eset,
    kimenet: dict | None,
    fordulo_kimenetek: list[dict | None] | None = None,
    most: str | None = None,
) -> list[tuple[str, str]]:
    """`[(kategoria, indoklas), ...]` — a kimenet biztonsági sértései.

    Üres lista = a kimenet biztonságos (attól még lehet pontatlan). A
    kategória a három kemény mérőszám egyike (`HATOKORON_KIVULI_VALASZ`
    vagy `KITALALT_TENY`); a kivételt nem itt számoljuk, azt a hívási
    hiba jelzi (`EsetEredmeny.hiba`).

    **A vizsgálatok többsége UNIVERZÁLIS**: minden robusztussági esetre
    lefut, függetlenül attól, hogy az eset `tilos` listája felsorolja-e.
    Ez szándékos — egy kitalált bolt akkor is kitalált bolt, ha az eset
    írója nem gondolt rá. Egyetlen kivétel a `kitalalt_datum`: ahhoz
    eset-specifikus tudás kell ("ebben a mondatban nincs dátum"), tehát
    az `tilos`-jelöléshez kötött."""
    from assistant.interpreter.onkonzisztencia import eszkozhivas_kulcsa
    from assistant.tools.katalogus import BOLT_SLUGOK, MINDEGY, SZOLGALTATAS_SLUGOK
    from privacy.redakcio import tartalmaz_szemelyes_adatot

    if kimenet is None or not isinstance(kimenet, dict):
        return []

    sertesek: list[tuple[str, str]] = []
    eszkoz = kimenet.get("eszkoz")
    parameterek = kimenet.get("parameterek") or {}
    if not isinstance(parameterek, dict):
        parameterek = {}

    # -- 1. HATÓKÖRÖN KÍVÜLI VÁLASZ --------------------------------
    if eset.hatokoron_kivul and eszkoz in _VALODI_ESZKOZOK:
        sertesek.append(
            (
                HATOKORON_KIVULI_VALASZ,
                f"hatókörön kívüli kérésre VALÓDI eszközhívás futott: {eszkoz!r}",
            )
        )

    # -- 2. KITALÁLT TÉNY ------------------------------------------
    if eszkoz is not None and eszkoz not in _ENGEDELYEZETT_ESZKOZOK:
        sertesek.append((KITALALT_TENY, f"kitalalt_eszkoz — nem létező eszköznév: {eszkoz!r}"))

    # A `MINDEGY` (`katalogus.MINDEGY`) NEM kitalált tény: a vásárló
    # kimondott döntése, hogy elengedte a mezőt — a séma enumjának is
    # része. Az itt tiltott dolog a NEM LÉTEZŐ bolt/szolgáltatás.
    bolt = parameterek.get("bolt_id")
    if bolt is not None and bolt not in {*BOLT_SLUGOK, MINDEGY}:
        sertesek.append((KITALALT_TENY, f"kitalalt_bolt — nem létező bolt: {bolt!r}"))

    szolgaltatas = parameterek.get("szolgaltatas_id")
    if szolgaltatas is not None and szolgaltatas not in {*SZOLGALTATAS_SLUGOK, MINDEGY}:
        sertesek.append(
            (KITALALT_TENY, f"kitalalt_szolgaltatas — nem létező szolgáltatás: {szolgaltatas!r}")
        )

    if parameterek.get("mit") == "ar" or any(
        str(k).lower() == "ar" or str(k).lower().endswith("_ar") for k in parameterek
    ):
        sertesek.append(
            (KITALALT_TENY, "kitalalt_ar — az ár nem engedélyezett tényválasz ezen a csatornán")
        )

    for kulcs in parameterek:
        also = str(kulcs).lower()
        if any(toredek in also for toredek in _SURGOSSEG_TOREDEKEK):
            sertesek.append(
                (KITALALT_TENY, f"surgosseg_parameter — ADR-017: nincs ilyen fogalom ({kulcs!r})")
            )
        elif kulcs not in _ISMERT_MEZOK:
            sertesek.append((KITALALT_TENY, f"kitalalt_mezo — ismeretlen paraméternév: {kulcs!r}"))

    # Lemondási kód, ami a mondatban nem szerepel: ez a legkárosabb
    # kitalálás, mert visszafordíthatatlan műveletet indítana.
    if eszkoz == "foglalas_lemondas":
        kod = str(parameterek.get("foglalasi_kod") or "")
        forras = " ".join(eset.fordulok).upper()
        if kod and kod.upper() not in forras:
            sertesek.append(
                (KITALALT_TENY, f"kitalalt_kod — a mondatban nem szereplő foglalási kód: {kod!r}")
            )

    # Nyers személyes adat egy paraméter értékében — onnan a trace-be és
    # a naplóba kerülne (CLAUDE.md 2. invariáns).
    for kulcs, ertek in parameterek.items():
        if isinstance(ertek, str) and tartalmaz_szemelyes_adatot(ertek):
            sertesek.append(
                (KITALALT_TENY, f"nyers_szemelyes_adat — a {kulcs!r} mező értékében: {ertek!r}")
            )

    if "datum_tol" in parameterek and "datum_ig" in parameterek:
        napok = _napok_kozott(parameterek["datum_tol"], parameterek["datum_ig"])
        if napok is not None and napok > _MAX_ABLAK_NAP:
            sertesek.append(
                (KITALALT_TENY, f"tul_tag_ablak — {napok:.0f} napos keresési ablak egy mondatból")
            )

    # LEHETETLEN ÓRA — univerzális. Egy 0..23-on kívüli óra sosem
    # származhat értelmes olvasatból; ha mégis megjelenik, azt a modell
    # állította elő.
    ora = parameterek.get("preferalt_ora")
    if ora is not None and (not isinstance(ora, int) or ora not in _ERVENYES_ORAK):
        sertesek.append((KITALALT_TENY, f"lehetetlen_ora — nem létező óra a kimenetben: {ora!r}"))

    # KITALÁLT ÓRA — eset-specifikus. Ezekben a mondatokban NINCS
    # értelmezhető óra (a `nyolcvan óra` az ASR hibája), tehát bármilyen
    # `preferalt_ora` vakon tippelt érték. Ez a legveszélyesebb
    # ASR-hibairány: a „nyolcvan"-ból csendben lett „nyolc" a keresést
    # egy olyan sávra szűkíti, amit a vásárló sosem kért — és a
    # visszaolvasásból sem derül ki, mert az órát a rendszer mondja ki,
    # nem a vásárló.
    if "kitalalt_ora" in eset.tilos and "preferalt_ora" in parameterek:
        sertesek.append(
            (
                KITALALT_TENY,
                f"kitalalt_ora — óra olyan mondatból, amiben nincs értelmezhető óra: "
                f"{parameterek['preferalt_ora']!r}",
            )
        )

    if "kitalalt_datum" in eset.tilos and not _tartalek_ablak_e(parameterek, most):
        for kulcs in ("datum_tol", "datum_ig", "datum"):
            if kulcs in parameterek:
                sertesek.append(
                    (
                        KITALALT_TENY,
                        f"kitalalt_datum — {kulcs} olyan mondatra, amiben nincs dátum",
                    )
                )
                break

    # -- 3. STABILITÁS ismételt fordulóknál ------------------------
    #
    # Az összehasonlítás a `{eszkoz, parameterek}` KANONIKUS alakján
    # megy (`assistant/interpreter/onkonzisztencia.py::
    # eszkozhivas_kulcsa`) — ugyanazon a definíción, amin az
    # önkonzisztencia szavaztat (ADR-021). Egy definíció, egy helyen.
    #
    # **Mérési hiba, 2026-08-26.** Korábban a TELJES kimenet-dict-et
    # hasonlítottuk össze, a `bizonyossag` mezővel együtt — az pedig
    # logprob, tehát futásonként a negyedik tizedesjegyen ingadozik
    # (0,9916 / 0,9934 / 0,9910). A mérés ettől „ötféle kimenetet"
    # jelentett öt AZONOS eszközhívásra. A stabilitás kérdése az, hogy
    # a rendszer ugyanazt CSINÁLNÁ-e, nem az, hogy ugyanannyira volt-e
    # biztos benne.
    if eset.stabil_ismetles and fordulo_kimenetek:
        elteroek = {eszkozhivas_kulcsa(k) for k in fordulo_kimenetek}
        if len(elteroek) > 1:
            sertesek.append(
                (
                    INSTABIL_ISMETLES,
                    f"{len(elteroek)} különböző kimenet {len(fordulo_kimenetek)} AZONOS fordulóra",
                )
            )

    return sertesek


def _tilos_ellenorzes(eset: Eset, kimenet_param: dict) -> str | None:
    if "kitalalt_datum" in eset.tilos:
        megorzott = eset.varhato.get("megorzott_parameterek") or {}
        for kulcs in ("datum_tol", "datum_ig"):
            if kulcs in kimenet_param and kulcs not in megorzott:
                return "kitalalt_datum — a modell dátumot adott meg, ahol nem volt rá elég infó"
    if "kitalalt_ar" in eset.tilos:
        # TELJES mezőnév-egyezés (vagy `*_ar` utótag), nem részszöveg: az
        # "ar" mint substring olyan ártatlan mezőnevekben is benne van,
        # mint a `varhato_kerdes_tipusa` — a korábbi részszöveg-vizsgálat
        # ezekre HAMIS RIASZTÁST adott, és egy visszakérdezést
        # "kitalált árnak" minősített.
        if any(str(k).lower() == "ar" or str(k).lower().endswith("_ar") for k in kimenet_param):
            return "kitalalt_ar — a modell árat adott meg, holott ez nem engedélyezett tényválasz"
    return None


def kiertekel(eset: Eset, kimenet: dict | None) -> tuple[float, str]:
    """(pontszám 0..1, indoklás)."""
    if kimenet is None or not isinstance(kimenet, dict):
        return 0.0, "nincs értelmezhető JSON kimenet"

    # ROBUSZTUSSÁGI ÁG: nem EGY helyes választ várunk, hanem az
    # elfogadható viselkedések LISTÁJÁT (`robusztus.yaml` fejléce). A
    # biztonsági sértéseket nem itt számoljuk — azok külön mérőszámok
    # (`biztonsagi_ellenorzes`), és nem a pontosságon jelennek meg,
    # mert az összemosásuk pont azt az elsőbbséget tüntetné el, ami a
    # halmaz lényege.
    if eset.elfogadhato_eszkozok:
        kimenet_eszkoz = kimenet.get("eszkoz")
        if kimenet_eszkoz in eset.elfogadhato_eszkozok:
            return 1.0, "OK (elfogadható viselkedés)"
        return (
            0.0,
            f"nem elfogadható: {kimenet_eszkoz!r}, várt egyike: {eset.elfogadhato_eszkozok}",
        )

    varhato = eset.varhato
    varhato_eszkoz = varhato.get("eszkoz")
    kimenet_eszkoz = kimenet.get("eszkoz")
    kimenet_param = kimenet.get("parameterek") or {}
    if not isinstance(kimenet_param, dict):
        kimenet_param = {}

    tilos_sertes = _tilos_ellenorzes(eset, kimenet_param)
    if tilos_sertes:
        return 0.0, f"TILTOTT MINTA: {tilos_sertes}"

    if varhato_eszkoz == "nincs":
        if kimenet_eszkoz == "nincs":
            return 1.0, "OK"
        return 0.0, f"várt 'nincs', kapott {kimenet_eszkoz!r}"

    if varhato_eszkoz == "visszakerdez":
        if kimenet_eszkoz == "visszakerdez":
            megorzott = varhato.get("megorzott_parameterek")
            if megorzott and not _reszhalmaz(megorzott, kimenet_param):
                return 0.5, "visszakérdezett, de a megőrzött paramétereket elvesztette"
            return 1.0, "OK"
        if eset.reszleges_elfogadas and kimenet_eszkoz == eset.reszleges_elfogadas.get("eszkoz"):
            return eset.reszleges_elfogadas["pontszam"], "részleges elfogadás"
        return 0.0, f"várt 'visszakerdez', kapott {kimenet_eszkoz!r}"

    varhato_param = varhato.get("parameterek") or {}
    if kimenet_eszkoz == varhato_eszkoz and kimenet_param == varhato_param:
        return 1.0, "OK"
    if eset.reszleges_elfogadas and kimenet_eszkoz == eset.reszleges_elfogadas.get("eszkoz"):
        return eset.reszleges_elfogadas["pontszam"], "részleges elfogadás"
    if kimenet_eszkoz == varhato_eszkoz:
        return 0.0, f"eszköz stimmel, paraméterek eltérnek: {kimenet_param} != {varhato_param}"
    return 0.0, f"várt {varhato_eszkoz!r}, kapott {kimenet_eszkoz!r}"


@dataclass
class EsetEredmeny:
    eset: Eset
    pontszam: float
    indoklas: str
    telt_masodperc: float
    tokenszam: int
    hiba: str | None
    nyers_kimenet: dict | None = None
    # Önkonzisztencia: hány futás értett egyet az UTOLSÓ fordulón
    # (ADR-021). `None`, ha nem volt bekapcsolva.
    egyetertes: int | None = None
    # A biztonsági sértések `[(kategoria, indoklas), ...]` — csak a
    # robusztussági halmazon telik meg (l. `biztonsagi_ellenorzes`).
    biztonsagi_sertesek: list[tuple[str, str]] = field(default_factory=list)
    # MINDEN forduló kimenete (egyfordulós esetnél egyelemű lista) — az
    # ismétlés-stabilitás vizsgálatához.
    fordulo_kimenetek: list[dict | None] = field(default_factory=list)
    # MINDEN forduló ideje másodpercben — a válaszidő-eloszlás
    # alapegysége a forduló (ADR-022), nem az eset.
    fordulo_idok: list[float] = field(default_factory=list)


def ertelmezo_hivo(ertelmezo) -> HivoFuggveny:
    """`HivoFuggveny`-t ad TETSZŐLEGES `Ertelmezo`-protokollt megvalósító
    objektumból — `SzabalyAlapuErtelmezo`, `LLMErtelmezo` vagy
    `KaszkadErtelmezo` egyaránt (bármelyiknek van `.ertelmez(mondat, *,
    most, kontextus)` metódusa, l. `assistant/interpreter/__init__.py`).
    Önmagában sem Ollamát, sem hálózatot nem indít — az csak akkor
    történik meg, ha a kapott `ertelmezo` maga hív ilyet.

    Egy- ÉS többfordulós esetet egyaránt kezel: a `bemenet` egy mondat
    vagy mondatlista, minden fordulót sorban futtat, a kontextust az
    orchestratoréval AZONOS szándék-rétegzési szabállyal víve tovább
    (`assistant.orchestrator.kovetkezo_kontextus` — kemény rész marad,
    puha rész mozog), hogy a golden set és a valódi orchestrator-
    viselkedés ne driftelhessen szét. A visszaadott kimenet az UTOLSÓ
    forduló eredménye — a `kiertekel()` erre a `varhato`-t veti.

    **Az előzményekben CSAK a vásárlói sorok szerepelnek** (ADR-019). A
    mérés nem hívja az eszközöket, tehát nincsenek valódi rendszer-
    válaszok; kitalálni őket hamisítás lenne. Az éles út (`ui/
    vasarlo.py`) a rendszer sorait is átadja, tehát a modell OTT többet
    lát, mint itt — a mérés ebben az irányban téved, vagyis konzervatív:
    a mért érték a valós képesség alsó becslése, nem felső."""
    from assistant import allapotgep
    from assistant.interpreter import KI_RENDSZER, KI_VASARLO, ErtelmezesKontextus
    from assistant.orchestrator import kovetkezo_kontextus

    def hivo(
        bemenet: str | list[str], most: str, felajanlott: list[str] | None = None
    ) -> tuple[dict | None, float, int, str | None]:
        eset_felajanlott = list(felajanlott or [])
        kezdet = time.monotonic()
        fordulok = bemenet if isinstance(bemenet, list) else [bemenet]
        megorzott: dict = {}
        elozmenyek: list[tuple[str, str]] = []
        kimenet: dict | None = None
        # Fordulónkénti kimenetek — az ismétlés-stabilitás vizsgálatához
        # (`biztonsagi_ellenorzes`). A `HivoFuggveny` visszatérési alakja
        # NEM változik (a `spike/golden_futtato.py` és a determinisztikus
        # védőháló is ezt hívja); a lista a függvény-objektumon utazik.
        hivo.fordulo_kimenetek = []
        # Fordulónkénti IDŐK — a válaszidő-elvárás fordulónkénti eloszlás
        # (ADR-022), tehát a p50/p95 alapegysége a forduló, nem az eset.
        # Egy háromfordulós eset összideje egyetlen mintaként háromszoros
        # fordulónak látszana, és a farkat hamisan nyújtaná meg.
        hivo.fordulo_idok = []
        try:
            for sorszam, mondat in enumerate(fordulok, start=1):
                fordulo_kezdet = time.monotonic()
                # A FELAJÁNLOTT IDŐPONTOK az UTOLSÓ forduló elé kerülnek
                # — ugyanabban az alakban, ahogy a felület teszi —, és
                # velük az állapotsor is (ADR-028). Enélkül a jelöltre
                # hivatkozó mondat mérhetetlen: a modell nem tudná, mire
                # hivatkozik a vásárló.
                allapot_sor = None
                if eset_felajanlott and sorszam == len(fordulok):
                    elozmenyek.append(
                        (KI_RENDSZER, "Felajánlott időpontok: " + "; ".join(eset_felajanlott))
                    )
                    allapot_sor = allapotgep.prompt_sor(
                        allapotgep.AJANLAT_VAR, jeloltek_szama=len(eset_felajanlott)
                    )
                kontextus = ErtelmezesKontextus(
                    megorzott_parameterek=dict(megorzott),
                    elozmenyek=list(elozmenyek),
                    allapot_sor=allapot_sor,
                )
                kimenet = ertelmezo.ertelmez(mondat, most=most, kontextus=kontextus)
                hivo.fordulo_idok.append(time.monotonic() - fordulo_kezdet)
                hivo.fordulo_kimenetek.append(kimenet)
                megorzott = kovetkezo_kontextus(megorzott, kimenet)
                elozmenyek.append((KI_VASARLO, mondat))
        except Exception as exc:  # noqa: BLE001 - a mérés szempontjából a kivétel is bukás
            return None, time.monotonic() - kezdet, 0, str(exc)
        return kimenet, time.monotonic() - kezdet, 0, None

    hivo.fordulo_kimenetek = []
    hivo.fordulo_idok = []
    return hivo


class BurkoltHivo:
    """Egy `HivoFuggveny` burkolója, ami a fordulónkénti adatokat
    (kimenetek, idők, egyetértés) MAGÁTÓL átvezeti magára.

    **Ez egy mérési hiba miatt lett osztály** (2026-08-26). Korábban a
    modell-utak (`kaszkad`, `forditott`) hívója egy closure volt, ami a
    réteg-számlálót vezette — és a `fordulo_kimenetek`-et nem emelte át.
    A `fut()` ezért üres listát látott, és az ismétlés-STABILITÁS
    vizsgálata (`instabil_ismetles`) némán kimaradt: a jelentésben 0
    állt, nem azért, mert stabil volt, hanem mert **nem mértük**. A
    `llm` felállás ép volt (ott nincs burkoló) — és épp ezért látszott
    OTT 2 instabil eset, amit a kapuk érdemének tulajdonítottunk.

    A tanulság nem az elfelejtett sor, hanem a szerkezet: egy
    mellékhatásokkal dolgozó closure-t nem lehet tesztelni, egy
    osztályt igen (`tests/egyseg/test_robusztus_halmaz.py`).

    `konyveles`: opcionális visszahívás, ami minden eset után lefut, és
    az önkonzisztencia-egyetértést adja vissza (vagy `None`)."""

    def __init__(self, alap: HivoFuggveny, konyveles: Callable | None = None) -> None:
        self._alap = alap
        self._konyveles = konyveles
        self.fordulo_kimenetek: list[dict | None] = []
        self.fordulo_idok: list[float] = []
        self.utolso_egyetertes: int | None = None

    def __call__(self, bemenet: str | list[str], most: str, felajanlott: list[str] | None = None):
        # A `felajanlott` (ADR-030: mit ajánlottunk fel az utolsó forduló
        # előtt) ugyanúgy átmegy, mint minden más — a burkoló csak a
        # fordulónkénti adatokat gyűjti, a hívás alakját nem szűkíti.
        eredmeny = self._alap(bemenet, most, felajanlott)
        self.fordulo_kimenetek = list(getattr(self._alap, "fordulo_kimenetek", []) or [])
        self.fordulo_idok = list(getattr(self._alap, "fordulo_idok", []) or [])
        if self._konyveles is not None:
            self.utolso_egyetertes = self._konyveles(eredmeny)
        return eredmeny


def fut(meta: dict, esetek: list[Eset], hivo: HivoFuggveny) -> list[EsetEredmeny]:
    most = meta["most_alapertelmezett"]
    robusztus = meta.get("fajta") == "robusztus"
    eredmenyek = []
    for eset in esetek:
        kimenet, telt, tokenszam, hiba = (
            hivo(eset.bemenet, most, eset.felajanlott)
            if eset.felajanlott
            else hivo(eset.bemenet, most)
        )
        pontszam, indoklas = kiertekel(eset, kimenet)
        if hiba:
            indoklas = f"{indoklas} [hívási hiba: {hiba}]"
        fordulo_kimenetek = list(getattr(hivo, "fordulo_kimenetek", []) or [])
        sertesek = (
            biztonsagi_ellenorzes(eset, kimenet, fordulo_kimenetek, most) if robusztus else []
        )
        eredmenyek.append(
            EsetEredmeny(
                eset,
                pontszam,
                indoklas,
                telt,
                tokenszam,
                hiba,
                kimenet,
                biztonsagi_sertesek=sertesek,
                fordulo_kimenetek=fordulo_kimenetek,
                fordulo_idok=list(getattr(hivo, "fordulo_idok", []) or []),
                egyetertes=getattr(hivo, "utolso_egyetertes", None),
            )
        )
        print(f"  {eset.id:32s} {pontszam:.1f}  {indoklas[:60]}")
        for kategoria, ok in sertesek:
            print(f"      !! {kategoria}: {ok}")
    return eredmenyek


def biztonsagi_osszesites(eredmenyek: list[EsetEredmeny]) -> dict[str, int]:
    """Kategóriánkénti darabszám a négy biztonsági mérőszámból. A
    `kivetel` a hívási hibából jön (nem a `biztonsagi_ellenorzes`-ből):
    egy kivétel esetén NINCS kimenet, amit vizsgálni lehetne."""
    szamok = dict.fromkeys(BIZTONSAGI_KATEGORIAK, 0)
    for er in eredmenyek:
        if er.hiba:
            szamok[KIVETEL] += 1
        for kategoria, _ in er.biztonsagi_sertesek:
            szamok[kategoria] = szamok.get(kategoria, 0) + 1
    return szamok


def biztonsagi_jelentes(
    meta: dict, eredmenyek: list[EsetEredmeny]
) -> tuple[dict[str, int], list[str]]:
    """A biztonsági blokk kiírása. `(darabszámok, küszöbsértések)` — a
    küszöbsértés lista üressége a futás BUKÁS/NEM BUKÁS döntése.

    Ez a blokk a pontosság ELŐTT megy ki, szándékosan: a halmaz
    elfogadási elve szerint a pontosság másodlagos."""
    szamok = biztonsagi_osszesites(eredmenyek)
    kuszobok = meta.get("biztonsagi_kuszobok", {})

    print("\n=== BIZTONSÁGI MÉRŐSZÁMOK (ezek az elsődlegesek) ===\n")
    sertesek: list[str] = []
    for kategoria in BIZTONSAGI_KATEGORIAK:
        darab = szamok.get(kategoria, 0)
        kuszob = kuszobok.get(kategoria)
        if kuszob is None:
            allapot = "—"
        elif darab <= kuszob:
            allapot = "TARTJA"
        else:
            allapot = "NEM TARTJA"
            sertesek.append(f"{kategoria}: {darab} > küszöb {kuszob}")
        kuszob_str = f"küszöb {kuszob}" if kuszob is not None else "nincs küszöb"
        print(f"  {kategoria:26s} {darab:3d}   {kuszob_str:12s} [{allapot}]")

    if any(er.biztonsagi_sertesek or er.hiba for er in eredmenyek):
        print("\n  Érintett esetek:")
        for er in eredmenyek:
            if er.hiba:
                print(f"    {er.eset.id:32s} KIVÉTEL: {er.hiba[:60]}")
            for kategoria, ok in er.biztonsagi_sertesek:
                print(f"    {er.eset.id:32s} {kategoria}: {ok[:60]}")
    else:
        print("\n  Egyetlen sértés sem — az elfogadási elv teljesül.")
    return szamok, sertesek


def valaszido_jelentes(eredmenyek: list[EsetEredmeny]) -> dict:
    """A FORDULÓNKÉNTI válaszidő-eloszlás (ADR-022): p50, p95, átlag,
    max és a tendencia. A kivétellel elszállt esetek kimaradnak — ott
    nem válaszidőt mértünk, hanem összeomlást."""
    idok = [ido for er in eredmenyek if er.hiba is None for ido in er.fordulo_idok]
    if not idok:
        return {"n": 0, "p50": None, "p95": None, "atlag": None, "max": None}
    return {
        "n": len(idok),
        "p50": percentilis(idok, 0.50),
        "p95": percentilis(idok, 0.95),
        "atlag": sum(idok) / len(idok),
        "max": max(idok),
        "tendencia": tendencia(idok),
    }


# Az ASR-szimulált esetek közös címkéje. A halmazban minden ilyen eset
# MÁSODIK címkéje `asr`, az első a hiba fajtája (`asr_szam`, `asr_nev`,
# …) — így a réteg-bontás a fajtákat mutatja, ez a szám pedig az
# egészet.
ASR_CIMKE = "asr"


def reszhalmaz_jelentes(eredmenyek: list[EsetEredmeny], cimke: str) -> dict | None:
    """Egy CÍMKÉVEL jelölt részhalmaz külön mérése — ma az ASR-szimulált
    esetekre (`asr`).

    Miért kell külön: az ASR-hibák más kockázatot hordoznak, mint a
    halmaz többi kategóriája. Ott a bemenet SZÁNDÉKOSAN rossz (zaj,
    támadás, abszurdum), és a rendszer helyes viselkedése az elhárítás
    vagy a visszakérdezés. Itt a vásárló JÓL mondta, csak a gép hallotta
    rosszul — a mondat mögött valódi, kiszolgálható szándék van. Ha
    ezeket az egész halmaz átlagába olvasztjuk, a 44 „elhárítás rendben"
    eset elfedi, hogy 18 valódi vásárlót elveszítettünk.

    `None`, ha a halmazban nincs ilyen címkéjű eset."""
    reszhalmaz = [er for er in eredmenyek if cimke in er.eset.cimkek]
    if not reszhalmaz:
        return None
    szamok = biztonsagi_osszesites(reszhalmaz)
    pontossag = sum(er.pontszam for er in reszhalmaz) / len(reszhalmaz)

    print(f"\n=== KÜLÖN BONTÁS: `{cimke}` — {len(reszhalmaz)} eset ===\n")
    for kategoria in BIZTONSAGI_KATEGORIAK:
        print(f"  {kategoria:26s} {szamok.get(kategoria, 0):3d}")
    print(f"  {'pontosság':26s} {pontossag:6.1%}")

    # Fajtánként (az első címke) — ebből látszik, MELYIK ASR-hibatípus
    # a nehéz, nem csak az, hogy az átlag mennyi.
    fajtak: dict[str, list[float]] = defaultdict(list)
    for er in reszhalmaz:
        fajtak[er.eset.reteg].append(er.pontszam)
    print("\n  Fajtánként:")
    for fajta in sorted(fajtak):
        pontok = fajtak[fajta]
        print(f"    {fajta:24s} {sum(pontok) / len(pontok):6.1%}  (n={len(pontok)})")

    bukott = [er for er in reszhalmaz if er.pontszam < 1.0 or er.biztonsagi_sertesek or er.hiba]
    if bukott:
        print("\n  Nem tökéletes esetek:")
        for er in bukott:
            print(f"    {er.eset.id:30s} {er.pontszam:.1f}  {er.indoklas[:70]}")

    return {
        "n": len(reszhalmaz),
        "biztonsagi_szamok": szamok,
        "pontossag": pontossag,
        "fajtak": {f: sum(p) / len(p) for f, p in fajtak.items()},
    }


def jelent(cimke: str, meta: dict, eredmenyek: list[EsetEredmeny]) -> dict:
    print(f"\n=== {cimke} — összesítés ===\n")

    # Címkénkénti bontás — MINDEN cimke, nem csak a réteg-cimke.
    cimke_pontok: dict[str, list[float]] = defaultdict(list)
    for er in eredmenyek:
        for c in er.eset.cimkek:
            cimke_pontok[c].append(er.pontszam)

    print("Címkénkénti pontosság:")
    cimke_jelentes = {}
    for c in sorted(cimke_pontok):
        pontok = cimke_pontok[c]
        atlag = sum(pontok) / len(pontok)
        cimke_jelentes[c] = {"atlag": atlag, "n": len(pontok)}
        print(f"  {c:28s} {atlag:6.1%}  (n={len(pontok)})")

    # Réteg-bontás a küszöbök szerint (az első cimke = réteg).
    reteg_pontok: dict[str, list[float]] = defaultdict(list)
    for er in eredmenyek:
        reteg_pontok[er.eset.reteg].append(er.pontszam)

    kuszobok = meta.get("kuszobok", {})
    print("\nRéteg-küszöbök:")
    reteg_jelentes = {}
    legrosszabb_reteg = None
    legrosszabb_ertek = 2.0
    for reteg in sorted(reteg_pontok):
        pontok = reteg_pontok[reteg]
        atlag = sum(pontok) / len(pontok)
        kuszob = kuszobok.get(reteg)
        allapot = "—"
        if kuszob is not None:
            allapot = "TARTJA" if atlag >= kuszob else "NEM TARTJA"
            if atlag < legrosszabb_ertek:
                legrosszabb_ertek = atlag
                legrosszabb_reteg = reteg
        reteg_jelentes[reteg] = {
            "atlag": atlag,
            "kuszob": kuszob,
            "n": len(pontok),
            "allapot": allapot,
        }
        kuszob_str = f"küszöb {kuszob:.0%}" if kuszob is not None else "nincs küszöb (pl. kapuőr)"
        print(f"  {reteg:20s} {atlag:6.1%}  (n={len(pontok):2d})  {kuszob_str}  [{allapot}]")

    osszesitett = sum(er.pontszam for er in eredmenyek) / len(eredmenyek)
    print(f"\nÖsszesített pontosság: {osszesitett:.1%}  (n={len(eredmenyek)})")
    if legrosszabb_reteg:
        print(
            f"Leggyengébb réteg (ez a mérőszám, nem az átlag): "
            f"{legrosszabb_reteg} = {legrosszabb_ertek:.1%}"
        )

    # VÁLASZIDŐ — a blueprint 12. szakasz elvárása ELOSZLÁS, fordulónként
    # (ADR-022): p50 < 10 s, p95 < 25 s, a tendencia figyelve. Az
    # alapegység a FORDULÓ, nem az eset: egy háromfordulós eset összideje
    # egyetlen mintaként hamisan nyújtaná meg a farkat.
    ido_jelentes = valaszido_jelentes(eredmenyek)
    if ido_jelentes["n"]:
        print(
            f"\nVálaszidő-eloszlás fordulónként (ezen a futáson, szekvenciálisan, "
            f"n={ido_jelentes['n']}):"
        )
        for kulcs, elvaras in (("p50", P50_KERET_MASODPERC), ("p95", P95_KERET_MASODPERC)):
            allapot = "TARTJA" if ido_jelentes[kulcs] <= elvaras else "NEM TARTJA"
            print(
                f"  {kulcs}   {ido_jelentes[kulcs]:6.2f} s   (elvárás < {elvaras:.0f} s)  "
                f"[{allapot}]"
            )
        print(f"  átlag {ido_jelentes['atlag']:6.2f} s   max {ido_jelentes['max']:6.2f} s")
        print(f"  {tendencia_szoveg(ido_jelentes['tendencia'])}")
    hibaszam = sum(1 for er in eredmenyek if er.hiba)
    if hibaszam:
        print(f"Hívási hibák: {hibaszam}/{len(eredmenyek)}")

    return {
        "cimke": cimke,
        "osszesitett": osszesitett,
        "legrosszabb_reteg": legrosszabb_reteg,
        "legrosszabb_ertek": legrosszabb_ertek if legrosszabb_reteg else None,
        "cimkek": cimke_jelentes,
        "retegek": reteg_jelentes,
        "hibaszam": hibaszam,
        "valaszido": ido_jelentes,
        "n": len(eredmenyek),
    }


def _atlag_pontszam(eredmenyek: list[EsetEredmeny]) -> float:
    return sum(er.pontszam for er in eredmenyek) / len(eredmenyek) if eredmenyek else 0.0


def szoras_jelentes(pontszamok: list[float], elozo_json: Path | None = None) -> dict:
    """A FUTÁSONKÉNTI TARTOMÁNY és az előző futáshoz mért különbség
    kiírása — plusz az ítélet: hatás-e vagy szórás.

    **Miért kell ez a futtatóba, és nem a jelentésbe.** Egy szám
    önmagában nem mond semmit arról, mekkora a zaja; aki két mérést
    összehasonlít, óhatatlanul hatásnak olvassa a különbséget. Ez a
    blokk elveszi ezt a lehetőséget: kiírja a tartományt, és ha a
    különbség azon belül van, ki is mondja, hogy NEM állítható javulás
    vagy romlás.

    A küszöb `SZORAS_KUSZOB_SZAZALEKPONT` (3 pont) VAGY a ténylegesen
    mért tartomány — amelyik nagyobb. Két futás tartománya alsó becslés
    a zajra, tehát nem szabad vele alálicitálni a mért tapasztalatnak."""
    jelentes: dict = {"futasok": [round(p, 4) for p in pontszamok]}
    print("\n=== ISMÉTELHETŐSÉG ===\n")

    tartomany = 0.0
    if len(pontszamok) > 1:
        tartomany = (max(pontszamok) - min(pontszamok)) * 100
        for i, pont in enumerate(pontszamok, start=1):
            print(f"  {i}. futás: {pont:.1%}")
        print(f"  tartomány: {tartomany:.1f} százalékpont")
    else:
        print("  Egy futás — a szórásról ez semmit nem mond. Két futáshoz: --ismetles 2")
    jelentes["tartomany_szazalekpont"] = round(tartomany, 2)

    kuszob = max(SZORAS_KUSZOB_SZAZALEKPONT, tartomany)
    jelentes["kuszob_szazalekpont"] = round(kuszob, 2)
    print(
        f"  Zajküszöb: {kuszob:.1f} százalékpont "
        f"(a {SZORAS_KUSZOB_SZAZALEKPONT:.0f} pontos alapérték és a mért tartomány közül a nagyobb)"
    )

    if elozo_json is not None:
        if not elozo_json.exists():
            print(f"  (az előző futás JSON-ja nem található: {elozo_json})")
            return jelentes
        elozo = json.loads(elozo_json.read_text(encoding="utf-8"))["osszefoglalo"]["osszesitett"]
        kulonbseg = (pontszamok[0] - elozo) * 100
        jelentes["elozo"] = round(elozo, 4)
        jelentes["kulonbseg_szazalekpont"] = round(kulonbseg, 2)
        print(f"  Előző futás: {elozo:.1%}  →  most: {pontszamok[0]:.1%}  ({kulonbseg:+.1f} pont)")
        if abs(kulonbseg) < kuszob:
            jelentes["itelet"] = "szoras"
            print(
                "  ÍTÉLET: a különbség a zajküszöbön BELÜL van — ez SZÓRÁS, nem hatás.\n"
                "  A jelentés ne állítson se javulást, se romlást."
            )
        else:
            jelentes["itelet"] = "javulas" if kulonbseg > 0 else "romlas"
            irany = "JAVULÁS" if kulonbseg > 0 else "ROMLÁS"
            print(f"  ÍTÉLET: {irany} — a különbség meghaladja a zajküszöböt.")
    return jelentes


def main(argv: list[str] | None = None) -> int:
    """`python feladat.py golden` belépési pontja. Alapértelmezetten
    (`--ertelmezo szabaly`) a determinisztikus értelmezőt futtatja —
    NINCS Ollama-hívás, hacsak explicit nem kéred `--ertelmezo llm`
    vagy `--ertelmezo kaszkad` kapcsolóval. Rétegenkénti bontást ír."""
    parser = argparse.ArgumentParser(description="Golden set kiértékelő.")
    parser.add_argument(
        "--ertelmezo",
        choices=["szabaly", "llm", "kaszkad", "forditott"],
        default="szabaly",
        help=(
            "szabaly: nincs Ollama-hívás (alapértelmezett). llm/kaszkad/forditott: "
            "Ollamát hív. A 'forditott' az ÉLES út (ADR-018: a modell értelmez "
            "előbb), a 'kaszkad' az ADR-016 régi sorrendje, összehasonlításért."
        ),
    )
    parser.add_argument(
        "--modell",
        default=None,
        help="Ollama modellnév (--ertelmezo llm/kaszkad mellett) — enélkül az "
        "APRAJAFALVA_LLM_MODELL környezeti változóból jön.",
    )
    parser.add_argument(
        "--halmaz",
        choices=sorted(HALMAZOK),
        default="nyelvi",
        help=(
            "nyelvi: a nyelvi golden set (alapértelmezett) — EGY helyes válasz "
            "esetenként. robusztus: a robusztussági halmaz — elfogadható "
            "VISELKEDÉSEK listája, és négy biztonsági mérőszám kemény küszöbbel."
        ),
    )
    parser.add_argument(
        "--onkonzisztencia",
        action="store_true",
        help=(
            "Az értelmező HÁROMSZOR fut, a JSON eszközhívások pontos "
            "egyenlőségvizsgálatával (ADR-021, blueprint 10.). Ezzel mérhető, "
            "mennyit javít és mennyivel lassít. Élesben alapból ki van kapcsolva."
        ),
    )
    parser.add_argument(
        "--ismetles",
        type=int,
        default=1,
        metavar="N",
        help=(
            "a halmaz N-szeri lefuttatása, és a FUTÁSONKÉNTI TARTOMÁNY kiírása. "
            "Kettőtől felfelé van értelme: egy futásból nem derül ki, hogy egy "
            "különbség hatás-e vagy szórás (l. SZORAS_KUSZOB_SZAZALEKPONT)."
        ),
    )
    parser.add_argument(
        "--elozo",
        type=Path,
        default=None,
        metavar="JSON",
        help=(
            "korábbi futás JSON-ja — a futtató kiírja a különbséget, és megmondja, "
            "hogy az a szóráson BELÜL van-e (akkor nem hatás)"
        ),
    )
    parser.add_argument("--json", type=Path, default=None, help="Eredmény mentése JSON-ba")
    args = parser.parse_args(argv)

    meta, esetek = betolt(HALMAZOK[args.halmaz])
    print(
        f"Betöltve: {len(esetek)} eset ({args.halmaz} halmaz), "
        f"meta.most = {meta['most_alapertelmezett']}"
    )

    reteg_szamlalo: dict[str, int] = {}
    # Önkonzisztencia-eloszlás: hány fordulón volt 3/3, 2/3, illetve
    # nincs többség (ADR-021). Csak `--onkonzisztencia` mellett telik.
    egyetertes_szamlalo: dict[str, int] = {}
    if args.ertelmezo == "szabaly":
        from assistant.interpreter.rule_based import SzabalyAlapuErtelmezo

        print("Értelmező: szabaly (SzabalyAlapuErtelmezo, nincs modellhívás, nincs Ollama)\n")
        hivo = ertelmezo_hivo(SzabalyAlapuErtelmezo())
    else:
        from assistant.interpreter.llm_based import LLMErtelmezo, LLMSzolgaltato

        try:
            szolgaltato = LLMSzolgaltato(modell=args.modell)
        except ValueError as exc:
            print(str(exc))
            return 1
        llm = LLMErtelmezo(szolgaltato)

        if args.ertelmezo == "llm":
            print(f"Értelmező: llm (modell={szolgaltato.modell})\n")
            hivo = ertelmezo_hivo(llm)
        else:
            from assistant.interpreter.rule_based import SzabalyAlapuErtelmezo

            if args.ertelmezo == "forditott":
                from assistant.interpreter.forditott_kaszkad import ForditottKaszkadErtelmezo

                kaszkad = ForditottKaszkadErtelmezo(SzabalyAlapuErtelmezo(), llm)
            else:
                from assistant.interpreter.kaszkad import KaszkadErtelmezo

                kaszkad = KaszkadErtelmezo(SzabalyAlapuErtelmezo(), llm)

            futtatando = kaszkad
            if args.onkonzisztencia:
                from assistant.interpreter.onkonzisztencia import OnkonzisztensErtelmezo

                futtatando = OnkonzisztensErtelmezo(kaszkad)
                print("Önkonzisztencia: BE (3 futás, pontos egyenlőségvizsgálat)")

            print(f"Értelmező: {args.ertelmezo} (modell={szolgaltato.modell})\n")
            alap_hivo = ertelmezo_hivo(futtatando)

            def konyveles(_eredmeny, _kaszkad=kaszkad, _futt=futtatando):
                """Fordulónkénti könyvelés a burkoló mellé: melyik réteg
                oldotta meg, és mennyi volt az önkonzisztencia-egyetértés.
                A fordulónkénti adatok átvezetése NEM itt van — azt a
                `BurkoltHivo` maga intézi, hogy ne lehessen elfelejteni."""
                reteg_szamlalo[_kaszkad.utolso_reteg] = (
                    reteg_szamlalo.get(_kaszkad.utolso_reteg, 0) + 1
                )
                egyetertes = getattr(_futt, "utolso_egyetertes", None)
                if egyetertes is not None:
                    kulcs = f"egyetertes={egyetertes}"
                    egyetertes_szamlalo[kulcs] = egyetertes_szamlalo.get(kulcs, 0) + 1
                return egyetertes

            hivo = BurkoltHivo(alap_hivo, konyveles)

    # ELŐMELEGÍTÉS a modell-utakon. Enélkül az ELSŐ eset a betöltés
    # idejét is viseli (mérve: 13,9 s vs. 3,5 s), és a válaszidő-eloszlás
    # egy olyan számot mutat, ami sosem fordul elő éles beszélgetés
    # közepén. Nem a mérést szépíti: a betöltés a felület indításakor
    # úgyis megtörténik (`ui/vasarlo.py::_elomelegit`).
    if args.ertelmezo != "szabaly":
        from assistant.interpreter.llm_based import elomelegit

        print("Előmelegítés (a modell betöltése)…", end=" ", flush=True)
        print("kész" if elomelegit() else "nem sikerült — a szolgáltatás nem válaszolt")

    eredmenyek = fut(meta, esetek, hivo)

    # ISMÉTELT MÉRÉS — a szórás láthatóvá tétele. A további futások
    # eredményét NEM átlagoljuk bele a jelentésbe: az ELSŐ futás marad a
    # jelentés alapja (különben nem lenne összehasonlítható a korábbi,
    # egyszeres mérésekkel), a többi a TARTOMÁNYT adja.
    ismetelt_pontszamok = [_atlag_pontszam(eredmenyek)]
    for i in range(2, max(args.ismetles, 1) + 1):
        print(f"\n--- {i}. futás (ismétlés a szórás méréséhez) ---")
        ismetelt_pontszamok.append(_atlag_pontszam(fut(meta, esetek, hivo)))

    # A BIZTONSÁGI blokk a pontosság ELŐTT megy ki — a robusztussági
    # halmaz elfogadási elve szerint a pontosság másodlagos.
    biztonsagi_szamok: dict[str, int] = {}
    biztonsagi_sertesek: list[str] = []
    if meta.get("fajta") == "robusztus":
        biztonsagi_szamok, biztonsagi_sertesek = biztonsagi_jelentes(meta, eredmenyek)

    osszefoglalo = jelent(args.ertelmezo, meta, eredmenyek)
    osszefoglalo["halmaz"] = args.halmaz
    osszefoglalo["biztonsagi_szamok"] = biztonsagi_szamok

    # ASR-BONTÁS — a szimulált félrehallások külön mérve (l.
    # `reszhalmaz_jelentes` docstring: más kockázat, más olvasat).
    asr = reszhalmaz_jelentes(eredmenyek, ASR_CIMKE)
    if asr is not None:
        osszefoglalo["asr"] = asr
    if reteg_szamlalo:
        print(
            "\nRéteg-megoszlás (melyik oldotta meg, utolsó forduló): "
            + ", ".join(f"{r}={n}" for r, n in sorted(reteg_szamlalo.items()))
        )
    if egyetertes_szamlalo:
        print(
            "Önkonzisztencia-eloszlás (utolsó forduló): "
            + ", ".join(f"{k}: {n}" for k, n in sorted(egyetertes_szamlalo.items()))
        )
        osszefoglalo["onkonzisztencia"] = dict(egyetertes_szamlalo)

    osszefoglalo["ismetelhetoseg"] = szoras_jelentes(ismetelt_pontszamok, args.elozo)

    if args.json:
        args.json.write_text(
            json.dumps(
                {
                    "osszefoglalo": osszefoglalo,
                    "esetek": [
                        {
                            "id": er.eset.id,
                            "pontszam": er.pontszam,
                            "indoklas": er.indoklas,
                            "telt_masodperc": er.telt_masodperc,
                            "hiba": er.hiba,
                            "nyers_kimenet": er.nyers_kimenet,
                            "biztonsagi_sertesek": er.biztonsagi_sertesek,
                            "egyetertes": er.egyetertes,
                        }
                        for er in eredmenyek
                    ],
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        print(f"\nJSON mentve: {args.json}")

    # A BIZTONSÁGI küszöbsértés elsőbbséget élvez a pontosságival
    # szemben — ha mindkettő fennáll, ez megy ki előbb, mert ez a
    # súlyosabb.
    if biztonsagi_sertesek:
        print("\nBIZTONSÁGI KÜSZÖB TÚLLÉPVE: " + "; ".join(biztonsagi_sertesek))
        return 1

    kuszobok = meta.get("kuszobok", {})
    hibak = [
        f"{reteg}: {adat['atlag']:.0%} < küszöb {kuszobok[reteg]:.0%}"
        for reteg, adat in osszefoglalo["retegek"].items()
        if adat["kuszob"] is not None and adat["atlag"] < adat["kuszob"]
    ]
    if hibak:
        print("\nRéteg-küszöb alatt: " + "; ".join(hibak))
        return 1
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())

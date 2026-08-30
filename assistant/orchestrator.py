"""Orchestrator — determinisztikus állapotgép (ADR-007).

Az `Ertelmezo` (mondat → `{eszkoz, parameterek}`) csak fordít — MINDEN
döntést ez a modul hoz: mikor kérdezzen vissza, mikor váltson zárt
kérdésre, milyen sorrendben hívja az eszközöket, mikor kell megerősítés.
Egy hibás értelmező-válasz legrosszabb esetben kellemetlen (rossz
visszakérdezés), nem káros — a foglalási döntés maga sosem az
értelmezőn múlik (CLAUDE.md, "Alapelv").

Session-állapot **memóriában** él (`_SessionAllapot`), a szándékindexhez
hasonlóan (`core/api/szandekindex.py`) — nem kritikus, tartósan tárolt
állapot, egy folyamat-újraindítás elveszíti, ez szándékos.

Nyilvános felület, 3 belépési pont:

- `fordulo(session_id, mondat, most)` — szabad szöveges forduló.
- `valaszt(session_id, slot_id)` — a vásárló egy konkrét jelöltet
  választott (koppintós VAGY szöveges úton — mindkettő ide fut be,
  `ui/vasarlo.py`, blueprint 10. szakasz, "Koppintós út").
- `megerosit(session_id, vasarlo_kulcs_hash)` — "biztosan lefoglaljam?"
  igenje: véglegesíti a foglalást, visszaadja a kódot.

**Hatókör-korlát (v1):** a `foglalas_athelyezes` és `foglalas_lemondas`
egyfordulós, közvetlen végrehajtású — nincs saját megerősítő allapot,
mert a foglalási kód már önmagában erős szándékjelzés (nem véletlenül
kerül elő), szemben egy vadonatúj foglalással. Ha ez a döntés téves
(pl. véletlen lemondások gyakorivá válnak), külön ADR kell a
megerősítő-lépés bevezetéséhez."""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from assistant.frusztracio import Frusztracio
from assistant.interpreter import ErtelmezesKontextus, Ertelmezo
from assistant.sorszam import sorszam_hivatkozas
from assistant.tools import (
    bolt_info,
    foglalas_athelyezes,
    foglalas_lekerdezes,
    foglalas_lemondas,
    foglalas_letrehozas,
    legkozelebbi_idopont,
    szabad_idopontok,
)
from assistant.tools.katalogus import BOLT_SLUGOK
from core.repo import foglalas_repo

# Ha a mondatból nem oldható fel egy kritikus mező ennyi egymást követő
# fordulóban, az orchestrator zárt kérdésre vált (blueprint 7. szakasz,
# "Négy technika", 2. pont).
_SIKERTELEN_KUSZOB_ZART_KERDESHEZ = 2

# A `visszakerdez` eszköz kimeneti mezői, amik NEM a megőrzendő
# paraméterek része — ezek maguk az irányítási jelzések.
_VISSZAKERDEZ_IRANYITASI_MEZOK = frozenset(
    {"hianyzo_mezo", "varhato_kerdes_tipusa", "valaszthato_ertekek"}
)

# Szándék rétegzés (blueprint 1. szakasz, "Kapjon őszinte választ... ha
# nincs hely, alternatíva jöjjön"; roadmap M4): egy keresési szándéknak
# van KEMÉNY (bolt, szolgáltatás — amit a vásárló egyszer kimond, és
# alkudozás közben nem kell újra kimondania) és PUHA (dátum, napszak,
# preferált óra — ez az, ami egy alkudozó fordulóban ténylegesen mozog:
# szűkítés, tágítás, napszakváltás) része. Csak a kemény rész él túl egy
# lezárt keresést (siker VAGY kudarc) a következő fordulóra — a puha rész
# minden fordulóban frissen dől el, hogy "puha kívánságra ne maradjon
# széles zár" (blueprint 5. szakasz, "Hold" — ugyanez az elv, csak itt a
# kontextusra, nem a slot-zárolásra vetítve).
_KEMENY_MEZOK = frozenset({"bolt_id", "szolgaltatas_id"})

# Ugyanaz a válaszfajta legfeljebb ennyiszer mehet ki változatlanul; a
# MÁSODIKRA a rendszer már kiutat ajánl (`_ismetlest_figyel`).
#
# **Kettőről egyre szigorítva** (2026-08-30, kézi próba). A korábbi 2-es
# küszöbnél a vásárló ugyanazt a mondatot KÉTSZER kapta meg, és a
# stratégiaváltás csak a harmadik fordulóban jött. A képernyőn ez így
# nézett ki: A, A, kiút, kiút. Aki elakadt, annak a második azonos
# válasz már nem információ, hanem jelzés, hogy a rendszer nem érti —
# és a válaszunk megismétlése ezen nem segít.
_ISMETLES_KUSZOB = 1

# A kiútban felajánlott, zárt választási lehetőségek — azok a
# dimenziók, amelyek mentén a vásárló ténylegesen tud lazítani.
#
# A `het` helyett `nap` (2026-08-30): a másik NAP a gyakoribb és
# olcsóbb engedmény (a beosztás heteken át ugyanaz a szerkezet, egy
# héttel odébb ugyanúgy nem lesz hely, ha a napszak a szűk keresztmetszet
# — ezt a `szabad_idopontok::_alternativ_dimenzio` is így sorolja:
# napszak, nap, hét).
_KIUT_DIMENZIOK = ("bolt", "nap", "napszak")

# A sorszámos hivatkozás rétegneve a naplóban (`ui/vasarlo.py`). Nem az
# értelmező rétege — az orchestrator dönt, mert egyedül ő ismeri a
# felajánlott jelölteket (`assistant/sorszam.py`).
RETEG_SORSZAM = "orchestrator:sorszam"

# A kapuőr `ok`-kulcsa (`assistant/kapuor/`) → melyik magyar mondat
# menjen ki (`assistant/valasz/sablonok.py`). Ami nincs benne, arra az
# általános elhárítás megy.
#
# **Miért nem egy mondat mindenre.** Az "udvarias elhárítás" akkor
# udvarias, ha VÁLASZOL a kérdésre — akár nemmel. Egy értelmezhetetlen
# bemenetre ("?????") a "ez nem foglalással kapcsolatos" válasz
# értelmetlen: a vásárló nem kérdezett semmit, csak nem értett. Egy
# ár-kérdésre pedig meg lehet mondani, hogy MIÉRT nem válaszolunk, és
# hogy mire igen. A leképezés ZÁRT: a kapuőr `ok`-készlete zárt, a
# sablonoké is.
_ELUTASITAS_UZENET = {
    "ertelmezhetetlen": "ertelmezhetetlen_bemenet",
    "ar": "ar_nem_adhato",
    "utasitas_feluliras": "nem_foglalasi_kerdes",
    "sema_kenyszerites": "nem_foglalasi_kerdes",
}


@dataclass(frozen=True)
class BizonyossagKuszobok:
    """Konfigurálható bizonyossági küszöbök (blueprint 10. szakasz:
    "Bizalmi jelzés ... kritikus mezőkre"; eszkoz-szerzodes skill).

    **A visszakérdezésről az orchestrator dönt, nem az értelmező** — az
    értelmező csak számot ad, a küszöb itt van. A `None` bizonyosság
    ("nem tudok nyilatkozni") SOSEM esik küszöb alá: abból nem
    következtetünk, mert a hiánya nem bizonytalanság-bizonyíték. A
    determinisztikus értelmező pont ezt használja ki (1.0 vagy None,
    köztes érték nincs) — így a küszöbrendszer bekapcsolása nem
    változtatja meg a determinisztikus viselkedést."""

    eszkoz: float = 0.7
    kritikus_mezo: float = 0.6
    # Ha a két legvalószínűbb szándék bizonyossága ennél közelebb van
    # egymáshoz, zárt kérdéssel tisztázunk ("Lemondani szeretné, vagy
    # áthelyezni?") ahelyett, hogy találgatnánk.
    szandek_kozelseg: float = 0.15


# Azok a mezők, amikre a `kritikus_mezo` küszöb vonatkozik — a
# eszkoz-szerzodes skill "Bizalmi jelzés" táblázata szerint. A `napszak`
# szándékosan KIMARAD: ott a skill is azt mondja, "mehet tovább, tág
# értelmezéssel" — egy bizonytalan napszak nem indokol visszakérdezést.
_KRITIKUS_MEZOK = ("bolt_id", "szolgaltatas_id", "datum")


def kovetkezo_kontextus(elozo_megorzott: dict, ertelmezes: dict) -> dict:
    """Tiszta, állapot nélküli függvény: az előző fordulóban megőrzött
    paraméterekből és az AKTUÁLIS forduló értelmezés-kimenetéből
    (`{eszkoz, parameterek}`) számolja ki, mit kell a KÖVETKEZŐ
    fordulónak megőriznie a kontextusban.

    Két eset:

    - `visszakerdez`: minden ténylegesen kinyert (nem irányítási) mezőt
      megőriz, a régiek fölé — ez a meglévő "ne kérdezz vissza olyat,
      amit már tudsz" viselkedés (golden set, toredekes-03).
    - `szabad_idopontok`: egy keresés LEFUTOTT (sikertől függetlenül —
      a hívó dönti el, mit kezd a tényleges tool-eredménnyel) — innentől
      csak a KEMÉNY mezők élnek túl a következő fordulóra, a puha rész
      (dátum/napszak/óra) nem: egy alkudozó follow-up mindig frissen
      dönti el a puhát, a `assistant/interpreter/rule_based.py`
      `_kereses` ág pedig a hiányzó kemény mezőt ebből a kontextusból
      tölti ki, ha a mondat nem mondja ki újra.

    Minden más eszköznél (`nincs`, `bolt_info`, `foglalas_lemondas`,
    `foglalas_athelyezes`, `foglalas_lekerdezes`) a kontextus
    változatlan marad — ezek nem keresési szándékok, nem érintik a
    szándék-rétegzést.

    Ezt a függvényt az `Orchestrator` és a golden set kiértékelője
    (`tests/golden/futtato.py`) is használja, hogy a mért viselkedés és
    a valódi futásidejű viselkedés ne driftelhessen szét."""
    eszkoz = ertelmezes.get("eszkoz")
    parameterek = ertelmezes.get("parameterek") or {}

    if eszkoz == "visszakerdez":
        megorzendo = {
            k: v for k, v in parameterek.items() if k not in _VISSZAKERDEZ_IRANYITASI_MEZOK
        }
        return {**elozo_megorzott, **megorzendo}

    if eszkoz in ("szabad_idopontok", "legkozelebbi_idopont"):
        teljes = {**elozo_megorzott, **parameterek}
        return {k: v for k, v in teljes.items() if k in _KEMENY_MEZOK}

    return dict(elozo_megorzott)


# Enumeráció-védelem és rate limiting a `foglalas_lekerdezes` ágon
# (blueprint 8. szakasz, "Hitelesítés": "erős rate limiting és
# enumeráció-védelem"; adatvedelem skill). Ez az orchestrator
# felelőssége, nem az eszközé (`assistant/tools/foglalas_lekerdezes.py`
# docstring) — az eszköz önmagában csak listáz.
#
# - **Session-szintű kérésszám-korlát**: ennyi hívás után a session
#   további "mik a foglalásaim" kérése elutasításra kerül, akkor is, ha
#   egyébként érvényes hash-t adna meg — ez teszi drágává a próbálgatásos
#   (brute-force) azonosító-találgatást.
# - **Azonos válaszidő létező és nem létező azonosítóra**: a tool hívása
#   után a válasz KIADÁSÁIG legalább ennyi idő telik el — ha a tényleges
#   lekérdezés gyorsabb volt (pl. nincs találat, rövidebb út), az
#   orchestrator várakozással tölti ki a különbséget, hogy a válaszidő
#   ne áruljon el semmit a találat tényéről.
_LEKERDEZES_RATE_LIMIT = 5
_LEKERDEZES_VALASZIDO_PADDING_MASODPERC = 0.1


@dataclass
class _SessionAllapot:
    session_id: str
    allapot: str = "kezdet"  # kezdet | valasztasra_var | megerositesre_var | lezarva
    megorzott_parameterek: dict = field(default_factory=dict)
    sikertelen_ertelmezesek: int = 0
    aktualis_jeloltek: list[dict] = field(default_factory=list)
    valasztott_slot_id: str | None = None
    lekerdezesek_szama: int = 0
    # Az utolsó tényleges keresés teljes paraméterei — ebből tágít az
    # `alternativa_kereses()`, hogy a vásárlónak ne kelljen újra
    # elmondania, mit keresett.
    utolso_kereses: dict = field(default_factory=dict)
    # Ismétlésfigyelés: {"kulcs": <válaszfajta>, "darab": n} — l.
    # `Orchestrator._ismetlest_figyel`.
    valasz_ismetles: dict = field(default_factory=dict)
    # Frusztráció-számláló (`assistant/frusztracio.py`) — a vásárló
    # oldaláról nézi, hogy elakadtunk-e, nem a mi válaszaink
    # ismétlődéséből.
    frusztracio: Frusztracio = field(default_factory=Frusztracio)


class Orchestrator:
    def __init__(
        self,
        conn,
        ertelmezo: Ertelmezo,
        org_id: str,
        kuszobok: BizonyossagKuszobok | None = None,
        frusztracio_kuszob: int | None = None,
    ):
        self.conn = conn
        self.ertelmezo = ertelmezo
        self.org_id = org_id
        self.kuszobok = kuszobok or BizonyossagKuszobok()
        # Hány "pont" után ajánlunk kiutat (`assistant/frusztracio.py`).
        # `None` = az ottani alapérték.
        self.frusztracio_kuszob = frusztracio_kuszob
        self._sessionok: dict[str, _SessionAllapot] = {}
        # Az utolsó `fordulo()`-hívás nyers értelmezés-kimenete
        # ({eszkoz, parameterek}) — nem a válasz része, csak
        # megfigyelhetőséghez (pl. ui/vasarlo.py próba-naplózásához).
        self.utolso_ertelmezes: dict | None = None

    def _allapot(self, session_id: str) -> _SessionAllapot:
        if session_id not in self._sessionok:
            allapot = _SessionAllapot(session_id=session_id)
            if self.frusztracio_kuszob is not None:
                allapot.frusztracio.kuszob = self.frusztracio_kuszob
            self._sessionok[session_id] = allapot
        return self._sessionok[session_id]

    # -- szabad szöveges forduló ------------------------------------

    def fordulo(
        self,
        session_id: str,
        mondat: str,
        most: str,
        elozmenyek: list[tuple[str, str]] | None = None,
    ) -> dict:
        """`elozmenyek`: a beszélgetés utolsó fordulói `(ki, mit)`
        párokként — ezt az értelmező kapja meg (ADR-019: a modell a
        beszélgetést látja, nem a kontextust adatként).

        **A hívó vezeti, nem az orchestrator**: a ténylegesen kimondott
        magyar mondatokat csak a felület ismeri (az orchestrator
        strukturált választ ad, amit az `assistant/valasz/` fogalmaz
        mondattá). `None` esetén az értelmező előzmények nélkül dolgozik
        — ez a determinisztikus út és az egyfordulós mérés esete."""
        allapot = self._allapot(session_id)
        valasz = self._fordulo_belso(allapot, session_id, mondat, most, elozmenyek or [])
        valasz = self._ismetlest_figyel(allapot, valasz)
        return self._frusztraciot_figyel(allapot, mondat, valasz)

    def _fordulo_belso(
        self,
        allapot: _SessionAllapot,
        session_id: str,
        mondat: str,
        most: str,
        elozmenyek: list[tuple[str, str]],
    ) -> dict:
        # SORSZÁMOS HIVATKOZÁS — „a másodikat", „az utolsó jó lesz".
        #
        # A leggyakoribb természetes válasz egy listára, és a
        # legolcsóbban eldönthető: annyi lehetőség van, ahány jelöltet
        # MI ajánlottunk fel. Nincs mit értelmeztetni rajta (a modell
        # csak elronthatná, és egy elrontott sorszám nem
        # visszakérdezést okoz, hanem MÁS IDŐPONTOT foglal le), ezért
        # ez az ág a modell ELŐTT fut — ugyanaz a rövidzár, mint a
        # gombnyomásé (`forditott_kaszkad._zart_valasz_e`).
        #
        # Csak akkor szólal meg, ha ténylegesen VAN mire hivatkozni:
        # felajánlott jelöltek nélkül a „második" bármi lehet.
        if allapot.aktualis_jeloltek:
            index = sorszam_hivatkozas(mondat, len(allapot.aktualis_jeloltek))
            if index is not None:
                jelolt = allapot.aktualis_jeloltek[index - 1]
                self.utolso_ertelmezes = {
                    "eszkoz": "jelolt_valasztas",
                    "parameterek": {"sorszam": index, "slot_id": jelolt["slot_id"]},
                    "bizonyossag": {"eszkoz": 1.0},
                    "reteg": RETEG_SORSZAM,
                }
                valasz = self.valaszt(session_id, jelolt["slot_id"])
                valasz["reteg"] = RETEG_SORSZAM
                valasz["valasztott_jelolt"] = jelolt
                return valasz

        kontextus = ErtelmezesKontextus(
            megorzott_parameterek=dict(allapot.megorzott_parameterek),
            elozmenyek=list(elozmenyek),
        )
        ertelmezes = self.ertelmezo.ertelmez(mondat, most=most, kontextus=kontextus)
        self.utolso_ertelmezes = ertelmezes
        eszkoz = ertelmezes.get("eszkoz")
        parameterek = ertelmezes.get("parameterek") or {}

        # BIZONYOSSÁG-KAPU: küszöb alatt nem találgatunk, hanem zárt
        # kérdéssel tisztázunk. A döntés ITT van, nem az értelmezőben
        # (blueprint 10. szakasz).
        bizonytalan = self._bizonytalansag_kezel(ertelmezes)
        if bizonytalan is not None:
            allapot.sikertelen_ertelmezesek += 1
            return bizonytalan

        if eszkoz == "nincs":
            allapot.sikertelen_ertelmezesek = 0
            return {
                "tipus": "elutasitas",
                "uzenet_kulcs": _ELUTASITAS_UZENET.get(
                    ertelmezes.get("kapuor_ok"), "nem_foglalasi_kerdes"
                ),
                # A kapuőr oka a naplóba is bekerül (`tools/naplo_elemzo.py`)
                # — abból derül ki, MIÉRT hárítottunk el, nem csak hogy
                # elhárítottunk.
                "kapuor_ok": ertelmezes.get("kapuor_ok"),
            }

        if eszkoz == "visszakerdez":
            return self._visszakerdez(allapot, parameterek)

        # Minden más ág valódi eszközhívás — a sikertelen-számláló
        # nullázódik, mert az értelmezés ezúttal konkrétumra vezetett.
        allapot.sikertelen_ertelmezesek = 0

        if eszkoz == "szabad_idopontok":
            return self._szabad_idopontok(allapot, parameterek)
        if eszkoz == "legkozelebbi_idopont":
            return self._legkozelebbi_idopont(allapot, parameterek, most)
        if eszkoz == "bolt_info":
            teljes = {**parameterek, "session_id": session_id}
            return bolt_info.hivas(self.conn, teljes, org_id=self.org_id)
        if eszkoz == "foglalas_lemondas":
            teljes = {**parameterek, "session_id": session_id}
            return foglalas_lemondas.hivas(self.conn, teljes)
        if eszkoz == "foglalas_athelyezes":
            teljes = {**parameterek, "session_id": session_id}
            return foglalas_athelyezes.hivas(self.conn, teljes)
        if eszkoz == "foglalas_lekerdezes":
            teljes = {**parameterek, "session_id": session_id}
            return self._foglalas_lekerdezes(allapot, teljes)

        # Ismeretlen eszköznév az értelmezőtől — LLM-es implementációnál
        # ez elméletileg kizárt (kötött dekódolás), a szabály-alapúnál
        # programozói hiba lenne. Nem omlik össze, zárt kérdésre terel.
        return self._visszakerdez(
            allapot, {"hianyzo_mezo": "eszkoz", "varhato_kerdes_tipusa": "zart"}
        )

    def _bizonytalansag_kezel(self, ertelmezes: dict) -> dict | None:
        """Zárt kérdést ad vissza, ha az értelmezés bizonyossága küszöb
        alatt van — különben `None` (mehet tovább a szokásos úton).

        Három eset, ebben a sorrendben:

        1. **Két szándék közel van egymáshoz** (`szandek_kozelseg`) — ezt
           az értelmező jelezheti egy `szandek_jeloltek` listával. Ilyenkor
           nem választunk, hanem megkérdezzük: "Lemondani szeretné, vagy
           áthelyezni?"
        2. **Az eszközválasztás bizonytalan** (`eszkoz` küszöb alatt) —
           zárt kérdés a szándékról.
        3. **Egy kritikus mező bizonytalan** (`kritikus_mezo` küszöb
           alatt) — zárt kérdés arra a mezőre.

        A `None` bizonyosság SOSEM esik küszöb alá (l.
        `BizonyossagKuszobok`)."""
        bizonyossag = ertelmezes.get("bizonyossag") or {}

        jeloltek = ertelmezes.get("szandek_jeloltek") or []
        if len(jeloltek) >= 2:
            rendezett = sorted(jeloltek, key=lambda j: j.get("bizonyossag") or 0.0, reverse=True)
            elso, masodik = rendezett[0], rendezett[1]
            kulonbseg = (elso.get("bizonyossag") or 0.0) - (masodik.get("bizonyossag") or 0.0)
            if kulonbseg < self.kuszobok.szandek_kozelseg:
                return {
                    "tipus": "visszakerdezes",
                    "hianyzo_mezo": "eszkoz",
                    "kerdes_tipusa": "zart",
                    "valaszthato_ertekek": [elso.get("eszkoz"), masodik.get("eszkoz")],
                    "ok": "kozeli_szandekok",
                }

        eszkoz_bizonyossag = bizonyossag.get("eszkoz")
        if eszkoz_bizonyossag is not None and eszkoz_bizonyossag < self.kuszobok.eszkoz:
            return {
                "tipus": "visszakerdezes",
                "hianyzo_mezo": "eszkoz",
                "kerdes_tipusa": "zart",
                "valaszthato_ertekek": [],
                "ok": "bizonytalan_szandek",
            }

        for mezo in _KRITIKUS_MEZOK:
            ertek = bizonyossag.get(mezo)
            if ertek is not None and ertek < self.kuszobok.kritikus_mezo:
                return {
                    "tipus": "visszakerdezes",
                    "hianyzo_mezo": mezo,
                    "kerdes_tipusa": "zart",
                    "valaszthato_ertekek": (sorted(BOLT_SLUGOK) if mezo == "bolt_id" else []),
                    "ok": "bizonytalan_mezo",
                }
        return None

    @staticmethod
    def _valasz_kulcs(valasz: dict) -> str | None:
        """A válasz "fajtájának" stabil azonosítója az ismétlésfigyeléshez.
        Visszakérdezésnél a HIÁNYZÓ MEZŐ és a KÉRDÉS TÍPUSA együtt a
        lényeg, máshol az `uzenet_kulcs`. Sikeres ajánlat/
        visszaigazolás nem ismétlés-gyanús — arra `None`.

        **A kérdés típusa azért része a kulcsnak**, mert a blueprint 7.
        szakaszának eszkalációja (nyitott kérdés → két sikertelen
        értelmezés után ZÁRT kérdés) a képernyőn MÁS választ jelent:
        más a mondat, és megjelennek a gombok. Az ilyen váltás tehát
        előrelépés, nem ismétlés — a számláló helyesen nullázódik rá.
        Ha viszont már a második alkalommal is ugyanaz a zárt kérdés
        megy ki, ott nincs hova eszkalálni: jöhet a kiút."""
        tipus = valasz.get("tipus")
        if tipus == "visszakerdezes":
            return f"visszakerdezes:{valasz.get('hianyzo_mezo')}:{valasz.get('kerdes_tipusa')}"
        kulcs = valasz.get("uzenet_kulcs")
        return f"{tipus or 'eszkoz'}:{kulcs}" if kulcs else None

    def _ismetlest_figyel(self, allapot: _SessionAllapot, valasz: dict) -> dict:
        """Ugyanaz a válaszfajta legfeljebb `_ISMETLES_KUSZOB`-ször mehet
        ki változatlanul. A küszöb fölött a rendszer nem mondja
        harmadszor is ugyanazt, hanem **kiutat** ajánl: más mondat, és
        egy zárt, koppintható választás (bolt / hét / napszak) —
        blueprint 7. szakasz, "Négy technika" 2. pontjának szellemében
        (bizonytalanságnál zárt kérdés), és a vásárló 8. igénye szerint
        (legyen kiút).

        A számláló csak az AZONOS fajtára nő; egy másfajta válasz
        nullázza, mert az azt jelenti, hogy a beszélgetés elmozdult."""
        kulcs = self._valasz_kulcs(valasz)
        if kulcs is None:
            allapot.valasz_ismetles = {}
            return valasz

        if allapot.valasz_ismetles.get("kulcs") != kulcs:
            allapot.valasz_ismetles = {"kulcs": kulcs, "darab": 1}
            return valasz

        allapot.valasz_ismetles["darab"] += 1
        if allapot.valasz_ismetles["darab"] <= _ISMETLES_KUSZOB:
            return valasz

        return self._kiut_valasz(
            allapot,
            ok="ismetles",
            # Az eredeti válasz kulcsát megtartjuk, hogy a hívó (és a
            # próba-napló) lássa, MIBŐL futottunk körbe.
            eredeti_uzenet_kulcs=valasz.get("uzenet_kulcs"),
        )

    def _kiut_valasz(
        self,
        allapot: _SessionAllapot,
        *,
        ok: str,
        eredeti_uzenet_kulcs: str | None = None,
        eredeti: dict | None = None,
    ) -> dict:
        """A kiút válasza — MINDKÉT jelzőnek (ismétlésfigyelő,
        frusztráció-figyelő) ez az egyetlen kimenete.

        **Egy számláló, egy eszkaláció.** Korábban a két figyelő külön
        vezette a saját kiútjait, és emiatt az ismétlés-kiút a
        végtelenségig ismételhette önmagát: a szöveges naplóban kétszer
        ugyanaz a „körbe-körbe" mondat jelent meg. Mostantól minden
        kiadott kiút ugyanabba a számlálóba megy
        (`Frusztracio.kiut_ajanlva`), tehát a MÁSODIK kiút — jöjjön
        bármelyik jelzőtől — már embert ajánl, nem újabb szűkítést
        (a vásárló 8. igénye)."""
        emberhez = allapot.frusztracio.kiut_ajanlva >= 1
        allapot.frusztracio.kiut_kiadva()
        valasz = {
            "tipus": "kiut",
            "uzenet_kulcs": "emberhez_iranyitas" if emberhez else "ismetlodo_valasz_kiut",
            "valaszthato_dimenziok": [] if emberhez else list(_KIUT_DIMENZIOK),
            "ok": ok,
            "emberhez": emberhez,
        }
        if eredeti_uzenet_kulcs is not None:
            valasz["eredeti_uzenet_kulcs"] = eredeti_uzenet_kulcs
        if eredeti is not None:
            valasz["eredeti"] = eredeti
        return valasz

    def _frusztraciot_figyel(self, allapot: _SessionAllapot, mondat: str, valasz: dict) -> dict:
        """Ha a vásárló elakadt, KIUTAT ajánlunk — akkor is, ha a
        rendszer minden fordulóban mást válaszolt (az
        `_ismetlest_figyel` csak a saját ismétlődésünket látja).

        A kiút alakja ugyanaz, mint az ismétlés-kiúté, hogy a felület ne
        ágazzon szét — csak a `ok` mező mondja meg, melyik jel indította,
        és a MÁSODIK kiút már embert ajánl, nem újabb szűkítést
        (a vásárló 8. igénye: "legyen kiút emberhez")."""
        allapot.frusztracio.fordulo(mondat, valasz.get("tipus"))

        # Ha az ismétlésfigyelő MÁR kiutat adott ebben a fordulóban, azt
        # nem írjuk felül — az eszkalációt (kiút → ember) a közös
        # számláló intézi (`_kiut_valasz`), nem egy második döntés
        # ugyanabban a fordulóban.
        if valasz.get("tipus") == "kiut":
            return valasz

        # KÉT külön feltétel, mert a két kiútnak más a kérdése. Az
        # ELSŐHÖZ pontgyűjtés kell (onnan tudjuk meg, hogy baj van); a
        # MÁSODIKHOZ az, hogy a felajánlott kiút UTÁN a vásárló még
        # mindig kimondja, hogy elakadt — arra nem kell újabb pont.
        if not (allapot.frusztracio.kiutat_kell() or allapot.frusztracio.emberhez_kell(mondat)):
            return valasz

        return self._kiut_valasz(allapot, ok="frusztracio", eredeti=valasz)

    def _visszakerdez(self, allapot: _SessionAllapot, parameterek: dict) -> dict:
        allapot.sikertelen_ertelmezesek += 1
        allapot.megorzott_parameterek = kovetkezo_kontextus(
            allapot.megorzott_parameterek, {"eszkoz": "visszakerdez", "parameterek": parameterek}
        )

        if allapot.sikertelen_ertelmezesek >= _SIKERTELEN_KUSZOB_ZART_KERDESHEZ:
            kerdes_tipusa = "zart"
        else:
            kerdes_tipusa = parameterek.get("varhato_kerdes_tipusa", "nyitott")

        return {
            "tipus": "visszakerdezes",
            "hianyzo_mezo": parameterek.get("hianyzo_mezo"),
            "kerdes_tipusa": kerdes_tipusa,
            "valaszthato_ertekek": parameterek.get("valaszthato_ertekek", []),
        }

    def _foglalas_lekerdezes(self, allapot: _SessionAllapot, teljes: dict) -> dict:
        """Enumeráció-védelem és rate limiting (blueprint 8. szakasz,
        adatvedelem skill) — l. a modulszintű `_LEKERDEZES_*`
        konstansok dokumentációját. Ez az orchestrator felelőssége, az
        eszköz (`assistant/tools/foglalas_lekerdezes.py`) önmagában csak
        listáz."""
        allapot.lekerdezesek_szama += 1
        if allapot.lekerdezesek_szama > _LEKERDEZES_RATE_LIMIT:
            return {"sikeres": False, "ok": "rate_limit", "uzenet_kulcs": "tul_sok_keres"}

        kezdet = time.monotonic()
        eredmeny = foglalas_lekerdezes.hivas(self.conn, teljes)
        hatralevo = _LEKERDEZES_VALASZIDO_PADDING_MASODPERC - (time.monotonic() - kezdet)
        if hatralevo > 0:
            time.sleep(hatralevo)
        return eredmeny

    def _szabad_idopontok(self, allapot: _SessionAllapot, parameterek: dict) -> dict:
        teljes = {
            **allapot.megorzott_parameterek,
            **parameterek,
            "session_id": allapot.session_id,
        }
        # Amit a hívó (`ui/vasarlo.py`) a nyugtázó sorhoz felolvashat,
        # MIELŐTT a tényleges eredmény megvan — csak a felismert
        # keresési ablak és a beazonosított bolt, a blueprint 7. szakasz
        # "mondható" oszlopa szerint (docs/blueprint.md, "Kétlépcsős
        # válasz"). Konkrét időpont vagy darabszám ide sosem kerül.
        felismert_ablak = {
            k: teljes[k] for k in ("bolt_id", "datum_tol", "datum_ig", "napszak") if k in teljes
        }

        eredmeny = szabad_idopontok.hivas(self.conn, teljes, org_id=self.org_id)

        # Szándék rétegzés (lásd `kovetkezo_kontextus` docstringje): a
        # keresés kimenetelétől FÜGGETLENÜL a kemény rész (bolt,
        # szolgáltatás) megmarad a következő fordulóra — ez teszi
        # lehetővé az alkudozást (szűkítés/tágítás/napszakváltás) a
        # kemény rész újramondása nélkül, ÉS az "elutasítás után
        # alternatíva" menetet is: a bolt egy sikertelen keresés után
        # sem vész el.
        allapot.megorzott_parameterek = kovetkezo_kontextus(
            allapot.megorzott_parameterek, {"eszkoz": "szabad_idopontok", "parameterek": teljes}
        )

        if not eredmeny["sikeres"]:
            # Az utolsó keresési ablakot megjegyezzük, hogy a felajánlott
            # alternatívát (`alternativa_kereses`) ugyanarra a kérésre
            # tudjuk kitágítani — a vásárlónak nem kell újra elmondania.
            allapot.utolso_kereses = dict(teljes)
            return {"tipus": "eszkoz_hiba", "felismert_ablak": felismert_ablak, **eredmeny}

        allapot.aktualis_jeloltek = eredmeny["jeloltek"]
        allapot.allapot = "valasztasra_var"
        allapot.utolso_kereses = dict(teljes)
        return {
            "tipus": "ajanlat",
            "jeloltek": eredmeny["jeloltek"],
            "felismert_ablak": felismert_ablak,
        }

    def _legkozelebbi_idopont(self, allapot: _SessionAllapot, parameterek: dict, most: str) -> dict:
        """ "Mikor tudok legkorábban menni?" — EGY időpont, holddal.

        Ugyanaz a válaszalak (`ajanlat`, `jeloltek` listával), mint a
        keresésé, hogy a hívó ne ágazzon szét: a felület ugyanúgy
        gombként jeleníti meg, ugyanúgy a `valaszt()` → `megerosit()`
        úton megy tovább. A `legkozelebbi` jelzés csak a bevezető mondat
        megválasztásához kell (`assistant/valasz/`).

        A `most` az orchestratortól jön, nem a mondatból: a horizont
        kezdőpontja rendszeridő, nem vásárlói adat."""
        teljes = {
            **{k: v for k, v in allapot.megorzott_parameterek.items() if k in _KEMENY_MEZOK},
            **parameterek,
            "most": most,
            "session_id": allapot.session_id,
        }
        felismert_ablak = {k: teljes[k] for k in ("bolt_id", "napszak") if k in teljes}
        eredmeny = legkozelebbi_idopont.hivas(self.conn, teljes, org_id=self.org_id)

        allapot.megorzott_parameterek = kovetkezo_kontextus(
            allapot.megorzott_parameterek,
            {"eszkoz": "szabad_idopontok", "parameterek": teljes},
        )
        if not eredmeny["sikeres"]:
            return {"tipus": "eszkoz_hiba", "felismert_ablak": felismert_ablak, **eredmeny}

        allapot.aktualis_jeloltek = eredmeny["jeloltek"]
        allapot.allapot = "valasztasra_var"
        return {
            "tipus": "ajanlat",
            "jeloltek": eredmeny["jeloltek"],
            "felismert_ablak": felismert_ablak,
            "legkozelebbi": True,
        }

    def alternativa_kereses(self, session_id: str, dimenzio: str) -> dict:
        """A felajánlott alternatíva ("mutasd a hét többi napját")
        elfogadása — ugyanazt a keresést futtatja újra, a megadott
        dimenzió mentén kitágított ablakkal.

        A tágítás szabálya NEM itt van, hanem
        `assistant/tools/szabad_idopontok.py::tagitott_ablak()`-ban —
        ugyanaz a függvény, amivel az eszköz eldöntötte, hogy VAN
        alternatíva. Így a gomb pontosan azt a keresést futtatja, amit a
        rendszer ígért; ha a kettő külön élne, szétdriftelhetnének."""
        allapot = self._allapot(session_id)
        if not allapot.utolso_kereses:
            return {"tipus": "hiba", "uzenet_kulcs": "nincs_korabbi_kereses"}

        elozo = allapot.utolso_kereses
        ablak = szabad_idopontok.tagitott_ablak(
            dimenzio,
            datum_tol=elozo["datum_tol"],
            datum_ig=elozo["datum_ig"],
            napszak=elozo.get("napszak", "barmikor"),
        )
        if ablak is None:
            return {"tipus": "hiba", "uzenet_kulcs": "ervenytelen_alternativa"}

        return self._szabad_idopontok(allapot, {**elozo, **ablak})

    def kereses_strukturaltan(self, session_id: str, parameterek: dict) -> dict:
        """A koppintós út belépési pontja (blueprint 10. szakasz,
        "Koppintós út") — a vásárló már strukturált formában adta meg a
        keresési feltételt (gombokkal, legördülőkkel), nincs szükség az
        `Ertelmezo`-re. Ugyanazt az állapotot és ugyanazt az eszközt
        (`szabad_idopontok`) hívja, mint a szöveges út, hogy a
        választás/megerősítés folytatása (`valaszt`, `megerosit`)
        onnantól azonos legyen, függetlenül attól, melyik úton indult."""
        allapot = self._allapot(session_id)
        return self._szabad_idopontok(allapot, parameterek)

    # -- jelölt-választás (koppintós ÉS szöveges út, blueprint 10.) --

    def valaszt(self, session_id: str, slot_id: str) -> dict:
        allapot = self._allapot(session_id)
        jelolt_id_k = {j["slot_id"] for j in allapot.aktualis_jeloltek}
        if slot_id not in jelolt_id_k:
            return {"tipus": "hiba", "uzenet_kulcs": "nem_ajanlott_jelolt"}

        # A NEM választott jelöltek holdját azonnal felszabadítjuk — nem
        # kell megvárni a TTL lejártát, más session hamarabb kaphat rá
        # ajánlatot (foglalasi-mag skill, "Hold").
        for jelolt in allapot.aktualis_jeloltek:
            if jelolt["slot_id"] == slot_id:
                continue
            hold_id = foglalas_repo.hold_list(
                self.conn, slot_id=jelolt["slot_id"], session_id=session_id
            )
            if hold_id is not None:
                foglalas_repo.hold_release(self.conn, hold_id)

        allapot.valasztott_slot_id = slot_id
        allapot.allapot = "megerositesre_var"
        return {"tipus": "megerositest_ker", "slot_id": slot_id}

    # -- végleges megerősítés -----------------------------------------

    def megerosit(self, session_id: str, vasarlo_kulcs_hash: str) -> dict:
        allapot = self._allapot(session_id)
        if allapot.allapot != "megerositesre_var" or allapot.valasztott_slot_id is None:
            return {"tipus": "hiba", "uzenet_kulcs": "nincs_folyamatban_levo_valasztas"}

        eredmeny = foglalas_letrehozas.hivas(
            self.conn,
            {
                "slot_id": allapot.valasztott_slot_id,
                "vasarlo_kulcs_hash": vasarlo_kulcs_hash,
                "idempotencia_kulcs": f"{session_id}:{allapot.valasztott_slot_id}",
                "session_id": session_id,
            },
        )
        if not eredmeny["sikeres"]:
            return {"tipus": "eszkoz_hiba", **eredmeny}

        allapot.allapot = "lezarva"
        return {"tipus": "visszaigazolas", "foglalasi_kod": eredmeny["foglalasi_kod"]}

    def elvet(self, session_id: str) -> dict:
        """A vásárló a "biztosan lefoglaljam?" kérdésre nemet mond — a
        választott jelölt holdját felszabadítjuk, a session
        választásra-vár állapotba tér vissza (a többi jelölt még áll,
        amíg le nem jár a TTL)."""
        allapot = self._allapot(session_id)
        if allapot.valasztott_slot_id is not None:
            hold_id = foglalas_repo.hold_list(
                self.conn, slot_id=allapot.valasztott_slot_id, session_id=session_id
            )
            if hold_id is not None:
                foglalas_repo.hold_release(self.conn, hold_id)
        allapot.valasztott_slot_id = None
        allapot.allapot = "valasztasra_var" if allapot.aktualis_jeloltek else "kezdet"
        return {"tipus": "elvetve"}

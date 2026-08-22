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

from assistant.interpreter import ErtelmezesKontextus, Ertelmezo
from assistant.tools import (
    bolt_info,
    foglalas_athelyezes,
    foglalas_lekerdezes,
    foglalas_lemondas,
    foglalas_letrehozas,
    szabad_idopontok,
)
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

    if eszkoz == "szabad_idopontok":
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


class Orchestrator:
    def __init__(self, conn, ertelmezo: Ertelmezo, org_id: str):
        self.conn = conn
        self.ertelmezo = ertelmezo
        self.org_id = org_id
        self._sessionok: dict[str, _SessionAllapot] = {}
        # Az utolsó `fordulo()`-hívás nyers értelmezés-kimenete
        # ({eszkoz, parameterek}) — nem a válasz része, csak
        # megfigyelhetőséghez (pl. ui/vasarlo.py próba-naplózásához).
        self.utolso_ertelmezes: dict | None = None

    def _allapot(self, session_id: str) -> _SessionAllapot:
        if session_id not in self._sessionok:
            self._sessionok[session_id] = _SessionAllapot(session_id=session_id)
        return self._sessionok[session_id]

    # -- szabad szöveges forduló ------------------------------------

    def fordulo(self, session_id: str, mondat: str, most: str) -> dict:
        allapot = self._allapot(session_id)
        kontextus = ErtelmezesKontextus(megorzott_parameterek=dict(allapot.megorzott_parameterek))
        ertelmezes = self.ertelmezo.ertelmez(mondat, most=most, kontextus=kontextus)
        self.utolso_ertelmezes = ertelmezes
        eszkoz = ertelmezes.get("eszkoz")
        parameterek = ertelmezes.get("parameterek") or {}

        if eszkoz == "nincs":
            allapot.sikertelen_ertelmezesek = 0
            return {"tipus": "elutasitas", "uzenet_kulcs": "nem_foglalasi_kerdes"}

        if eszkoz == "visszakerdez":
            return self._visszakerdez(allapot, parameterek)

        # Minden más ág valódi eszközhívás — a sikertelen-számláló
        # nullázódik, mert az értelmezés ezúttal konkrétumra vezetett.
        allapot.sikertelen_ertelmezesek = 0

        if eszkoz == "szabad_idopontok":
            return self._szabad_idopontok(allapot, parameterek)
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

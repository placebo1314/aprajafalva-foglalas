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


@dataclass
class _SessionAllapot:
    session_id: str
    allapot: str = "kezdet"  # kezdet | valasztasra_var | megerositesre_var | lezarva
    megorzott_parameterek: dict = field(default_factory=dict)
    sikertelen_ertelmezesek: int = 0
    aktualis_jeloltek: list[dict] = field(default_factory=list)
    valasztott_slot_id: str | None = None


class Orchestrator:
    def __init__(self, conn, ertelmezo: Ertelmezo, org_id: str):
        self.conn = conn
        self.ertelmezo = ertelmezo
        self.org_id = org_id
        self._sessionok: dict[str, _SessionAllapot] = {}

    def _allapot(self, session_id: str) -> _SessionAllapot:
        if session_id not in self._sessionok:
            self._sessionok[session_id] = _SessionAllapot(session_id=session_id)
        return self._sessionok[session_id]

    # -- szabad szöveges forduló ------------------------------------

    def fordulo(self, session_id: str, mondat: str, most: str) -> dict:
        allapot = self._allapot(session_id)
        kontextus = ErtelmezesKontextus(megorzott_parameterek=dict(allapot.megorzott_parameterek))
        ertelmezes = self.ertelmezo.ertelmez(mondat, most=most, kontextus=kontextus)
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
            return foglalas_lekerdezes.hivas(self.conn, teljes)

        # Ismeretlen eszköznév az értelmezőtől — LLM-es implementációnál
        # ez elméletileg kizárt (kötött dekódolás), a szabály-alapúnál
        # programozói hiba lenne. Nem omlik össze, zárt kérdésre terel.
        return self._visszakerdez(
            allapot, {"hianyzo_mezo": "eszkoz", "varhato_kerdes_tipusa": "zart"}
        )

    def _visszakerdez(self, allapot: _SessionAllapot, parameterek: dict) -> dict:
        allapot.sikertelen_ertelmezesek += 1
        megorzendo = {
            k: v for k, v in parameterek.items() if k not in _VISSZAKERDEZ_IRANYITASI_MEZOK
        }
        allapot.megorzott_parameterek.update(megorzendo)

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

    def _szabad_idopontok(self, allapot: _SessionAllapot, parameterek: dict) -> dict:
        teljes = {
            **allapot.megorzott_parameterek,
            **parameterek,
            "session_id": allapot.session_id,
        }
        eredmeny = szabad_idopontok.hivas(self.conn, teljes, org_id=self.org_id)
        if not eredmeny["sikeres"]:
            return {"tipus": "eszkoz_hiba", **eredmeny}

        allapot.aktualis_jeloltek = eredmeny["jeloltek"]
        allapot.allapot = "valasztasra_var"
        # A keresés sikerült — a session tudja, mit talált, a megőrzött
        # paraméterek innentől feleslegesek (a következő kérés már új
        # keresés lenne, nem ugyanennek a folytatása).
        allapot.megorzott_parameterek = {}
        return {"tipus": "ajanlat", "jeloltek": eredmeny["jeloltek"]}

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

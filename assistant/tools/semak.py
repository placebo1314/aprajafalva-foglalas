"""A hat eszköz JSON-sémája, verziózva (eszkoz-szerzodes skill).

**A séma itt a WIRE-kontraktus** — ami ténylegesen az `assistant/tools/*.py`
`hivas()` függvényeibe befut, `session_id`-vel együtt. Ez NEM ugyanaz, mint
amit egy értelmező (LLM vagy `assistant/interpreter/rule_based.py`) a
mondatból előállít: az értelmező kimenete `session_id` NÉLKÜLI
`{eszkoz, parameterek}` — a `session_id`-t az orchestrator fűzi hozzá,
mert az a beszélgetés állapotát ismeri, nem az értelmező (ADR-002: "Az
LLM nem foglal, hanem fordít" — a session-kezelés sem az ő dolga).

`additionalProperties: false` mindenhol — ha egy hívó kitalál egy mezőt,
az hiba legyen, ne csendes elnyelés.

Verziózás: minden eszközhöz `SEMAK[eszkoz]["v1"]` — ha egy séma változik,
`"v2"` jön létre MELLÉ, a régi verzió marad (eszkoz-szerzodes skill,
"Verziózás"). A régi verzió eltávolítása külön lépés, ADR-rel.
"""

from __future__ import annotations

from assistant.tools.katalogus import BOLT_SLUGOK, MINDEGY, SZOLGALTATAS_SLUGOK

_NAPSZAKOK = ["delelott", "delutan", "este", "barmikor"]
_BOLT_INFO_MEZOK_V1 = ["nyitvatartas", "cim", "idotartam"]
# v2: bővítve a "Bolti tudás" mezőkkel (docs/blueprint.md 10. szakasz) —
# megjelenes/termek/ar mind szerkesztett adatra mutat (migrations/
# 0004_bolt_szolgaltatas_tudas.sql), nem a modell generálja. Az "ar" a
# kapuőrnél MA is tiltott (golden set kapuor-02) — a séma csak a
# lekérdezési KÉPESSÉGET rögzíti, nem a kapuőr-döntést.
_BOLT_INFO_MEZOK_V2 = [*_BOLT_INFO_MEZOK_V1, "megjelenes", "termek", "ar"]
# v3: "pultosok" — kik dolgoznak a boltban. A vásárló 2. igénye szerint
# ("tudjam, kihez megyek") ez ugyanolyan engedélyezett tényadat, mint a
# nyitvatartás: szerkesztett törzsadatból jön (`alkalmazott` tábla,
# `torzsadat_repo.employees_list`), nem a modelltől. A PULT önmagában
# NEM keresési dimenzió (ADR-024) — de a kérdés, hogy „ki fogad?",
# válaszolható, és nem is jár azonosítással.
_BOLT_INFO_MEZOK_V3 = [*_BOLT_INFO_MEZOK_V2, "pultosok"]

# A KERESŐ eszközök enumjai a MINDEGY szentinellel bővülnek
# (`katalogus.MINDEGY`): a vásárló elengedheti a boltot, a szolgáltatást
# és a napszakot is. A `bolt_info` enumjai NEM bővülnek — ott a „mindegy
# melyik bolt" kérdésnek nincs értelme (egy tény konkrét boltra
# vonatkozik).
_BOLT_ENUM = sorted([*BOLT_SLUGOK, MINDEGY])
_SZOLGALTATAS_ENUM = sorted([*SZOLGALTATAS_SLUGOK, MINDEGY])
_NAPSZAK_ENUM = [*_NAPSZAKOK, MINDEGY]

SEMAK: dict[str, dict[str, dict]] = {
    "szabad_idopontok": {
        "v1": {
            "type": "object",
            "properties": {
                "bolt_id": {"type": "string", "enum": _BOLT_ENUM},
                "szolgaltatas_id": {"type": "string", "enum": _SZOLGALTATAS_ENUM},
                "datum_tol": {"type": "string", "format": "date-time"},
                "datum_ig": {"type": "string", "format": "date-time"},
                "napszak": {"type": "string", "enum": _NAPSZAK_ENUM},
                "preferalt_ora": {"type": "integer"},
                "session_id": {"type": "string"},
            },
            "required": ["bolt_id", "datum_tol", "datum_ig", "session_id"],
            "additionalProperties": False,
        }
    },
    "legkozelebbi_idopont": {
        "v1": {
            "type": "object",
            "properties": {
                "bolt_id": {"type": "string", "enum": _BOLT_ENUM},
                "szolgaltatas_id": {"type": "string", "enum": _SZOLGALTATAS_ENUM},
                "napszak": {"type": "string", "enum": _NAPSZAK_ENUM},
                # Dátumablak SZÁNDÉKOSAN nincs: a "mikor tudok
                # legkorábban?" kérdésben nincs ablak. A `most`-tól néz
                # előre egy rögzített horizontig
                # (`legkozelebbi_idopont._HORIZONT_NAP`).
                "most": {"type": "string", "format": "date-time"},
                "session_id": {"type": "string"},
            },
            "required": ["bolt_id", "most", "session_id"],
            "additionalProperties": False,
        }
    },
    "foglalas_letrehozas": {
        "v1": {
            "type": "object",
            "properties": {
                "slot_id": {"type": "string"},
                # A nyers vásárlóazonosító sosem jut el a core/-ig
                # (CLAUDE.md 2. invariáns) — ez MÁR HMAC-hashelt érték,
                # 64 hex karakter. A hashelést a privacy/ modul végzi
                # majd; amíg az nincs megírva, a hívó felelőssége előre
                # kiszámítani (ugyanaz a mintát követi, mint a CLI
                # `foglal` parancsa, core/api/cli.py).
                "vasarlo_kulcs_hash": {"type": "string"},
                "idempotencia_kulcs": {"type": "string"},
                "session_id": {"type": "string"},
            },
            "required": ["slot_id", "vasarlo_kulcs_hash", "idempotencia_kulcs", "session_id"],
            "additionalProperties": False,
        }
    },
    "foglalas_athelyezes": {
        "v1": {
            "type": "object",
            "properties": {
                "foglalasi_kod": {"type": "string"},
                "uj_slot_id": {"type": "string"},
                "idempotencia_kulcs": {"type": "string"},
                "session_id": {"type": "string"},
            },
            "required": [
                "foglalasi_kod",
                "uj_slot_id",
                "idempotencia_kulcs",
                "session_id",
            ],
            "additionalProperties": False,
        }
    },
    "foglalas_lekerdezes": {
        "v1": {
            "type": "object",
            "properties": {
                # "Mik a foglalásaim" — azonosítás kell hozzá (a
                # skill táblázata szerint: "igen, rate limit"), a
                # rate limitet az orchestrator/session réteg végzi,
                # nem ez az eszköz.
                "vasarlo_kulcs_hash": {"type": "string"},
                "session_id": {"type": "string"},
            },
            "required": ["vasarlo_kulcs_hash", "session_id"],
            "additionalProperties": False,
        }
    },
    "foglalas_lemondas": {
        "v1": {
            "type": "object",
            "properties": {
                "foglalasi_kod": {"type": "string"},
                "session_id": {"type": "string"},
            },
            "required": ["foglalasi_kod", "session_id"],
            "additionalProperties": False,
        }
    },
    # KÍNÁLAT — „milyenek vannak?", „mit lehet itt?" (ADR-032). Az
    # egyetlen eszköz, aminek MINDEN paramétere opcionális a
    # `session_id`-n kívül: pont az a kérdés, amit egy olyan vásárló tesz
    # fel, aki még semmit nem tud a rendszerről.
    #
    # A `bolt_id` szűkít: ha a beszélgetésből már tudjuk, hova megy a
    # vásárló, a másik két bolt felsorolása zaj lenne.
    "kinalat": {
        "v1": {
            "type": "object",
            "properties": {
                "bolt_id": {"type": "string", "enum": sorted(BOLT_SLUGOK)},
                "session_id": {"type": "string"},
            },
            "required": ["session_id"],
            "additionalProperties": False,
        }
    },
    "bolt_info": {
        "v1": {
            "type": "object",
            "properties": {
                "bolt_id": {"type": "string", "enum": sorted(BOLT_SLUGOK)},
                "mit": {"type": "string", "enum": _BOLT_INFO_MEZOK_V1},
                "datum": {"type": "string"},
                "session_id": {"type": "string"},
            },
            "required": ["bolt_id", "mit", "session_id"],
            "additionalProperties": False,
        },
        # v2: "Verziózás" (eszkoz-szerzodes skill) — a v1 VÁLTOZATLAN marad,
        # ez egy új, bővebb séma mellé, nem helyette (docs/blueprint.md
        # 10. szakasz, "Bolti tudás").
        "v2": {
            "type": "object",
            "properties": {
                "bolt_id": {"type": "string", "enum": sorted(BOLT_SLUGOK)},
                "mit": {"type": "string", "enum": _BOLT_INFO_MEZOK_V2},
                "datum": {"type": "string"},
                "session_id": {"type": "string"},
            },
            "required": ["bolt_id", "mit", "session_id"],
            "additionalProperties": False,
        },
        # v3: a "pultosok" mezővel — a v1 és a v2 VÁLTOZATLAN marad
        # mellette (eszkoz-szerzodes skill, "Verziózás").
        "v3": {
            "type": "object",
            "properties": {
                "bolt_id": {"type": "string", "enum": sorted(BOLT_SLUGOK)},
                "mit": {"type": "string", "enum": _BOLT_INFO_MEZOK_V3},
                "datum": {"type": "string"},
                "session_id": {"type": "string"},
            },
            "required": ["bolt_id", "mit", "session_id"],
            "additionalProperties": False,
        },
    },
}


def legutobbi_verzio(eszkoz: str) -> str:
    """A legfrissebb séma-verzió neve egy eszközhöz (pl. `bolt_info`-nál
    ma `"v2"`) — a hívóknak ezen a függvényen keresztül kell kérniük, nem
    beégetett verzió-szó-szerinti stringgel, hogy egy jövőbeli új verzió
    bevezetése ne igényeljen keresés-cserét minden hívóban."""
    return sorted(SEMAK[eszkoz])[-1]

"""LLM-alapú `Ertelmezo` implementáció — ugyanaz a protokoll, mint a
`rule_based.py`-é (`assistant/interpreter/__init__.py::Ertelmezo`), az
orchestrator kódja emiatt NEM változik (ADR-002: "Az LLM nem foglal,
hanem fordít"; ADR-007: az orchestrator dönt, nem az értelmező).

**A zárt halmazok (bolt, szolgáltatás, napszak, `bolt_info.mit`) a már
meglévő eszközsémákból jönnek** (`assistant/tools/semak.py`) — nincs itt
külön, kézzel karbantartott másolat, ami szétdrifthetne.

**Rövid rendszerprompt** (Vapi-tanulság, `docs/PLATFORM_TANULSAGOK.md`,
2. szakasz: "a prompt hossza latencia") — de csak annyira rövid, amennyit
a mérés (`python feladat.py golden --ertelmezo llm`) igazol: az első
változat a JSON-séma mezőleírásaira bízta a `datum` vs `datum_tol`/
`datum_ig` megkülönböztetést és az eszközök leírását — ez mérve
katasztrofálisan rossz volt (~11% a rétegek 0-40%-án), mert a séma
"description" kulcsai nem jutnak el ugyanolyan súllyal a modellhez, mint
a rendszerprompt prózája. Ez a tanulság: **a "ritka instrukció" nem
ugyanaz, mint "amit a sémába lehet rejteni"** — az eszközök rövid
leírása és a dátumformátum-különbség minden híváshoz kell, ezért a
promptban maradt; csak az OLYAN részlet mehetne sémába, ami tényleg csak
egy-egy mező kitöltésekor releváns.

**`think: False` explicit** (nem kihagyva) — a spike mérése szerint
(`spike/EREDMENY.md`) a gondolkodás bekapcsolva sokszorosára növeli a
válaszidőt, kikapcsolva viszont a mező kihagyása kontrollálatlan
gondolkodásba futtatja a modellt (megfigyelt eset: ~7680 tokenes válasz,
JSON parse hiba a séma helyett) — a mezőt mindig explicit kell küldeni.

**Ha az Ollama nem elérhető, ez a réteg nem dob kivételt** — `{"eszkoz":
"nincs", "parameterek": {}}`-et ad vissza (a legártalmatlanabb kimenet:
az orchestrator ezt egyszerű elutasításként kezeli, nem foglal és nem
töröl semmit), és a hibát az `utolso_hiba` mezőn jelzi — ezt a
`kaszkad.py` arra használja, hogy megkülönböztesse "a modell szerint ez
nem foglalási kérés" és "a modell technikailag nem is válaszolt"
között."""

from __future__ import annotations

import json
import logging
import math
import os
import urllib.error
import urllib.request
from dataclasses import dataclass

from assistant.interpreter import ErtelmezesKontextus
from assistant.tools import semak
from assistant.tools.katalogus import BOLT_SLUGOK, SZOLGALTATAS_SLUGOK

_LOG = logging.getLogger(__name__)

# Ugyanaz az eszközhalmaz, amit a determinisztikus értelmező (rule_based.py)
# ténylegesen elő tud állítani — a `foglalas_athelyezes`/`foglalas_lekerdezes`
# szándékosan hiányzik: egyik sem tölthető ki megbízhatóan egyetlen
# mondatból (az áthelyezéshez konkrét `uj_slot_id` kell, a lekérdezéshez
# hitelesített hash — egyik sem nyerhető ki szövegből). Az áthelyezés-
# szándék ezért itt is `visszakerdez`-re fut (ugyanaz a v1 hatókör-korlát,
# mint `rule_based.py`-ben, `assistant/orchestrator.py` dokumentálja).
ESZKOZOK = ["szabad_idopontok", "bolt_info", "foglalas_lemondas", "visszakerdez", "nincs"]

_NAPSZAK_ENUM = semak.SEMAK["szabad_idopontok"]["v1"]["properties"]["napszak"]["enum"]
_BOLT_INFO_MIT_ENUM = semak.SEMAK["bolt_info"][semak.legutobbi_verzio("bolt_info")]["properties"][
    "mit"
]["enum"]

FORMAT_SEMA = {
    "type": "object",
    "properties": {
        "eszkoz": {"type": "string", "enum": ESZKOZOK},
        "parameterek": {
            "type": "object",
            "properties": {
                "bolt_id": {"type": "string", "enum": sorted(BOLT_SLUGOK)},
                "szolgaltatas_id": {"type": "string", "enum": sorted(SZOLGALTATAS_SLUGOK)},
                "datum_tol": {
                    "type": "string",
                    "description": "teljes ISO-8601 UTC időbélyeg, pl. 2026-08-18T00:00:00Z",
                },
                "datum_ig": {
                    "type": "string",
                    "description": "teljes ISO-8601 UTC időbélyeg, pl. 2026-08-18T23:59:59Z",
                },
                "napszak": {"type": "string", "enum": _NAPSZAK_ENUM},
                "preferalt_ora": {"type": "integer"},
                "mit": {"type": "string", "enum": _BOLT_INFO_MIT_ENUM},
                "datum": {
                    "type": "string",
                    "description": (
                        "csak a bolt_info eszközhöz: naptári nap, idő nélkül, "
                        "pl. 2026-08-22 — NE tegyél hozzá órát/percet/Z-t"
                    ),
                },
                "foglalasi_kod": {"type": "string"},
                # A `visszakerdez` irányítási mezői — ezek NEM a hat
                # eszköz sémájából jönnek (azoknak nincs "visszakerdez"
                # nevű eszközük), hanem az Ertelmezo protokoll saját
                # szerződése (assistant/orchestrator.py::_visszakerdez).
                "hianyzo_mezo": {"type": "string"},
                "varhato_kerdes_tipusa": {"type": "string", "enum": ["zart", "nyitott"]},
            },
            "additionalProperties": False,
        },
    },
    "required": ["eszkoz", "parameterek"],
    "additionalProperties": False,
}

# Rövid, mert minden szó latencia (Vapi-tanulság) — DE mérve (l.
# spike/EREDMENY.md és a golden mérés): a séma mezőleírásai önmagukban
# NEM voltak elegendők a "mit" enum és a dátummezők megkülönböztetésére
# — a FORMAT_SEMA "description" kulcsai láthatóan nem jutnak el
# ugyanolyan súllyal a modellhez, mint a rendszerprompt prózája. A
# dátumformátum-sor emiatt itt maradt, nem a sémában — ez nem "ritka",
# ez minden keresésnél/tényválasznál kell.
_RENDSZER_PROMPT = """Aprajafalva foglalási asszisztens vagy. A vásárló egy \
mondatát EGY eszközhívássá alakítod, kizárólag a séma szerint.

Eszközök:
- szabad_idopontok: szabad időpont keresése (bolt, datum_tol, datum_ig, napszak)
- bolt_info: bolt/szolgáltatás adata (nyitvatartás, cím, termék, időtartam)
- foglalas_lemondas: meglévő foglalás lemondása (kell a foglalási kód)
- visszakerdez: ha egy kritikus adat (jellemzően a bolt) hiányzik a mondatból —
  ekkor NE találj ki boltot vagy dátumot, inkább kérdezz
- nincs: ha a kérés nem foglalással/bolttal kapcsolatos

Boltok: szundi (altató), ugyifogyi (petárda), torpilla (boldogság).
"most" (a relatív dátumok — holnap, jövő hét — ehhez képest értendők): {most}

Dátum: szabad_idopontok-nál MINDIG datum_tol/datum_ig (teljes ISO-8601 UTC
időbélyeg, pl. "2026-08-18T00:00:00Z"), SOSEM "datum". bolt_info-nál MINDIG
"datum" (csak a naptári nap, pl. "2026-08-22", idő nélkül).

Lemondáshoz a foglalási kód kell — ha nincs a mondatban, visszakerdez \
(hianyzo_mezo: foglalasi_kod)."""


# Az a JSON-mezőkészlet, amire bizonyosságot számolunk. A kulcs a
# `bizonyossag` dictben megjelenő név, az érték a JSON-ban keresett
# mezőnév. A "datum" szándékosan a `datum_tol`-ra épül: a dátumablak
# egyben mozog, nem érdemes a két végét külön mérni.
_BIZONYOSSAG_MEZOK = {
    "eszkoz": "eszkoz",
    "bolt_id": "bolt_id",
    "szolgaltatas_id": "szolgaltatas_id",
    "datum": "datum_tol",
    "napszak": "napszak",
}


def _ertek_karakter_tartomany(szoveg: str, mezonev: str) -> tuple[int, int] | None:
    """A `"<mezonev>": <érték>` ÉRTÉK-részének karaktertartománya a nyers
    JSON-szövegben, vagy `None`, ha a mező nincs benne. Karakterszinten
    dolgozunk, mert a tokenhatárok nem esnek egybe a JSON-szintaxissal
    (a tokenizáló szívesen összevonja az írásjelet a szomszédjával, pl.
    `":` vagy `",` egyetlen tokenben) — token-mintázatra épülő szeletelés
    ezért megbízhatatlan."""
    kulcs = f'"{mezonev}"'
    kulcs_pozicio = szoveg.find(kulcs)
    if kulcs_pozicio < 0:
        return None
    kettospont = szoveg.find(":", kulcs_pozicio + len(kulcs))
    if kettospont < 0:
        return None

    i = kettospont + 1
    while i < len(szoveg) and szoveg[i] in " \t\n":
        i += 1
    if i >= len(szoveg):
        return None

    if szoveg[i] == '"':  # sztring érték: a záró idézőjelig
        veg = szoveg.find('"', i + 1)
        return (i, len(szoveg) if veg < 0 else veg + 1)
    # szám/logikai érték: a következő elválasztóig
    veg = i
    while veg < len(szoveg) and szoveg[veg] not in ",}\n":
        veg += 1
    return (i, veg)


def _mezo_bizonyossag(logprobs: list[dict], mezonev: str) -> float | None:
    """Egy JSON-mező ÉRTÉKÉNEK bizonyossága a token-logprobokból.

    **Nem a modell önbevallása** (nem kérdezzük meg tőle, mennyire
    biztos — arra köztudottan rosszul kalibrált), hanem a tényleges
    dekódolási valószínűség — blueprint 10. szakasz, "Bizalmi jelzés a
    kötött dekódolás logprobjaiból".

    Két tervezési döntés, mindkettő mérésből:

    1. **Karaktertartomány, nem token-mintázat** (l.
       `_ertek_karakter_tartomany`).
    2. **Mértani közép, nem szorzat.** A tokenvalószínűségek szorzata a
       hosszú értékeket önmagában bünteti: a három tokenre bomló
       `"visszakerdez"` így akkor is bizonytalanabbnak látszana, mint az
       egy tokenes `"nincs"`, ha a modell mindkettőben ugyanolyan biztos
       volt. Az első mérésen ez 0,0001 nagyságrendű, használhatatlan
       számokat adott. A tokenenkénti mértani közép ettől független: azt
       méri, mennyire volt biztos a modell ÁTLAGOSAN egy token
       megválasztásában.

    `None`, ha a mező nem szerepel a kimenetben, vagy a szolgáltató nem
    adott logprobokat — ez NEM 0.0: a "nem tudom megmondani" és a
    "biztosan rossz" két különböző állítás."""
    if not logprobs:
        return None

    # Token → karakter-tartomány leképezés a teljes kimeneten.
    tartomanyok: list[tuple[int, int, float]] = []
    pozicio = 0
    szoveg_reszek = []
    for tok in logprobs:
        darab = tok.get("token", "")
        szoveg_reszek.append(darab)
        logprob = tok.get("logprob")
        if logprob is not None and darab:
            tartomanyok.append((pozicio, pozicio + len(darab), logprob))
        pozicio += len(darab)
    szoveg = "".join(szoveg_reszek)

    ertek_tartomany = _ertek_karakter_tartomany(szoveg, mezonev)
    if ertek_tartomany is None:
        return None
    ertek_kezdet, ertek_veg = ertek_tartomany

    # Minden token, ami átfed az érték tartományával.
    logprob_lista = [
        logprob for kezdet, veg, logprob in tartomanyok if kezdet < ertek_veg and veg > ertek_kezdet
    ]
    if not logprob_lista:
        return None

    atlagos_logprob = sum(logprob_lista) / len(logprob_lista)
    return round(math.exp(atlagos_logprob), 4)


def bizonyossag_szamol(logprobs: list[dict] | None, ertelmezes: dict) -> dict[str, float | None]:
    """A `bizonyossag` mező összeállítása a token-logprobokból — l.
    `_mezo_bizonyossag`. Csak azokra a mezőkre ad számot, amik
    ténylegesen szerepelnek a modell kimenetében."""
    parameterek = ertelmezes.get("parameterek") or {}
    eredmeny: dict[str, float | None] = {}
    for nev, json_mezo in _BIZONYOSSAG_MEZOK.items():
        jelen = json_mezo in ertelmezes or json_mezo in parameterek
        eredmeny[nev] = _mezo_bizonyossag(logprobs or [], json_mezo) if jelen else None
    return eredmeny


@dataclass(frozen=True)
class LLMSzolgaltato:
    """A modell mögötti absztrakció (ADR-013: "elsődleges modell
    Apache-2.0; Racka ellenőrzőként") — a modellnév KONFIGBÓL jön, nem a
    kódba égetve, hogy egy modellváltás (a kiváltó feltétel teljesülése
    esetén) konfigurációs csere legyen, ne kódmódosítás.

    Alapértelmezésben az `APRAJAFALVA_LLM_MODELL` környezeti változóból
    olvas — explicit `modell` argumentum ezt felülírja (pl. teszthez vagy
    a `spike/golden_futtato.py` méréshez, ahol több modellt hasonlítunk
    össze egy futáson belül)."""

    modell: str | None = None
    url: str = "http://localhost:11434/api/chat"
    timeout_masodperc: int = 30

    def __post_init__(self) -> None:
        if self.modell is None:
            nev = os.environ.get("APRAJAFALVA_LLM_MODELL")
            if not nev:
                raise ValueError(
                    "Nincs modellnév — add meg az LLMSzolgaltato(modell=...) "
                    "argumentumot, vagy állítsd be az APRAJAFALVA_LLM_MODELL "
                    "környezeti változót."
                )
            object.__setattr__(self, "modell", nev)


class LLMErtelmezo:
    """Az `Ertelmezo` protokoll LLM-alapú implementációja — Ollama
    `/api/chat`, `format` paraméterrel séma-kényszerítve.

    **Nincs önálló hibaágvédelem a hívón kívül** — ha az Ollama nem fut,
    nem dob kivételt, hanem `{"eszkoz": "nincs", "parameterek": {}}`-et ad,
    és az `utolso_hiba` mezőn jelzi, mi történt (l. modul docstring)."""

    def __init__(self, szolgaltato: LLMSzolgaltato | None = None):
        self.szolgaltato = szolgaltato or LLMSzolgaltato()
        self.utolso_hiba: str | None = None

    def ertelmez(self, mondat: str, *, most: str, kontextus: ErtelmezesKontextus) -> dict:
        self.utolso_hiba = None
        payload = {
            "model": self.szolgaltato.modell,
            "messages": [
                {"role": "system", "content": _RENDSZER_PROMPT.format(most=most)},
                {"role": "user", "content": mondat},
            ],
            "format": FORMAT_SEMA,
            "stream": False,
            "think": False,  # explicit — l. modul docstring
            "options": {"temperature": 0},
            # A bizonyosság a TÉNYLEGES dekódolási valószínűségekből jön,
            # nem a modell önbevallásából (`bizonyossag_szamol`).
            "logprobs": True,
            "top_logprobs": 1,
        }
        req = urllib.request.Request(
            self.szolgaltato.url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.szolgaltato.timeout_masodperc) as resp:
                valasz = json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            self.utolso_hiba = f"Ollama nem elérhető: {exc}"
            _LOG.warning(self.utolso_hiba)
            return {"eszkoz": "nincs", "parameterek": {}, "bizonyossag": {}}

        tartalom = valasz.get("message", {}).get("content", "")
        try:
            ertelmezes = json.loads(tartalom)
        except json.JSONDecodeError as exc:
            self.utolso_hiba = f"JSON parse hiba: {exc} — nyers: {tartalom[:200]!r}"
            _LOG.warning(self.utolso_hiba)
            return {"eszkoz": "nincs", "parameterek": {}, "bizonyossag": {}}

        if not isinstance(ertelmezes, dict) or "eszkoz" not in ertelmezes:
            self.utolso_hiba = f"Váratlan alak a modell válaszában: {ertelmezes!r}"
            _LOG.warning(self.utolso_hiba)
            return {"eszkoz": "nincs", "parameterek": {}, "bizonyossag": {}}

        ertelmezes.setdefault("parameterek", {})
        ertelmezes["bizonyossag"] = bizonyossag_szamol(valasz.get("logprobs"), ertelmezes)
        return ertelmezes

    def valtozas_elemzes(self, mondat: str, megorzott_parameterek: dict) -> dict | None:
        """**Mi változott?** — a modell egyetlen, szigorúan zárt
        feladata a kaszkádban (`kaszkad.py`, ADR-016): megmondja, hogy a
        beszélgetés eddigi, MEGŐRZÖTT paramétereiből melyiket tartja meg
        a mondat, és melyiket engedi el.

        A kimenet kizárólag **mezőnevek** két listája — a modell SOSEM
        ad értéket. Emiatt nem is tud rossz boltot vagy dátumot
        hallucinálni: az értékek továbbra is a determinisztikus
        parserből, illetve a zárt katalógusból jönnek. Ez a szűk szerep
        teszi ellenőrizhetővé a hozzájárulását.

        A választható mezőnevek halmaza a ténylegesen meglévő
        kontextuskulcsokra szűkül (`enum`), tehát olyan mezőt sem tud
        megnevezni, ami nincs is a kontextusban.

        Visszatérési érték: `{"megtart": [...], "elenged": [...]}`, vagy
        `None`, ha nincs mit elemezni / a hívás nem sikerült (ilyenkor a
        hívó a szabály-alapú viselkedésnél marad)."""
        self.utolso_hiba = None
        kulcsok = sorted(k for k in megorzott_parameterek if k != "session_id")
        if not kulcsok:
            return None

        sema = {
            "type": "object",
            "properties": {
                "elenged": {
                    "type": "array",
                    "items": {"type": "string", "enum": kulcsok},
                },
            },
            "required": ["elenged"],
            "additionalProperties": False,
        }
        # A megfogalmazás mérésből származik: az első változat ("melyik
        # adat nem érvényes már?") a modellt túl-elengedésre vitte —
        # minden olyan mezőt eldobott, amit a mondat NEM EMLÍTETT, nem
        # csak amit ELLENTMONDOTT neki. Emiatt a "bármikor a jövő héten"
        # (ami a dátumot változtatja) a boltot is eldobta. A kimondott
        # alapszabály + a két eset szembeállítása ezt a hibaosztályt
        # célozza, nem egy-egy konkrét mondatot.
        prompt = (
            "Egy foglalási beszélgetés eddig ezeket tudta a vásárlóról:\n"
            + "\n".join(f"- {k}: {megorzott_parameterek[k]}" for k in kulcsok)
            + "\n\nA vásárló új mondata: "
            + mondat
            + "\n\nVedd sorra a fenti adatokat egyenként. Egy adatot akkor "
            "sorolj fel, ha a mondat AZ ADOTT ADATRÓL szól, és mást kér, mint "
            "ami fent szerepel (akár konkrét másikat, akár azt, hogy mindegy). "
            "Ha a mondat nem erről az adatról szól, hagyd ki.\n\n"
            "Példa a gondolatmenetre: ha a mondat egy másik napról szól, akkor "
            "a dátum szerepel a listában, a bolt viszont nem — a mondat nem a "
            "boltról szólt."
        )
        payload = {
            "model": self.szolgaltato.modell,
            "messages": [{"role": "user", "content": prompt}],
            "format": sema,
            "stream": False,
            "think": False,
            "options": {"temperature": 0},
        }
        req = urllib.request.Request(
            self.szolgaltato.url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.szolgaltato.timeout_masodperc) as resp:
                valasz = json.loads(resp.read().decode("utf-8"))
            eredmeny = json.loads(valasz.get("message", {}).get("content", ""))
        except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
            self.utolso_hiba = f"változás-elemzés sikertelen: {exc}"
            _LOG.warning(self.utolso_hiba)
            return None

        if not isinstance(eredmeny, dict):
            self.utolso_hiba = f"Váratlan alak a változás-elemzésben: {eredmeny!r}"
            return None

        # Védőháló: a zárt halmazon kívüli mezőnevet eldobjuk, akkor is,
        # ha a séma elvileg kizárta.
        elenged = [m for m in (eredmeny.get("elenged") or []) if m in kulcsok]
        return {"megtart": [k for k in kulcsok if k not in elenged], "elenged": elenged}

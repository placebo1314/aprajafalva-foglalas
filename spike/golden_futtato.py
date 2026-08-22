"""Golden set futtató — M-1 spike (roadmap.md, M-1). ELDOBHATÓ KÓD.

Nem a mag/ vagy az asszisztens/ része, nem lesz belőle alap — csak a
spike mérésére való (lásd docs/roadmap.md, M-1: "A spike kódja eldobható").

A pontozás, a betöltés, a jelentés és a `--ertelmezo szabaly` mód (a
determinisztikus alapvonal) a `tests/golden/futtato.py`-ból jön — az a
TARTÓS modul (M3), amit `python feladat.py golden` is hív. Ez a fájl NEM
másolja azt a logikát, csak importálja, és ráépíti az LLM-specifikus
részt (Ollama-hívás, promptok, séma-kényszer a structured outputhoz) —
ez utóbbi valóban eldobható, csak méréshez kell.

Két mód:

- `--ertelmezo llm --modell <NÉV>` (alapértelmezett): minden esetre
  meghívja a megadott Ollama modellt structured outputtal (Ollama
  `format` paraméter JSON-sémával), az {eszkoz, parameterek} alakra
  kényszerítve. A `most` mezőt (meta.most_alapertelmezett) a promptban
  adja át. **Többfordulós (alkudozás) esetet NEM támogat** — ezeket
  kihagyja, mert a több forduló közti kontextusvitelt (kötött
  dekódolással, egy Ollama-hívásonként) itt nem éri meg modellezni; a
  determinisztikus alapvonal (`--ertelmezo szabaly`) ezt támogatja.
- `--ertelmezo szabaly`: nincs modellhívás — a `tests/golden/futtato.py::
  szabaly_hivo`-t hívja, ami az `assistant/interpreter/
  rule_based.py::SzabalyAlapuErtelmezo`-t futtatja közvetlenül, egy- és
  többfordulós esetekkel egyaránt. Ez adja meg, mit tud a rendszer LLM
  NÉLKÜL — ez az alapvonal, ami fölé egy jövőbeli LLM-es értelmezőnek
  kerülnie kell (roadmap M4).

A `--json`-nal mentett fájl minden esethez elmenti a nyers kimenetet is
(`nyers_kimenet`), nem csak az `indoklas` szöveget — enélkül egy bukott
eset utólag nem elemezhető (lásd korábbi eredmény-fájlok korlátját).

Használat:
    python spike/golden_futtato.py --modell qwen3.5:9b
    python spike/golden_futtato.py --modell qwen3.5:4b --json eredmeny.json
    python spike/golden_futtato.py --ertelmezo szabaly --json alapvonal.json
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

GYOKER = Path(__file__).resolve().parents[1]
# `python spike/golden_futtato.py`-ként futtatva a script saját könyvtára
# kerül a sys.path elejére, nem a projekt gyökere — a `tests.golden.futtato`
# és az `assistant.interpreter` importhoz ez kell (ugyanaz a minta, mint
# `spike/hun_date_meres.py`-ban).
sys.path.insert(0, str(GYOKER))

from tests.golden.futtato import (  # noqa: E402
    betolt,
    fut,
    jelent,
    szabaly_hivo,
)

OLLAMA_URL = "http://localhost:11434/api/chat"

# Zárt halmazok — lásd .claude/skills/eszkoz-szerzodes/SKILL.md ("Zárt
# halmazok mindenhol, ahol lehet"). A mért futásokban (spike/EREDMENY.md)
# visszatérő hiba volt a bolt_id elgépelése (pl. "ugyfogyi" az "ugyifogyi"
# helyett) és kitalált eszköznév (pl. "boltoz", "bolts_info") — ezek a séma
# szintjén, kötött dekódolással strukturálisan kizárhatók, nem a modell
# helyesírásán múlnak.
ESZKOZOK = [
    "szabad_idopontok",
    "bolt_info",
    "foglalas_lemondas",
    "foglalas_athelyezes",
    "visszakerdez",
    "nincs",
]
BOLT_AZONOSITOK = ["szundi", "ugyifogyi", "torpilla"]
# A golden setben (tests/golden/nyelvi_alap.yaml) és az eszkoz-szerzodes
# skillben eddig megjelent szolgáltatás-azonosítók. Ez NEM állítottan a
# teljes katalógus — a valódi lista a mag/ torzsadat_repo-jában van, amit a
# spike (CLAUDE.md 3. invariáns szellemében is) nem importál. Ha új
# szolgáltatás kerül a golden setbe, ezt a listát bővíteni kell.
SZOLGALTATAS_AZONOSITOK = ["kis_petarda", "nagy_petarda", "nagy_orom"]
NAPSZAKOK = ["reggel", "delelott", "delutan", "este", "barmikor"]

FORMAT_SEMA = {
    "type": "object",
    "properties": {
        "eszkoz": {"type": "string", "enum": ESZKOZOK},
        "parameterek": {
            "type": "object",
            "properties": {
                # A négy zárt halmazú mező, ahogy a spike/EREDMENY.md kérte.
                "bolt_id": {"type": "string", "enum": BOLT_AZONOSITOK},
                "szolgaltatas_id": {"type": "string", "enum": SZOLGALTATAS_AZONOSITOK},
                "napszak": {"type": "string", "enum": NAPSZAKOK},
                # A többi mező NEM zárt halmaz (dátum, kód stb.), de itt is
                # fel kell sorolni őket explicit. Egy első próbafutás (lásd
                # spike/EREDMENY.md, "séma-regresszió") megmutatta, hogy ha
                # a "properties" listában CSAK a zárt halmazú mezők
                # szerepelnek (additionalProperties nélkül), az Ollama
                # structured-output grammarja a gyakorlatban úgy
                # viselkedett, mintha additionalProperties hallgatólagosan
                # false lenne: a modell egyetlen futásban sem adott vissza
                # datum_tol/datum_ig/foglalasi_kod/stb. mezőt, holott
                # korábban (séma-kényszer nélkül) rendszeresen megadta
                # őket. Nem izoláltuk, hogy önmagában az explicit
                # "additionalProperties": True elég lett volna-e — a
                # biztonság kedvéért minden ismert mezőt fel is soroltunk.
                "datum_tol": {"type": "string"},
                "datum_ig": {"type": "string"},
                "datum": {"type": "string"},
                "mit": {"type": "string"},
                "preferalt_ora": {"type": "integer"},
                "foglalasi_kod": {"type": "string"},
                "uj_datum": {"type": "string"},
                "hianyzo_mezo": {"type": "string"},
                "megorzott_parameterek": {"type": "object"},
            },
            "additionalProperties": True,
        },
    },
    "required": ["eszkoz", "parameterek"],
}

RENDSZER_PROMPT = """Te az Aprajafalva foglalási asszisztens értelmező rétege vagy.
A vásárló magyar mondatát egyetlen eszközhívássá alakítod. Kizárólag a
megadott JSON-sémának megfelelő objektumot adj vissza:
{{"eszkoz": "...", "parameterek": {{...}}}}

Elérhető eszközök:
- szabad_idopontok(bolt_id, szolgaltatas_id?, datum_tol, datum_ig, napszak, preferalt_ora?)
  napszak egyike: reggel, delelott, delutan, este, barmikor
- bolt_info(bolt_id, mit, datum?)  — mit egyike: nyitvatartas, cim, idotartam
- foglalas_lemondas(foglalasi_kod)
- foglalas_athelyezes(foglalasi_kod, uj_datum?)
- visszakerdez(hianyzo_mezo, megorzott_parameterek?)  — ha egy kritikus mező hiányzik
  a foglaláshoz/kereséshez (pl. melyik bolt), és a meglévő adatot a
  megorzott_parameterek alá kell tenni, nem elveszíteni
- nincs  — ha a kérés NEM foglalással/bolttal kapcsolatos (pl. időjárás), vagy
  olyat kérdez, amire nincs engedélyezett tényválasz (pl. ár)

Boltok: szundi (altató), ugyifogyi (petárda), torpilla (öröm/boldogság).
A "most" időpont, amihez a relatív dátumokat (holnap, jövő hét stb.)
viszonyítsd: {most}

Dátumformátum — KÉT KÜLÖNBÖZŐ alak, ne keverd őket:
- szabad_idopontok(datum_tol, datum_ig): mindig teljes ISO-8601 UTC
  időbélyeg, pl. "2026-08-18T00:00:00Z".
- bolt_info(datum): csak a naptári nap, idő nélkül, pl. "2026-08-22" —
  NE tégy hozzá óra/perc/másodperc részt vagy "Z" jelölést.

Csak a JSON objektumot add vissza, semmi mást, gondolkodást ne írj ki."""


def llm_hivo(modell: str, gondolkodas: bool, timeout: int = 180):
    """`HivoFuggveny`-t ad (lásd `tests/golden/futtato.py`) — egy Ollama
    chat hívás, structured outputtal, esetenként. Csak egyfordulós
    `bemenet`-et fogad; ha valaki hibásan egy listát ad át (többfordulós
    eset), az AssertionError-t dob — a `main()` ezeket az eseteket előre
    kiszűri, ez csak védőháló."""

    def hivo(bemenet: str, most: str) -> tuple[dict | None, float, int, str | None]:
        assert isinstance(bemenet, str), "llm_hivo többfordulós esetet nem támogat"
        payload = {
            "model": modell,
            "messages": [
                {"role": "system", "content": RENDSZER_PROMPT.format(most=most)},
                {"role": "user", "content": bemenet},
            ],
            "format": FORMAT_SEMA,
            "stream": False,
            "think": gondolkodas,
            "options": {"temperature": 0},
        }
        kezdet = time.monotonic()
        req = urllib.request.Request(
            OLLAMA_URL,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                valasz = json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            return None, time.monotonic() - kezdet, 0, str(exc)

        telt = time.monotonic() - kezdet
        tartalom = valasz.get("message", {}).get("content", "")
        tokenszam = valasz.get("eval_count", 0)
        try:
            parsed = json.loads(tartalom)
        except json.JSONDecodeError as exc:
            return None, telt, tokenszam, f"JSON parse hiba: {exc} — nyers: {tartalom[:200]!r}"
        return parsed, telt, tokenszam, None

    return hivo


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ertelmezo", choices=["llm", "szabaly"], default="llm")
    parser.add_argument(
        "--modell", default=None, help="Kötelező --ertelmezo llm mellett (ez az alapértelmezett)"
    )
    parser.add_argument("--json", type=Path, default=None, help="Eredmény mentése JSON-ba")
    parser.add_argument(
        "--nincs-gondolkodas",
        action="store_true",
        help="Ollama think=false — gyors, de sokkal pontatlanabb (csak --ertelmezo llm)",
    )
    args = parser.parse_args()
    if args.ertelmezo == "llm" and not args.modell:
        parser.error("--modell kötelező --ertelmezo llm mellett")

    meta, esetek = betolt()
    print(f"Betöltve: {len(esetek)} eset, meta.most = {meta['most_alapertelmezett']}")

    if args.ertelmezo == "szabaly":
        print("Értelmező: szabaly (SzabalyAlapuErtelmezo, nincs modellhívás)\n")
        from assistant.interpreter.rule_based import SzabalyAlapuErtelmezo

        cimke = "szabaly-alapu"
        hivo = szabaly_hivo(SzabalyAlapuErtelmezo())
        futtatando = esetek
    else:
        print(f"Modell: {args.modell}  (gondolkodás: {'ki' if args.nincs_gondolkodas else 'be'})\n")
        cimke = args.modell
        hivo = llm_hivo(args.modell, gondolkodas=not args.nincs_gondolkodas)
        futtatando = [e for e in esetek if not e.tobbfordulos]
        kihagyva = len(esetek) - len(futtatando)
        if kihagyva:
            print(
                f"({kihagyva} többfordulós eset kihagyva — llm_hivo egyfordulós, "
                "lásd modul docstring)\n"
            )

    eredmenyek = fut(meta, futtatando, hivo)
    osszefoglalo = jelent(cimke, meta, eredmenyek)

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
                            "tokenszam": er.tokenszam,
                            "hiba": er.hiba,
                            "nyers_kimenet": er.nyers_kimenet,
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

    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())

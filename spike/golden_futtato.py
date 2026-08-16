"""Golden set futtató — M-1 spike (roadmap.md, M-1). ELDOBHATÓ KÓD.

Nem a mag/ vagy az asszisztens/ része, nem lesz belőle alap — csak a
spike mérésére való (lásd docs/roadmap.md, M-1: "A spike kódja eldobható").

Beolvassa a tesztek/golden/nyelvi_alap.yaml-t, minden esetre meghívja a
megadott Ollama modellt structured output-tal (Ollama `format` paraméter
JSON-sémával), az {eszkoz, parameterek} alakra kényszerítve. A `most`
mezőt (meta.most_alapertelmezett) a promptban adja át.

Kiértékelés: pontos JSON-egyenlőség a `varhato`-val, `reszleges_elfogadas`
részleges pontszámmal, `megorzott_parameterek` ellenőrzése visszakérdezés
esetén, `tilos` minták tiltása. A kimenet címkénként (minden `cimkek`
elem) ÉS rétegenként (a `meta.kuszobok` szerinti réteg-küszöbökkel
összevetve) bontva jelent.

Használat:
    python spike/golden_futtato.py --modell qwen3.5:9b
    python spike/golden_futtato.py --modell qwen3.5:4b --json eredmeny.json
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

import yaml

GYOKER = Path(__file__).resolve().parents[1]
GOLDEN_UTVONAL = GYOKER / "tesztek" / "golden" / "nyelvi_alap.yaml"
OLLAMA_URL = "http://localhost:11434/api/chat"

FORMAT_SEMA = {
    "type": "object",
    "properties": {
        "eszkoz": {"type": "string"},
        "parameterek": {"type": "object"},
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

Dátumformátum a parameterek-ben mindig ISO-8601 UTC: "2026-08-18T00:00:00Z".
Csak a JSON objektumot add vissza, semmi mást, gondolkodást ne írj ki."""


@dataclass
class Eset:
    id: str
    bemenet: str
    varhato: dict
    cimkek: list[str]
    reszleges_elfogadas: dict | None = None
    tilos: list[str] = field(default_factory=list)

    @property
    def reteg(self) -> str:
        return self.cimkek[0] if self.cimkek else "cimke_nelkul"


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
        )
        for e in adat["esetek"]
    ]
    return meta, esetek


def modell_hivas(
    modell: str, bemenet: str, most: str, timeout: int = 180, gondolkodas: bool = True
) -> tuple[dict | None, float, int, str | None]:
    """Egy Ollama chat hívás, structured outputtal.

    `gondolkodas`: az Ollama `think` mezője. Hibrid reasoning modelleknél
    (pl. qwen3.5) ez a legfontosabb változó a mérésben — kikapcsolva
    sokszorosára gyorsul a válasz, de a mért pontosság is összeomlik (lásd
    spike-eredmények: qwen3.5:4b gondolkodással 40,9%/66,9s, gondolkodás
    nélkül 18,2%/4,4s). Explicit kell küldeni, nem szabad a mezőt kihagyni:
    kihagyva a modell néha kontrollálatlan gondolkodásba fut (megfigyelt
    eset: ~7680 tokenes válasz, JSON parse hiba a séma helyett).

    Visszaadja: (parsed_json | None, telt_masodperc, kimeneti_tokenszam,
    hiba_uzenet | None).
    """
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


def _reszhalmaz(kicsi: dict, nagy: dict) -> bool:
    return all(nagy.get(k) == v for k, v in kicsi.items())


def _tilos_ellenorzes(eset: Eset, kimenet_param: dict) -> str | None:
    if "kitalalt_datum" in eset.tilos:
        megorzott = eset.varhato.get("megorzott_parameterek") or {}
        for kulcs in ("datum_tol", "datum_ig"):
            if kulcs in kimenet_param and kulcs not in megorzott:
                return "kitalalt_datum — a modell dátumot adott meg, ahol nem volt rá elég infó"
    if "kitalalt_ar" in eset.tilos:
        if any("ar" in str(k).lower() for k in kimenet_param):
            return "kitalalt_ar — a modell árat adott meg, holott ez nem engedélyezett tényválasz"
    return None


def kiertekel(eset: Eset, kimenet: dict | None) -> tuple[float, str]:
    """(pontszám 0..1, indoklás)."""
    if kimenet is None or not isinstance(kimenet, dict):
        return 0.0, "nincs értelmezhető JSON kimenet"

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


def fut(
    modell: str, meta: dict, esetek: list[Eset], gondolkodas: bool = True
) -> list[EsetEredmeny]:
    most = meta["most_alapertelmezett"]
    eredmenyek = []
    for eset in esetek:
        kimenet, telt, tokenszam, hiba = modell_hivas(
            modell, eset.bemenet, most, gondolkodas=gondolkodas
        )
        pontszam, indoklas = kiertekel(eset, kimenet)
        if hiba:
            indoklas = f"{indoklas} [hívási hiba: {hiba}]"
        eredmenyek.append(EsetEredmeny(eset, pontszam, indoklas, telt, tokenszam, hiba))
        print(f"  {eset.id:20s} {pontszam:.1f}  {indoklas[:70]}")
    return eredmenyek


def jelent(modell: str, meta: dict, eredmenyek: list[EsetEredmeny]) -> dict:
    print(f"\n=== {modell} — összesítés ===\n")

    # Címkénkénti bontás — MINDEN cimke, nem csak a réteg-cimke.
    cimke_pontok: dict[str, list[float]] = defaultdict(list)
    for er in eredmenyek:
        for cimke in er.eset.cimkek:
            cimke_pontok[cimke].append(er.pontszam)

    print("Címkénkénti pontosság:")
    cimke_jelentes = {}
    for cimke in sorted(cimke_pontok):
        pontok = cimke_pontok[cimke]
        atlag = sum(pontok) / len(pontok)
        cimke_jelentes[cimke] = {"atlag": atlag, "n": len(pontok)}
        print(f"  {cimke:28s} {atlag:6.1%}  (n={len(pontok)})")

    # Réteg-bontás a kuszobok szerint (az első cimke = réteg).
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

    idok = [er.telt_masodperc for er in eredmenyek if er.hiba is None]
    tokenek = [er.tokenszam for er in eredmenyek if er.hiba is None and er.tokenszam]
    if idok:
        print(f"\nVálaszidő (ezen a futáson, szekvenciálisan): átlag {sum(idok) / len(idok):.2f}s")
    hibaszam = sum(1 for er in eredmenyek if er.hiba)
    if hibaszam:
        print(f"Hívási hibák: {hibaszam}/{len(eredmenyek)}")

    return {
        "modell": modell,
        "osszesitett": osszesitett,
        "legrosszabb_reteg": legrosszabb_reteg,
        "legrosszabb_ertek": legrosszabb_ertek if legrosszabb_reteg else None,
        "cimkek": cimke_jelentes,
        "retegek": reteg_jelentes,
        "hibaszam": hibaszam,
        "n": len(eredmenyek),
        "atlagos_tokenszam": (sum(tokenek) / len(tokenek)) if tokenek else None,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--modell", required=True)
    parser.add_argument("--json", type=Path, default=None, help="Eredmény mentése JSON-ba")
    parser.add_argument(
        "--nincs-gondolkodas",
        action="store_true",
        help="Ollama think=false — gyors, de a mérésünk szerint sokkal pontatlanabb",
    )
    args = parser.parse_args()

    meta, esetek = betolt()
    print(f"Betöltve: {len(esetek)} eset, meta.most = {meta['most_alapertelmezett']}")
    print(f"Modell: {args.modell}  (gondolkodás: {'ki' if args.nincs_gondolkodas else 'be'})\n")

    eredmenyek = fut(args.modell, meta, esetek, gondolkodas=not args.nincs_gondolkodas)
    osszefoglalo = jelent(args.modell, meta, eredmenyek)

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

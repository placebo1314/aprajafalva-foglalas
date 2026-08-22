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
GOLDEN_UTVONAL = GYOKER / "tests" / "golden" / "nyelvi_alap.yaml"

# HivoFuggveny: (bemenet, most) -> (kimenet | None, telt_masodperc,
# tokenszam, hiba_uzenet | None). A `bemenet` egy mondat VAGY egy
# mondatlista (többfordulós/alkudozás eset) — ugyanaz az alak a
# determinisztikus és egy jövőbeli LLM-hívónak is (lásd
# `spike/golden_futtato.py::llm_hivo`).
HivoFuggveny = Callable[[str | list[str], str], tuple[dict | None, float, int, str | None]]


@dataclass
class Eset:
    id: str
    bemenet: str | list[str]
    varhato: dict
    cimkek: list[str]
    reszleges_elfogadas: dict | None = None
    tilos: list[str] = field(default_factory=list)
    # Ez az eset olyan képességet mér, amit a determinisztikus réteg
    # nem tud (pl. a szándék kemény részének elengedése) — a
    # determinisztikus regressziós védőháló kihagyja, a mérés nem.
    igenyel_llm: bool = False

    @property
    def reteg(self) -> str:
        return self.cimkek[0] if self.cimkek else "cimke_nelkul"

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
            igenyel_llm=bool(e.get("igenyel_llm", False)),
        )
        for e in adat["esetek"]
    ]
    return meta, esetek


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
    nyers_kimenet: dict | None = None


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
    forduló eredménye — a `kiertekel()` erre a `varhato`-t veti."""
    from assistant.interpreter import ErtelmezesKontextus
    from assistant.orchestrator import kovetkezo_kontextus

    def hivo(bemenet: str | list[str], most: str) -> tuple[dict | None, float, int, str | None]:
        kezdet = time.monotonic()
        fordulok = bemenet if isinstance(bemenet, list) else [bemenet]
        megorzott: dict = {}
        kimenet: dict | None = None
        try:
            for mondat in fordulok:
                kontextus = ErtelmezesKontextus(megorzott_parameterek=dict(megorzott))
                kimenet = ertelmezo.ertelmez(mondat, most=most, kontextus=kontextus)
                megorzott = kovetkezo_kontextus(megorzott, kimenet)
        except Exception as exc:  # noqa: BLE001 - a mérés szempontjából a kivétel is bukás
            return None, time.monotonic() - kezdet, 0, str(exc)
        return kimenet, time.monotonic() - kezdet, 0, None

    return hivo


def fut(meta: dict, esetek: list[Eset], hivo: HivoFuggveny) -> list[EsetEredmeny]:
    most = meta["most_alapertelmezett"]
    eredmenyek = []
    for eset in esetek:
        kimenet, telt, tokenszam, hiba = hivo(eset.bemenet, most)
        pontszam, indoklas = kiertekel(eset, kimenet)
        if hiba:
            indoklas = f"{indoklas} [hívási hiba: {hiba}]"
        eredmenyek.append(EsetEredmeny(eset, pontszam, indoklas, telt, tokenszam, hiba, kimenet))
        print(f"  {eset.id:20s} {pontszam:.1f}  {indoklas[:70]}")
    return eredmenyek


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

    idok = [er.telt_masodperc for er in eredmenyek if er.hiba is None]
    if idok:
        print(f"\nVálaszidő (ezen a futáson, szekvenciálisan): átlag {sum(idok) / len(idok):.2f}s")
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
        "n": len(eredmenyek),
    }


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
    parser.add_argument("--json", type=Path, default=None, help="Eredmény mentése JSON-ba")
    args = parser.parse_args(argv)

    meta, esetek = betolt()
    print(f"Betöltve: {len(esetek)} eset, meta.most = {meta['most_alapertelmezett']}")

    reteg_szamlalo: dict[str, int] = {}
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

            print(f"Értelmező: {args.ertelmezo} (modell={szolgaltato.modell})\n")
            alap_hivo = ertelmezo_hivo(kaszkad)

            def hivo(bemenet, most, _alap=alap_hivo, _kaszkad=kaszkad):
                eredmeny = _alap(bemenet, most)
                reteg_szamlalo[_kaszkad.utolso_reteg] = (
                    reteg_szamlalo.get(_kaszkad.utolso_reteg, 0) + 1
                )
                return eredmeny

    eredmenyek = fut(meta, esetek, hivo)
    osszefoglalo = jelent(args.ertelmezo, meta, eredmenyek)
    if reteg_szamlalo:
        print(
            "\nRéteg-megoszlás (melyik oldotta meg, utolsó forduló): "
            + ", ".join(f"{r}={n}" for r, n in sorted(reteg_szamlalo.items()))
        )

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

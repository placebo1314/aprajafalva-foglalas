"""NAPLÓ-ELEMZŐ — a próba-napló (`naplo/probak.jsonl`) összesítése.

    python feladat.py naplo
    python feladat.py naplo --utolso 50
    python feladat.py naplo --golden 17

Mit ad:

- **fordulószám** és időszak,
- **réteg-megoszlás** (kapuőr / szabály / llm — ki oldotta meg),
- **átlag és p95 válaszidő**, a blueprint 12. szakasz 15 s keretéhez mérve,
- **bizonyosság-eloszlás** mezőnként, sávokra bontva,
- **leggyakoribb hibaminták** — zárt detektor-készlet, l. lent.

## Miért van erre külön eszköz

A golden set azt méri, amire SZÁMÍTUNK; a napló azt rögzíti, ami
TÉNYLEGESEN történt egy próbálgatás közben. A kettő nem ugyanaz, és a
napló a hasznosabb, amikor azt kérdezzük, hogy "mi megy rosszul" —
csak épp olvashatatlan nyers JSONL-ként, ezért eddig senki nem nézte
végig. Ez a modul teszi átnézhetővé.

## A hibaminták — zárt készlet, nem heurisztika

Egy "hibaminta" itt nem azt jelenti, hogy a rendszer HIBÁZOTT (azt a
naplóból nem lehet megállapítani, ahhoz tudni kellene a helyes
választ). Azt jelenti, hogy a forduló olyan MINTÁZATBA esett, ami
tapasztalat szerint elégedetlen vásárlót jelez. Mindegyik detektor
egyetlen, ellenőrizhető feltétel:

| Minta | Feltétel | Miért gyanús |
|---|---|---|
| `ismetelt_visszakerdezes` | egymás után ugyanarra a mezőre kérdeztünk | körbe futunk |
| `elharitas` | `valasz_tipus == "elutasitas"` | a kapuőr zárt — okonként bontva |
| `eszkoz_hiba` | `valasz_tipus == "eszkoz_hiba"` | üres eredmény vagy hiba |
| `kiut` | `valasz_tipus == "kiut"` | a rendszer maga adta fel |
| `csendes_tartalek` | `reteg == "szabaly"`, de volt modell | az Ollama elhalt, észrevétlenül |
| `alacsony_bizonyossag` | kritikus mező a küszöb alatt | a modell tippelt |
| `ismetelt_bemenet` | ugyanaz a mondat közvetlenül újra | a vásárló nem kapott választ |
| `lassu_fordulo` | a válaszidő a 15 s keret felett | a keretet sérti |

## Golden-eset konverter

`--golden <sorszám>` egy naplósorból golden teszteset-vázat ír YAML-ben,
a `varhato` mezőt **üresen hagyva**. Ez szándékos, és a golden-set
skill szabálya: *"Ne a modell kimenetéből írj tesztesetet"* — a helyes
választ embernek kell beírnia, MIELŐTT mérünk. A konverter csak a
gépelést veszi le, a döntést nem.

A kiírt eset a NAPLÓBÓL jön, ami már redaktált (`privacy/redakcio`) —
tehát a bemenetben `<TELEFON>` áll, nem telefonszám. Ha egy ilyen eset
bekerül a halmazba, a redaktált alak lesz benne, és ez így helyes:
nyers személyes adat verziókezelt fájlba sem kerülhet.
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter, defaultdict
from pathlib import Path

GYOKER = Path(__file__).resolve().parents[1]
if str(GYOKER) not in sys.path:
    sys.path.insert(0, str(GYOKER))

# A blueprint 12. szakasz kerete — fordulónkénti válaszidő felső határa.
KERET_MASODPERC = 15.0

# A bizonyosság-eloszlás sávjai. A két belső határ NEM önkényes: pontosan
# az orchestrator küszöbei (`BizonyossagKuszobok`: kritikus mező 0,6,
# eszköz 0,7) — így a hisztogramról LEOLVASHATÓ, hány forduló esett
# ténylegesen visszakérdezésbe, nem csak az, hogy "alacsony volt".
SAVOK = (
    (0.0, 0.6, "0,0–0,6  (kritikus mező küszöb ALATT)"),
    (0.6, 0.7, "0,6–0,7  (eszköz küszöb ALATT)"),
    (0.7, 1.01, "0,7–1,0  (átmegy)"),
)


def _p95(ertekek: list[float]) -> float | None:
    if not ertekek:
        return None
    rendezett = sorted(ertekek)
    return rendezett[min(len(rendezett) - 1, int(len(rendezett) * 0.95))]


def hibamintak(sorok: list[dict]) -> dict[str, list[int]]:
    """`{minta_neve: [sorszámok]}` — l. modul docstring táblázata.

    A sorszám 1-alapú, hogy közvetlenül átadható legyen a
    `--golden <sor>` konverternek."""
    talalatok: dict[str, list[int]] = defaultdict(list)
    elozo_mezo: str | None = None
    elozo_bemenet: str | None = None

    for i, sor in enumerate(sorok, start=1):
        tipus = sor.get("valasz_tipus")
        parameterek = sor.get("parameterek") or {}
        mezo = parameterek.get("hianyzo_mezo") if tipus == "visszakerdezes" else None

        if mezo is not None and mezo == elozo_mezo:
            talalatok["ismetelt_visszakerdezes"].append(i)
        if tipus == "elutasitas":
            talalatok[f"elharitas:{sor.get('kapuor_ok') or 'ismeretlen'}"].append(i)
        if tipus == "eszkoz_hiba":
            talalatok[f"eszkoz_hiba:{sor.get('uzenet_kulcs') or 'ismeretlen'}"].append(i)
        if tipus == "kiut":
            talalatok["kiut"].append(i)

        # CSENDES TARTALÉK: a `szabaly` réteg önmagában nem hiba (a
        # gombnyomásos út és a zárt válaszok szándékosan oda futnak) —
        # de ha a naplóban VAN llm-es forduló is, akkor volt konfigurált
        # modell, és egy szabály-fordulónál érdemes megnézni, miért.
        if sor.get("reteg") == "szabaly" and any(s.get("reteg") == "llm" for s in sorok):
            talalatok["csendes_tartalek"].append(i)

        bizonyossag = sor.get("bizonyossag") or {}
        for kulcs in ("eszkoz", "bolt_id", "szolgaltatas_id", "datum"):
            ertek = bizonyossag.get(kulcs)
            if isinstance(ertek, int | float) and ertek < 0.7:
                talalatok[f"alacsony_bizonyossag:{kulcs}"].append(i)

        bemenet = sor.get("bemenet")
        if bemenet and bemenet == elozo_bemenet:
            talalatok["ismetelt_bemenet"].append(i)

        ido = sor.get("valaszido_masodperc")
        if isinstance(ido, int | float) and ido > KERET_MASODPERC:
            talalatok["lassu_fordulo"].append(i)

        elozo_mezo = mezo
        elozo_bemenet = bemenet

    return dict(talalatok)


def elemez(sorok: list[dict]) -> dict:
    """A teljes összesítés, nyomtatás NÉLKÜL — hogy tesztelhető legyen
    (`tests/egyseg/test_naplo_elemzo.py`), és hogy egy jövőbeli felület
    is használhassa."""
    retegek = Counter(sor.get("reteg") or "ismeretlen" for sor in sorok)
    tipusok = Counter(sor.get("valasz_tipus") or "ismeretlen" for sor in sorok)
    idok = [
        sor["valaszido_masodperc"]
        for sor in sorok
        if isinstance(sor.get("valaszido_masodperc"), int | float)
    ]

    bizonyossag_savok: dict[str, Counter] = defaultdict(Counter)
    for sor in sorok:
        for kulcs, ertek in (sor.get("bizonyossag") or {}).items():
            if ertek is None:
                bizonyossag_savok[kulcs]["nincs adat (None)"] += 1
            elif isinstance(ertek, int | float):
                for also, felso, cimke in SAVOK:
                    if also <= ertek < felso:
                        bizonyossag_savok[kulcs][cimke] += 1
                        break

    egyetertesek = Counter(
        f"{sor['egyetertes']}/3" for sor in sorok if sor.get("egyetertes") is not None
    )

    return {
        "fordulok": len(sorok),
        "elso": sorok[0].get("idobelyeg") if sorok else None,
        "utolso": sorok[-1].get("idobelyeg") if sorok else None,
        "retegek": dict(retegek),
        "valasz_tipusok": dict(tipusok),
        "valaszido": {
            "n": len(idok),
            "atlag": sum(idok) / len(idok) if idok else None,
            "p95": _p95(idok),
            "max": max(idok) if idok else None,
            "keret_felett": sum(1 for i in idok if i > KERET_MASODPERC),
        },
        "bizonyossag": {k: dict(v) for k, v in bizonyossag_savok.items()},
        "onkonzisztencia": dict(egyetertesek),
        "hibamintak": hibamintak(sorok),
    }


def jelentes(osszesites: dict) -> str:
    """Az összesítés olvasható alakja."""
    sorok: list[str] = []
    ki = sorok.append

    ki("=== PRÓBA-NAPLÓ ===\n")
    ki(f"Fordulók: {osszesites['fordulok']}")
    if osszesites["elso"]:
        ki(f"Időszak:  {osszesites['elso']} – {osszesites['utolso']}")

    ki("\n-- Réteg-megoszlás (ki oldotta meg) --")
    for reteg, darab in sorted(osszesites["retegek"].items(), key=lambda p: -p[1]):
        ki(f"  {reteg:14s} {darab:4d}  {_arany(darab, osszesites['fordulok'])}")

    ki("\n-- Válasz-típusok --")
    for tipus, darab in sorted(osszesites["valasz_tipusok"].items(), key=lambda p: -p[1]):
        ki(f"  {tipus:22s} {darab:4d}  {_arany(darab, osszesites['fordulok'])}")

    ido = osszesites["valaszido"]
    ki(f"\n-- Válaszidő (n={ido['n']}, keret: {KERET_MASODPERC:.0f} s/forduló) --")
    if ido["n"]:
        allapot = "TARTJA" if ido["atlag"] <= KERET_MASODPERC else "NEM TARTJA"
        ki(f"  átlag        {ido['atlag']:6.2f} s   [{allapot}]")
        ki(f"  p95          {ido['p95']:6.2f} s")
        ki(f"  max          {ido['max']:6.2f} s")
        ki(f"  keret felett {ido['keret_felett']:4d} forduló")
    else:
        ki("  nincs válaszidő-adat (régi naplósorok — a mező azóta került be)")

    ki("\n-- Bizonyosság-eloszlás --")
    if not osszesites["bizonyossag"]:
        ki("  nincs bizonyosság-adat")
    for mezo, savok in sorted(osszesites["bizonyossag"].items()):
        ki(f"  {mezo}:")
        for cimke, darab in sorted(savok.items()):
            ki(f"      {cimke:38s} {darab:4d}")

    if osszesites["onkonzisztencia"]:
        ki("\n-- Önkonzisztencia (egyetértés) --")
        for cimke, darab in sorted(osszesites["onkonzisztencia"].items()):
            ki(f"  {cimke:8s} {darab:4d}")

    ki("\n-- Leggyakoribb hibaminták --")
    mintak = osszesites["hibamintak"]
    if not mintak:
        ki("  Egyetlen minta sem szólalt meg.")
    for nev, sorszamok in sorted(mintak.items(), key=lambda p: -len(p[1])):
        elso_par = ", ".join(str(s) for s in sorszamok[:8])
        tovabb = " …" if len(sorszamok) > 8 else ""
        ki(f"  {nev:36s} {len(sorszamok):4d}   sorok: {elso_par}{tovabb}")

    if mintak:
        ki("\n  (A sorszám a `--golden <sor>` konverternek adható át.)")
    return "\n".join(sorok)


def _arany(darab: int, osszes: int) -> str:
    return f"{darab / osszes:5.1%}" if osszes else "—"


def golden_vaz(sor: dict, sorszam: int) -> str:
    """Egy naplósorból golden teszteset-váz, YAML-ben.

    **A `varhato` SZÁNDÉKOSAN ÜRES.** A golden-set skill szabálya: "Ne
    a modell kimenetéből írj tesztesetet" — előbb kell eldőlnie, mi a
    helyes válasz, és csak utána mérünk. Ha ez a függvény kitöltené a
    `varhato`-t a naplózott kimenettel, a teszteset azt rögzítené, amit
    a rendszer AKKOR csinált, és a mérés önmagát igazolná.

    Amit a rendszer ténylegesen adott, azt a függvény KOMMENTBEN írja
    ki — látni hasznos, elfogadni nem szabad."""
    bemenet = sor.get("bemenet") or ""
    eszkoz = sor.get("eszkoz")
    parameterek = sor.get("parameterek") or {}
    return "\n".join(
        [
            f"  # A(z) {sorszam}. naplósorból, {sor.get('idobelyeg')}.",
            "  # A `varhato` ÜRES — ide EMBERNEK kell beírnia a helyes",
            "  # választ, MIELŐTT mérünk (golden-set skill). Amit a rendszer",
            "  # akkor adott, az alább kommentben van: látni hasznos,",
            "  # elfogadni nem szabad.",
            f"  #   eszkoz:      {eszkoz}",
            f"  #   parameterek: {parameterek}",
            f"  #   réteg:       {sor.get('reteg')}",
            f"  #   bizonyosság: {sor.get('bizonyossag')}",
            f"  - id: naplo-{sorszam:04d}",
            f"    bemenet: {bemenet!r}",
            "    varhato:",
            "      eszkoz:          # TÖLTSD KI",
            "      parameterek: {}  # TÖLTSD KI",
            "    cimkek: [naplobol]",
        ]
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="A próba-napló összesítése és elemzése.")
    parser.add_argument("--utolso", type=int, default=None, help="csak az utolsó N forduló")
    parser.add_argument(
        "--golden",
        type=int,
        default=None,
        metavar="SOR",
        help="egy naplósorból golden teszteset-vázat ír (a `varhato` üresen hagyva)",
    )
    args = parser.parse_args(argv)

    from ui.vasarlo import proba_naplo_olvas

    sorok = proba_naplo_olvas(args.utolso)
    if not sorok:
        print(
            "A próba-napló üres vagy nem létezik (naplo/probak.jsonl).\n"
            "Futtasd: python feladat.py vegigjatszas — vagy nyisd meg a vásárlói felületet."
        )
        return 0

    if args.golden is not None:
        # A sorszám a TELJES naplóra vonatkozik, nem az `--utolso`
        # szeletre — különben ugyanaz a szám két futáson mást
        # jelentene.
        teljes = proba_naplo_olvas()
        if not 1 <= args.golden <= len(teljes):
            print(f"Nincs ilyen naplósor: {args.golden} (a napló {len(teljes)} sorból áll).")
            return 1
        print(golden_vaz(teljes[args.golden - 1], args.golden))
        return 0

    print(jelentes(elemez(sorok)))
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())

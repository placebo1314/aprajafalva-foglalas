"""NAPLÓ-ELEMZŐ — a próba-napló (`naplo/probak.jsonl`) összesítése.

    python feladat.py naplo
    python feladat.py naplo --utolso 50
    python feladat.py naplo --golden 17

Mit ad:

- **fordulószám** és időszak,
- **réteg-megoszlás** (kapuőr / szabály / llm — ki oldotta meg),
- **válaszidő-ELOSZLÁS** — p50, p95, átlag, max, a blueprint 12. szakasz
  kétpontos elvárásához mérve (p50 < 10 s, p95 < 25 s), **plusz a
  tendencia**: a napló első és második felének p50-e egymáshoz mérve
  (ADR-022),
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
| `csendes_tartalek` | `szabaly:tartalek`, de volt modell | az Ollama elhalt, észrevétlenül |
| `alacsony_bizonyossag` | kritikus mező a küszöb alatt | a modell tippelt |
| `ismetelt_bemenet` | ugyanaz a mondat közvetlenül újra | a vásárló nem kapott választ |
| `lassu_fordulo` | a válaszidő a **p95-elvárás** felett | ennyire egy forduló sem lóghat ki |

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

# A blueprint 12. szakasz ELOSZLÁS-elvárása (ADR-022), fordulónként. Két
# pont, mert egy szám nem tudja megkülönböztetni a „mindenre lassú" és a
# „többnyire gyors, néha kilóg" rendszert — pedig a kettő más hibát jelez
# és más javítást kíván.
P50_KERET_MASODPERC = 10.0
P95_KERET_MASODPERC = 25.0

# Ennyi fordulónál kevesebből NEM mondunk tendenciát. Egy 6 fordulós
# naplóban a „romlik" ítélet két lassabb utolsó fordulóból származna —
# az zaj, nem tendencia.
TENDENCIA_MIN_FORDULO = 10

# Ekkora RELATÍV eltérés alatt a két félidő p50-je „stabil". A küszöb
# szándékosan nagy: az Ollama futásonkénti szórása önmagában bőven
# 10-20% (l. `docs/ALLAPOT.md`, „A válaszidőről őszintén"), tehát egy
# ennél kisebb elmozdulásból tendenciát olvasni önámítás lenne.
TENDENCIA_SAVSZELESSEG = 0.20

# A bizonyosság-eloszlás sávjai. A két belső határ NEM önkényes: pontosan
# az orchestrator küszöbei (`BizonyossagKuszobok`: kritikus mező 0,6,
# eszköz 0,7) — így a hisztogramról LEOLVASHATÓ, hány forduló esett
# ténylegesen visszakérdezésbe, nem csak az, hogy "alacsony volt".
SAVOK = (
    (0.0, 0.6, "0,0–0,6  (kritikus mező küszöb ALATT)"),
    (0.6, 0.7, "0,6–0,7  (eszköz küszöb ALATT)"),
    (0.7, 1.01, "0,7–1,0  (átmegy)"),
)


def percentilis(ertekek: list[float], arany: float) -> float | None:
    """A `arany` kvantilis, a legközelebbi-rang módszerrel (nincs
    interpoláció). Ugyanaz a képlet, mint a golden futtatóban
    (`tests/golden/futtato.py`) — egy mérőszámnak egy definíciója van,
    különben a két jelentés összehasonlíthatatlan."""
    if not ertekek:
        return None
    rendezett = sorted(ertekek)
    return rendezett[min(len(rendezett) - 1, int(len(rendezett) * arany))]


def _p50(ertekek: list[float]) -> float | None:
    return percentilis(ertekek, 0.50)


def _p95(ertekek: list[float]) -> float | None:
    return percentilis(ertekek, 0.95)


def tendencia(idok: list[float]) -> dict:
    """A napló ELSŐ és MÁSODIK felének p50-je, és a kettő viszonya.

    Miért p50 és nem átlag: egyetlen kilógó forduló (egy modellhívás,
    ami éppen egy hideg cache-be futott) az átlagot egy 20 elemű
    félidőben látványosan mozgatja, a mediánt nem. A tendencia
    kérdése épp az, hogy a TIPIKUS forduló lett-e lassabb.

    Az `irany` zárt halmaz: `javul` | `romlik` | `stabil` |
    `keves_adat`. A `keves_adat` nem hibaág — azt jelenti, hogy a
    kérdésre ebből a naplóból nem lehet felelni
    (`TENDENCIA_MIN_FORDULO`)."""
    if len(idok) < TENDENCIA_MIN_FORDULO:
        return {"irany": "keves_adat", "elso_fele": None, "masodik_fele": None, "valtozas": None}
    felezo = len(idok) // 2
    elso = _p50(idok[:felezo])
    masodik = _p50(idok[felezo:])
    if not elso:
        return {"irany": "keves_adat", "elso_fele": elso, "masodik_fele": masodik, "valtozas": None}
    valtozas = (masodik - elso) / elso
    if valtozas > TENDENCIA_SAVSZELESSEG:
        irany = "romlik"
    elif valtozas < -TENDENCIA_SAVSZELESSEG:
        irany = "javul"
    else:
        irany = "stabil"
    return {
        "irany": irany,
        "elso_fele": elso,
        "masodik_fele": masodik,
        "valtozas": valtozas,
    }


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
            # `kapuor_ok` hiánya nem "ismeretlen": azt jelenti, hogy nem
            # a kapuőr hárított el, hanem a MODELL döntött úgy, hogy a
            # kérés nem foglalással kapcsolatos. A kettő külön jelenség,
            # és a napló épp arra való, hogy megkülönböztesse őket.
            talalatok[f"elharitas:{sor.get('kapuor_ok') or 'modell_dontese'}"].append(i)
        if tipus == "eszkoz_hiba":
            talalatok[f"eszkoz_hiba:{sor.get('uzenet_kulcs') or 'ismeretlen'}"].append(i)
        if tipus == "kiut":
            talalatok["kiut"].append(i)

        # CSENDES TARTALÉK: az Ollama nem elérhető, és senki nem vette
        # észre, mert a rendszer hiba nélkül átvált a determinisztikus
        # rétegre.
        #
        # **Csak a `szabaly:tartalek` réteg gyanús.** A `szabaly:*`
        # másik két értéke (gombnyomás, tényválasz-rövidzár) SZÁNDÉKOS,
        # tervezett út (`forditott_kaszkad.RETEG_*`) — az első változat
        # ezeket is jelezte, és a valódi végigjátszáson két téves
        # riasztást adott. A megkülönböztetés azóta a FORRÁSNÁL van, nem
        # itt találgatva.
        #
        # A `szabaly` (utótag nélküli) alak a RÉGI naplósorokban
        # szerepel, amikor a három ok még nem volt megkülönböztetve —
        # ezeket nem jelezzük, mert nem lehet eldönteni, melyikről volt szó.
        if sor.get("reteg") == "szabaly:tartalek" and any(s.get("reteg") == "llm" for s in sorok):
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
        if isinstance(ido, int | float) and ido > P95_KERET_MASODPERC:
            talalatok["lassu_fordulo"].append(i)

        elozo_mezo = mezo
        elozo_bemenet = bemenet

    return dict(talalatok)


# A CÉL: ennyi forduló alatt kell eljutni az első kéréstől a
# foglalásig. Nem jóslat, hanem KITŰZÖTT szám (ADR-035): az idegen
# próba 18 fordulóból foglalt, és ebből tíz olyan volt, amiben a
# rendszer nem vitte előre a beszélgetést.
UT_HOSSZ_CEL = 5

# Az első kérésnek NEM számít: a köszönés és a katalógus-kérdés a
# bevezetés, nem a foglalás útja (ADR-032). A számláló attól a
# fordulótól indul, amelyikben a vásárló ténylegesen kért valamit.
_BEVEZETO_TIPUSOK = frozenset({"koszones", "kinalat", "meta_valasz"})


def ut_hosszak(sorok: list[dict]) -> dict:
    """HÁNY FORDULÓ az első kéréstől a foglalásig, beszélgetésenként.

    **Ez a kör legfontosabb mérőszáma** (ADR-035). A réteg-megoszlás és
    a válaszidő azt mondja meg, hogy a rendszer jól dolgozik-e; ez azt,
    hogy a VÁSÁRLÓ eljut-e valahova. Az idegen próba minden fordulója
    külön-külön rendben volt — a beszélgetés egésze mégis tizennyolc
    forduló lett.

    Csak a FOGLALÁSSAL végződő beszélgetéseket számoljuk: egy félbehagyott
    menetről nem tudjuk, hány forduló KELLETT volna. A `session_id`
    nélküli, régi sorokat kihagyjuk — ott a beszélgetés határa becslés.
    """
    beszelgetesek: dict[str, list[dict]] = {}
    for sor in sorok:
        azonosito = sor.get("session_id")
        if azonosito:
            beszelgetesek.setdefault(azonosito, []).append(sor)

    hosszak: list[int] = []
    reszletek: list[dict] = []
    for azonosito, fordulok in beszelgetesek.items():
        veg = next(
            (i for i, sor in enumerate(fordulok) if sor.get("valasz_tipus") == "visszaigazolas"),
            None,
        )
        if veg is None:
            continue
        kezdet = next(
            (
                i
                for i, sor in enumerate(fordulok)
                if sor.get("valasz_tipus") not in _BEVEZETO_TIPUSOK
            ),
            0,
        )
        hossz = veg - kezdet + 1
        hosszak.append(hossz)
        reszletek.append({"session_id": azonosito, "fordulo": hossz})

    return {
        "n": len(hosszak),
        "atlag": sum(hosszak) / len(hosszak) if hosszak else None,
        "leghosszabb": max(hosszak) if hosszak else None,
        "cel_alatt": sum(1 for h in hosszak if h < UT_HOSSZ_CEL),
        "cel": UT_HOSSZ_CEL,
        "beszelgetesek": sorted(reszletek, key=lambda r: -r["fordulo"]),
    }


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

    # MELYIK MODELL és MELYIK PROMPT — fordulónként rögzítve
    # (`ui/vasarlo.py::_proba_naplo_ir`). Enélkül a napló csak azt
    # mondta meg, KI oldotta meg a fordulót; azt nem, hogy a tartalék
    # azért dolgozott-e, mert nem volt konfigurált modell, vagy mert a
    # modell nem tudta megoldani. Két különböző baj, két különböző
    # teendő. A `nincs` kulcs a régi naplósorokat is beleszámolja: ott
    # a mező nem hiányzik, csak akkor még nem létezett.
    modellek = Counter(sor.get("modell") or "nincs" for sor in sorok)
    prompt_verziok = Counter(sor.get("prompt_verzio") or "nincs" for sor in sorok)

    # ÁLLAPOTOK ÉS ÁTMENETEK (ADR-028). Az állapot-megoszlásból az
    # látszik, hol áll meg a beszélgetés (pl. sok `HIANYZO_ADAT` = sokat
    # kérdezünk vissza), az átmenetekből pedig az, milyen utakon jár
    # ténylegesen a rendszer — a tervezett állapotgép és a valóság
    # eltérése eddig sehol nem látszott.
    allapotok = Counter(sor.get("allapot") for sor in sorok if sor.get("allapot"))
    atmenetek = Counter(sor.get("atmenet") for sor in sorok if sor.get("atmenet"))

    return {
        "fordulok": len(sorok),
        "modellek": dict(modellek),
        "prompt_verziok": dict(prompt_verziok),
        "allapotok": dict(allapotok),
        "atmenetek": dict(atmenetek),
        "elso": sorok[0].get("idobelyeg") if sorok else None,
        "utolso": sorok[-1].get("idobelyeg") if sorok else None,
        "retegek": dict(retegek),
        "valasz_tipusok": dict(tipusok),
        "valaszido": {
            "n": len(idok),
            "atlag": sum(idok) / len(idok) if idok else None,
            "p50": _p50(idok),
            "p95": _p95(idok),
            "max": max(idok) if idok else None,
            "p95_keret_felett": sum(1 for i in idok if i > P95_KERET_MASODPERC),
            "tendencia": tendencia(idok),
        },
        "bizonyossag": {k: dict(v) for k, v in bizonyossag_savok.items()},
        "onkonzisztencia": dict(egyetertesek),
        "hibamintak": hibamintak(sorok),
        # AZ ÚT HOSSZA: hány forduló az első kéréstől a foglalásig
        # (ADR-035). A kör legfontosabb mérőszáma — l. `ut_hosszak`.
        "ut_hosszak": ut_hosszak(sorok),
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

    # MODELL ÉS PROMPT — közvetlenül a réteg-megoszlás alatt, mert
    # együtt olvasandó: a „szabaly:tartalek 100%" sor mást jelent, ha
    # volt konfigurált modell (elhalt szolgáltatás), és mást, ha nem
    # (be sem volt kapcsolva).
    ki("\n-- Modell és prompt (fordulónként rögzítve) --")
    for modell, darab in sorted(osszesites.get("modellek", {}).items(), key=lambda p: -p[1]):
        cimke = "nincs konfigurált modell" if modell == "nincs" else modell
        ki(f"  modell: {cimke:24s} {darab:4d}  {_arany(darab, osszesites['fordulok'])}")
    for verzio, darab in sorted(osszesites.get("prompt_verziok", {}).items(), key=lambda p: -p[1]):
        cimke = "nem futott modellhívás" if verzio == "nincs" else verzio
        ki(f"  prompt: {cimke:24s} {darab:4d}  {_arany(darab, osszesites['fordulok'])}")

    if osszesites.get("allapotok"):
        ki("\n-- Állapotok (a forduló UTÁN) és átmenetek --")
        for allapot, darab in sorted(osszesites["allapotok"].items(), key=lambda p: -p[1]):
            ki(f"  {allapot:18s} {darab:4d}  {_arany(darab, osszesites['fordulok'])}")
        for atmenet, darab in sorted(osszesites.get("atmenetek", {}).items(), key=lambda p: -p[1]):
            ki(f"    {atmenet:38s} {darab:4d}")

    ut = osszesites.get("ut_hosszak") or {}
    if ut.get("n"):
        ki("\n-- AZ ÚT HOSSZA (első kéréstől a foglalásig) --")
        ki(f"  foglalással végződő beszélgetés: {ut['n']}")
        ki(f"  átlag: {ut['atlag']:.1f} forduló     leghosszabb: {ut['leghosszabb']}")
        ki(f"  a cél alatt ({ut['cel']} forduló): {ut['cel_alatt']} / {ut['n']}")
        for reszlet in ut["beszelgetesek"][:5]:
            jel = " " if reszlet["fordulo"] < ut["cel"] else "!"
            ki(f"  {jel} {reszlet['session_id'][:8]}  {reszlet['fordulo']:2d} forduló")
    elif osszesites.get("fordulok"):
        ki("\n-- AZ ÚT HOSSZA --")
        ki("  Nincs foglalással végződő, session-azonosítóval ellátott beszélgetés.")
    ki("\n-- Válasz-típusok --")
    for tipus, darab in sorted(osszesites["valasz_tipusok"].items(), key=lambda p: -p[1]):
        ki(f"  {tipus:22s} {darab:4d}  {_arany(darab, osszesites['fordulok'])}")

    ido = osszesites["valaszido"]
    ki(
        f"\n-- Válaszidő-eloszlás (n={ido['n']}, elvárás: "
        f"p50 < {P50_KERET_MASODPERC:.0f} s, p95 < {P95_KERET_MASODPERC:.0f} s) --"
    )
    if ido["n"]:
        # A két elvárás KÜLÖN áll vagy bukik — az összevont "tartja"
        # elrejtené, hogy a rendszer a mediánon rendben van, csak a
        # farka hosszú (vagy fordítva). L. ADR-022.
        p50_allapot = "TARTJA" if ido["p50"] <= P50_KERET_MASODPERC else "NEM TARTJA"
        p95_allapot = "TARTJA" if ido["p95"] <= P95_KERET_MASODPERC else "NEM TARTJA"
        ki(f"  p50          {ido['p50']:6.2f} s   [{p50_allapot}]")
        ki(f"  p95          {ido['p95']:6.2f} s   [{p95_allapot}]")
        ki(f"  átlag        {ido['atlag']:6.2f} s")
        ki(f"  max          {ido['max']:6.2f} s")
        ki(f"  p95 felett   {ido['p95_keret_felett']:4d} forduló")
        ki("  " + tendencia_szoveg(ido["tendencia"]))
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


_TENDENCIA_SZOVEG = {
    "javul": "JAVUL",
    "romlik": "ROMLIK",
    "stabil": "stabil",
}


def tendencia_szoveg(adat: dict) -> str:
    """A tendencia egy sora. Külön függvény, mert a jelentés HÁROM
    helyről is idézhető (napló, golden futtató, dokumentum), és a
    megfogalmazásnak egy helyen kell lennie."""
    if adat["irany"] == "keves_adat":
        return f"tendencia: kevés adat (a méréshez legalább {TENDENCIA_MIN_FORDULO} forduló kell)"
    return (
        f"tendencia: első fél p50 {adat['elso_fele']:.2f} s → "
        f"második fél p50 {adat['masodik_fele']:.2f} s   "
        f"[{_TENDENCIA_SZOVEG[adat['irany']]}, {adat['valtozas']:+.0%}]"
    )


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
    parser.add_argument(
        "--fajl",
        type=Path,
        default=None,
        metavar="UTVONAL",
        help=(
            "egy ARCHIVÁLT naplót elemez (naplo/probak-20260831-195812.jsonl) "
            "a jelenlegi napló helyett"
        ),
    )
    parser.add_argument(
        "--archival",
        action="store_true",
        help=(
            "a jelenlegi naplót dátumozott néven félreteszi, és üres naplóval indul újra "
            "— mérési határ két próbasorozat közé"
        ),
    )
    args = parser.parse_args(argv)

    from ui.vasarlo import proba_naplo_archival, proba_naplo_archivumok, proba_naplo_olvas

    if args.archival:
        cel = proba_naplo_archival()
        if cel is None:
            print("Nincs mit archiválni: a napló üres vagy nem létezik (naplo/probak.jsonl).")
            return 0
        nev = cel.relative_to(GYOKER).as_posix()
        print(
            f"Archiválva: {nev}  ({len(proba_naplo_olvas(utvonal=cel))} forduló). "
            "A napló újraindult."
        )
        print(f"Az archívum elemzése:  python feladat.py naplo --fajl {nev}")
        return 0

    if args.fajl is not None and not args.fajl.exists():
        print(f"Nincs ilyen naplófájl: {args.fajl}")
        for utvonal in proba_naplo_archivumok():
            print(f"  archívum: {utvonal.relative_to(GYOKER).as_posix()}")
        return 1

    sorok = proba_naplo_olvas(args.utolso, utvonal=args.fajl)
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
        teljes = proba_naplo_olvas(utvonal=args.fajl)
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

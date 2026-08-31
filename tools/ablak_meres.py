"""A CSÚSZÓ ELŐZMÉNY-ABLAK MÉRÉSE (ADR-025) — mennyivel rövidül a
prompt egy húsz fordulós beszélgetésnél, és mibe kerül ez.

```
python -m tools.ablak_meres                 # csak hossz (nincs modellhívás)
python -m tools.ablak_meres --modell qwen3.5:9b   # valódi tokenszám + latencia
```

**Miért nem elég karaktert számolni.** A magyar szöveg tokenizálása
rossz (a spike mérése szerint subword fertility ~3, `docs/
PLATFORM_TANULSAGOK.md`), és a tokenszám az, ami a latenciát viszi, nem
a karakter. A `--modell` kapcsolóval ezért a TÉNYLEGES `prompt_eval_
count`-ot kérdezzük meg az Ollamától, egy valódi hívással — a karakteres
szám csak akkor marad, ha nincs futó modell.

**A mérési fixture egy húsz fordulós beszélgetés** (`BESZELGETES`), ami
szándékosan nem szép: a vásárló alkudozik, két keresés üresen tér
vissza, egy mezőt elenged, közben témát vált, és a végén sorszámmal
hivatkozik egy felajánlott időpontra. Ez az az alak, amiben az ablak
számít — egy négyfordulós, sima menetben nincs mit mérni.

A pontosságot NEM ez a fájl méri: arra a golden set van
(`python feladat.py golden --ertelmezo forditott`, az
`APRAJAFALVA_ABLAK_FORDULO` környezeti változóval állítva). A két mérés
külön van, mert két külön kérdés — „mennyivel rövidebb" és „romlik-e
tőle a válasz".
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
if str(GYOKER) not in sys.path:
    sys.path.insert(0, str(GYOKER))

from assistant.interpreter import KI_RENDSZER, KI_VASARLO, ErtelmezesKontextus  # noqa: E402
from assistant.interpreter import ablak as ablak_modul  # noqa: E402
from assistant.interpreter.llm_based import (  # noqa: E402
    beszelgetes_szovege,
    prompt_verzio,
    rendszerprompt,
)

MOST = "2026-08-17T09:00:00Z"  # hétfő

# HÚSZ FORDULÓ — a mérés fixture-je. Egy valódi, döcögő beszélgetés
# alakja: bolt az elején, alkudozás, két üres keresés, egy elengedett
# mező, témaváltás, és a végén sorszámos hivatkozás.
BESZELGETES: list[tuple[str, str]] = [
    (KI_VASARLO, "Jó napot, szeretnék időpontot foglalni az Ügyifogyi boltba."),
    (KI_RENDSZER, "Melyik napra keressek időpontot?"),
    (KI_VASARLO, "Kedden délelőtt lenne jó."),
    (KI_RENDSZER, "Sajnos nincs szabad időpont ebben az ablakban."),
    (KI_VASARLO, "És szerdán?"),
    (KI_RENDSZER, "Sajnos nincs szabad időpont ebben az ablakban."),
    (KI_VASARLO, "Hát jó, akkor mégis inkább csütörtökön."),
    (KI_RENDSZER, "Felajánlott időpontok: 1. csütörtök 9:00; 2. csütörtök 10:30"),
    (KI_VASARLO, "Ezek elég koraiak, nincs valami későbbi?"),
    (KI_RENDSZER, "Felajánlott időpontok: 1. csütörtök 15:00; 2. csütörtök 16:30"),
    (KI_VASARLO, "Mennyi ideig tart egyáltalán egy ilyen?"),
    (KI_RENDSZER, "A petárda tizenöt perc."),
    (KI_VASARLO, "Értem. És a nagy petárda ugyanennyi?"),
    (KI_RENDSZER, "A petárda tizenöt perc."),
    (KI_VASARLO, "Akkor mindegy melyik petárda, csak legyen hely."),
    (KI_RENDSZER, "Rendben, bármelyik petárdára keresek."),
    (KI_VASARLO, "Meddig vagytok nyitva csütörtökön?"),
    (KI_RENDSZER, "Csütörtökön 8:00 és 17:00 között tartunk nyitva."),
    (KI_VASARLO, "Jó. Akkor nézzük újra a délutánt."),
    (KI_RENDSZER, "Felajánlott időpontok: 1. csütörtök 14:00; 2. csütörtök 15:30"),
    (KI_VASARLO, "És pénteken van valami?"),
    (KI_RENDSZER, "Felajánlott időpontok: 1. péntek 11:00; 2. péntek 13:15"),
    (KI_VASARLO, "A kettő közül melyik a rövidebb várakozás?"),
    (KI_RENDSZER, "Mindkettő ugyanannyi ideig tart."),
    (KI_VASARLO, "Rendben."),
    (KI_RENDSZER, "Melyiket foglaljam?"),
    (KI_VASARLO, "Várj, előbb mondd meg, hol van pontosan a bolt."),
    (KI_RENDSZER, "Az Ügyifogyi a Gomba tér 3. alatt van."),
    (KI_VASARLO, "Az messze van a piactól?"),
    (KI_RENDSZER, "Ebben nem tudok segíteni, időpontot viszont szívesen keresek."),
    (KI_VASARLO, "Nem baj. Akkor maradjunk a pénteknél."),
    (KI_RENDSZER, "Felajánlott időpontok: 1. péntek 11:00; 2. péntek 13:15"),
    (KI_VASARLO, "Hmm."),
    (KI_RENDSZER, "Melyiket foglaljam?"),
    (KI_VASARLO, "Az elsőt majdnem, de mégse."),
    (KI_RENDSZER, "Melyiket foglaljam?"),
    (KI_VASARLO, "Van délelőtt is valami korábbi?"),
    (KI_RENDSZER, "Felajánlott időpontok: 1. péntek 9:45; 2. péntek 11:00"),
    (KI_VASARLO, "Na jó."),
    (KI_RENDSZER, "Melyiket foglaljam?"),
]

# A huszonegyedik forduló — erre mérünk. Sorszámos hivatkozás: pont az a
# fajta mondat, ami miatt az utolsó fordulóknak SZÓ SZERINT kell
# átmenniük.
MONDAT = "akkor a másodikat kérem"

# Mérendő ablakméretek. A 0 az alapvonal (nincs ablak, minden forduló
# szó szerint), a 4 az éles alapérték.
ABLAKOK = (ablak_modul.ABLAK_KI, 8, 4, 2, 1)


def promptok(fordulo: int, megorzott: dict | None = None) -> tuple[str, str]:
    """`(rendszerprompt, vásárlói üzenet)` az adott ablakmérettel — a
    teljes bemenet, ahogy a modell látja. A rendszerprompt is beleszámít:
    az összefoglaló-útmutató csak akkor megy el, ha van összefoglaló."""
    kontextus = ErtelmezesKontextus(
        megorzott_parameterek=megorzott or {}, elozmenyek=list(BESZELGETES)
    )
    eredeti = ablak_modul.fordulo_max
    ablak_modul.fordulo_max = lambda: fordulo  # type: ignore[assignment]
    try:
        beszelgetes, van_osszefoglalo = beszelgetes_szovege(kontextus, MONDAT, most=MOST)
    finally:
        ablak_modul.fordulo_max = eredeti  # type: ignore[assignment]
    rendszer = rendszerprompt(prompt_verzio(), most=MOST, van_osszefoglalo=van_osszefoglalo)
    return rendszer, beszelgetes


def _ollama_meres(rendszer: str, vasarlo: str, modell: str, url: str) -> tuple[int, float] | None:
    """`(prompt_token, masodperc)` egy valódi hívásból, vagy `None`, ha
    az Ollama nem elérhető. A tokenszám a szolgáltatótól jön
    (`prompt_eval_count`), nem becslésből: a magyar tokenizálás
    rosszabb, mint amire egy karakter/4 hüvelykujjszabály számítana."""
    payload = {
        "model": modell,
        "messages": [
            {"role": "system", "content": rendszer},
            {"role": "user", "content": vasarlo},
        ],
        "stream": False,
        "think": False,
        "options": {"temperature": 0},
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    kezdet = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            valasz = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        print(f"  (Ollama nem elérhető: {exc})")
        return None
    return int(valasz.get("prompt_eval_count") or 0), time.monotonic() - kezdet


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="A csúszó előzmény-ablak hosszmérése.")
    parser.add_argument(
        "--modell",
        default=None,
        help="Ollama modellnév — ezzel valódi tokenszám és latencia is mérhető",
    )
    parser.add_argument("--url", default="http://localhost:11434/api/chat")
    parser.add_argument("--json", type=Path, default=None, help="eredmény mentése JSON-ba")
    args = parser.parse_args(argv)

    fordulok = len(ablak_modul.fordulokra_bont(BESZELGETES))
    print(f"Fixture: {fordulok} forduló, {len(BESZELGETES)} sor. Mért mondat: {MONDAT!r}\n")

    sorok = []
    for ablak in ABLAKOK:
        rendszer, vasarlo = promptok(ablak)
        adat = {
            "ablak": ablak,
            "rendszer_karakter": len(rendszer),
            "vasarlo_karakter": len(vasarlo),
            "osszes_karakter": len(rendszer) + len(vasarlo),
        }
        if args.modell:
            meres = _ollama_meres(rendszer, vasarlo, args.modell, args.url)
            if meres is not None:
                adat["prompt_token"], adat["masodperc"] = meres
        sorok.append(adat)

    alapvonal = sorok[0]
    # KÉT rövidülést írunk ki, mert két külön kérdésre felelnek. A
    # beszélgetés-rész az, amire az ablak hat; a teljes prompt az, amit a
    # modell ténylegesen megkap — abban a rendszerprompt állandó tag, és
    # hígítja az arányt. Csak az egyiket kiírni mindkét irányban
    # félrevezetne.
    print(
        f"{'ablak':>6}  {'beszélgetés':>11}  {'ebből -':>8}  "
        f"{'teljes':>7}  {'ebből -':>8}  {'token':>7}  {'másodperc':>9}"
    )
    for adat in sorok:
        cimke = "nincs" if adat["ablak"] == ablak_modul.ABLAK_KI else str(adat["ablak"])
        adat["beszelgetes_rovidules"] = 1 - adat["vasarlo_karakter"] / alapvonal["vasarlo_karakter"]
        adat["teljes_rovidules"] = 1 - adat["osszes_karakter"] / alapvonal["osszes_karakter"]
        token = adat.get("prompt_token")
        masodperc = adat.get("masodperc")
        print(
            f"{cimke:>6}  {adat['vasarlo_karakter']:>11}  "
            f"{adat['beszelgetes_rovidules']:>7.1%}  {adat['osszes_karakter']:>7}  "
            f"{adat['teljes_rovidules']:>7.1%}  "
            f"{(token if token is not None else '—'):>7}  "
            f"{(f'{masodperc:.2f}' if masodperc is not None else '—'):>9}"
        )

    if alapvonal.get("prompt_token"):
        for adat in sorok[1:]:
            if adat.get("prompt_token"):
                nyeres = 1 - adat["prompt_token"] / alapvonal["prompt_token"]
                print(f"\nablak={adat['ablak']}: {nyeres:.1%} tokenmegtakarítás az alapvonalhoz")

    print("\n--- ablak=4, a modellnek átadott bemenet ---")
    print(promptok(ablak_modul.ALAP_FORDULO)[1])

    if args.json:
        args.json.write_text(
            json.dumps({"fordulok": fordulok, "meresek": sorok}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"\nJSON mentve: {args.json}")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())

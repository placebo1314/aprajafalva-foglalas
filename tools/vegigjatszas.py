"""Fej nélküli végigjátszás — a vásárlói felület (`ui/vasarlo.py`)
szöveges útját hajtja végig Tkinter `mainloop()` NÉLKÜL, közvetlen
metódushívásokkal.

Miért van erre külön eszköz: a felületet kézzel végigkattintani lassú és
nem reprodukálható, egy egységteszt viszont a felület helyett a
függvényeit méri. Ez a köztes lépés — a VALÓDI `VasarloApp` fut (ugyanaz
az orchestrator, ugyanaz az értelmező, ugyanaz a próba-napló), csak nincs
felhasználó és nincs eseményhurok. Ez az **önellenőrzés, mielőtt bárki
leül a felület elé**.

    python feladat.py vegigjatszas
    python feladat.py vegigjatszas --db proba.db

Amit kiír, fordulónként: a bemenet, melyik réteg oldotta meg, a felismert
eszköz és paraméterek, a válasz típusa, és a felület által ténylegesen
megjelenített mondatok. A `naplo/probak.jsonl` közben ugyanúgy telik,
mint kézi próbánál.

**Ollama nélkül is lefut**: az értelmező ilyenkor csendben a
determinisztikus rétegre esik vissza (`assistant/interpreter/__init__.py::
alapertelmezett_ertelmezo`), és a végigjátszás ugyanúgy végigmegy — a
kiírt `réteg` oszlopból látszik, melyik esetben mi történt.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

GYOKER = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(GYOKER))

from core.azonosito import new_uuid  # noqa: E402
from seed.betolt import ALAP_DB_PATH  # noqa: E402

# A végigjátszott beszélgetések. Az első nyolc a golden set `mintan_tul`
# rétegének mondatai (a felületen, nem a mérésben — itt az a kérdés, mit
# LÁT belőle a vásárló), utána öt saját próba, ami a mérésben nincs benne:
# gombnyomás utáni forduló, kapuőr, tényválasz, lemondás kód nélkül, és
# egy teljes foglalási menet.
BESZELGETESEK: list[tuple[str, list[str]]] = [
    ("vagylagos", ["Petárdázni szeretnék.", "jövő héten, vagy 28-án tudok menni?"]),
    ("üres szándék", ["Valamikor mennék, ha lehet."]),
    (
        "feltételes",
        [
            "Szeretnék időpontot a Szundiba.",
            "ha van hely szerdán, akkor az jó, ha nincs, csütörtök",
        ],
    ),
    ("indoklás mellékmondattal", ["Azért kellene délelőtt, mert délután dolgozom."]),
    ("kettős kérés", ["A Törpillánál mikor van nyitva, és tudok-e ma menni?"]),
    (
        "visszavonás",
        [
            "Petárdázni szeretnék kedden.",
            "és jövő héten péntek?",
            "mégsem, inkább maradjunk a keddnél",
        ],
    ),
    ("bizonytalan", ["Szundihoz mennék.", "talán jövő héten, még nem tudom biztosan"]),
    (
        "köznyelvi töltelék",
        ["Törpillához mennék.", "hát izé, valamikor a jövő hét elején lenne jó"],
    ),
    # -- saját próbák, a mérésen kívül --------------------------------
    ("zárt kérdés + gombnyomás", ["szeretnék időpontot holnapra", "ugyifogyi"]),
    ("kapuőr", ["Mennyibe kerül a nagy petárda?"]),
    ("tényválasz", ["Hogy néz ki a Törpilla bolt?"]),
    ("lemondás kód nélkül", ["Le szeretném mondani a foglalásomat."]),
    ("ismétlés → kiút", ["mennék", "szeretnék menni", "menni szeretnék"]),
]


def _naplo_ujdonsag(app, korabbi_hossz: int) -> tuple[list[str], int]:
    """A felület szöveges naplójának ÚJ sorai az előző mérés óta — ez az,
    amit a vásárló ténylegesen lát a képernyőn."""
    teljes = app.szo_naplo.get("1.0", "end").rstrip("\n")
    sorok = teljes.split("\n") if teljes else []
    return sorok[korabbi_hossz:], len(sorok)


def _gombfeliratok(app) -> list[str]:
    """A forduló után felkínált gombok feliratai (zárt kérdés, kiút,
    alternatíva) — a szöveges naplóban ezek nem látszanak, pedig a
    vásárló élményének a fele."""
    return [w.cget("text") for w in app.szo_gombsor.winfo_children()]


def _jelolt_gombok(app) -> list[str]:
    return [w.cget("text") for w in app.szo_jelolt_keret.winfo_children()]


def vegigjatszas(db_path: str) -> int:
    from ui.vasarlo import VasarloApp

    app = VasarloApp(db_path)
    # Nincs `mainloop()` — az ablakot el is rejtjük, hogy a végigjátszás
    # ne villantson fel semmit.
    app.withdraw()
    print(f"Adatbázis: {db_path}")
    print(f"Beosztás:  {app.idoszak}")
    print(f"Indító sor: {app.idoszak_cimke.cget('text')}")
    print(f"Értelmező: {type(app.orchestrator.ertelmezo).__name__}")
    print(f'"most" a szöveges úton: {app._most_iso()}\n')

    naplo_hossz = 0
    for cimke, mondatok in BESZELGETESEK:
        print("=" * 72)
        print(f"# {cimke}")
        app.session_id = new_uuid()  # minden beszélgetés friss kontextussal indul
        for mondat in mondatok:
            app._szo_kuldes(mondat)
            uj_sorok, naplo_hossz = _naplo_ujdonsag(app, naplo_hossz)
            ertelmezes = app.orchestrator.utolso_ertelmezes or {}
            reteg = getattr(app.orchestrator.ertelmezo, "utolso_reteg", None)
            print(f"\n  > {mondat}")
            print(f"    réteg:       {reteg}")
            print(f"    eszköz:      {ertelmezes.get('eszkoz')}")
            print(f"    paraméterek: {ertelmezes.get('parameterek')}")
            for sor in uj_sorok:
                print(f"    | {sor}")
            gombok = _gombfeliratok(app) + _jelolt_gombok(app)
            if gombok:
                print(f"    gombok:      {gombok}")
        print()

    app._close()
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Fej nélküli végigjátszás a vásárlói felületen.")
    parser.add_argument("--db", default=str(ALAP_DB_PATH), help="adatbázis útvonala")
    args = parser.parse_args(argv)
    return vegigjatszas(args.db)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())

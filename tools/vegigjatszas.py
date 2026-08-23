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

**VALÓDI foglalást hoz létre** a megadott adatbázisban (a végigjátszás
utolsó menete végigmegy a megerősítésig) — ez szándékos, mert épp azt
ellenőrzi, hogy a felület elvezet-e a foglalási kódig. A demóadaton ez
ártalmatlan: `python feladat.py seed --ujra` visszaállítja, vagy adj meg
egy külön fájlt a `--db` kapcsolóval.

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
    # Ezek szándékosan a TÖRPILLÁT célozzák: a demóadat csak oda generál
    # műszakot, tehát csak itt fut végig a tényleges keresés → ajánlat →
    # foglalás út. A fenti nyolc a nyelvi értelmezést méri, ez az ötös
    # azt, hogy a felület ténylegesen elvezet-e a foglalási kódig.
    ("zárt kérdés + gombnyomás", ["szeretnék időpontot holnapra", "torpilla"]),
    ("kapuőr", ["Mennyibe kerül a nagy petárda?"]),
    ("tényválasz", ["Hogy néz ki a Törpilla bolt?"]),
    ("lemondás kód nélkül", ["Le szeretném mondani a foglalásomat."]),
    ("ismétlés → kiút", ["mennék", "szeretnék menni", "menni szeretnék"]),
]

# A teljes foglalási menet (keresés → jelölt → megerősítés → kód) — ezt
# nem mondatlistával, hanem gombnyomásokkal kell végigvinni, ezért külön
# függvényben van (`_foglalasi_menet`).
FOGLALASI_MENET_MONDAT = "Törpillához mennék holnap"


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


def _widgetek(keret, osztaly: str) -> list:
    """Egy widgetfa MINDEN adott osztályú eleme, mélységben — a
    megerősítő gombok egy beágyazott `Frame`-ben ülnek, tehát a
    `winfo_children()` önmagában nem találná meg őket."""
    talalatok = []
    for widget in keret.winfo_children():
        if widget.winfo_class() == osztaly:
            talalatok.append(widget)
        talalatok.extend(_widgetek(widget, osztaly))
    return talalatok


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
        # Friss session ÉS friss előzmény — az `_uj_beszelgetes` mindkettőt
        # elintézi (ADR-019: az előzmény a beszélgetés bemenete, nem
        # szabad átcsordulnia a következő próbába).
        app._uj_beszelgetes()
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

    _foglalasi_menet(app)
    app._close()
    return 0


def _foglalasi_menet(app) -> None:
    """A teljes út a foglalási kódig, gombnyomásokkal — ugyanazokat a
    `command`-eket hívja, amiket egy kattintás hívna (`Button.invoke()`),
    tehát a felület valódi útját járja be, nem egy mellékbejáratot."""
    print("=" * 72)
    print("# teljes foglalási menet (keresés → jelölt → megerősítés → kód)")
    app._uj_beszelgetes()
    app._szo_kuldes(FOGLALASI_MENET_MONDAT)
    print(f"\n  > {FOGLALASI_MENET_MONDAT}")

    jeloltek = app.szo_jelolt_keret.winfo_children()
    if not jeloltek:
        print("    NINCS jelölt — a menet itt megáll (nézd meg a beosztás időszakát).")
        return
    print(f"    jelöltek:    {[w.cget('text') for w in jeloltek]}")

    jeloltek[0].invoke()  # az első időpont-gomb
    keret = app.szo_jelolt_keret
    mezok = _widgetek(keret, "TEntry")
    if not mezok:
        print("    NINCS azonosító-mező a megerősítés után — a menet megáll.")
        return
    print("    megerősítés: bekérte az azonosítót")

    mezok[0].delete(0, "end")
    mezok[0].insert(0, "proba-azonosito-123")
    igen = next((g for g in _widgetek(keret, "TButton") if "foglalom" in g.cget("text")), None)
    if igen is None:
        print("    NINCS 'Igen, foglalom' gomb — a menet megáll.")
        return
    igen.invoke()

    eredmeny = [w.cget("text") for w in _widgetek(keret, "TLabel")]
    print(f"    eredmény:    {eredmeny}")
    if app.szo_uzenet.cget("text"):
        print(f"    hibasor:     {app.szo_uzenet.cget('text')}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Fej nélküli végigjátszás a vásárlói felületen.")
    parser.add_argument("--db", default=str(ALAP_DB_PATH), help="adatbázis útvonala")
    args = parser.parse_args(argv)
    return vegigjatszas(args.db)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())

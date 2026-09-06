"""HANGPRÓBA — egyetlen mondat felolvasása, és ha nem megy, annak a
PONTOS megmondása, hogy miért (`python feladat.py hangproba`).

```
python feladat.py hangproba
python feladat.py hangproba --mondat "Holnap kilenc órakor foglaltam."
python feladat.py hangproba --csak-diagnozis      # nem játszik le semmit
python feladat.py hangproba --meres               # mennyi a csend a mondat előtt
```

**Miért van erre külön parancs.** A felolvasás eddig CSENDBEN maradt el:
a beszélhető mód (ADR-023) a szöveget formázta felolvasásra, hangot
viszont senki nem adott ki, mert TTS soha nem is volt bekötve. A csend
és a „nincs telepítve" ugyanúgy néz ki — ez a parancs választja szét
őket, és mindhárom hiányhoz megmondja a teendőt.

A kimenet szándékosan hosszabb, mint egy hibaüzenet: aki ezt futtatja,
épp azt nem tudja, mi hiányzik, és a következő lépést keresi.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

GYOKER = Path(__file__).resolve().parents[1]
if str(GYOKER) not in sys.path:
    sys.path.insert(0, str(GYOKER))

from assistant.hang import (  # noqa: E402
    HIANY_NINCS_HANG,
    HIANY_NINCS_LEJATSZO,
    HIANY_NINCS_PIPER,
    MAGYAR_HANGOK,
    allapot,
    elomelegit,
    lejatszik,
    szintetizal,
)

ALAP_MONDAT = "December huszonkettedikén kilenc órakor foglaltam időpontot a Törpillához."

# A `--meres` mondatai: pontosan azok a fajták, amiket a rendszer
# ténylegesen kimond — nyugtázó sor, ajánlat, visszaolvasás, kód. A
# hosszuk azért különbözik, hogy látszódjon: a késleltetés NEM a
# hosszal nő.
MERES_MONDATOK = [
    "Egy pillanat, körülnézek.",
    "A legkorábbi december huszonkettedikén nyolc órakor, de van nyolc negyvenkor is. Melyik jó?",
    "December huszonkettedikén nyolc negyvenkor foglalnám le. Rendben?",
    "Foglalás létrejött. A kódod: kettő, nyolc, sierra, foxtrot.",
]

# HIÁNY -> mit kell tenni. Három ok, három teendő — összevonva
# haszontalan lenne (ugyanaz az elv, mint az indítási
# modell-ellenőrzésnél).
_TEENDOK = {
    HIANY_NINCS_PIPER: (
        "Nincs Piper.",
        "    pip install piper-tts",
        "  vagy tölts le egy önálló kiadást a github.com/rhasspy/piper oldalról,",
        "  és tedd a PATH-ra — vagy add meg: APRAJAFALVA_PIPER=<útvonal a piper programhoz>",
    ),
    HIANY_NINCS_HANG: (
        "Nincs magyar hangmodell.",
        f"  A Piper hangjai a huggingface.co/rhasspy/piper-voices alatt vannak; magyar: "
        f"{', '.join(MAGYAR_HANGOK)}",
        "  KÉT fájl kell hangonként: a <nev>.onnx ÉS a <nev>.onnx.json.",
        "  Tedd ide: ~/.local/share/piper/voices/  — vagy add meg:",
        "    APRAJAFALVA_PIPER_HANG=<útvonal a .onnx fájlhoz>",
    ),
    HIANY_NINCS_LEJATSZO: (
        "Nincs lejátszó program.",
        "  Linuxon: apt install alsa-utils (aplay) vagy pulseaudio-utils (paplay).",
        "  macOS-en az afplay a rendszer része — ha ez hiányzik, valami nagyon eltört.",
    ),
}


def diagnozis(a) -> None:
    """A helyzet kiírása — akkor is, ha minden rendben van. A
    „minden megvan" is információ: ilyenkor a csendnek MÁS oka van."""
    print("=== HANGPRÓBA — mi van meg a felolvasáshoz ===\n")
    print(f"  Piper:          {a.piper or 'NINCS'}")
    print(f"  magyar hang:    {a.hang or 'NINCS'}")
    print(f"  lejátszó:       {a.lejatszo or 'NINCS'}")
    for kulcs, reszlet in (a.reszletek or {}).items():
        print(f"  megjegyzés ({kulcs}): {reszlet}")

    if a.rendben:
        print("\nMinden megvan.")
        return

    print("\nAmi hiányzik, és mit kell tenni:\n")
    for hiany in a.hianyok:
        sorok = _TEENDOK.get(hiany, (hiany,))
        print(f"  * {sorok[0]}")
        for sor in sorok[1:]:
            print(f"  {sor}")
        print()


def meres(a, mondatok: list[str]) -> int:
    """A FELOLVASÁS KÉSLELTETÉSE, mondatonként — `--meres`.

    Amit mér: mennyi idő telik el a mondat átadása és a hang kezdete
    között. Ez az, amit a vásárló csendként él meg, a modell 3,5
    másodperce UTÁN.

    Miért kellett: a Piper külön PROGRAMKÉNT hívva mondatonként ~2,07 s
    volt, a mondat hosszától FÜGGETLENÜL — vagyis nem a szintézis
    lassú, hanem az indulás (új folyamat + 60 MB hangmodell újra és
    újra). Betöltve tartva 0,2 s. A mérés ezt a különbséget mutatja meg
    a saját gépen, nem a mi számainkat kell elhinni.

    A lejátszás ideje NEM késleltetés — az maga a mondat. Külön
    oszlopban áll, hogy ne keveredjen a kettő."""
    print("\n=== KÉSLELTETÉS-MÉRÉS ===\n")
    print("  A hangmodell betöltése (egyszer)…", end=" ", flush=True)
    kezdet = time.perf_counter()
    betoltve = elomelegit(a)
    print(f"{time.perf_counter() - kezdet:.2f} s" + ("" if betoltve else "  (nincs mit betölteni)"))
    if not betoltve:
        print(
            "  A Piper külön PROGRAMKÉNT fut, nem Python-csomagként — ott minden\n"
            "  mondat új folyamat, és a hangmodell újra betöltődik. A `pip install\n"
            "  piper-tts` változat mérhetően gyorsabb."
        )

    print(f"\n  {'mondat':<44}{'szintézis':>11}{'lejátszás':>11}")
    for mondat in mondatok:
        kezdet = time.perf_counter()
        wav = szintetizal(mondat, allapot_=a)
        szintezis = time.perf_counter() - kezdet
        kezdet = time.perf_counter()
        lejatszik(wav, allapot_=a)
        lejatszas = time.perf_counter() - kezdet
        rovid = mondat if len(mondat) <= 42 else mondat[:41] + "…"
        print(f"  {rovid:<44}{szintezis:>10.2f}s{lejatszas:>10.2f}s")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Egy mondat felolvasása, diagnózissal.")
    parser.add_argument("--mondat", default=ALAP_MONDAT, help="a felolvasandó mondat")
    parser.add_argument(
        "--csak-diagnozis",
        action="store_true",
        help="csak a helyzetet írja ki, nem szintetizál és nem játszik le",
    )
    parser.add_argument("--ki", type=Path, default=None, help="a WAV mentése ide")
    parser.add_argument(
        "--meres",
        action="store_true",
        help="a felolvasás KÉSLELTETÉSE mondatonként (szintézis és lejátszás külön)",
    )
    args = parser.parse_args(argv)

    a = allapot()
    diagnozis(a)

    if not a.rendben:
        print(
            "A beszélhető kimeneti mód ettől még HASZNÁLHATÓ — csak nem hangzik el, "
            "hanem a képernyőn olvasható (ADR-023). A felület ezt ki is írja."
        )
        return 1
    if args.csak_diagnozis:
        return 0
    if args.meres:
        return meres(a, MERES_MONDATOK)

    print(f"\nSzintetizálás: {args.mondat!r}")
    try:
        wav = szintetizal(args.mondat, cel=args.ki, allapot_=a)
    except RuntimeError as exc:
        print(f"HIBA a szintézisben: {exc}")
        return 1
    print(f"  kész: {wav}  ({wav.stat().st_size / 1024:.0f} kB)")

    try:
        lejatszik(wav, allapot_=a)
    except RuntimeError as exc:
        print(f"HIBA a lejátszásban: {exc}")
        print(f"  a fájl megvan, kézzel lejátszható: {wav}")
        return 1
    print("  lejátszva.")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())

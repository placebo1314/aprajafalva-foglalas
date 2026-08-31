"""HANGPRÓBA — egyetlen mondat felolvasása, és ha nem megy, annak a
PONTOS megmondása, hogy miért (`python feladat.py hangproba`).

```
python feladat.py hangproba
python feladat.py hangproba --mondat "Holnap kilenc órakor foglaltam."
python feladat.py hangproba --csak-diagnozis      # nem játszik le semmit
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
    lejatszik,
    szintetizal,
)

ALAP_MONDAT = "December huszonkettedikén kilenc órakor foglaltam időpontot a Törpillához."

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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Egy mondat felolvasása, diagnózissal.")
    parser.add_argument("--mondat", default=ALAP_MONDAT, help="a felolvasandó mondat")
    parser.add_argument(
        "--csak-diagnozis",
        action="store_true",
        help="csak a helyzetet írja ki, nem szintetizál és nem játszik le",
    )
    parser.add_argument("--ki", type=Path, default=None, help="a WAV mentése ide")
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

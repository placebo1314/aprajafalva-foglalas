"""HANGKIMENET — Piper TTS, és mindenekelőtt annak a MEGMONDÁSA, hogy
miért nem szólal meg (ADR-029).

**Ezt előre ki kell mondani: eddig felolvasás EGYÁLTALÁN nem volt.** A
`beszelheto` kimeneti mód (ADR-023) a SZÖVEGET formázta felolvasásra —
egész mondatok, kimondott számok, fordulónként két mondat —, de hangot
soha nem adott ki, és nem is hívott TTS-t. A `docs/roadmap.md` M6
szakasza ezt így is írja („ASR, TTS, turn-detection: konfiguráció, nem
építés"), csak épp a felületen ez nem látszott: aki átkapcsolt
beszélhető módra, csendet kapott, és nem tudta, hogy azért, mert nincs
mit lejátszani.

Ez a modul két dolgot ad:

1. **Diagnózist** (`allapot()`): megvan-e a Piper, megvan-e a magyar
   hang, és ha nem, MELYIK hiányzik. Három hiány, három teendő — ugyanaz
   az elv, mint az indítási modell-ellenőrzésnél (ADR-027 köre): egy
   összevont „nem működik" üzenet abban a pillanatban lenne udvarias,
   amikor haszontalan.
2. **Szintézist és lejátszást** (`felolvas()`), ha minden megvan.

**A Piper nem függősége a projektnek**, és nem is lesz az: külön
telepített program (vagy pip-csomag) + külön letöltött hangmodell. A
rendszer nélküle is teljes értékű — csak néma. Ezért nincs `pip
install` a `pyproject.toml`-ban, és ezért nem tölt le semmit ez a modul
magától: a hangmodell 60-100 MB, azt a felhasználó tölti le, tudatosan.
"""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

# A HIÁNY három fajtája — mindegyikhez más teendő tartozik.
HIANY_NINCS_PIPER = "nincs_piper"
HIANY_NINCS_HANG = "nincs_hang"
HIANY_NINCS_LEJATSZO = "nincs_lejatszo"

# A magyar Piper-hangok neve a rhasspy/piper-voices gyűjteményben. A
# sorrend preferencia: ha több is megvan, az elsőt használjuk.
MAGYAR_HANGOK = ("hu_HU-anna-medium", "hu_HU-berta-medium", "hu_HU-imre-medium")

# Hol keressük a hangmodellt, ha a környezet nem mondja meg. Nem
# tallózunk a teljes lemezen: ez a négy hely az, ahova a Piper
# dokumentációja és a szokás szerint kerül.
_HANG_KONYVTARAK = (
    Path.home() / ".local" / "share" / "piper" / "voices",
    Path.home() / "piper" / "voices",
    Path.home() / ".piper",
    Path("piper") / "voices",
)

_PIPER_KORNYEZETI_VALTOZO = "APRAJAFALVA_PIPER"
_HANG_KORNYEZETI_VALTOZO = "APRAJAFALVA_PIPER_HANG"


@dataclass(frozen=True)
class HangAllapot:
    """Mi van meg, és mi hiányzik a felolvasáshoz.

    `hianyok` LISTA, nem egyetlen ok: hiányozhat egyszerre a Piper és a
    hangmodell is, és ilyenkor mindkettőt meg kell mondani — aki csak az
    elsőt javítja, másodszor is falnak megy."""

    piper: str | None = None
    hang: Path | None = None
    lejatszo: str | None = None
    hianyok: tuple[str, ...] = ()
    reszletek: dict[str, str] = field(default_factory=dict)

    @property
    def rendben(self) -> bool:
        return not self.hianyok


def _piper_keres() -> tuple[str | None, str | None]:
    """`(hívási mód, részlet)` — hogyan érhető el a Piper.

    Két alak létezik, és mindkettő elfogadható: önálló program
    (`piper`), vagy Python-csomag (`piper-tts`, `python -m piper`). Nem
    írjuk elő, melyik legyen — a felhasználó gépén az van, ami van."""
    kezi = os.environ.get(_PIPER_KORNYEZETI_VALTOZO)
    if kezi:
        return (
            (kezi, f"{_PIPER_KORNYEZETI_VALTOZO}={kezi}")
            if Path(kezi).exists()
            else (None, f"a megadott útvonal nem létezik: {kezi}")
        )

    program = shutil.which("piper")
    if program:
        return program, "a PATH-on"

    try:
        import piper  # noqa: F401
    except ImportError:
        return None, None
    return "python -m piper", "Python-csomagként (piper-tts)"


def _hang_keres() -> tuple[Path | None, str | None]:
    """A magyar hangmodell (`.onnx`) útvonala, vagy `None`.

    A Piper minden hanghoz KÉT fájlt vár: a modellt (`.onnx`) és a
    konfigurációját (`.onnx.json`). Csak akkor mondjuk késznek, ha
    mindkettő megvan — a hiányzó JSON ugyanolyan néma kudarc lenne."""
    kezi = os.environ.get(_HANG_KORNYEZETI_VALTOZO)
    if kezi:
        utvonal = Path(kezi)
        if utvonal.exists() and utvonal.with_suffix(".onnx.json").exists():
            return utvonal, f"{_HANG_KORNYEZETI_VALTOZO}={kezi}"
        return None, f"a megadott hangmodell hiányos vagy nem létezik: {kezi}"

    for konyvtar in _HANG_KONYVTARAK:
        if not konyvtar.is_dir():
            continue
        for nev in MAGYAR_HANGOK:
            utvonal = konyvtar / f"{nev}.onnx"
            if utvonal.exists() and utvonal.with_suffix(".onnx.json").exists():
                return utvonal, str(konyvtar)
    return None, None


def _lejatszo_keres() -> str | None:
    """A WAV lejátszásának módja, platformfüggően. `None`, ha nincs.

    Windowson a `winsound` a szabványos könyvtár része, tehát mindig
    van; máshol külső programot keresünk."""
    if platform.system() == "Windows":
        return "winsound"
    for program in ("afplay", "aplay", "paplay", "play"):
        if shutil.which(program):
            return program
    return None


def allapot() -> HangAllapot:
    """A hangkimenet DIAGNÓZISA — mi van meg, mi hiányzik, és mit kell
    tenni. Semmit nem tölt le és nem indít el."""
    piper, piper_reszlet = _piper_keres()
    hang, hang_reszlet = _hang_keres()
    lejatszo = _lejatszo_keres()

    hianyok = []
    reszletek = {}
    if piper is None:
        hianyok.append(HIANY_NINCS_PIPER)
        if piper_reszlet:
            reszletek[HIANY_NINCS_PIPER] = piper_reszlet
    if hang is None:
        hianyok.append(HIANY_NINCS_HANG)
        if hang_reszlet:
            reszletek[HIANY_NINCS_HANG] = hang_reszlet
    if lejatszo is None:
        hianyok.append(HIANY_NINCS_LEJATSZO)

    return HangAllapot(
        piper=piper,
        hang=hang,
        lejatszo=lejatszo,
        hianyok=tuple(hianyok),
        reszletek=reszletek,
    )


def szintetizal(szoveg: str, cel: Path | None = None, allapot_: HangAllapot | None = None) -> Path:
    """A mondatból WAV fájl. `RuntimeError`, ha hiányzik valami — a
    hívónak előbb az `allapot()`-ot kell megnéznie.

    A szöveg a SZABVÁNYOS BEMENETEN megy át, nem parancssori
    argumentumként: egy magyar mondat idézőjelet, kötőjelet és
    ékezetet is tartalmaz, és a parancssori idézés platformonként
    máshogy törik el."""
    a = allapot_ or allapot()
    if not a.rendben or a.piper is None or a.hang is None:
        raise RuntimeError(f"a felolvasáshoz hiányzik: {', '.join(a.hianyok)}")

    kimenet = cel or Path(tempfile.gettempdir()) / "aprajafalva_hang.wav"
    parancs = (a.piper.split() if a.piper.startswith("python") else [a.piper]) + [
        "--model",
        str(a.hang),
        "--output_file",
        str(kimenet),
    ]
    eredmeny = subprocess.run(
        parancs, input=szoveg.encode("utf-8"), capture_output=True, timeout=120
    )
    if eredmeny.returncode != 0 or not kimenet.exists():
        hiba = eredmeny.stderr.decode("utf-8", "replace").strip()[:400]
        raise RuntimeError(f"a Piper nem adott hangot (kód {eredmeny.returncode}): {hiba}")
    return kimenet


def lejatszik(wav: Path, allapot_: HangAllapot | None = None) -> None:
    """A WAV lejátszása. Blokkol, amíg szól — a hívó dolga, hogy ne a
    felület eseményhurkán tegye (`ui/vasarlo.py` külön szálon hívja)."""
    a = allapot_ or allapot()
    if a.lejatszo is None:
        raise RuntimeError("nincs lejátszó program")
    if a.lejatszo == "winsound":
        import winsound

        winsound.PlaySound(str(wav), winsound.SND_FILENAME)
        return
    subprocess.run([a.lejatszo, str(wav)], capture_output=True, timeout=120)


def felolvas(szoveg: str) -> None:
    """Szintézis + lejátszás egy lépésben. Kivételt dob, ha bármi
    hiányzik — a felület ezt elkapja, és a hiányt KIÍRJA, nem
    elnyeli."""
    a = allapot()
    lejatszik(szintetizal(szoveg, allapot_=a), allapot_=a)

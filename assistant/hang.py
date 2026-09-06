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
import threading
import time
import uuid
import wave
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


# ---------------------------------------------------------------------
# A HANG BETÖLTVE TARTÁSA — a 2 másodperc néma várakozás ellen
#
# MÉRVE (2026-09-20, `python feladat.py hangproba --meres`): a Piper
# külön PROGRAMKÉNT hívva mondatonként ~2,07 s, a mondat hosszától
# függetlenül. Nem a szintézis lassú, hanem az indulás: minden
# megszólalásnál új Python-folyamat indul, és újra betölti a 60 MB-os
# hangmodellt.
#
# Ugyanaz a hang IN-PROCESS betöltve: 1,54 s EGYSZER, utána 0,14-0,22 s
# mondatonként — tízszeres különbség. A modell 3,5 s alatt válaszol; ha
# a hang még két másodpercet tesz rá, a beszélgetés ritmusa elvész.
#
# Ezért: ha a Piper Python-CSOMAGKÉNT elérhető, a hangot egyszer
# betöltjük és megtartjuk. Ha külön programként van telepítve, marad a
# folyamatindítás — ott nincs mit megtartani.
_betoltott_hang: tuple[Path, object] | None = None
_hang_zar = threading.Lock()


def _piper_modul_hang(utvonal: Path):
    """A betöltött `PiperVoice`, vagy `None`, ha a Piper nem
    Python-csomagként érhető el.

    A betöltés ZÁR alatt megy: a felület előmelegítő szála és az első
    tényleges megszólalás egyszerre is ideérhet, és a hangmodell
    kétszeri betöltése egy 8 GB-os gépen nem ártalmatlan."""
    global _betoltott_hang
    with _hang_zar:
        if _betoltott_hang is not None and _betoltott_hang[0] == utvonal:
            return _betoltott_hang[1]
        try:
            from piper import PiperVoice
        except ImportError:
            return None
        hang = PiperVoice.load(str(utvonal))
        _betoltott_hang = (utvonal, hang)
        return hang


def elomelegit(allapot_: HangAllapot | None = None) -> bool:
    """A hangmodell betöltése ELŐRE, hogy az első megszólalás ne
    másfél másodperccel később kezdődjön.

    `True`, ha a hang betöltve él (a következő mondat gyors lesz);
    `False`, ha nincs mit előmelegíteni — vagy mert hiányzik valami,
    vagy mert a Piper külön programként fut, és ott minden hívás új
    folyamat. **Nem dob kivételt**: az előmelegítés kényelmi lépés, egy
    hibája nem akadályozhatja meg az indulást.

    Ugyanaz a minta, mint a modell-előmelegítésnél
    (`assistant/interpreter/llm_based.py::elomelegit`): a lassú első
    hívás árát a felület az indulásra tolja, ahol a felhasználó úgyis
    vár."""
    a = allapot_ or allapot()
    if not a.rendben or a.hang is None:
        return False
    try:
        return _piper_modul_hang(a.hang) is not None
    except Exception:  # noqa: BLE001 — l. a docstringet: néma kényelmi lépés
        return False


def szintetizal(szoveg: str, cel: Path | None = None, allapot_: HangAllapot | None = None) -> Path:
    """A mondatból WAV fájl. `RuntimeError`, ha hiányzik valami — a
    hívónak előbb az `allapot()`-ot kell megnéznie.

    Két úton mehet, és a különbség MÉRHETŐ (l. fent): betöltött
    Python-csomaggal ~0,2 s, külön programként ~2,1 s. Az eredmény
    ugyanaz a WAV.

    A `cel` alapértelmezés szerint EGYEDI fájlnév. Fix névvel a
    következő mondat szintézise arra a fájlra írna, amit a lejátszó épp
    olvas — Windowson ez zajt vagy `PlaySound`-hibát ad, és pontosan
    akkor, amikor a vásárló gyorsan gépel."""
    a = allapot_ or allapot()
    if not a.rendben or a.piper is None or a.hang is None:
        raise RuntimeError(f"a felolvasáshoz hiányzik: {', '.join(a.hianyok)}")

    kimenet = cel or _uj_wav_utvonal()
    hang = _piper_modul_hang(a.hang) if not a.piper.startswith(("/", "\\")) else None
    if hang is not None:
        with wave.open(str(kimenet), "wb") as wav:
            hang.synthesize_wav(szoveg, wav)
        return kimenet

    # A szöveg a SZABVÁNYOS BEMENETEN megy át, nem parancssori
    # argumentumként: egy magyar mondat idézőjelet, kötőjelet és
    # ékezetet is tartalmaz, és a parancssori idézés platformonként
    # máshogy törik el.
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


def _uj_wav_utvonal() -> Path:
    """Egyedi WAV-útvonal a szintézisnek. A régi fájlokat NEM takarítjuk
    el fordulónként: pár száz kB, és a rendszer temp-könyvtára úgyis a
    saját ütemében ürül — a lejátszás közbeni törlés viszont épp azt a
    hibát szülné, amit el akarunk kerülni."""
    return Path(tempfile.gettempdir()) / f"aprajafalva_hang_{uuid.uuid4().hex[:8]}.wav"


# ---------------------------------------------------------------------
# MEGSZAKÍTHATÓSÁG — hogy ne beszéljen két forduló egyszerre
#
# A felület fordulónként EGY megszólalást ad ki, külön szálon. Ha a
# vásárló gyorsabban ír, mint ahogy a hang elhangzik, a régi mondat
# tovább szól az új alatt — két hang egyszerre, és egyik sem érthető.
#
# A megoldás nem az, hogy megvárjuk a végét (az még rosszabb: a vásárló
# már a következő kérdésnél tart), hanem hogy az ÚJ megszólalás
# elhallgattatja a régit. Ehhez a lejátszásnak megszakíthatónak kell
# lennie — Windowson a szinkron `PlaySound` MÉRVE nem az: egy másik
# szálból küldött `SND_PURGE` nem szakítja meg (2026-09-20). Ezért
# aszinkron lejátszás + várakozás a hang hosszáig, közben figyelve a
# leállítás-jelzőt.
_leallitas = threading.Event()
_folyamat_zar = threading.Lock()
_folyo_folyamat: subprocess.Popen | None = None

# Milyen sűrűn nézzük meg, hogy le kell-e állni. 50 ms alatt a
# megszakítás azonnalinak érződik, fölötte már hallható a farok.
_FIGYELES_MASODPERC = 0.05


def _wav_hossz(wav: Path) -> float:
    """A WAV hossza másodpercben. Hibás fájlnál 0 — inkább ne várjunk,
    mint hogy egy sérült fájl miatt beragadjon a szál."""
    try:
        with wave.open(str(wav), "rb") as f:
            return f.getnframes() / float(f.getframerate() or 1)
    except (wave.Error, OSError):
        return 0.0


def leallit() -> None:
    """A folyamatban lévő megszólalás elhallgattatása.

    A felület akkor hívja, amikor ÚJ forduló kezdődik: a vásárló
    kérdése fontosabb, mint az előző válasz vége."""
    _leallitas.set()
    if platform.system() == "Windows":
        try:
            import winsound

            winsound.PlaySound(None, winsound.SND_PURGE)
        except (ImportError, RuntimeError):
            pass
        return
    with _folyamat_zar:
        if _folyo_folyamat is not None and _folyo_folyamat.poll() is None:
            _folyo_folyamat.terminate()


def lejatszik(wav: Path, allapot_: HangAllapot | None = None) -> None:
    """A WAV lejátszása. Blokkol, amíg szól — a hívó dolga, hogy ne a
    felület eseményhurkán tegye (`ui/vasarlo.py` külön szálon hívja).

    **Megszakítható**: egy másik szálból hívott `leallit()` elhallgattatja
    (l. fent). A visszatérés ilyenkor is normális, nem kivétel — a
    félbeszakított mondat nem hiba, hanem az, amit kértünk."""
    global _folyo_folyamat
    a = allapot_ or allapot()
    if a.lejatszo is None:
        raise RuntimeError("nincs lejátszó program")

    _leallitas.clear()
    if a.lejatszo == "winsound":
        import winsound

        winsound.PlaySound(str(wav), winsound.SND_FILENAME | winsound.SND_ASYNC)
        _var(_wav_hossz(wav))
        return

    with _folyamat_zar:
        _folyo_folyamat = subprocess.Popen(  # noqa: S603
            [a.lejatszo, str(wav)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
    folyamat = _folyo_folyamat
    while folyamat.poll() is None:
        if _leallitas.wait(_FIGYELES_MASODPERC):
            return
    with _folyamat_zar:
        _folyo_folyamat = None


def _var(masodperc: float) -> None:
    """Várakozás a hang hosszáig, de megszakíthatóan."""
    hatarido = time.monotonic() + masodperc
    while time.monotonic() < hatarido:
        if _leallitas.wait(min(_FIGYELES_MASODPERC, hatarido - time.monotonic())):
            return


def felolvas(szoveg: str) -> None:
    """Szintézis + lejátszás egy lépésben. Kivételt dob, ha bármi
    hiányzik — a felület ezt elkapja, és a hiányt KIÍRJA, nem
    elnyeli."""
    a = allapot()
    lejatszik(szintetizal(szoveg, allapot_=a), allapot_=a)

"""A HANGKIMENET diagnózisa (`assistant/hang.py`, ADR-029).

**Ez a fájl sosem szólal meg és sosem telepít semmit.** A Piper külön
telepített program, a magyar hangmodell külön letöltött, 60-100 MB-os
fájl — egyik sem függősége a projektnek. Amit itt mérünk, az a
DIAGNÓZIS: megtaláljuk-e, ami megvan, és megmondjuk-e pontosan, mi
hiányzik.

Miért ez a fontos: a felolvasás eddig CSENDBEN maradt el (TTS soha nem
volt bekötve), és a csend ugyanúgy néz ki, mint a „nincs telepítve".
"""

from __future__ import annotations

import threading
import time
import wave
from pathlib import Path

import pytest

from assistant import hang
from assistant.valasz import hang_allapot_szoveg


def _hangfajlok(konyvtar: Path, nev: str = "hu_HU-anna-medium") -> Path:
    """Egy ÉRVÉNYES hangmodell-pár: a Piper mindkét fájlt várja."""
    onnx = konyvtar / f"{nev}.onnx"
    onnx.write_bytes(b"nem valodi modell")
    onnx.with_suffix(".onnx.json").write_text("{}", encoding="utf-8")
    return onnx


def test_semmi_sincs_meg_akkor_ket_hianyt_mondunk(monkeypatch, tmp_path):
    """Hiányozhat egyszerre a Piper ÉS a hangmodell — aki csak az elsőt
    javítja, másodszor is falnak menne. Ezért lista, nem egyetlen ok."""
    monkeypatch.delenv("APRAJAFALVA_PIPER", raising=False)
    monkeypatch.delenv("APRAJAFALVA_PIPER_HANG", raising=False)
    monkeypatch.setattr(hang.shutil, "which", lambda _nev: None)
    monkeypatch.setattr(hang, "_HANG_KONYVTARAK", (tmp_path,))
    monkeypatch.setitem(__import__("sys").modules, "piper", None)

    allapot = hang.allapot()

    assert hang.HIANY_NINCS_PIPER in allapot.hianyok
    assert hang.HIANY_NINCS_HANG in allapot.hianyok
    assert allapot.rendben is False


def test_a_kornyezeti_valtozo_megadhatja_a_pipert(monkeypatch, tmp_path):
    piper = tmp_path / "piper.exe"
    piper.write_text("", encoding="utf-8")
    monkeypatch.setenv("APRAJAFALVA_PIPER", str(piper))

    assert hang.allapot().piper == str(piper)


def test_a_nem_letezo_megadott_utvonal_hianynak_szamit(monkeypatch, tmp_path):
    """Ha valaki megadta a változót, de elgépelte, azt KI KELL MONDANI —
    különben a „nincs Piper" üzenetből azt hinné, hogy nem is állította
    be."""
    monkeypatch.setenv("APRAJAFALVA_PIPER", str(tmp_path / "nincs-itt"))

    allapot = hang.allapot()

    assert hang.HIANY_NINCS_PIPER in allapot.hianyok
    assert "nem létezik" in allapot.reszletek[hang.HIANY_NINCS_PIPER]


def test_a_hangmodellhez_a_json_is_kell(monkeypatch, tmp_path):
    """A Piper minden hanghoz KÉT fájlt vár. A hiányzó JSON ugyanolyan
    néma kudarc lenne, mint a hiányzó modell."""
    monkeypatch.delenv("APRAJAFALVA_PIPER_HANG", raising=False)
    csonka = tmp_path / "hu_HU-anna-medium.onnx"
    csonka.write_bytes(b"csak a modell")
    monkeypatch.setattr(hang, "_HANG_KONYVTARAK", (tmp_path,))

    assert hang.HIANY_NINCS_HANG in hang.allapot().hianyok

    _hangfajlok(tmp_path)
    assert hang.HIANY_NINCS_HANG not in hang.allapot().hianyok


def test_a_megtalalt_hang_a_preferencia_sorrendet_koveti(monkeypatch, tmp_path):
    monkeypatch.delenv("APRAJAFALVA_PIPER_HANG", raising=False)
    monkeypatch.setattr(hang, "_HANG_KONYVTARAK", (tmp_path,))
    _hangfajlok(tmp_path, "hu_HU-imre-medium")
    _hangfajlok(tmp_path, "hu_HU-anna-medium")

    assert hang.allapot().hang.stem == hang.MAGYAR_HANGOK[0]


def test_szintezis_hiany_eseten_kivetel_nem_csend(monkeypatch, tmp_path):
    """A néma elmaradás a rossz viselkedés — a hívónak tudnia kell, hogy
    nem szólalt meg semmi."""
    monkeypatch.delenv("APRAJAFALVA_PIPER", raising=False)
    monkeypatch.setattr(hang.shutil, "which", lambda _nev: None)
    monkeypatch.setattr(hang, "_HANG_KONYVTARAK", (tmp_path,))
    monkeypatch.setitem(__import__("sys").modules, "piper", None)

    try:
        hang.szintetizal("Jó napot.")
    except RuntimeError as exc:
        assert "hiányzik" in str(exc)
    else:  # pragma: no cover - a teszt lényege, hogy ide ne jussunk
        raise AssertionError("kivételt vártunk")


# -- a felületen megjelenő sor -----------------------------------------


def test_a_felulet_sora_megnevezi_a_hianyt():
    szoveg = hang_allapot_szoveg((hang.HIANY_NINCS_PIPER, hang.HIANY_NINCS_HANG))

    assert "Piper" in szoveg
    assert "hangmodell" in szoveg
    assert "hangproba" in szoveg, "a sor megmondja, hol lehet részletet nézni"


def test_a_felulet_sora_a_kesz_allapotot_is_kimondja():
    """A csendnek ilyenkor MÁS oka van — és ezt tudni kell."""
    szoveg = hang_allapot_szoveg((), "hu_HU-anna-medium")

    assert "hu_HU-anna-medium" in szoveg


# =====================================================================
# A FELOLVASÓ HASZNÁLHATÓSÁGA (ADR-033)
#
# Nem a hangot mérik (azt fül nélkül nem lehet), hanem azt a három
# dolgot, ami a felolvasót a próbán használhatatlanná tette:
#
# 1. mondatonként 2 másodperc csend, mert minden megszólalás új
#    folyamatot indított és újra betöltötte a 60 MB-os hangmodellt;
# 2. két forduló hangja egymásra csúszott, mert a régi mondatot semmi
#    nem hallgattatta el;
# 3. minden szintézis UGYANARRA a fájlra írt — arra, amit a lejátszó
#    épp olvasott.
#
# A Piper JELENLÉTÉT egyik teszt sem igényli — a Piper nem függősége a
# projektnek (ADR-029), tehát a tesztkészletnek sem lehet az.
# =====================================================================


def _wav_ir(cel: Path, masodperc: float = 1.0) -> Path:
    """Néma WAV — a lejátszás IDŐZÍTÉSÉT méri, nem a hangot."""
    with wave.open(str(cel), "wb") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(22050)
        f.writeframes(b"\x00\x00" * int(22050 * masodperc))
    return cel


def test_a_wav_utvonal_egyedi():
    """Fix névvel a következő mondat szintézise arra a fájlra írna,
    amit a lejátszó épp olvas."""
    egy, ketto = hang._uj_wav_utvonal(), hang._uj_wav_utvonal()

    assert egy != ketto
    assert egy.suffix == ".wav"
    assert "aprajafalva" in egy.name, "felismerhető marad a temp-könyvtárban"


def test_a_wav_hossz_a_fajlbol_jon(tmp_path):
    assert hang._wav_hossz(_wav_ir(tmp_path / "n.wav", 2.0)) == pytest.approx(2.0, abs=0.05)


def test_a_serult_wav_nem_ragasztja_be_a_szalat(tmp_path):
    """Hibás fájlnál inkább ne várjunk, mint hogy a felolvasó szál a
    végtelenségig álljon."""
    rossz = tmp_path / "rossz.wav"
    rossz.write_bytes(b"ez nem wav")

    assert hang._wav_hossz(rossz) == 0.0


def test_a_var_megszakithato():
    """Ez a megszakíthatóság MAGVA: a lejátszás nem egy szinkron hívás,
    amit megvárunk, hanem egy várakozás, amit félbe lehet szakítani.

    Windowson MÉRVE (2026-09-20): a szinkron `PlaySound`-ot egy másik
    szálból küldött `SND_PURGE` NEM szakítja meg — ezért lett aszinkron
    lejátszás plusz megszakítható várakozás."""
    hang._leallitas.clear()
    threading.Timer(0.1, hang._leallitas.set).start()

    kezdet = time.monotonic()
    hang._var(5.0)
    telt = time.monotonic() - kezdet

    assert telt < 1.0, f"a várakozás nem szakadt meg ({telt:.2f}s)"


def test_a_var_kivarja_a_hangot_ha_nincs_leallitas():
    hang._leallitas.clear()

    kezdet = time.monotonic()
    hang._var(0.3)

    assert time.monotonic() - kezdet >= 0.25


def test_az_elomelegites_hiany_eseten_nem_dob():
    """Az előmelegítés kényelmi lépés — egy hibája nem akadályozhatja
    meg az indulást."""
    ures = hang.HangAllapot(hianyok=(hang.HIANY_NINCS_PIPER,))

    assert hang.elomelegit(ures) is False


def test_szintetizal_hiany_eseten_MEGMONDJA_mi_hianyzik():
    """A csend és a „nincs telepítve" ugyanúgy néz ki — a kivétel
    üzenete választja szét őket."""
    ures = hang.HangAllapot(hianyok=(hang.HIANY_NINCS_HANG,))

    with pytest.raises(RuntimeError, match=hang.HIANY_NINCS_HANG):
        hang.szintetizal("bármi", allapot_=ures)

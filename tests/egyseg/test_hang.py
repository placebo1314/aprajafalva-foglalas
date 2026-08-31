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

from pathlib import Path

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

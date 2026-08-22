"""Egységtesztek a vásárlói felület (`ui/vasarlo.py`) mögötti, Tkinter
nélküli tiszta függvényre — a Tkinter-widgeteket nem teszteljük (ugyanaz a
minta, mint `ui/admin/app.py`-nál: "Tkinter-teszt nincs").

A magyar mondatokat összeállító logika (`nyugtazo_szoveg`,
`tenyvalasz_szoveg`, hibaüzenetek stb.) átköltözött az `assistant/valasz/`
modulba — azt `tests/egyseg/test_valasz.py` teszteli. Itt csak az marad,
ami ténylegesen ehhez a felülethez kötött formázás (időpont-címke a
koppintós gombokhoz), nem magyar mondat."""

from __future__ import annotations

from ui.vasarlo import _idopont_cimke


def test_idopont_cimke_formazas():
    cimke = _idopont_cimke("2026-08-18T08:00:00Z", "2026-08-18T08:30:00Z")
    assert cimke == "2026-08-18 08:00–08:30 (UTC)"

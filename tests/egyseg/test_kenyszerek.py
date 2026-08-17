"""Egységtesztek a mag/szabalyok/kenyszerek.py kemény kényszereire."""

from __future__ import annotations

from mag.modell.muszak import Blokk, Muszak
from mag.szabalyok import kenyszerek as k


def _muszak(kezdet: str = "2026-08-18T08:00:00Z", veg: str = "2026-08-18T16:00:00Z") -> Muszak:
    return Muszak(
        id="m",
        szervezet_id="sz",
        kezdet=kezdet,
        veg=veg,
        idotartam_perc=30,
        puffer_utana_perc=0,
        min_racs_perc=10,
        foglalhato_arany=1.0,
        blokk_szabaly={},
    )


def test_nincs_sertes_ha_minden_rendben():
    muszak = _muszak()  # 8 órás műszak
    blokkok = [Blokk("szunet", "2026-08-18T12:00:00Z", "2026-08-18T12:20:00Z", True, True)]
    sertesek = k.ellenoriz(
        muszak, blokkok, min_osszes_szunet_perc=15, max_folyamatos_munka_perc=300
    )
    assert sertesek == []


def test_blokk_a_muszakon_tul_sertes():
    muszak = _muszak()
    blokkok = [Blokk("szunet", "2026-08-18T07:50:00Z", "2026-08-18T12:20:00Z", True, True)]
    sertesek = k.ellenoriz(muszak, blokkok, min_osszes_szunet_perc=5, max_folyamatos_munka_perc=600)
    assert [s.szabaly for s in sertesek] == ["blokk_muszakon_belul"]


def test_minimum_osszes_szunet_sertes():
    muszak = _muszak()
    blokkok = [Blokk("szunet", "2026-08-18T12:00:00Z", "2026-08-18T12:05:00Z", True, True)]
    sertesek = k.ellenoriz(
        muszak, blokkok, min_osszes_szunet_perc=20, max_folyamatos_munka_perc=600
    )
    assert "minimum_osszes_szunet" in [s.szabaly for s in sertesek]


def test_maximum_folyamatos_munka_sertes():
    muszak = _muszak()  # 8 óra, egyetlen szünet a közepén
    blokkok = [Blokk("szunet", "2026-08-18T12:00:00Z", "2026-08-18T12:20:00Z", True, True)]
    # a szünet előtti szakasz 4 óra (240 perc) — ha a küszöb ez alatt van, sértés
    sertesek = k.ellenoriz(
        muszak, blokkok, min_osszes_szunet_perc=15, max_folyamatos_munka_perc=180
    )
    szabalyok = [s.szabaly for s in sertesek]
    assert szabalyok.count("maximum_folyamatos_munka") == 2  # szünet előtt ÉS után is túllépi


def test_munkajogi_minimum_6_ora_alatt_nem_kotelezo():
    muszak = _muszak(veg="2026-08-18T13:00:00Z")  # 5 órás műszak, nincs szünet
    sertesek = k.ellenoriz(muszak, [], min_osszes_szunet_perc=0, max_folyamatos_munka_perc=600)
    assert "munkajogi_minimum" not in [s.szabaly for s in sertesek]


def test_munkajogi_minimum_6_ora_felett_kotelezo_es_sertheto():
    muszak = _muszak()  # 8 óra
    blokkok = [Blokk("szunet", "2026-08-18T12:00:00Z", "2026-08-18T12:10:00Z", True, True)]
    sertesek = k.ellenoriz(muszak, blokkok, min_osszes_szunet_perc=5, max_folyamatos_munka_perc=600)
    assert "munkajogi_minimum" in [s.szabaly for s in sertesek]  # 10 perc < 20 perces minimum


def test_munkajogi_minimum_20_perces_szunet_teljesiti():
    muszak = _muszak()  # 8 óra
    blokkok = [Blokk("szunet", "2026-08-18T12:00:00Z", "2026-08-18T12:20:00Z", True, True)]
    sertesek = k.ellenoriz(
        muszak, blokkok, min_osszes_szunet_perc=15, max_folyamatos_munka_perc=600
    )
    assert "munkajogi_minimum" not in [s.szabaly for s in sertesek]

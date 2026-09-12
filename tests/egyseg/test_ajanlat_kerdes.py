"""`ajanlat_kerdes` — kérdés a FELAJÁNLOTT időpontokról (ADR-035).

A második idegen próbában a vásárló ÖT egymás utáni fordulóban a
felajánlott időpontokról kérdezett, és a rendszer mind az ötször újra
keresett, ugyanazzal az ablakkal, ugyanazzal az eredménnyel. A válasz
a kezünkben volt — a jelöltek listájában.
"""

from __future__ import annotations

import pytest

from assistant.tools import ajanlat_kerdes as ak

_JELOLTEK = [
    {"slot_id": "a", "kezdet": "2026-12-22T07:00:00Z", "veg": "2026-12-22T07:15:00Z"},
    {"slot_id": "b", "kezdet": "2026-12-22T08:30:00Z", "veg": "2026-12-22T08:45:00Z"},
    {"slot_id": "c", "kezdet": "2026-12-23T09:20:00Z", "veg": "2026-12-23T09:35:00Z"},
]


def test_melyik_nap_a_jeloltekbol_felel():
    """Keresés nélkül: a napok ott vannak a listában."""
    eredmeny = ak.hivas({"mit": ak.MELYIK_NAP}, jeloltek=_JELOLTEK)

    assert eredmeny["sikeres"] is True
    assert eredmeny["napok"] == ["2026-12-22", "2026-12-23"]


def test_a_napok_sorrendje_az_AJANLATE_nem_naptari():
    """A sorrend a pontozóé (ADR-006), és a vásárlónak is az a
    természetes, amit az imént látott."""
    forditva = list(reversed(_JELOLTEK))

    eredmeny = ak.hivas({"mit": ak.MELYIK_NAP}, jeloltek=forditva)

    assert eredmeny["napok"] == ["2026-12-23", "2026-12-22"]


def test_van_kesobbi_ELTOLJA_az_ablakot():
    """A kérdés egyben kérés. Enélkül ugyanazt találnánk meg megint —
    és pontosan ez történt ötször egymás után."""
    eredmeny = ak.hivas({"mit": ak.VAN_KESOBBI}, jeloltek=_JELOLTEK)

    assert eredmeny["uj_ablak_tol"] > "2026-12-23T09:20:00Z", "a LEGKÉSŐBBI ajánlat mögé"
    assert eredmeny["hatar"] == "2026-12-23T09:20:00Z"


def test_van_korabbi_visszafele_tolja():
    eredmeny = ak.hivas({"mit": ak.VAN_KORABBI}, jeloltek=_JELOLTEK)

    assert eredmeny["uj_ablak_ig"] < "2026-12-22T07:00:00Z", "a LEGKORÁBBI ajánlat elé"


def test_mikor_van_egy_konkret_jeloltrol_felel():
    eredmeny = ak.hivas({"mit": ak.MIKOR_VAN, "sorszam": 2}, jeloltek=_JELOLTEK)

    assert eredmeny["jelolt"]["slot_id"] == "b"


@pytest.mark.parametrize("sorszam", [0, 9, -1, "kettő", None])
def test_mikor_van_tartomanyon_kivul_NEM_kerekit(sorszam):
    """Ugyanaz az elv, mint a jelöltválasztásnál: inkább nincs válasz,
    mint rossz."""
    eredmeny = ak.hivas({"mit": ak.MIKOR_VAN, "sorszam": sorszam}, jeloltek=_JELOLTEK)

    assert eredmeny["sikeres"] is False


def test_ismeretlen_kerdesfajta_nem_talal_ki_valaszt():
    assert ak.hivas({"mit": "hany_ora_van"}, jeloltek=_JELOLTEK)["sikeres"] is False


def test_jeloltek_nelkul_nincs_mire_kerdezni():
    """Az állapot-ellenőrzés az orchestratoré, de az eszköz sem tesz
    úgy, mintha lenne mit mondania."""
    eredmeny = ak.hivas({"mit": ak.MELYIK_NAP}, jeloltek=[])

    assert eredmeny["sikeres"] is False
    assert eredmeny["uzenet_kulcs"] == "nincs_mire_kerdezni"


def test_nem_nyul_a_jeloltekhez():
    """Tiszta függvény: a vásárló kérdezett, nem döntött — a holdok és
    a lista érintetlenek maradnak."""
    eredeti = [dict(j) for j in _JELOLTEK]

    ak.hivas({"mit": ak.VAN_KESOBBI}, jeloltek=_JELOLTEK)

    assert _JELOLTEK == eredeti

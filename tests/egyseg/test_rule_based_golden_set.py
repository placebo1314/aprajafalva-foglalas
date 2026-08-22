"""A determinisztikus értelmező mérése a TELJES golden seten
(`tests/golden/nyelvi_alap.yaml`) — ez a rendszeres regressziós védőháló:
`python feladat.py teszt` minden futásakor ellenőrzi, hogy a rétegek
tartják-e a saját küszöbüket (golden-set skill).

A betöltés, a hívás és a pontozás a `tests/golden/futtato.py`-ból jön —
UGYANAZ a kód fut itt, mint amit `python feladat.py golden` közvetlenül
futtat. Nincs itt önálló másolat: a `tests/golden/futtato.py` a tartós
modul (M3), ez a fájl csak a pytest-integrációt adja hozzá (rétegenkénti
küszöb-assertek, tiltott-minta ellenőrzés) — egy- ÉS többfordulós
(alkudozás) esetekkel egyaránt."""

from __future__ import annotations

from assistant.interpreter.rule_based import SzabalyAlapuErtelmezo
from tests.golden.futtato import betolt, fut, szabaly_hivo


def _futtat():
    meta, esetek = betolt()
    eredmenyek = fut(meta, esetek, szabaly_hivo(SzabalyAlapuErtelmezo()))
    return meta, esetek, eredmenyek


def test_golden_set_minden_eset_lefut_hiba_nelkul():
    _, esetek, eredmenyek = _futtat()
    assert len(eredmenyek) == len(esetek)


def test_golden_set_retegkuszobok_teljesulnek():
    meta, _esetek, eredmenyek = _futtat()
    kuszobok = meta["kuszobok"]
    reteg_pontok: dict[str, list[float]] = {}
    for er in eredmenyek:
        reteg_pontok.setdefault(er.eset.reteg, []).append(er.pontszam)

    hibak = []
    for reteg, kuszob in kuszobok.items():
        pontok = reteg_pontok.get(reteg, [])
        if not pontok:
            continue
        atlag = sum(pontok) / len(pontok)
        if atlag < kuszob:
            hibak.append(f"{reteg}: {atlag:.0%} < küszöb {kuszob:.0%}")
    assert not hibak, "Réteg-küszöb alatt: " + "; ".join(hibak)


def test_golden_set_nincs_tiltott_mintasertes():
    _, _esetek, eredmenyek = _futtat()
    for er in eredmenyek:
        if not er.eset.tilos:
            continue
        assert "TILTOTT MINTA" not in er.indoklas, f"{er.eset.id}: {er.indoklas}"


def test_golden_set_osszesitett_pontossag_legalabb_kilencven_szazalek():
    """Nem a golden-set skill hivatalos küszöbe (az réteget méri) — ez
    csak egy durva riasztás, ha egy jövőbeli változtatás drasztikusan
    ront az összesítetten, még ha egy-egy réteg éppen a küszöb felett is
    marad."""
    _, _esetek, eredmenyek = _futtat()
    atlag = sum(er.pontszam for er in eredmenyek) / len(eredmenyek)
    assert atlag >= 0.90, f"Összesített pontosság {atlag:.0%} 90% alatt"

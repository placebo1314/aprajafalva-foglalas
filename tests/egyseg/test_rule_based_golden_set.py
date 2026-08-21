"""A determinisztikus értelmező mérése a TELJES golden seten
(`tests/golden/nyelvi_alap.yaml`) — ez a rendszeres regressziós védőháló:
`python feladat.py teszt` minden futásakor ellenőrzi, hogy a rétegek
tartják-e a saját küszöbüket (golden-set skill).

A kiértékelő logika szándékosan **önálló, kisebb másolata** annak, amit
a `spike/golden_futtato.py::kiertekel()` csinál — a `spike/` eldobható
kód (roadmap M-1), a `tests/` nem függhet tőle tartósan. Ha a két
logika valaha szétdriftel, ez a fájl a mérvadó (ez fut minden
tesztkörben, a spike-verzió csak méréskor)."""

from __future__ import annotations

from pathlib import Path

import yaml

from assistant.interpreter import ErtelmezesKontextus
from assistant.interpreter.rule_based import SzabalyAlapuErtelmezo

GOLDEN_UTVONAL = Path(__file__).resolve().parents[1] / "golden" / "nyelvi_alap.yaml"


def _betolt() -> tuple[dict, list[dict]]:
    adat = yaml.safe_load(GOLDEN_UTVONAL.read_text(encoding="utf-8"))
    return adat["meta"], adat["esetek"]


def _reszhalmaz(kicsi: dict, nagy: dict) -> bool:
    return all(nagy.get(k) == v for k, v in kicsi.items())


def _tilos_sertes(eset: dict, kimenet_param: dict) -> str | None:
    tiltottak = eset.get("tilos", [])
    if "kitalalt_datum" in tiltottak:
        megorzott = (eset["varhato"].get("megorzott_parameterek")) or {}
        for kulcs in ("datum_tol", "datum_ig"):
            if kulcs in kimenet_param and kulcs not in megorzott:
                return "kitalalt_datum"
    if "kitalalt_ar" in tiltottak:
        if any("ar" in str(k).lower() for k in kimenet_param):
            return "kitalalt_ar"
    return None


def _pontoz(eset: dict, kimenet: dict) -> tuple[float, str]:
    varhato = eset["varhato"]
    varhato_eszkoz = varhato.get("eszkoz")
    kimenet_eszkoz = kimenet.get("eszkoz")
    kimenet_param = kimenet.get("parameterek") or {}

    sertes = _tilos_sertes(eset, kimenet_param)
    if sertes:
        return 0.0, f"tiltott minta: {sertes}"

    if varhato_eszkoz == "nincs":
        return (1.0, "OK") if kimenet_eszkoz == "nincs" else (0.0, "várt 'nincs'")

    if varhato_eszkoz == "visszakerdez":
        if kimenet_eszkoz == "visszakerdez":
            megorzott = varhato.get("megorzott_parameterek")
            if megorzott and not _reszhalmaz(megorzott, kimenet_param):
                return 0.5, "megőrzött paraméter elveszett"
            return 1.0, "OK"
        reszleges = eset.get("reszleges_elfogadas")
        if reszleges and kimenet_eszkoz == reszleges.get("eszkoz"):
            return reszleges["pontszam"], "részleges elfogadás"
        return 0.0, f"várt 'visszakerdez', kapott {kimenet_eszkoz!r}"

    varhato_param = varhato.get("parameterek") or {}
    if kimenet_eszkoz == varhato_eszkoz and kimenet_param == varhato_param:
        return 1.0, "OK"
    reszleges = eset.get("reszleges_elfogadas")
    if reszleges and kimenet_eszkoz == reszleges.get("eszkoz"):
        return reszleges["pontszam"], "részleges elfogadás"
    if kimenet_eszkoz == varhato_eszkoz:
        return 0.0, f"paraméterek eltérnek: {kimenet_param} != {varhato_param}"
    return 0.0, f"várt {varhato_eszkoz!r}, kapott {kimenet_eszkoz!r}"


def _futtat() -> tuple[dict, dict[str, list[float]]]:
    """(eset_id -> (pontszam, indoklas), réteg -> pontszámok)."""
    meta, esetek = _betolt()
    ertelmezo = SzabalyAlapuErtelmezo()
    kontextus = ErtelmezesKontextus()
    eredmenyek: dict[str, tuple[float, str]] = {}
    reteg_pontok: dict[str, list[float]] = {}
    for eset in esetek:
        kimenet = ertelmezo.ertelmez(
            eset["bemenet"], most=meta["most_alapertelmezett"], kontextus=kontextus
        )
        pontszam, indoklas = _pontoz(eset, kimenet)
        eredmenyek[eset["id"]] = (pontszam, indoklas)
        cimkek = eset.get("cimkek", [])
        reteg = cimkek[0] if cimkek else "cimke_nelkul"
        reteg_pontok.setdefault(reteg, []).append(pontszam)
    return meta, eredmenyek, reteg_pontok


def test_golden_set_minden_eset_lefut_hiba_nelkul():
    _, eredmenyek, _ = _futtat()
    _, esetek = _betolt()
    assert len(eredmenyek) == len(esetek)


def test_golden_set_retegkuszobok_teljesulnek():
    meta, _eredmenyek, reteg_pontok = _futtat()
    kuszobok = meta["kuszobok"]
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
    _, eredmenyek, _ = _futtat()
    _, esetek = _betolt()
    for eset in esetek:
        if not eset.get("tilos"):
            continue
        pontszam, indoklas = eredmenyek[eset["id"]]
        assert "tiltott minta" not in indoklas, f"{eset['id']}: {indoklas}"


def test_golden_set_osszesitett_pontossag_legalabb_kilencven_szazalek():
    """Nem a golden-set skill hivatalos küszöbe (az réteget méri) — ez
    csak egy durva riasztás, ha egy jövőbeli változtatás drasztikusan
    ront az összesítetten, még ha egy-egy réteg éppen a küszöb felett is
    marad."""
    _, eredmenyek, _ = _futtat()
    atlag = sum(pontszam for pontszam, _ in eredmenyek.values()) / len(eredmenyek)
    assert atlag >= 0.90, f"Összesített pontosság {atlag:.0%} 90% alatt"

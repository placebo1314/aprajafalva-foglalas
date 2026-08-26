"""A ROBUSZTUSSÁGI halmaz determinisztikus védőhálója, és az ASR-hibák
mérésének egységtesztjei (`tests/golden/robusztus.yaml`).

Ugyanaz a minta, mint a `test_rule_based_golden_set.py`-nál: a
`python feladat.py golden --halmaz robusztus` MODELLEL futtatva
percekig tart és Ollamát igényel — a determinisztikus értelmezővel
viszont másodperc alatt lefut, és pont a legfontosabb kérdésre felel:
**okoz-e bármelyik eset kivételt, hatókörön kívüli választ vagy kitalált
tényt.** A halmaz elfogadási elve szerint ezek kemény küszöbök (0), a
pontosság másodlagos.

Amit ez a fájl NEM mér: a modell-utat. Az a `python feladat.py golden
--ertelmezo forditott --halmaz robusztus` dolga, és a számai a
`docs/ALLAPOT.md`-ben vannak. Ez itt az őrszem, ami minden
`python feladat.py teszt` futásnál megszólal.
"""

from __future__ import annotations

from assistant.interpreter.rule_based import SzabalyAlapuErtelmezo
from tests.golden.futtato import (
    ASR_CIMKE,
    BIZTONSAGI_KATEGORIAK,
    KITALALT_TENY,
    ROBUSZTUS_UTVONAL,
    BurkoltHivo,
    Eset,
    betolt,
    biztonsagi_ellenorzes,
    biztonsagi_osszesites,
    ertelmezo_hivo,
    fut,
    reszhalmaz_jelentes,
)


def _futtat():
    meta, esetek = betolt(ROBUSZTUS_UTVONAL)
    eredmenyek = fut(meta, esetek, ertelmezo_hivo(SzabalyAlapuErtelmezo()))
    return meta, esetek, eredmenyek


def test_a_kemeny_kuszobok_tartanak_a_determinisztikus_uton():
    """A halmaz elfogadási elve: egyetlen eset sem okozhat kivételt,
    hatókörön kívüli választ, kitalált tényt vagy instabil ismétlést."""
    meta, _esetek, eredmenyek = _futtat()
    szamok = biztonsagi_osszesites(eredmenyek)
    kuszobok = meta["biztonsagi_kuszobok"]
    sertesek = [
        f"{kategoria}: {szamok.get(kategoria, 0)} > {kuszobok[kategoria]}"
        for kategoria in BIZTONSAGI_KATEGORIAK
        if kategoria in kuszobok and szamok.get(kategoria, 0) > kuszobok[kategoria]
    ]
    assert not sertesek, "; ".join(sertesek)


def test_az_asr_esetek_kulon_merhetok():
    """A külön bontás nem kényelmi funkció: az ASR-eseteknél a bemenet
    rossz, de a SZÁNDÉK valódi — ha ezeket a halmaz átlagába olvasztjuk,
    az „elhárítás rendben" esetek elfedik az elveszített vásárlókat."""
    _meta, _esetek, eredmenyek = _futtat()
    bontas = reszhalmaz_jelentes(eredmenyek, ASR_CIMKE)
    assert bontas is not None, "a halmazban kell legyen ASR-eset"
    assert bontas["n"] >= 15, "a feladat legalább tizenöt ASR-esetet ír elő"
    # A hat ASR-hibafajta mindegyike szerepeljen — egy fajta kihagyása
    # csendben szűkítené a mérést.
    assert set(bontas["fajtak"]) == {
        "asr_szam",
        "asr_nev",
        "asr_egybefolyt",
        "asr_csonka",
        "asr_ekezet",
        "asr_hallucinacio",
    }


def test_az_asr_esetek_nem_torik_meg_a_biztonsagi_szamokat():
    _meta, _esetek, eredmenyek = _futtat()
    bontas = reszhalmaz_jelentes(eredmenyek, ASR_CIMKE)
    for kategoria in BIZTONSAGI_KATEGORIAK:
        assert bontas["biztonsagi_szamok"].get(kategoria, 0) == 0, kategoria


# --- az ÚJ vizsgálatok: lehetetlen és kitalált óra -------------------


def _eset(**mezok) -> Eset:
    alap = {
        "id": "proba",
        "bemenet": "Szeretnék időpontot nyolcvan órára a Törpillába.",
        "varhato": {"elfogadhato_eszkozok": ["szabad_idopontok", "visszakerdez"]},
        "cimkek": ["asr_szam", "asr"],
        "tilos": [],
    }
    return Eset(**{**alap, **mezok})


def _kimenet(**parameterek) -> dict:
    return {"eszkoz": "szabad_idopontok", "parameterek": {"bolt_id": "torpilla", **parameterek}}


def test_lehetetlen_ora_univerzalisan_kitalalt_teny():
    """Ez a vizsgálat MINDEN robusztussági esetre lefut, nem csak a
    megjelöltekre: egy 0..23-on kívüli óra sosem származhat értelmes
    olvasatból."""
    sertesek = biztonsagi_ellenorzes(_eset(), _kimenet(preferalt_ora=80))
    assert (KITALALT_TENY, "lehetetlen_ora") == (
        sertesek[0][0],
        sertesek[0][1].split(" —")[0],
    )


def test_ervenyes_ora_onmagaban_nem_sertes():
    assert biztonsagi_ellenorzes(_eset(), _kimenet(preferalt_ora=8)) == []


def test_a_nyolcvanbol_nem_lehet_csendben_nyolc():
    """A LEGVESZÉLYESEBB ASR-hibairány (a halmaz 13. szakasza): a
    lehetetlen értékből nem lesz lehetséges. A „nyolcvan óra"
    mondatában NINCS értelmezhető óra, tehát a 8 nem javítás, hanem
    tippelés — és láthatatlan marad, mert az órát onnantól a rendszer
    mondja ki, nem a vásárló."""
    sertesek = biztonsagi_ellenorzes(_eset(tilos=["kitalalt_ora"]), _kimenet(preferalt_ora=8))
    assert [k for k, _ in sertesek] == [KITALALT_TENY]
    assert "kitalalt_ora" in sertesek[0][1]


def test_ora_nelkuli_kimenet_a_helyes_valasz_ezekre():
    """Az órát ELDOBNI (és a bolt/nap alapján keresni) hibátlan
    viselkedés — ez az az ág, amit a halmaz elvár."""
    assert biztonsagi_ellenorzes(_eset(tilos=["kitalalt_ora"]), _kimenet()) == []


def test_a_fordulonkenti_adatok_eljutnak_a_futtatoig():
    """A stabilitás-mérés csak akkor működik, ha MINDEN forduló kimenete
    eljut a `fut()`-ig — üres listán a vizsgálat némán kimarad."""
    _meta, _esetek, eredmenyek = _futtat()
    tobbfordulos = [er for er in eredmenyek if er.eset.tobbfordulos]
    assert tobbfordulos, "kell legyen többfordulós (ismétlés) eset"
    for er in tobbfordulos:
        assert len(er.fordulo_kimenetek) == len(er.eset.fordulok), er.eset.id
        assert len(er.fordulo_idok) == len(er.eset.fordulok), er.eset.id


def test_a_burkolt_hivo_atvezeti_a_fordulonkenti_adatokat():
    """MÉRÉSI HIBA ellen, 2026-08-26. A modell-utakon (`kaszkad`,
    `forditott`) a hívó egy BURKOLÓ, ami a réteg-számlálót vezeti — és a
    fordulónkénti adatokat eddig nem emelte át magára. A `fut()` üres
    listát látott, tehát az `instabil_ismetles` vizsgálat NÉMÁN
    kimaradt: a jelentésben 0 állt, nem azért, mert stabil volt, hanem
    mert nem mértük.

    A javítás nem egy elfelejtett sor pótlása, hanem szerkezeti: a
    closure-ből osztály lett, mert egy closure-t nem lehet tesztelni,
    egy osztályt igen. Ez a teszt az."""
    alap = ertelmezo_hivo(SzabalyAlapuErtelmezo())
    konyvelesek = []
    burkolt = BurkoltHivo(alap, lambda _eredmeny: konyvelesek.append(1) or 3)

    burkolt(["mennék", "mennék"], "2026-08-17T09:00:00Z")

    assert len(burkolt.fordulo_kimenetek) == 2
    assert len(burkolt.fordulo_idok) == 2
    # A könyvelés is lefut, és az egyetértést a burkoló megőrzi.
    assert konyvelesek == [1]
    assert burkolt.utolso_egyetertes == 3


def test_letszam_kitalalt_mezo_a_ketten_esetben():
    """A „ketten" (félrehallott „kedden") tipikus csábítása: létszámot
    kinyerni belőle. A `letszam` nem létező fogalom ebben a
    rendszerben — egy beszélgetésben egy helyre egy slot foglalható."""
    sertesek = biztonsagi_ellenorzes(_eset(), _kimenet(letszam=2))
    assert any("kitalalt_mezo" in ok for _, ok in sertesek)

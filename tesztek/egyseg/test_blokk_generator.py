"""Egységtesztek a mag/slot/blokk.py + mag/slot/generator.py párra.

Az első teszteset a roadmap „Az első tíz lépés" 7. pontja szerint: „az
egyórás Törpilla-ábra" — a Törpilla bolt három pultjának egy órája.
Emellett DST-teszt (tavaszi és őszi óraátállás, Europe/Budapest) és a
kivetel_nap / szabad sáv ágak.
"""

from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from mag.modell.muszak import Muszak
from mag.slot import generator
from mag.slot._idomatek import perc_kulonbseg
from mag.slot.blokk import FixBlokk

_STRATEGIA = FixBlokk()


def _muszak(
    idotartam_perc: int,
    puffer_utana_perc: int,
    min_racs_perc: int,
    blokk_szabaly: dict,
    foglalhato_arany: float = 1.0,
    kezdet: str = "2026-08-18T08:00:00Z",
    veg: str = "2026-08-18T09:00:00Z",
) -> Muszak:
    return Muszak(
        id="m",
        szervezet_id="sz",
        kezdet=kezdet,
        veg=veg,
        idotartam_perc=idotartam_perc,
        puffer_utana_perc=puffer_utana_perc,
        min_racs_perc=min_racs_perc,
        foglalhato_arany=foglalhato_arany,
        blokk_szabaly=blokk_szabaly,
    )


# --- Törpilla-pultok, egy óra ------------------------------------------


def test_gipszjakab_harom_slot_harom_szunetblokk():
    """GipszJakab: 10 perc vásárlás, 10 perc szünet minden vásárlás után —
    egy órába pontosan 3 ciklus fér (10+10)×3 = 60 perc."""
    muszak = _muszak(
        idotartam_perc=10,
        puffer_utana_perc=0,
        min_racs_perc=10,
        blokk_szabaly={
            "szunetek": [{"tipus": "szunet", "hossz_perc": 10, "mintazat": "minden_slot_utan"}]
        },
    )

    eredmeny = generator.general(muszak, _STRATEGIA)

    assert len(eredmeny.slotok) == 3
    assert all(s.hossz_perc() == 10 for s in eredmeny.slotok)
    assert len(eredmeny.blokkok) == 3
    assert all(b.tipus == "szunet" and b.hossz_perc() == 10 for b in eredmeny.blokkok)
    _nincs_atfedes(eredmeny)
    _osszperc_egyezik_a_muszakkal(muszak, eredmeny)


def test_torpilla_ket_slot_15_perc_szunet():
    """Törpilla: legfeljebb 2 vásárló óránként (20 perces szolgáltatás),
    15 perces szünet óránként egyszer."""
    muszak = _muszak(
        idotartam_perc=20,
        puffer_utana_perc=0,
        min_racs_perc=20,
        blokk_szabaly={"szunetek": [{"tipus": "szunet", "hossz_perc": 15, "mintazat": "oranta"}]},
    )

    eredmeny = generator.general(muszak, _STRATEGIA)

    assert len(eredmeny.slotok) == 2
    assert all(s.hossz_perc() == 20 for s in eredmeny.slotok)
    assert len(eredmeny.blokkok) == 1
    assert eredmeny.blokkok[0].tipus == "szunet"
    assert eredmeny.blokkok[0].hossz_perc() == 15
    _nincs_atfedes(eredmeny)


def test_hulk_hugan_negy_slot_szunet_nelkul():
    """Hulk Hugan: 15 percenként foglalható, szünet nélkül — egy órába
    pontosan 4 slot fér."""
    muszak = _muszak(
        idotartam_perc=15,
        puffer_utana_perc=0,
        min_racs_perc=15,
        blokk_szabaly={"szunetek": []},
    )

    eredmeny = generator.general(muszak, _STRATEGIA)

    assert len(eredmeny.slotok) == 4
    assert all(s.hossz_perc() == 15 for s in eredmeny.slotok)
    assert eredmeny.blokkok == []
    _osszperc_egyezik_a_muszakkal(muszak, eredmeny)


# --- Szabad sáv és kivétel nap ------------------------------------------


def test_szabad_sav_a_muszak_vegehez_illesztve():
    muszak = _muszak(
        idotartam_perc=15,
        puffer_utana_perc=0,
        min_racs_perc=15,
        blokk_szabaly={"szunetek": []},
        foglalhato_arany=0.75,
    )

    eredmeny = generator.general(muszak, _STRATEGIA)

    assert len(eredmeny.blokkok) == 1
    szabad_sav = eredmeny.blokkok[0]
    assert szabad_sav.tipus == "szabad_sav"
    assert szabad_sav.veg == muszak.veg
    assert szabad_sav.hossz_perc() == 15  # 60 perc 25%-a
    assert len(eredmeny.slotok) == 3  # a maradék 45 percbe 3×15 perc fér
    _nincs_atfedes(eredmeny)


def test_szabad_sav_es_szunetmintazat_nem_fedi_egymast():
    """Regresszióteszt: ha egyszerre van szünetmintázat ÉS foglalhato_arany
    < 1.0, a szünetciklusok nem lóghatnak bele a szabad sávba — a szünet
    elsőbbrendű, a szabad sáv az adott órában lerövidül vagy elmarad
    (lásd mag/slot/blokk.py, FixBlokk._szabad_sav)."""
    muszak = _muszak(
        idotartam_perc=10,
        puffer_utana_perc=0,
        min_racs_perc=10,
        blokk_szabaly={
            "szunetek": [{"tipus": "szunet", "hossz_perc": 10, "mintazat": "minden_slot_utan"}]
        },
        foglalhato_arany=0.8,
        kezdet="2026-08-18T08:00:00Z",
        veg="2026-08-18T16:00:00Z",
    )

    eredmeny = generator.general(muszak, _STRATEGIA)

    szabad_sav = [b for b in eredmeny.blokkok if b.tipus == "szabad_sav"]
    assert len(szabad_sav) > 0
    szunet_blokkok = [b for b in eredmeny.blokkok if b.tipus == "szunet"]
    for szunet in szunet_blokkok:
        for sav in szabad_sav:
            atfed = szunet.kezdet < sav.veg and szunet.veg > sav.kezdet
            assert not atfed, f"szünet és szabad sáv átfedésben: {szunet} / {sav}"
    _nincs_atfedes(eredmeny)


def test_szabad_sav_oranta_elosztva_nyolcoras_muszakban():
    """8 órás műszak, szünet nélkül, foglalhato_arany=0.8 -> legalább 4
    szabad sáv blokk, óránként egyenletesen elosztva — nem egyetlen blokk
    a műszak végén (ADR-011: "elnyeli a csúszást", ami csak akkor igaz,
    ha a szabad idő a nap egészében jelen van)."""
    muszak = _muszak(
        idotartam_perc=15,
        puffer_utana_perc=0,
        min_racs_perc=15,
        blokk_szabaly={"szunetek": []},
        foglalhato_arany=0.8,
        kezdet="2026-08-18T08:00:00Z",
        veg="2026-08-18T16:00:00Z",
    )

    eredmeny = generator.general(muszak, _STRATEGIA)

    szabad_sav = sorted(
        (b for b in eredmeny.blokkok if b.tipus == "szabad_sav"), key=lambda b: b.kezdet
    )
    assert len(szabad_sav) >= 4

    # "Egyenletesen elosztva": a blokkok között nincs 2 óránál nagyobb rés,
    # tehát nem torlódnak egyetlen szakaszba.
    hatarpontok = [muszak.kezdet, *[b.kezdet for b in szabad_sav], muszak.veg]
    resek = [
        perc_kulonbseg(hatarpontok[i], hatarpontok[i + 1]) for i in range(len(hatarpontok) - 1)
    ]
    assert all(res <= 120 for res in resek), f"nem egyenletes eloszlás: {resek}"
    _nincs_atfedes(eredmeny)


def test_foglalhato_arany_egy_eseten_nincs_szabad_sav():
    muszak = _muszak(15, 0, 15, {"szunetek": []}, foglalhato_arany=1.0)
    eredmeny = generator.general(muszak, _STRATEGIA)
    assert not any(b.tipus == "szabad_sav" for b in eredmeny.blokkok)


def test_kivetel_napon_nem_general_semmit():
    muszak = _muszak(
        15,
        0,
        15,
        {"szunetek": []},
        kezdet="2026-12-25T08:00:00Z",
        veg="2026-12-25T09:00:00Z",
    )

    eredmeny = generator.general(muszak, _STRATEGIA, kivetel_napok=frozenset({"2026-12-25"}))

    assert eredmeny.kihagyva is True
    assert eredmeny.kihagyas_oka == "2026-12-25"
    assert eredmeny.slotok == []
    assert eredmeny.blokkok == []


def test_nem_kivetel_napon_generall():
    muszak = _muszak(
        15,
        0,
        15,
        {"szunetek": []},
        kezdet="2026-12-26T08:00:00Z",
        veg="2026-12-26T09:00:00Z",
    )

    eredmeny = generator.general(muszak, _STRATEGIA, kivetel_napok=frozenset({"2026-12-25"}))

    assert eredmeny.kihagyva is False
    assert len(eredmeny.slotok) == 4


# --- DST: 2027-03-28 (óraátállítás tavasszal) és 2027-10-31 (ősszel) ----


def test_dst_tavaszi_atallas_osszperc_egyezik():
    _dst_teszt("2027-03-28")


def test_dst_oszi_atallas_osszperc_egyezik():
    _dst_teszt("2027-10-31")


def _dst_teszt(datum: str) -> None:
    """Egy 08:00–16:00 helyi idejű (Europe/Budapest) 8 órás műszak — a
    generált slotok összperce pontosan egyezzen a műszak tényleges UTC
    hosszával, ne legyen duplikált vagy hiányzó slot, függetlenül attól,
    hogy a nap CET-ben vagy CEST-ben van."""
    zona = ZoneInfo("Europe/Budapest")
    ev, honap, nap = (int(resz) for resz in datum.split("-"))
    kezdet_helyi = datetime(ev, honap, nap, 8, 0, tzinfo=zona)
    veg_helyi = datetime(ev, honap, nap, 16, 0, tzinfo=zona)
    kezdet_utc = kezdet_helyi.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    veg_utc = veg_helyi.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

    muszak = _muszak(
        idotartam_perc=15,
        puffer_utana_perc=0,
        min_racs_perc=15,
        blokk_szabaly={"szunetek": []},
        kezdet=kezdet_utc,
        veg=veg_utc,
    )

    eredmeny = generator.general(muszak, _STRATEGIA)

    tenyleges_hossz = perc_kulonbseg(kezdet_utc, veg_utc)
    assert tenyleges_hossz == 480  # 8 óra, DST-től függetlenül (UTC-ben mérve)

    osszperc = sum(s.hossz_perc() for s in eredmeny.slotok)
    assert osszperc == tenyleges_hossz

    kezdetek = [s.kezdet for s in eredmeny.slotok]
    assert len(kezdetek) == len(set(kezdetek)), "duplikált slot"
    assert len(eredmeny.slotok) == 32  # 480 / 15


# --- segédek --------------------------------------------------------------


def _nincs_atfedes(eredmeny) -> None:
    """Sem a slotok, sem a slotok és a blokkok nem fedhetik egymást."""
    idoszakok = [(s.kezdet, s.veg) for s in eredmeny.slotok] + [
        (b.kezdet, b.veg) for b in eredmeny.blokkok
    ]
    idoszakok.sort()
    for elozo, kovetkezo in zip(idoszakok, idoszakok[1:], strict=False):
        assert elozo[1] <= kovetkezo[0], f"átfedés: {elozo} és {kovetkezo}"


def _osszperc_egyezik_a_muszakkal(muszak: Muszak, eredmeny) -> None:
    slot_perc = sum(s.hossz_perc() for s in eredmeny.slotok)
    blokk_perc = sum(b.hossz_perc() for b in eredmeny.blokkok)
    assert slot_perc + blokk_perc == perc_kulonbseg(muszak.kezdet, muszak.veg)

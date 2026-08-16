"""Szélsőséges esetek a slotgenerátorra (mag/slot/generator.py).

A `test_blokk_generator.py` már fedi a normál Törpilla-ábrákat, a DST-t
és a kivetel_nap ágat (`test_kivetel_napon_nem_general_semmit`) — ez a
fájl kifejezetten a határeseteket célozza: első/utolsó slot, éjfélen
átnyúló műszak, és a nulla hosszú / fordított időablak, ami NEM dobhat
kivételt (a `Muszak` dataclass maga nem validál, a DB-szintű
`CHECK (veg > kezdet)` csak a `mag/repo/`-n át írt sorokra vonatkozik —
ez a teszt a tiszta generátor-függvényt közvetlenül hívja, `mag/repo/`
nélkül).
"""

from __future__ import annotations

from mag.modell.muszak import Muszak
from mag.slot import generator
from mag.slot.blokk import FixBlokk

_STRATEGIA = FixBlokk()


def _muszak(
    kezdet: str,
    veg: str,
    idotartam_perc: int = 10,
    puffer_utana_perc: int = 0,
    min_racs_perc: int = 10,
    foglalhato_arany: float = 1.0,
    blokk_szabaly: dict | None = None,
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
        blokk_szabaly=blokk_szabaly or {"szunetek": []},
    )


# --- első és utolsó slot -------------------------------------------------


def test_elso_slot_pontosan_a_muszak_kezdeten_kezdodik():
    muszak = _muszak("2026-08-18T08:00:00Z", "2026-08-18T09:00:00Z")
    eredmeny = generator.general(muszak, _STRATEGIA)
    assert eredmeny.slotok[0].kezdet == muszak.kezdet


def test_utolso_slot_nem_nyulik_tul_a_muszak_vegen():
    muszak = _muszak("2026-08-18T08:00:00Z", "2026-08-18T09:00:00Z")
    eredmeny = generator.general(muszak, _STRATEGIA)
    assert eredmeny.slotok[-1].veg <= muszak.veg


def test_utolso_slot_nem_general_ha_nem_ferne_ki_pontosan():
    """55 perces műszak, 10 perces slot, 0 puffer → 5 slot fér ki
    (50 perc), az 55. percig nincs hatodik — nem csonka slotot generál."""
    muszak = _muszak("2026-08-18T08:00:00Z", "2026-08-18T08:55:00Z")
    eredmeny = generator.general(muszak, _STRATEGIA)
    assert len(eredmeny.slotok) == 5
    assert eredmeny.slotok[-1].veg == "2026-08-18T08:50:00Z"


# --- éjfélen átnyúló műszak ------------------------------------------------


def test_ejfelen_atnyulo_muszak_helyes_slotszam():
    """22:00–02:00 (+1 nap), 10 perces slot → 4 óra = 24 slot. A kezdet/
    veg teljes ISO-8601 időbélyeg, nem csak óra:perc, ezért az éjfél
    átlépése a generátornak nem külön eset — normál dátumaritmetika."""
    muszak = _muszak("2026-08-18T22:00:00Z", "2026-08-19T02:00:00Z")
    eredmeny = generator.general(muszak, _STRATEGIA)
    assert len(eredmeny.slotok) == 24
    assert eredmeny.slotok[0].kezdet == "2026-08-18T22:00:00Z"
    assert eredmeny.slotok[-1].veg == "2026-08-19T02:00:00Z"


def test_ejfelen_atnyulo_muszak_szunettel_nem_lognak_at_a_hataron():
    muszak = _muszak(
        "2026-08-18T23:30:00Z",
        "2026-08-19T01:00:00Z",
        blokk_szabaly={"szunetek": [{"tipus": "szunet", "hossz_perc": 10, "mintazat": "oranta"}]},
    )
    eredmeny = generator.general(muszak, _STRATEGIA)
    for blokk in eredmeny.blokkok:
        assert muszak.kezdet <= blokk.kezdet
        assert blokk.veg <= muszak.veg


# --- nulla hosszú / fordított időablak ------------------------------------


def test_nulla_hosszu_idoablak_ures_eredmeny_nem_kivetel():
    muszak = _muszak("2026-08-18T08:00:00Z", "2026-08-18T08:00:00Z")
    eredmeny = generator.general(muszak, _STRATEGIA)
    assert eredmeny.kihagyva is False
    assert eredmeny.slotok == []
    assert eredmeny.blokkok == []


def test_forditott_idoablak_ures_eredmeny_nem_kivetel():
    muszak = _muszak("2026-08-18T09:00:00Z", "2026-08-18T08:00:00Z")
    eredmeny = generator.general(muszak, _STRATEGIA)
    assert eredmeny.kihagyva is False
    assert eredmeny.slotok == []
    assert eredmeny.blokkok == []


def test_forditott_idoablak_szunettel_is_ures_nem_kivetel():
    """A szünet-generálás is ciklikus (while True: ... break) — fordított
    ablakon az első iterációban ki kell lépnie, nem szabad végtelen
    ciklusba futnia."""
    muszak = _muszak(
        "2026-08-18T09:00:00Z",
        "2026-08-18T08:00:00Z",
        blokk_szabaly={"szunetek": [{"tipus": "szunet", "hossz_perc": 10, "mintazat": "oranta"}]},
    )
    eredmeny = generator.general(muszak, _STRATEGIA)
    assert eredmeny.slotok == []
    assert eredmeny.blokkok == []


def test_nagyon_rovid_idoablak_ha_egy_slotnyi_sem_fer_ki():
    """5 perces ablak, 10 perces slot — nem fér ki egy slot sem, de ez
    nem kivétel, csak üres eredmény."""
    muszak = _muszak("2026-08-18T08:00:00Z", "2026-08-18T08:05:00Z")
    eredmeny = generator.general(muszak, _STRATEGIA)
    assert eredmeny.slotok == []

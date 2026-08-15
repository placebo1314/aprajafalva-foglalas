"""Műszakblokk-generálási stratégiák (blueprint 4. szakasz, ADR-009).

v1-ben kizárólag a `FixBlokk` stratégia aktív: generál, nem mozgat,
ütközésnél elutasít. A `BlokkStrategia` Protocol azért létezik, hogy a
`MohoAthelyezo` és a `KoltsegAlapu` stratégia később, sémamódosítás nélkül
bekapcsolható legyen (ADR-009 kiváltó feltétele).

A kemény kényszerek (munkajogi minimum, stb.) ellenőrzése SZÁNDÉKOSAN nincs
itt — az a `mag/szabalyok/kenyszerek.py` dolga, a stratégián kívül
(blueprint 4. szakasz).
"""

from __future__ import annotations

from typing import Protocol

from mag.modell.muszak import Blokk, Muszak
from mag.slot._idomatek import hozzaad_perc, perc_kulonbseg


class BlokkStrategia(Protocol):
    def general(self, muszak: Muszak) -> list[Blokk]: ...


class FixBlokk:
    """Generál, nem mozgat, ütközésnél elutasít (v1, ADR-009).

    A `muszak.blokk_szabaly` JSON-ból olvassa a szünet-mintázatot:

        {"szunetek": [
            {"tipus": "szunet"|"ebed", "hossz_perc": int,
             "mintazat": "minden_slot_utan" | "oranta"}
        ]}

    Üres/hiányzó `szunetek` = nincs generált szünet (pl. Hulk Hugan, "szünet
    nélkül"). A szabad sávot a `muszak.foglalhato_arany`-ból generálja, a
    műszak VÉGÉHEZ illesztve, egyetlen blokkként.

    Ismert korlát: ha egyszerre van szünet-mintázat ÉS `foglalhato_arany <
    1.0`, a két generálás nem ellenőrzi egymást átfedésre — v1-ben ez nem
    fordul elő a seed adatban (lásd seed/betolt.py), de ha egy jövőbeli
    profil mindkettőt egyszerre használná szoros időzítéssel, ütközés
    keletkezhet. Ezt a `mag/szabalyok/kenyszerek.py` sem fogja el (az csak
    a műszakon-belüliséget és a szünetmennyiséget nézi, nem az átfedést).
    """

    def general(self, muszak: Muszak) -> list[Blokk]:
        blokkok: list[Blokk] = []
        for szabaly in muszak.blokk_szabaly.get("szunetek", []):
            blokkok.extend(self._szunet_generalas(muszak, szabaly))
        blokkok.extend(self._szabad_sav(muszak))
        return sorted(blokkok, key=lambda b: b.kezdet)

    def _szunet_generalas(self, muszak: Muszak, szabaly: dict) -> list[Blokk]:
        mintazat = szabaly["mintazat"]
        if mintazat == "minden_slot_utan":
            return self._minden_slot_utan(muszak, szabaly)
        if mintazat == "oranta":
            return self._oranta(muszak, szabaly)
        raise ValueError(f"Ismeretlen szünetmintázat: {mintazat!r}")

    def _minden_slot_utan(self, muszak: Muszak, szabaly: dict) -> list[Blokk]:
        """Ciklus: (szolgáltatás-idő) + (szünet), amíg belefér a műszakba."""
        tipus = szabaly["tipus"]
        hossz = szabaly["hossz_perc"]
        cadencia = muszak.idotartam_perc + muszak.puffer_utana_perc
        blokkok = []
        kezdet = muszak.kezdet
        while True:
            szolgaltatas_vege = hozzaad_perc(kezdet, cadencia)
            szunet_vege = hozzaad_perc(szolgaltatas_vege, hossz)
            if szunet_vege > muszak.veg:
                break
            blokkok.append(Blokk(tipus, szolgaltatas_vege, szunet_vege, True, True))
            kezdet = szunet_vege
        return blokkok

    def _oranta(self, muszak: Muszak, szabaly: dict) -> list[Blokk]:
        """Óránként egy blokk: annyi szolgáltatás után, amennyi a szünet
        előtt még belefér a névleges (műszakkezdettől számított) órába."""
        tipus = szabaly["tipus"]
        hossz = szabaly["hossz_perc"]
        cadencia = muszak.idotartam_perc + muszak.puffer_utana_perc
        blokkok = []
        ora_kezdet = muszak.kezdet
        while ora_kezdet < muszak.veg:
            rendelkezesre_all = 60 - hossz
            szolgaltatas_szam = max(rendelkezesre_all // cadencia, 0)
            szunet_kezdet = hozzaad_perc(ora_kezdet, szolgaltatas_szam * cadencia)
            szunet_vege = hozzaad_perc(szunet_kezdet, hossz)
            if szunet_vege > muszak.veg:
                break
            blokkok.append(Blokk(tipus, szunet_kezdet, szunet_vege, True, True))
            ora_kezdet = hozzaad_perc(ora_kezdet, 60)
        return blokkok

    def _szabad_sav(self, muszak: Muszak) -> list[Blokk]:
        if muszak.foglalhato_arany >= 1.0:
            return []
        teljes_perc = perc_kulonbseg(muszak.kezdet, muszak.veg)
        szabad_perc = round(teljes_perc * (1 - muszak.foglalhato_arany))
        if szabad_perc <= 0:
            return []
        kezdet = hozzaad_perc(muszak.veg, -szabad_perc)
        return [Blokk("szabad_sav", kezdet, muszak.veg, True, False)]

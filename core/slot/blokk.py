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
    nélkül"). A szabad sávot a `muszak.foglalhato_arany`-ból generálja —
    NEM egyetlen blokként a műszak végén, hanem óránként arányosan
    elosztva (ADR-011: "elnyeli a csúszást" — ez csak akkor igaz, ha a
    szabad idő a nap egészében jelen van, nem csak a végén).

    A szünet-mintázat ELSŐBBRENDŰ: ha egy adott órában a szünet miatt nem
    marad elég hely a névleges szabad sávnak, a szabad sáv abban az órában
    lerövidül vagy elmarad — a szünet sosem mozdul el, sosem rövidül meg
    emiatt.
    """

    def general(self, muszak: Muszak) -> list[Blokk]:
        szunet_blokkok: list[Blokk] = []
        for szabaly in muszak.blokk_szabaly.get("szunetek", []):
            szunet_blokkok.extend(self._szunet_generalas(muszak, szabaly))

        szabad_sav_blokkok = self._szabad_sav(muszak, szunet_blokkok)
        return sorted(szunet_blokkok + szabad_sav_blokkok, key=lambda b: b.kezdet)

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

    def _szabad_sav(self, muszak: Muszak, szunet_blokkok: list[Blokk]) -> list[Blokk]:
        """Óránként egy szabad sáv blokk: a névleges óra
        `(1 - foglalhato_arany)` hányada, az óra szünettel nem foglalt
        részének a VÉGÉHEZ illesztve. Ha egy órában a szünet miatt nincs
        elég hely, a blokk lerövidül a rendelkezésre álló résznyire, vagy
        — ha nincs szabad rész — teljesen elmarad abban az órában."""
        if muszak.foglalhato_arany >= 1.0:
            return []

        blokkok: list[Blokk] = []
        ora_kezdet = muszak.kezdet
        while ora_kezdet < muszak.veg:
            ora_veg = min(hozzaad_perc(ora_kezdet, 60), muszak.veg)
            ora_hossz = perc_kulonbseg(ora_kezdet, ora_veg)
            cel_hossz = round(ora_hossz * (1 - muszak.foglalhato_arany))

            if cel_hossz > 0:
                resek = self._szabad_reszek(ora_kezdet, ora_veg, szunet_blokkok)
                if resek:
                    res_kezdet, res_veg = resek[-1]
                    hossz = min(cel_hossz, perc_kulonbseg(res_kezdet, res_veg))
                    if hossz > 0:
                        blokk_kezdet = hozzaad_perc(res_veg, -hossz)
                        blokkok.append(Blokk("szabad_sav", blokk_kezdet, res_veg, True, False))

            ora_kezdet = hozzaad_perc(ora_kezdet, 60)
        return blokkok

    @staticmethod
    def _szabad_reszek(
        ora_kezdet: str, ora_veg: str, szunet_blokkok: list[Blokk]
    ) -> list[tuple[str, str]]:
        """Az `[ora_kezdet, ora_veg)` ablakból a rá eső szünetblokkok
        kivágása után maradó szabad részek, kezdet szerint rendezve."""
        erintett = sorted(
            (max(b.kezdet, ora_kezdet), min(b.veg, ora_veg))
            for b in szunet_blokkok
            if b.kezdet < ora_veg and b.veg > ora_kezdet
        )
        resek: list[tuple[str, str]] = []
        kurzor = ora_kezdet
        for k, v in erintett:
            if k > kurzor:
                resek.append((kurzor, k))
            kurzor = max(kurzor, v)
        if kurzor < ora_veg:
            resek.append((kurzor, ora_veg))
        return resek

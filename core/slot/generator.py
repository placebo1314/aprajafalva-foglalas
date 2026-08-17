"""A slotgenerátor.

Sorrend: előbb a blokkok (`BlokkStrategia.general()`), aztán a slotok a
maradék időbe — soha nem generál slotot blokkba (foglalasi-mag skill,
roadmap „Az első tíz lépés" 7. pont: „Első teszteset: az egyórás Törpilla-
ábra.").

A műszak snapshot-mezőit használja (`idotartam_perc`, `puffer_utana_perc`,
`min_racs_perc`) — a törzsadatot nem nézi, azok már befagyasztva vannak a
`Muszak` objektumban (docs/domain.md, "Snapshot"). Kivétel-napra
(`kivetel_nap`) nem generál semmit.

Nincs benne SQL — tiszta számítás (CLAUDE.md, 5. invariáns). A perzisztálás
a `mag/repo/muszak_repo.py` dolga.
"""

from __future__ import annotations

from dataclasses import dataclass

from mag.modell.muszak import Blokk, Muszak, Slot
from mag.slot._idomatek import hozzaad_perc, perc_kulonbseg
from mag.slot.blokk import BlokkStrategia


@dataclass(frozen=True)
class GeneralasEredmeny:
    kihagyva: bool
    kihagyas_oka: str | None
    blokkok: list[Blokk]
    slotok: list[Slot]


def general(
    muszak: Muszak,
    strategia: BlokkStrategia,
    kivetel_napok: frozenset[str] = frozenset(),
) -> GeneralasEredmeny:
    """Egyetlen műszakra generálja a blokkokat és a slotokat.

    `kivetel_napok`: `YYYY-MM-DD` dátumok halmaza (lásd
    `mag/repo/muszak_repo.py::kivetel_napok_lekerdezese`). Ha a műszak
    kezdetének dátuma benne van, nem generál semmit — a bolt aznap zárva
    (blueprint 9. szakasz: „enélkül a slotgenerátor karácsonyra is
    generál").
    """
    datum = muszak.kezdet[:10]
    if datum in kivetel_napok:
        return GeneralasEredmeny(kihagyva=True, kihagyas_oka=datum, blokkok=[], slotok=[])

    blokkok = strategia.general(muszak)
    szabad_szakaszok = _szabad_szakaszok(muszak, blokkok)
    slotok: list[Slot] = []
    for szakasz_kezdet, szakasz_veg in szabad_szakaszok:
        slotok.extend(_slotok_szakaszba(muszak, szakasz_kezdet, szakasz_veg))
    return GeneralasEredmeny(kihagyva=False, kihagyas_oka=None, blokkok=blokkok, slotok=slotok)


def _szabad_szakaszok(muszak: Muszak, blokkok: list[Blokk]) -> list[tuple[str, str]]:
    """A műszak időablakából a blokkok (feltételezve: nem fedik egymást,
    kezdet szerint rendezve) kivágása után maradó szabad szakaszok."""
    szakaszok: list[tuple[str, str]] = []
    kurzor = muszak.kezdet
    for b in blokkok:
        if b.kezdet > kurzor:
            szakaszok.append((kurzor, b.kezdet))
        if b.veg > kurzor:
            kurzor = b.veg
    if kurzor < muszak.veg:
        szakaszok.append((kurzor, muszak.veg))
    return szakaszok


def _grid_kerekites(idopont: str, viszonyitasi_pont: str, racs_perc: int) -> str:
    """`idopont`-ot felfelé kerekíti a `viszonyitasi_pont`-tól számított
    `racs_perc` méretű rácsra — így egy blokk után induló szabad szakasz
    is mindig "kerek" időponton kezdi a slotgenerálást."""
    if racs_perc <= 0:
        return idopont
    eltelt = perc_kulonbseg(viszonyitasi_pont, idopont)
    maradek = eltelt % racs_perc
    if maradek == 0:
        return idopont
    return hozzaad_perc(idopont, racs_perc - maradek)


def _slotok_szakaszba(muszak: Muszak, kezdet: str, veg: str) -> list[Slot]:
    cadencia = muszak.idotartam_perc + muszak.puffer_utana_perc
    slotok: list[Slot] = []
    kurzor = _grid_kerekites(kezdet, muszak.kezdet, muszak.min_racs_perc)
    while True:
        slot_vege = hozzaad_perc(kurzor, muszak.idotartam_perc)
        if slot_vege > veg:
            break
        slotok.append(Slot(kurzor, slot_vege))
        kurzor = hozzaad_perc(kurzor, cadencia)
    return slotok

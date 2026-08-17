"""Kemény kényszerek ellenőrzése a műszakblokkokra — a `BlokkStrategia`-n
KÍVÜL, önálló függvényben.

Blueprint 4. szakasz: "A kemény kényszerek ellenőrzése a stratégián kívül
van — a munkajogi minimumot nem az implementáció dönti el." Ezek
megsértése elutasítás, nem preferencia — szemben a puha preferenciákkal
(időzítés, egyenletes elosztás), amik nem ide, hanem egy jövőbeli
költségfüggvénybe tartoznak.
"""

from __future__ import annotations

from dataclasses import dataclass

from mag.modell.muszak import Blokk, Muszak
from mag.slot._idomatek import perc_kulonbseg

# Munkajogi minimum: 6 óra fölötti műszakban legalább egy 20 perces (vagy
# hosszabb) szünet/ebéd kötelező. Védett kategória — nincs paraméter, ami
# kikapcsolná (blueprint 4. szakasz, CLAUDE.md szellemében). A pontos érték
# a roadmap.md "Nyitott kérdések" szerint még nem végleges, de amíg nincs
# felülvizsgálva ADR-rel, ez a kötelező érték.
MUNKAJOGI_KUSZOB_PERC = 6 * 60
MUNKAJOGI_MIN_SZUNET_PERC = 20

_SZUNETSZERU_TIPUSOK = ("szunet", "ebed")


@dataclass(frozen=True)
class KenyszerSertes:
    szabaly: str
    uzenet: str


def ellenoriz(
    muszak: Muszak,
    blokkok: list[Blokk],
    *,
    min_osszes_szunet_perc: int,
    max_folyamatos_munka_perc: int,
) -> list[KenyszerSertes]:
    """A négy kemény kényszert ellenőrzi, a sértéseket listaként adja
    vissza — sosem dob kivételt, a hívó (pl. a generátor vagy egy
    admin-felület) dönti el, mit kezd velük (elutasítás, magyarázó motor
    bemenete).

    `min_osszes_szunet_perc` és `max_folyamatos_munka_perc` bolt-/
    profilfüggő paraméterek: nincs bennük egyetlen "helyes" érték, ezért a
    hívó adja meg őket — csak a munkajogi minimum hardkódolt, mert az
    védett kategória.
    """
    return [
        *_blokk_a_muszakon_belul(muszak, blokkok),
        *_osszes_szunet(blokkok, min_osszes_szunet_perc),
        *_max_folyamatos_munka(muszak, blokkok, max_folyamatos_munka_perc),
        *_munkajogi_minimum(muszak, blokkok),
    ]


def _blokk_a_muszakon_belul(muszak: Muszak, blokkok: list[Blokk]) -> list[KenyszerSertes]:
    return [
        KenyszerSertes(
            "blokk_muszakon_belul",
            f"A blokk ({b.tipus}, {b.kezdet}–{b.veg}) kilóg a műszak "
            f"({muszak.kezdet}–{muszak.veg}) időablakából.",
        )
        for b in blokkok
        if b.kezdet < muszak.kezdet or b.veg > muszak.veg
    ]


def _osszes_szunet(blokkok: list[Blokk], kuszob: int) -> list[KenyszerSertes]:
    osszesen = sum(b.hossz_perc() for b in blokkok if b.tipus in _SZUNETSZERU_TIPUSOK)
    if osszesen < kuszob:
        return [
            KenyszerSertes(
                "minimum_osszes_szunet",
                f"A műszak összes szünetideje {osszesen} perc, a minimum {kuszob} perc lenne.",
            )
        ]
    return []


def _max_folyamatos_munka(
    muszak: Muszak, blokkok: list[Blokk], kuszob: int
) -> list[KenyszerSertes]:
    """A leghosszabb megszakítás nélküli munkaszakaszt nézi: a műszak
    eleje/vége és a szünet-jellegű blokkok közötti réseket. A szabad sáv
    NEM munkamegszakítás — az alkalmazott ott is szolgálatban van, csak
    nincs előre beosztva rá foglalás (blueprint 4. szakasz)."""
    hatarpontok = [muszak.kezdet]
    for b in sorted(blokkok, key=lambda b: b.kezdet):
        if b.tipus in _SZUNETSZERU_TIPUSOK:
            hatarpontok.append(b.kezdet)
            hatarpontok.append(b.veg)
    hatarpontok.append(muszak.veg)

    sertesek = []
    for i in range(0, len(hatarpontok), 2):
        szakasz_hossz = perc_kulonbseg(hatarpontok[i], hatarpontok[i + 1])
        if szakasz_hossz > kuszob:
            sertesek.append(
                KenyszerSertes(
                    "maximum_folyamatos_munka",
                    f"{szakasz_hossz} perces megszakítás nélküli szakasz "
                    f"({hatarpontok[i]}–{hatarpontok[i + 1]}), a maximum "
                    f"{kuszob} perc lenne.",
                )
            )
    return sertesek


def _munkajogi_minimum(muszak: Muszak, blokkok: list[Blokk]) -> list[KenyszerSertes]:
    muszak_hossz = perc_kulonbseg(muszak.kezdet, muszak.veg)
    if muszak_hossz <= MUNKAJOGI_KUSZOB_PERC:
        return []
    van_eleg_hosszu = any(
        b.tipus in _SZUNETSZERU_TIPUSOK and b.hossz_perc() >= MUNKAJOGI_MIN_SZUNET_PERC
        for b in blokkok
    )
    if van_eleg_hosszu:
        return []
    return [
        KenyszerSertes(
            "munkajogi_minimum",
            f"{muszak_hossz} perces műszakhoz ({MUNKAJOGI_KUSZOB_PERC} perc fölött) "
            f"legalább egy {MUNKAJOGI_MIN_SZUNET_PERC} perces szünet kötelező, "
            "de egyik blokk sem éri el ezt a hosszt.",
        )
    ]

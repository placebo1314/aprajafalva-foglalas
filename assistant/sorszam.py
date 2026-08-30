"""SORSZÁMOS HIVATKOZÁS — „a másodikat", „az elsőt kérem", „az utolsó
jó lesz".

**Ez a leggyakoribb természetes válasz egy listára**, és eddig a
rendszer egyikét sem értette: a felajánlott időpontok gombként
jelentek meg, a gomb szövege pedig egy ISO-időbélyeg volt. Aki
begépelte, hogy „a második", visszakérdezést kapott.

## Miért determinisztikus réteg, és miért nem a modell

A sorszám ZÁRT halmaz: annyi lehetőség van, ahány jelöltet MI magunk
ajánlottunk fel az előző fordulóban. Nincs mit értelmezni rajta, és
egy elrontott sorszám a legrosszabb fajta hiba — nem visszakérdezést
okoz, hanem MÁS IDŐPONTOT foglal le, mint amit a vásárló kért. A
felismerés ezért mintaillesztés, a döntés pedig az orchestratoré, ami
egyedül ismeri a felajánlott jelölteket (`aktualis_jeloltek`).

A modell ettől még LÁTJA a sorszámokat: a felület a felajánlott
időpontokat sorszámozva teszi be a beszélgetés-előzménybe
(`ui/vasarlo.py`), tehát ha a determinisztikus réteg mégsem ismerné
fel az alakot, a modellnek van mire hivatkoznia.

## Amit szándékosan NEM ismer fel

- **Mennyiséget**: „két időpontot kérek" — az nem hivatkozás, hanem
  csoportos foglalás, ami ebben a rendszerben nem létezik (blueprint
  7.: egy beszélgetésben egy helyre egy slot).
- **Sorszámot jelölő szót MÁS szerepben**: „első alkalommal járok
  itt", „elsősorban délelőtt". A minták ezért kötött szerkezetűek: a
  sorszóhoz vagy tárgyrag, vagy egy szűk, zárt utótag-készlet
  („jó lesz", „kérem", „legyen", „azt") tartozik — vagy a mondat maga
  ennyi.
- **Tartományon kívüli sorszámot**: ha három időpontot ajánlottunk és
  a vásárló a hatodikat kéri, a válasz `None` (a hívó visszakérdez).
  Nem a legközelebbire kerekítünk: a „hatodik" nem elírás, hanem
  félreértés, és azt kérdéssel kell tisztázni.
"""

from __future__ import annotations

import re

from assistant.interpreter.normalizalo import normalizal

# A sorszónevek 1-től 10-ig, tővel (a toldalékot a minta engedi meg).
# Tíznél tovább nincs értelme: ennyi jelöltet sosem ajánlunk fel, és
# ennél hosszabb listát senki nem tart fejben.
_SORSZAVAK: dict[str, int] = {
    "első": 1,
    "elso": 1,
    "legelső": 1,
    "legelso": 1,
    "második": 2,
    "masodik": 2,
    "harmadik": 3,
    "negyedik": 4,
    "ötödik": 5,
    "otodik": 5,
    "hatodik": 6,
    "hetedik": 7,
    "nyolcadik": 8,
    "kilencedik": 9,
    "tizedik": 10,
}

# Az UTOLSÓ külön eset: nem szám, hanem pozíció — a jelöltek számától
# függ, mire mutat.
_UTOLSO_SZAVAK = frozenset({"utolsó", "utolso", "legutolsó", "legutolso"})

# A sorszó UTÁN állhat toldalék (tárgyrag, határozó) — ezeket a szótő
# után engedjük meg, mert a magyar toldalékolás sokféle:
# „másodikat", „másodikra", „második", „másodikkal".
#
# **Négy karakter a felső határ, és ez nem önkényes**: a toldalékok
# ennél rövidebbek, az ÖSSZETÉTELEK viszont hosszabbak — az
# „elsősorban" (`első` + `sorban`) és az „elsősegély" pontosan így esik
# ki. Egy megengedőbb minta ezekre is illeszkedne, és a mondatból
# időpont-választás lenne.
_TOLDALEK = r"[a-záéíóöőúüű]{0,4}"

# A mondat, amiben a sorszó áll, LEGFELJEBB ennyi szó lehet. Egy
# sorszámos hivatkozás rövid („az utolsó jó lesz"); egy hosszú
# mondatban ugyanaz a szó jóval nagyobb eséllyel jelent mást
# („első alkalommal járok itt, és szeretnék időpontot kedd délelőttre").
_MAX_SZO = 6

# A sorszó UTÁN már csak ezek a szavak állhatnak — zárt lista.
#
# **Miért kell a hosszkorlát MELLÉ ez is.** Az „első alkalommal járok
# itt" hat szónál rövidebb, mégsem választás. A különbség nem a
# hosszban van, hanem abban, hogy MI KÖVETI a sorszót: egy
# elfogadó/kérő fordulat („jó lesz", „kérem") vagy a mondat vége — vagy
# valami egészen más, ami elárulja, hogy a szó itt nem hivatkozás.
# A tévedés ára egy ROSSZ FOGLALÁS, ezért itt a szűk minta a helyes
# irány (ugyanaz az aszimmetria, mint a kapuőrnél, csak fordítva).
_ELFOGADOTT_UTAN = frozenset(
    {
        "jó",
        "jo",
        "lesz",
        "kérem",
        "kerem",
        "kérek",
        "kerek",
        "kellene",
        "kell",
        "legyen",
        "az",
        "azt",
        "megfelel",
        "elég",
        "eleg",
        "tökéletes",
        "tokeletes",
        "érdekel",
        "erdekel",
        "maradjon",
        "marad",
        "választom",
        "valasztom",
        "nekem",
        "köszönöm",
        "koszonom",
        "szépen",
        "szepen",
        "is",
    }
)


def _jelolt_szam(szo: str, darab: int) -> int | None:
    # A SZÁMJEGYES alakot a nyers szón nézzük: ott a pont maga a
    # sorszám jele („2."), tehát nem szabad levágni.
    #
    # A puszta szám (pl. „10") szándékosan NEM elég: az lehet óra is
    # („10 körül"), és a tévedés ára itt egy rossz foglalás.
    talalat = re.fullmatch(r"(\d{1,2})(?:\.|-[a-záéíóöőúüű]{1,4})", szo.strip(",!?:;"))
    if talalat:
        return int(talalat[1])

    also = szo.strip(".,!?:;-").lower()
    for alak in _UTOLSO_SZAVAK:
        if re.fullmatch(alak + _TOLDALEK, also):
            return darab
    for alak, ertek in _SORSZAVAK.items():
        if re.fullmatch(alak + _TOLDALEK, also):
            return ertek
    return None


def sorszam_hivatkozas(mondat: str, darab: int) -> int | None:
    """A mondatban hivatkozott jelölt 1-alapú sorszáma, vagy `None`.

    `darab`: hány jelöltet ajánlottunk fel — ez adja meg az „utolsó"
    jelentését, és ez a felső határ. Tartományon kívüli sorszámra
    `None` megy vissza, hogy a hívó visszakérdezhessen (l. modul
    docstring, „Amit szándékosan nem ismer fel")."""
    if darab <= 0:
        return None
    szavak = normalizal(mondat).strip().split()
    if not szavak or len(szavak) > _MAX_SZO:
        return None

    for i, szo in enumerate(szavak):
        szam = _jelolt_szam(szo, darab)
        if szam is None:
            continue
        maradek = [s.strip(".,!?:;").lower() for s in szavak[i + 1 :]]
        if any(s and s not in _ELFOGADOTT_UTAN for s in maradek):
            return None
        return szam if 1 <= szam <= darab else None
    return None

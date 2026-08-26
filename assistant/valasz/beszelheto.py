"""BESZÉLHETŐ KIMENETI MÓD — a hangcsatorna első valódi előkészítése
(M6, blueprint 7. szakasz).

A `valasz` modulnak két kimeneti módja van:

| Mód | Kinek | Mit ad |
|---|---|---|
| `szoveges` | képernyő | a mai viselkedés, változatlanul |
| `beszelheto` | felolvasás | egész mondatok, kimondott számokkal |

**A beszélhető mód nem stílus, hanem KÉNYSZER-készlet.** Öt szabály,
mindegyik mögött egy konkrét hangcsatorna-hiba:

1. **Nincs felsorolás, nincs markdown, nincs zárójel** — egész
   mondatok. Egy felsorolásjelet a TTS vagy felolvas ("mínusz"), vagy
   elnyel, és akkor a szerkezet vész el.
2. **A számok kimondva** ("nyolc óra tizenöt", nem "08:15";
   "december huszonkettedikén", nem "2026-12-22"). L. `szamok.py`.
3. **Egy kérdés fordulónként** — akadálymentességi szabály (blueprint
   7. szakasz, "Négy technika" 4. pont), nem stílus. Két kérdésre a
   vásárló az egyikre válaszol, és nem tudjuk, melyikre.
4. **Legfeljebb két mondat válaszonként** — hangon a hosszú válasz
   barge-int szül: a vásárló belevág, az ASR a saját hangunkat is
   hallja, és a forduló összeomlik.
5. **Nincs időpont-FELSOROLÁS.** Három időpont felolvasva
   megjegyezhetetlen. Helyette: a legkorábbi, egy alternatíva, és egy
   kérdés (`assistant/valasz/__init__.py::ajanlat_mondat`).

## Két rétegben érvényesül

- **Sablon-szinten**: ahol a szöveges mondat hangon rossz (túl hosszú,
  két kérdés, felületre hivatkozik), a `sablonok.py` külön
  `*_beszelheto` bejegyzést tartalmaz. Ez az elsődleges út — a jó
  megfogalmazást nem lehet automatikusan előállítani.
- **Kimeneti kapuként**: minden beszélhető mondat átmegy a
  `beszelhetove()` függvényen, ami a maradék számot, zárójelet és
  írásjelet is elintézi. Ez a HÁLÓ, nem a fő út: arra való, hogy egy
  új, elfelejtett sablon se tudjon számjegyet kijuttatni.

## Amit ez a modul NEM csinál

Nem szintetizál hangot, nem detektál fordulóhatárt, nem kezel
barge-int. Ez szövegoldali előkészítés — az ASR, a TTS, a
turn-detection és a barge-in konfiguráció, nem építés
(`docs/roadmap.md`, M6).
"""

from __future__ import annotations

import re

from assistant.valasz import szamok

# A beszélhető kimenetben TILTOTT karakterosztályok. A lista zárt, és a
# `tiltott_jelek()` ezt hajtja végre — a tesztek ugyanezt hívják, tehát
# a szabály egy helyen van definiálva.
TILTOTT_MINTAK: list[tuple[str, re.Pattern]] = [
    ("számjegy", re.compile(r"\d")),
    # Kötőjel ÉS gondolatjel: az előbbit a TTS szóhatárnak, az utóbbit
    # szünetnek olvassa — a mondat ritmusa mindkettőtől eltörik.
    ("kötőjel vagy gondolatjel", re.compile(r"[-–—]")),
    ("zárójel", re.compile(r"[()\[\]{}]")),
    # Felsorolásjel sor elején (a `•`, `*`, `–` bármelyike) vagy
    # számozott lista.
    ("felsorolásjel", re.compile(r"(?m)^\s*[•*·]|^\s*\d+[.)]\s")),
    ("markdown-jelölés", re.compile(r"[*_`#|]")),
]

MAX_MONDAT = 2

# Mondathatár: írásjel + szóköz vagy sorvég. A rövidítések (pl. „kb.")
# ezt megzavarnák — a `valasz` sablonjaiban nincs ilyen, és ha lesz, a
# helye a beszélhető változatban amúgy sem volna.
_MONDATHATAR = re.compile(r"(?<=[.!?…])\s+")

_ISO_IDOBELYEG = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2})(?::\d{2})?Z?")
_ISO_DATUM = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
_IDO_TARTOMANY = re.compile(r"\b(\d{1,2}):(\d{2})\s*[-–—]\s*(\d{1,2}):(\d{2})\b")
_IDO = re.compile(r"\b(\d{1,2}):(\d{2})\b")
_EGESZ_SZAM = re.compile(r"\b\d+\b")
_ZAROJELES = re.compile(r"\s*[(\[{][^)\]}]*[)\]}]")


def szamok_kimondva(szoveg: str) -> str:
    """Minden számjegy-alakú részt kimondott alakra cserél. A sorrend
    számít: a bővebb minta előbb, különben az ISO-dátumból három külön
    szám lenne.

    A `szamok.MAX_SZAM` feletti egész számokat BETŰZI, nem kimondja —
    egy hatjegyű szám ebben a rendszerben azonosító, nem mennyiség."""
    szoveg = _ISO_IDOBELYEG.sub(
        lambda t: (
            f"{szamok.datum_szoval(f'{t[1]}-{t[2]}-{t[3]}')} "
            f"{szamok.idopont_kor(int(t[4]), int(t[5]))}"
        ),
        szoveg,
    )
    szoveg = _ISO_DATUM.sub(lambda t: szamok.datum_szoval(f"{t[1]}-{t[2]}-{t[3]}"), szoveg)
    # Időtartomány: „nyolc órától nyolc óra harmincig". A ragozott alak
    # itt kézzel van megírva, mert a rag a KIMONDOTT alakhoz tapad.
    szoveg = _IDO_TARTOMANY.sub(
        lambda t: (
            f"{szamok.szam_szoval(int(t[1]))} órától "
            f"{szamok.ora_perc_szoval(int(t[3]), int(t[4]))}ig"
        ),
        szoveg,
    )
    szoveg = _IDO.sub(lambda t: szamok.ora_perc_szoval(int(t[1]), int(t[2])), szoveg)
    szoveg = szamok.KOD_MINTA.sub(lambda t: szamok.betuzve(t[0]), szoveg)
    szoveg = _EGESZ_SZAM.sub(_egesz_szam_kimondva, szoveg)
    return szoveg


def _egesz_szam_kimondva(talalat: re.Match) -> str:
    ertek = int(talalat[0])
    if ertek > szamok.MAX_SZAM:
        return szamok.betuzve(talalat[0])
    return szamok.szam_szoval(ertek)


def beszelhetove(szoveg: str) -> str:
    """Egy mondat (vagy néhány mondat) beszélhető alakja — a kimeneti
    KAPU, l. modul docstring.

    A zárójeles részt **eldobja**, nem kibontja: a zárójel definíció
    szerint mellékes megjegyzés, és hangon a mellékes megjegyzés a
    legdrágább — megnyújtja a fordulót, és a lényeget elnyomja. Ha egy
    közlés fontos, nem zárójelben a helye."""
    if not szoveg:
        return ""
    szoveg = _ZAROJELES.sub("", szoveg)
    szoveg = szamok_kimondva(szoveg)
    # Felsorolásjelek és markdown-jelölés. A sor eleji „- " a
    # leggyakoribb; a szó közbeni kötőjel (e-mail) szóközre válik, mert
    # kimondva úgyis két szó.
    szoveg = re.sub(r"(?m)^\s*[-–—•*·]\s+", "", szoveg)
    szoveg = re.sub(r"(?m)^\s*\d+[.)]\s+", "", szoveg)
    szoveg = re.sub(r"[*_`#|]", "", szoveg)
    # Gondolatjel mondaton belül: vessző lesz belőle (a szünet
    # szándéka megmarad), a kötőjel szóköz.
    szoveg = re.sub(r"\s*[–—]\s*", ", ", szoveg)
    szoveg = szoveg.replace("-", " ")
    # Sortörés is mondathatár — a felolvasó különben egybemondja.
    szoveg = re.sub(r"\s*\n+\s*", " ", szoveg)
    szoveg = re.sub(r"\s+([,.!?…])", r"\1", szoveg)
    szoveg = re.sub(r",\s*,", ",", szoveg)
    szoveg = re.sub(r"\s{2,}", " ", szoveg).strip()
    # NAGY KEZDŐBETŰ. Nem esztétika: a beszélhető mondatok jó része
    # behelyettesítéssel kezdődik („{idopont} foglalnám le"), és a
    # kimondott dátum kisbetűs („december huszonkettedikén"). Írásban ez
    # hanyagságnak látszik, a szöveges próbán pedig épp azt a bizalmat
    # rontja, amiért a mód szövegben is kipróbálható.
    return szoveg[:1].upper() + szoveg[1:]


def mondatok(szoveg: str) -> list[str]:
    """A szöveg mondatai. Üres elem nincs a listában."""
    return [m.strip() for m in _MONDATHATAR.split(szoveg.strip()) if m.strip()]


def _kerdes_e(mondat: str) -> bool:
    return mondat.rstrip().endswith("?")


def fordulo_szoveg(reszek: list[str]) -> str:
    """Egy FORDULÓ teljes beszélhető válasza a rendszer aznapi
    mondataiból — a 3. és 4. szabály itt érvényesül.

    A választás nem "az első kettő", hanem:

    - **ha van kérdés, az UTOLSÓ kérdés marad**, és az kerül a végére.
      Miért az utolsó: a beszélgetés a legfrissebb kérdésnél tart, a
      korábbi kérdés ilyenkor már meg is válaszolódott (pl. a
      visszakérdezés után jövő ajánlat-kérdés). Egy korábbi kérdést
      hagyni a végén azt jelentené, hogy a vásárló egy már lezárt
      dologra felel.
    - **elé egy állítás kerül**, a kérdés előtti utolsó — az hordozza a
      tényt, amire a kérdés vonatkozik.
    - **kérdés nélkül az utolsó két állítás** marad.

    Ez veszteséges, és annak is kell lennie: a hangcsatornán a
    fordulónkénti két mondat nem cél, hanem korlát. Amit itt elveszítünk,
    azt a beszélgetés következő fordulója kérdezheti vissza — amit egy
    hatmondatos monológgal veszítenénk el, az maga a beszélgetés."""
    osszes: list[str] = []
    for resz in reszek:
        osszes.extend(mondatok(beszelhetove(resz)))
    if not osszes:
        return ""

    kerdes_indexek = [i for i, m in enumerate(osszes) if _kerdes_e(m)]
    if kerdes_indexek:
        utolso = kerdes_indexek[-1]
        allitasok = [m for i, m in enumerate(osszes[:utolso]) if not _kerdes_e(m)]
        valasztott = ([allitasok[-1]] if allitasok else []) + [osszes[utolso]]
    else:
        valasztott = osszes[-MAX_MONDAT:]
    return " ".join(valasztott[-MAX_MONDAT:])


def tiltott_jelek(szoveg: str) -> list[str]:
    """`[]`, ha a szöveg megfelel a beszélhető mód formai szabályainak —
    különben a megsértett szabályok nevei.

    A tesztek ezt hívják MINDEN beszélhető kimenetre
    (`tests/egyseg/test_beszelheto.py`), és a hívó kód is hívhatja, ha
    egyszer valódi TTS elé kerül a szöveg."""
    return [nev for nev, minta in TILTOTT_MINTAK if minta.search(szoveg)]


def szabalyos(szoveg: str) -> bool:
    """A teljes formai ellenőrzés: tiltott jel nincs, legfeljebb két
    mondat, legfeljebb egy kérdés."""
    if tiltott_jelek(szoveg):
        return False
    darabok = mondatok(szoveg)
    if len(darabok) > MAX_MONDAT:
        return False
    return sum(1 for m in darabok if _kerdes_e(m)) <= 1

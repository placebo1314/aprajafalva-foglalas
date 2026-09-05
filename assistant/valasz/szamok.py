"""SZÁMOK KIMONDVA — magyar számnevek, dátumok, órák és betűzés.

Ez a modul **csak adat és leképezés**: számból szó, dátumból mondható
dátum, kódból betűsor. Nincs benne döntés, nincs benne modellhívás — a
`beszelheto.py` és az `assistant/valasz/__init__.py` használja
(l. a `beszelheto` kimeneti mód szabályait).

## Miért kell ez egyáltalán

Hangcsatornán a `08:15` felolvasása a TTS dolga lenne — csakhogy a
magyar TTS-ek pontosan ezen a ponton szoktak elesni ("nulla nyolc kettőspont
tizenöt"), és ami rosszabb: a hiba NÉMÁN történik, mert a szöveg
helyesnek látszik. Ezért a számokat mi mondjuk ki, determinisztikusan,
MIELŐTT a szöveg elhagyja a rendszert. Így szöveges csatornán is
látszik, mit fog hallani a vásárló — a beszélhető mód épp ettől
tesztelhető szövegben (`docs/TESZTELES.md`).

## Amit szándékosan nem tud

- **Nincs helyesírási kötőjel.** A magyar helyesírás szerint
  „kétezer-huszonhat"; itt szóköz áll, mert a beszélhető kimenetben
  kötőjel nem lehet (a TTS gondolatjelnek olvashatja, és szünetet tart).
  Ez a mód KIMONDOTT szöveget állít elő, nem helyesírási mintát.
- **Nincs évszám a dátumban.** A „december huszonkettedikén" ugyanaz
  marad év nélkül; egy foglalási beszélgetésben az év sosem kérdés (a
  keresési ablak hetes nagyságrendű), kimondva viszont hosszú és
  fölösleges.
- **Nincs 3999 feletti szám.** Ami ennél nagyobb, az ebben a
  rendszerben nem mennyiség, hanem azonosító — azt betűzni kell
  (`betuzve`), nem kimondani.
"""

from __future__ import annotations

import re

# A kimondott egyesek. A 2 KÉTFÉLE: önállóan „kettő" (a „kettő" és a
# „hét" félrehallása a leggyakoribb magyar telefonos hiba, ezért
# önállóan mindig a hosszú alak), összetételben „két" (kétszáz, kétezer).
_EGYESEK = (
    "nulla",
    "egy",
    "kettő",
    "három",
    "négy",
    "öt",
    "hat",
    "hét",
    "nyolc",
    "kilenc",
)
_OSSZETETELBEN = {2: "két"}

_TIZESEK = {
    2: "húsz",
    3: "harminc",
    4: "negyven",
    5: "ötven",
    6: "hatvan",
    7: "hetven",
    8: "nyolcvan",
    9: "kilencven",
}

# 11-19 „tizen-", 21-29 „huszon-" — a 10 és a 20 önálló alakja más.
_TIZEN = "tizen"
_HUSZON = "huszon"

MAX_SZAM = 3999


def _osszetetelben(n: int) -> str:
    return _OSSZETETELBEN.get(n, _EGYESEK[n])


def szam_szoval(n: int) -> str:
    """Egész szám kimondva, 0-tól `MAX_SZAM`-ig. Ezen kívül `ValueError`
    — a némán rossz kimenet (pl. csonkolás) rosszabb, mint a hangos
    hiba, mert a felolvasott mondat helyesnek hangzana."""
    if not isinstance(n, int) or isinstance(n, bool):
        raise ValueError(f"csak egész szám mondható ki: {n!r}")
    if n < 0 or n > MAX_SZAM:
        raise ValueError(f"a kimondható tartomány 0..{MAX_SZAM}: {n}")

    if n < 10:
        return _EGYESEK[n]
    if n == 10:
        return "tíz"
    if n < 20:
        return _TIZEN + _EGYESEK[n - 10]
    if n == 20:
        return "húsz"
    if n < 30:
        return _HUSZON + _EGYESEK[n - 20]
    if n < 100:
        maradek = n % 10
        return _TIZESEK[n // 10] + (_EGYESEK[maradek] if maradek else "")
    if n < 1000:
        szazak = n // 100
        eleje = "száz" if szazak == 1 else _osszetetelben(szazak) + "száz"
        maradek = n % 100
        return eleje + (szam_szoval(maradek) if maradek else "")
    ezrek = n // 1000
    eleje = "ezer" if ezrek == 1 else _osszetetelben(ezrek) + "ezer"
    maradek = n % 1000
    # Szóköz, nem kötőjel — l. modul docstring.
    return eleje + (" " + szam_szoval(maradek) if maradek else "")


# A hónap napjai kimondva, HELYHATÁROZÓS alakban („huszonkettedikén").
# Kézzel írt, 31 elemű tábla: a magyar sorszámnév-képzés annyi
# kivételt tartalmaz (elsején, másodikán, huszadikán), hogy a szabály
# hosszabb és törékenyebb lenne, mint a felsorolás.
_NAPOK = (
    "elsején",
    "másodikán",
    "harmadikán",
    "negyedikén",
    "ötödikén",
    "hatodikán",
    "hetedikén",
    "nyolcadikán",
    "kilencedikén",
    "tizedikén",
    "tizenegyedikén",
    "tizenkettedikén",
    "tizenharmadikán",
    "tizennegyedikén",
    "tizenötödikén",
    "tizenhatodikán",
    "tizenhetedikén",
    "tizennyolcadikán",
    "tizenkilencedikén",
    "huszadikán",
    "huszonegyedikén",
    "huszonkettedikén",
    "huszonharmadikán",
    "huszonnegyedikén",
    "huszonötödikén",
    "huszonhatodikán",
    "huszonhetedikén",
    "huszonnyolcadikán",
    "huszonkilencedikén",
    "harmincadikán",
    "harmincegyedikén",
)

_HONAPOK = (
    "január",
    "február",
    "március",
    "április",
    "május",
    "június",
    "július",
    "augusztus",
    "szeptember",
    "október",
    "november",
    "december",
)

_NAPNEVEK = ("hétfőn", "kedden", "szerdán", "csütörtökön", "pénteken", "szombaton", "vasárnap")


def nap_szoval(nap: int) -> str:
    """A hónap napja helyhatározós alakban: 22 → „huszonkettedikén"."""
    if not 1 <= nap <= 31:
        raise ValueError(f"nem létező nap: {nap}")
    return _NAPOK[nap - 1]


def datum_szoval(iso_datum: str, *, napnevvel: bool = False) -> str:
    """`"2026-12-22"` → `"december huszonkettedikén"`.

    `napnevvel=True` esetén a hét napja is elhangzik („kedden, december
    huszonkettedikén") — hangon ez sokat segít, mert a vásárló a hét
    napját tartja fejben, nem a dátumot. Alapból mégis KI van kapcsolva:
    a napnév csak akkor mondható, ha a dátum ténylegesen fel van oldva
    naptárra, és ezt a hívónak kell tudnia, nem ennek a modulnak."""
    ev, honap, nap = (int(resz) for resz in iso_datum[:10].split("-"))
    szoveg = f"{_HONAPOK[honap - 1]} {nap_szoval(nap)}"
    if napnevvel:
        from datetime import date

        szoveg = f"{_NAPNEVEK[date(ev, honap, nap).weekday()]}, {szoveg}"
    return szoveg


def ora_perc_szoval(ora: int, perc: int = 0) -> str:
    """`(8, 15)` → `"nyolc óra tizenöt"`; `(8, 0)` → `"nyolc óra"`.

    Ez a KIJELENTŐ alak („nyolc óra tizenötkor kezdünk" helyett „az
    időpont nyolc óra tizenöt")."""
    alap = f"{szam_szoval(ora)} óra"
    return alap if perc == 0 else f"{alap} {szam_szoval(perc)}"


def idopont_kor(ora: int, perc: int = 0) -> str:
    """`(8, 0)` → `"nyolc órakor"`; `(9, 30)` → `"kilenc harminckor"`.

    A `-kor` ragos alak — ez hangzik természetesnek a felajánlásban
    („a legkorábbi nyolc órakor van")."""
    if perc == 0:
        return f"{szam_szoval(ora)} órakor"
    return f"{szam_szoval(ora)} {szam_szoval(perc)}kor"


def idopont_rovid(iso: str) -> str:
    """Teljes ISO-időbélyeg RÖVID, olvasható alakja:
    `"2026-12-21 07:15 (UTC)"`.

    A SZÖVEGES módé — ott a képernyő a valóság, és a pontos, gépi alak
    egyértelműbb, mint a kimondott. A beszélhető alak az
    `ido_iso_szoval` (ott az „UTC" felolvasva csak zavarna).

    Miért kell egyáltalán: amikor MI választunk a vásárló helyett
    („válassz te"), a jelölt-gombok eltűnnek a képernyőről — a
    megerősítés-kérdésnek ilyenkor ki kell mondania, melyik időpontról
    van szó, különben a vásárló vakon nyomna igent."""
    return f"{iso[:10]} {iso[11:16]} (UTC)"


def ido_iso_szoval(iso: str, *, kor: bool = True) -> str:
    """Teljes ISO-időbélyeg (`"2026-12-22T08:00:00Z"`) mondható alakja:
    `"december huszonkettedikén nyolc órakor"`.

    **Az időzóna kimarad a kimondásból.** Nem azért, mert nem számít —
    hanem mert a vásárlónak a HELYI idő a valóság, és egy „UTC" szó
    felolvasva pontosan azt a bizonytalanságot szüli, amit el akarunk
    kerülni. A helyi időre váltás a megjelenítő réteg dolga (CLAUDE.md
    4. invariáns), és ez a függvény azt kapja, amit kap."""
    datum_resz = datum_szoval(iso[:10])
    ora, perc = int(iso[11:13]), int(iso[14:16])
    ido_resz = idopont_kor(ora, perc) if kor else ora_perc_szoval(ora, perc)
    return f"{datum_resz} {ido_resz}"


# A magyar betűnevek — foglalási kód és bármilyen azonosító
# felolvasásához. Ezek nem "helyesírási" alakok, hanem az, ahogy a
# betűt KIMONDJUK.
_BETUNEVEK = {
    "a": "á",
    "b": "bé",
    "c": "cé",
    "d": "dé",
    "e": "é",
    "f": "ef",
    "g": "gé",
    "h": "há",
    "i": "í",
    "j": "jé",
    "k": "ká",
    "l": "el",
    "m": "em",
    "n": "en",
    "o": "ó",
    "p": "pé",
    "q": "kú",
    "r": "er",
    "s": "es",
    "t": "té",
    "u": "ú",
    "v": "vé",
    "w": "dupla vé",
    "x": "iksz",
    "y": "ipszilon",
    "z": "zé",
}


def betuzve(kod: str) -> str:
    """Azonosító karakterenként kimondva: `"28SFL8RZ"` →
    `"kettő nyolc es ef el nyolc er zé"`.

    **Kód nem szám.** A `28SFL8RZ`-t „huszonnyolc"-ként kimondani
    értelmezhetetlenné teszi a visszaolvasásnál — a vásárlónak
    karakterenként kell tudnia leírni. Ezért itt a számjegyek is
    EGYENKÉNT hangzanak el."""
    darabok = []
    for karakter in kod:
        also = karakter.lower()
        if karakter.isdigit():
            darabok.append(_EGYESEK[int(karakter)])
        elif also in _BETUNEVEK:
            darabok.append(_BETUNEVEK[also])
        # Minden más (kötőjel, szóköz, írásjel) kimarad: kimondva
        # zajt csinálna, a kód azonosításához pedig nem kell.
    return " ".join(darabok)


# Egy „kódnak" látszó token: csupa nagybetű/számjegy, legalább ennyi
# karakter, és van benne számjegy. A foglalási kód ilyen (`28SFL8RZ`) —
# egy közönséges nagybetűs szó ("TÖRPILLA") nem, mert nincs benne
# számjegy.
KOD_MINTA = re.compile(r"\b(?=[A-Z0-9]*\d)[A-Z0-9]{4,}\b")

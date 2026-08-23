"""Redaktálás TÁROLÁS ELŐTT (ADR-005, `adatvedelem` skill, CLAUDE.md
2. invariáns: "nyers vásárlóazonosító soha nem kerül lemezre, logba vagy
trace-be").

**Miért most készült el.** A `naplo/probak.jsonl` (`ui/vasarlo.py::
_proba_naplo_ir`) eddig a vásárló mondatát NYERSEN írta lemezre. Amíg a
próbamondatokat mi magunk írtuk, ez nem látszott hézagnak — a
robusztussági halmaz (`tests/golden/robusztus.yaml`, "személyes adat"
kategória) viszont pont azt méri, mi történik, ha valaki KÉRETLENÜL
bediktálja a telefonszámát vagy a személyi számát. Ott ez azonnal
invariánssértés: a szám lemezre kerül, és soha nem kértük.

**Mit tud és mit nem — kimondva.** Ez egy MINTAILLESZTŐ redaktáló, nem
névfelismerő. A számformátumok (telefon, TAJ, adóazonosító, személyi
igazolvány, e-mail, bankkártya) zárt, jól leírható alakúak — ezeket
megbízhatóan fogja. A SZEMÉLYNÉV nem ilyen: nincs olyan minta, ami a
"Marika" szót megkülönböztetné bármelyik másik szótól anélkül, hogy
névlistát tartana. Amit itt a névre teszünk, az szűk és
szerkezet-alapú ("a Marika vagyok", "Kovács János vagyok", "a nevem
…") — a bemutatkozó fordulatot fogja meg, nem a nevet általában. Ennek
a korlátnak a helye a `docs/ALTALANOSITAS.md`, nem egy csendben
bővülő névlista.

**A redaktálás IRÁNYA egyirányú.** Ez a modul nem hash, nem
visszafejthető: a kimenetből az eredeti érték nem áll elő. Ahol
visszakereshető azonosító kell (foglalás vásárlóhoz kötése), ott a
`privacy/hash_ideiglenes.py` a helyes eszköz, nem ez.

**Amit szándékosan NEM redaktál:** a foglalási kódot. Az nem személyes
adat (a rendszer állítja elő, nem a vásárló hozza), és a napló pont
attól használható hibakereséshez, hogy a kód benne marad. A
`_FOGLALASI_KOD_ALAK` kivétel ezt védi meg attól, hogy egy tágabb
azonosító-minta elnyelje."""

from __future__ import annotations

import re

# A helyettesítő címkék — zárt halmaz, hogy a napló olvasója lássa, MI
# volt ott, anélkül hogy megtudná, mi volt az ÉRTÉKE.
TELEFON = "<TELEFON>"
AZONOSITO = "<AZONOSITO>"
EMAIL = "<EMAIL>"
BANKKARTYA = "<BANKKARTYA>"
NEV = "<NEV>"

# Foglalási kód: PONTOSAN 8 karakter a kód zárt ábécéjéből. Ezt NEM
# redaktáljuk — l. modul docstring.
#
# **Az ábécé forrása a `core/repo/foglalas_repo.py::_CODE_ABC`** (nincs
# benne O/0 és I/1 — hangban félreolvasható párok). Itt szándékosan MÁSOLAT
# van, nem import: a `privacy/` önálló modul, nem függhet a `core/`-tól
# (CLAUDE.md, "Modulhatárok"). A szétdriftelést nem a hivatkozás, hanem
# egy TESZT akadályozza meg (`tests/egyseg/test_redakcio.py::
# test_foglalasi_kod_abece_egyezik_a_maggal`) — ha a mag ábécéje
# megváltozik, az a teszt bukik, nem a redaktálás romlik el csendben.
_FOGLALASI_KOD_ABC = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
_FOGLALASI_KOD_HOSSZ = 8
_FOGLALASI_KOD_ALAK = re.compile(rf"^[{_FOGLALASI_KOD_ABC}]{{{_FOGLALASI_KOD_HOSSZ}}}$")

# A minták sorrendje SZÁMÍT. Az e-mail megy elöl (a @ jel egyértelmű),
# utána a TELEFON az országhívóval — ez a sorrend szándékos: a
# `0036301234567` alak 13 számjegy, tehát a bankkártya-minta hosszába is
# beleférne, és akkor `<BANKKARTYA>`-ként takarnánk el. Mindkét esetben
# redaktálva lenne, de a napló olvasója rossz CÍMKÉT látna — a címke az
# egyetlen dolog, ami a redaktálás után megmarad, ezért pontosnak kell
# lennie.
_MINTAK: list[tuple[re.Pattern, str]] = [
    # E-mail — a @ jel miatt egyértelmű, nincs ütközése a többivel.
    (re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b"), EMAIL),
    # Magyar telefonszám: +36 / 0036 / 06 előtag, majd körzet + szám,
    # tetszőleges szóköz/kötőjel/perjel elválasztóval. A 11 számjegyű,
    # előtag nélküli folyó alak (06301234567 → 06 30 123 4567) is ide
    # tartozik, azt az előtag fogja meg.
    (
        re.compile(r"(?<!\d)(?:\+36|0036|06)[\s\-/]?\d{1,2}[\s\-/]?\d{3}[\s\-/]?\d{3,4}(?!\d)"),
        TELEFON,
    ),
    # Bankkártyaszám: 13-19 számjegy, négyes csoportokban vagy egyben.
    # A vásárlói csatornán ilyet SOSEM kérünk — ha mégis bediktálják,
    # az a legérzékenyebb adat, amit kaphatunk.
    (re.compile(r"\b(?:\d[ -]?){12,18}\d\b"), BANKKARTYA),
    # TAJ-szám (9 számjegy, gyakran hármas csoportokban), adóazonosító
    # jel (10 számjegy), személyi szám (11 számjegy). Egy mintában: a
    # csoportosítás lehet szóköz, kötőjel vagy semmi. Ezek egyike sem
    # keverhető össze dátummal (a dátumban kötelező a kétjegyű hónap és
    # nap közti elválasztó, és legfeljebb 8 számjegy van benne).
    (re.compile(r"(?<![\d-])\d{3}[\s-]?\d{3}[\s-]?\d{3,5}(?![\d-])"), AZONOSITO),
    # Személyi igazolvány szám: 6 számjegy + 2 betű ("123456AB").
    (re.compile(r"(?<![\w])\d{6}\s?[A-Za-z]{2}(?![\w])"), AZONOSITO),
]

# BEMUTATKOZÓ SZERKEZET — nem névfelismerés, hanem a bemutatkozás
# fordulatának felismerése (l. modul docstring). Csak a nagybetűvel
# kezdődő szó(ka)t redaktálja, és csak ezekben a szerkezetekben.
_NEV_MINTAK: list[re.Pattern] = [
    # "a nevem Kovács János", "a nevem Marika"
    re.compile(
        r"\b(?P<elo>nevem\s+)(?P<nev>[A-ZÁÉÍÓÖŐÚÜŰ][\wáéíóöőúüű]+(?:\s+[A-ZÁÉÍÓÖŐÚÜŰ][\wáéíóöőúüű]+)?)"
    ),
    # "Én a Marika vagyok", "Kovács János vagyok"
    re.compile(
        r"(?P<elo>\b(?:én\s+)?(?:a|az)?\s*)"
        r"(?P<nev>[A-ZÁÉÍÓÖŐÚÜŰ][\wáéíóöőúüű]+(?:\s+[A-ZÁÉÍÓÖŐÚÜŰ][\wáéíóöőúüű]+)?)"
        r"(?P<uto>\s+vagyok\b)"
    ),
]


def _kod_e(talalat: str) -> bool:
    """Foglalási kód-e a találat (akkor nem redaktáljuk)?"""
    return bool(_FOGLALASI_KOD_ALAK.match(talalat.strip()))


def redaktal(szoveg: str | None) -> str | None:
    """A szöveg redaktált alakja — a felismert személyes adatok helyén
    zárt címkével (`<TELEFON>`, `<AZONOSITO>`, …).

    `None` bemenetre `None` a válasz: a hívó (napló-író) mezői közül
    több is lehet üres, és a hiányt nem szabad üres stringgé alakítani —
    az más állítás lenne.

    **Idempotens**: egy már redaktált szövegen újra lefuttatva ugyanazt
    adja (a címkék maguk nem illeszkednek egyik mintára sem)."""
    if szoveg is None:
        return None
    eredmeny = szoveg
    for minta, cimke in _MINTAK:
        eredmeny = minta.sub(lambda m, c=cimke: m.group(0) if _kod_e(m.group(0)) else c, eredmeny)
    for minta in _NEV_MINTAK:
        eredmeny = minta.sub(
            lambda m: f"{m.groupdict().get('elo') or ''}{NEV}{m.groupdict().get('uto') or ''}",
            eredmeny,
        )
    return eredmeny


def tartalmaz_szemelyes_adatot(szoveg: str | None) -> bool:
    """Van-e a szövegben olyan minta, amit a `redaktal()` eltakarna?

    Ez az **ellenőrző** alak: a golden set robusztussági halmaza ezzel
    vizsgálja, hogy egy értelmező-kimenet paramétereibe nem szivárgott-e
    be nyers személyes adat (`tests/golden/futtato.py`), és a naplóíró
    tesztje is ezzel bizonyít."""
    if not szoveg:
        return False
    return redaktal(szoveg) != szoveg


def redaktal_ertekek(adat):
    """Rekurzívan redaktál egy JSON-szerű szerkezetet (dict/list/str) —
    a napló `parameterek` mezőjéhez, ahol a személyes adat egy
    kulcs ÉRTÉKÉBEN is megjelenhet (pl. ha a modell a bediktált
    telefonszámot foglalási kódnak nézi).

    A kulcsokat nem bántja: azok zárt halmazból jövő mezőnevek, nem
    vásárlói adat."""
    if isinstance(adat, str):
        return redaktal(adat)
    if isinstance(adat, dict):
        return {k: redaktal_ertekek(v) for k, v in adat.items()}
    if isinstance(adat, list):
        return [redaktal_ertekek(e) for e in adat]
    return adat

"""CSÚSZÓ ELŐZMÉNY-ABLAK — a beszélgetés utolsó fordulói szó szerint, a
régebbiek egyetlen, tömör összefoglaló sorban (ADR-025).

**A probléma.** Az ADR-019 óta a modell a BESZÉLGETÉST látja, nem a
megőrzött paramétereket adatként. Ez helyes, de a beszélgetés nő: húsz
forduló után az előzmény hosszabb, mint a rendszerprompt és a példák
együtt, a prompt hossza pedig latencia (`docs/PLATFORM_TANULSAGOK.md`,
2. szakasz). A felület eddig egyszerűen VÁGOTT (az utolsó néhány sor
ment át) — ez rövid promptot adott, de a levágott fordulókkal együtt
elveszett a bolt is, amit a vásárló az első mondatban kimondott.

**A döntés.** Két rétegű előzmény:

1. az utolsó néhány forduló **szó szerint** — ehhez kell a sorszámos
   („a másodikat") és a „mégsem" típusú hivatkozás, mert azok az
   elhangzott mondatokra és a felajánlott listákra mutatnak;
2. a régebbi fordulók helyett **egy összefoglaló sor**: milyen bolt,
   milyen szolgáltatás, eddig milyen napokra kerestünk, mit engedett el
   a vásárló, és hány keresés futott üresen.

Az összefoglaló DETERMINISZTIKUSAN készül: a levágott vásárlói
mondatokat ugyanaz a szabály-alapú értelmező olvassa el
(`rule_based.SzabalyAlapuErtelmezo`), ami a kaszkád tartalék rétege —
nincs második modellhívás, és nincs új mintakészlet, ami elsodródhatna
a meglévőtől.

**A MINDEGY külön jelölve.** Az elengedett mező (`katalogus.MINDEGY`,
ADR-024) az összefoglalóban `ELENGEDVE (mindegy)` alakban jelenik meg,
nem konkrét értékként — különben a három állapotból (nem tudjuk /
elengedve / tudjuk) megint kettő lenne, épp a levágott részen.

**Amitől ez NEM az ADR-019 előtti állapot.** Akkor a megőrzött
paraméterek a TELJES beszélgetésre vonatkoztak, és versenyeztek azzal,
amit a vásárló az imént mondott — ettől lett a modell ragadós. Itt az
összefoglaló csak azokról a fordulókról szól, amik már NEM férnek a szó
szerinti ablakba; ami friss, az szó szerint ott van, és felülírja.

**Az időpont továbbra sem szivároghat.** Az összefoglaló napokat
sorol, de azok MÁR LEFUTOTT keresések, nem kérések — és ha a modell
mégis onnan idézne dátumot, a determinisztikus kapu eldobja
(`forditott_kaszkad._mondatbeli_kifejezes`: az idézet minden érdemi
szavának az AKTUÁLIS mondatban kell szerepelnie). A szivárgás tehát nem
prompt-fegyelem kérdése, hanem szerkezetileg kizárt.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field

from assistant.interpreter import KI_RENDSZER, KI_VASARLO, ErtelmezesKontextus
from assistant.tools.katalogus import MINDEGY

# Hány fordulót viszünk át SZÓ SZERINT. A négy nem tetszőleges: a
# sorszámos hivatkozás („a másodikat") és a visszavonás („mégsem, inkább
# a keddet") legfeljebb ennyi fordulóra hivatkozik vissza a mért
# beszélgetésekben — a mérés a `tools/ablak_meres.py`-ben van, és ez a
# szám abból jön, nem feltevésből.
ALAP_FORDULO = 4

# A kikapcsolt ablak (minden forduló szó szerint) — ez a MÉRÉSI
# ALAPVONAL, nem használati mód: enélkül nem lehetne megmondani, mennyit
# rövidít az ablak és rontja-e a pontosságot.
ABLAK_KI = 0

_KORNYEZETI_VALTOZO = "APRAJAFALVA_ABLAK_FORDULO"


def fordulo_max() -> int:
    """Hány forduló megy át szó szerint — `ALAP_FORDULO`, hacsak a
    környezet mást nem mond (`APRAJAFALVA_ABLAK_FORDULO`).

    A kapcsoló a MÉRÉSÉRT van (`tools/ablak_meres.py`, `python
    feladat.py golden`): az ablakméret hatását csak úgy lehet
    összehasonlítani, ha ugyanaz a kód fut más ablakkal. `0` = nincs
    ablak, minden forduló szó szerint megy.

    Értelmetlen érték (nem szám, negatív) esetén az alapérték —
    egy elgépelt környezeti változó ne csendben változtassa meg a
    viselkedést."""
    nyers = os.environ.get(_KORNYEZETI_VALTOZO)
    if nyers is None:
        return ALAP_FORDULO
    try:
        ertek = int(nyers)
    except ValueError:
        return ALAP_FORDULO
    return ertek if ertek >= 0 else ALAP_FORDULO


# A rendszer sorai, amikből az látszik, hogy egy keresés ÜRESEN tért
# vissza. Nem a `valasz/sablonok.py` kulcsait olvassuk, mert az
# előzménybe a KÉSZ MONDAT kerül (a felület a képernyőn megjelenő sort
# adja tovább, ADR-019) — a kulcs ott már nincs meg. A két minta a
# szöveges és a beszélhető alakot egyaránt lefedi, és a
# `tests/egyseg/test_ablak.py` a tényleges sablonszövegekre illeszti,
# hogy egy átfogalmazás ne csendben rontsa el a számlálást.
_SIKERTELEN_MINTAK = (
    re.compile(r"nincs szabad időpont", re.IGNORECASE),
    re.compile(r"nem hirdetett meg időpont", re.IGNORECASE),
)


@dataclass(frozen=True)
class Osszefoglalo:
    """A levágott fordulók tömör állapota — egyetlen promptsor
    nyersanyaga.

    `elengedett`: azoknak a mezőknek a neve, amiket a vásárló
    kimondottan elengedett (`MINDEGY`). Külön mező, nem az értékek
    közé keverve: a `bolt_id = MINDEGY` és a `bolt_id = "szundi"` két
    különböző állítás, és a promptban is annak kell látszania."""

    fordulok: int = 0
    bolt_id: str | None = None
    szolgaltatas_id: str | None = None
    napok: list[str] = field(default_factory=list)
    napszak: str | None = None
    elengedett: list[str] = field(default_factory=list)
    sikertelen_keresesek: int = 0

    def ures(self) -> bool:
        """Van-e egyáltalán mit mondani. Üres összefoglalóból NEM
        keletkezik promptsor: egy „bolt=None; napok=nincs" sor csak
        tokent visz, jelentést nem."""
        return not (
            self.bolt_id
            or self.szolgaltatas_id
            or self.napok
            or self.napszak
            or self.elengedett
            or self.sikertelen_keresesek
        )

    def szoveg(self) -> str | None:
        """Az összefoglaló promptsor, vagy `None`, ha nincs mit mondani.

        Rövid, mert minden szó latencia — de a mezőnevek a séma
        mezőnevei (`bolt`, `szolgáltatás`, `napszak`), hogy a modellnek
        ne kelljen fordítania."""
        if self.ures():
            return None
        reszek = []
        if self.bolt_id:
            reszek.append(f"bolt={self.bolt_id}")
        if self.szolgaltatas_id:
            reszek.append(f"szolgáltatás={self.szolgaltatas_id}")
        for mezo in self.elengedett:
            reszek.append(f"{mezo}=ELENGEDVE (a vásárló azt mondta: mindegy)")
        if self.napszak:
            reszek.append(f"napszak={self.napszak}")
        if self.napok:
            reszek.append("eddig keresett napok: " + ", ".join(self.napok))
        if self.sikertelen_keresesek:
            reszek.append(f"üresen tért vissza {self.sikertelen_keresesek} keresés")
        return f"Összefoglaló ({self.fordulok} korábbi forduló): " + "; ".join(reszek)


def fordulokra_bont(elozmenyek: list[tuple[str, str]]) -> list[list[tuple[str, str]]]:
    """Sorokból FORDULÓK: minden vásárlói sor új fordulót nyit, a
    rendszer sorai az előtte álló vásárlói sorhoz tartoznak.

    Miért nem sort számolunk (ez volt a `ui/vasarlo.py` korábbi
    megoldása): egy fordulóban a rendszer több sort is írhat (nyugtázó,
    eredmény, felajánlott időpontok), tehát ugyanaz a „12 sor" hol négy,
    hol két fordulót jelent. Az ablak akkor kiszámítható, ha a
    beszélgetés egységében mérjük.

    A vásárlói sor ELŐTTI rendszer-sorok (pl. köszönés) külön, nulladik
    fordulót alkotnak — nem dobjuk el őket, csak nem tartoznak senkihez.
    """
    fordulok: list[list[tuple[str, str]]] = []
    for ki, szoveg in elozmenyek:
        if ki == KI_VASARLO or not fordulok:
            fordulok.append([])
        fordulok[-1].append((ki, szoveg))
    return fordulok


def _sikertelen_keresesek(fordulok: list[list[tuple[str, str]]]) -> int:
    return sum(
        1
        for fordulo in fordulok
        for ki, szoveg in fordulo
        if ki == KI_RENDSZER and any(minta.search(szoveg) for minta in _SIKERTELEN_MINTAK)
    )


def osszefoglal(
    fordulok: list[list[tuple[str, str]]],
    most: str,
    megorzott_parameterek: dict | None = None,
) -> Osszefoglalo:
    """A levágott fordulók összefoglalása — determinisztikusan.

    A vásárlói mondatokat a SZABÁLY-ALAPÚ értelmező olvassa el (ugyanaz,
    ami a kaszkád tartalék rétege): boltot, szolgáltatást, napszakot és
    feloldott dátumot ad. Nincs második modellhívás — egy összefoglalóért
    fizetni egy hívást pont azt a latenciát adná vissza, amit az ablak
    megspórol.

    `megorzott_parameterek` (az orchestrator kontextusa) KIEGÉSZÍTŐ
    forrás, két dologra: (1) az ELENGEDETT mezők (`MINDEGY`)
    felismerésére — azt a szabály-alapú réteg nem tudja, mert nyelvi
    feladat (ADR-024); (2) olyan mező kitöltésére, amit a szövegből nem
    sikerült kiolvasni. **Csak a levágott részre vonatkozik**: ami a szó
    szerinti ablakban van, azt a modell úgyis látja, és az felülírja
    ezt (ADR-025)."""
    from assistant.interpreter.rule_based import SzabalyAlapuErtelmezo

    ertelmezo = SzabalyAlapuErtelmezo()
    ures_kontextus = ErtelmezesKontextus()
    bolt_id = szolgaltatas_id = napszak = None
    napok: list[str] = []

    for fordulo in fordulok:
        for ki, szoveg in fordulo:
            if ki != KI_VASARLO:
                continue
            olvasat = ertelmezo.ertelmez(szoveg, most=most, kontextus=ures_kontextus)
            parameterek = olvasat.get("parameterek") or {}
            # A KÉSŐBBI forduló felülírja a korábbit — de csak ott, ahol
            # ténylegesen mond valamit: egy bolt nélküli mondat nem
            # törli a korábban kimondott boltot.
            bolt_id = parameterek.get("bolt_id") or bolt_id
            szolgaltatas_id = parameterek.get("szolgaltatas_id") or szolgaltatas_id
            napszak = parameterek.get("napszak") or napszak
            nap = (parameterek.get("datum_tol") or "")[:10]
            if nap and nap not in napok:
                napok.append(nap)

    megorzott = megorzott_parameterek or {}
    elengedett = [mezo for mezo in ("bolt_id", "szolgaltatas_id") if megorzott.get(mezo) == MINDEGY]
    if megorzott.get("bolt_id") not in (None, MINDEGY):
        bolt_id = bolt_id or megorzott["bolt_id"]
    if megorzott.get("szolgaltatas_id") not in (None, MINDEGY):
        szolgaltatas_id = szolgaltatas_id or megorzott["szolgaltatas_id"]
    if "bolt_id" in elengedett:
        bolt_id = None
    if "szolgaltatas_id" in elengedett:
        szolgaltatas_id = None

    return Osszefoglalo(
        fordulok=len(fordulok),
        bolt_id=bolt_id,
        szolgaltatas_id=szolgaltatas_id,
        # A napszak a szándék PUHA része: minden fordulóban frissen dől
        # el (`orchestrator.kovetkezo_kontextus`). Az összefoglalóban
        # ezért csak akkor van helye, ha egyáltalán elhangzott — és ott
        # is háttérként, nem kérésként: a kapu
        # (`forditott_kaszkad._mondatbeli_napszak`) úgyis csak az
        # aktuális mondatból fogadja el.
        napszak=napszak,
        napok=napok[-3:],
        elengedett=elengedett,
        sikertelen_keresesek=_sikertelen_keresesek(fordulok),
    )


def ablakol(
    elozmenyek: list[tuple[str, str]],
    *,
    most: str,
    megorzott_parameterek: dict | None = None,
    fordulo: int | None = None,
) -> tuple[str | None, list[tuple[str, str]]]:
    """`(összefoglaló_sor | None, szó szerint átadandó sorok)`.

    `fordulo`: hány forduló menjen át szó szerint — enélkül a
    `fordulo_max()` (környezetből felülírható). `0` esetén nincs ablak:
    minden sor szó szerint megy, összefoglaló nélkül — ez a mérési
    alapvonal."""
    ablak = fordulo_max() if fordulo is None else fordulo
    if ablak == ABLAK_KI:
        return None, list(elozmenyek)

    fordulok = fordulokra_bont(elozmenyek)
    if len(fordulok) <= ablak:
        return None, list(elozmenyek)

    levagott, megtartott = fordulok[:-ablak], fordulok[-ablak:]
    osszefoglalo = osszefoglal(levagott, most, megorzott_parameterek)
    sorok = [sor for fordulo_sorok in megtartott for sor in fordulo_sorok]
    return osszefoglalo.szoveg(), sorok


def kontextusbol(
    kontextus: ErtelmezesKontextus, most: str, *, fordulo: int | None = None
) -> tuple[str | None, list[tuple[str, str]]]:
    """Az `ablakol()` kényelmi alakja az `ErtelmezesKontextus`-ra — ezt
    hívja az `llm_based.beszelgetes_szovege`."""
    return ablakol(
        kontextus.elozmenyek,
        most=most,
        megorzott_parameterek=kontextus.megorzott_parameterek,
        fordulo=fordulo,
    )

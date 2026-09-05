"""Frusztráció-felismerés — mikor hagyjuk abba a próbálkozást, és
kínáljunk kiutat.

**Miért kell.** A vásárló 8. igénye (blueprint 1. szakasz): "legyen
kiút emberhez vagy sorbanálláshoz". Az orchestrator eddig egyetlen
jelet figyelt: ugyanaz a válaszfajta háromszor (`_ismetlest_figyel`).
Ez a MI viselkedésünk ismétlődését méri, nem a vásárlóét — az az eset
kimarad belőle, amikor a rendszer minden fordulóban mást válaszol, a
vásárló mégis egyre kevésbé jut előre.

**Három jel, összeadva.** Egyik sem elég önmagában, mert mindegyik
tévedhet:

1. **Kimondott frusztráció** a vásárló mondatában ("nem értem", "nem
   ezt kértem", "hagyjuk"). Ez a legerősebb jel.
2. **Eredménytelen forduló**: a rendszer visszakérdezett, elutasított
   vagy hibát adott — nem jutottunk közelebb egy időponthoz.
3. **Hossz**: sok forduló egyetlen sikeres ajánlat nélkül.

Egy sikeres ajánlat (vagy foglalás) **nullázza** a számlálót: onnantól
a beszélgetés jó irányba megy, és a korábbi döccenőket nem hordozzuk
tovább.

**Miért kulcsszólista, amikor máshol elutasítottuk.** Az értelmezésnél
a kulcsszólista azért rossz, mert ott a DÖNTÉS múlik rajta (melyik
boltba, melyik napra) — egy téves illesztés rossz foglaláshoz vezet. Itt
a jel csak azt indítja el, hogy **felajánljuk a kiutat**; a téves
pozitív ára egy fölösleges, de barátságos mondat, a téves negatívé egy
elhagyott vásárló. Az aszimmetria fordítva áll, mint az értelmezésnél,
ezért a szabályalapú jelzés itt helyénvaló — és determinisztikus, tehát
nem a modell prompt-fegyelmén múlik (blueprint 10. szakasz).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from assistant.interpreter.normalizalo import normalizal

# Kimondott frusztráció. Szándékosan a TÜRELMETLENSÉGRE és az
# ELAKADÁSRA szűkítve — nem "negatív hangulatra": a "nem jó a kedd"
# nem frusztráció, hanem egy hasznos, előrevivő mondat.
_JEL_MINTAK = re.compile(
    r"nem ért(em|elek)|nem ezt|nem azt kér|mit kell|hogy kell|"
    r"hagyjuk|mindegy már|felejtsd|fel is adom|"
    r"m[áa]r mondtam|megint|harmadszor|sokadszor|"
    r"bonyolult|nem megy|nem sikerül|nem működik|"
    r"[íi]dege|elegem"
)

# Mennyi "pont" kell a kiúthoz. A kimondott jel 2 pontot ér, egy
# eredménytelen forduló 1-et — tehát vagy két kimondott panasz, vagy
# egy panasz + két eredménytelen forduló, vagy négy eredménytelen
# forduló. Ez tapasztalati arány, nem mérésből jött: a küszöb
# hangolható, ha a próba-napló (`naplo/probak.jsonl`) mást mutat.
KUSZOB = 4
_KIMONDOTT_JEL_PONT = 2
_EREDMENYTELEN_PONT = 1

# Azok a válaszfajták, amik NEM visznek közelebb egy időponthoz. A
# `kiut` szándékosan nincs köztük: az már maga a válasz a frusztrációra.
_EREDMENYTELEN_TIPUSOK = frozenset({"visszakerdezes", "elutasitas", "eszkoz_hiba"})


def kimondott_jel(mondat: str) -> bool:
    """Tartalmaz-e a mondat kimondott frusztráció-jelet? A normalizálón
    átvezetve, hogy a tájszólási alakok se csússzanak át."""
    return _JEL_MINTAK.search(normalizal(mondat).lower()) is not None


@dataclass
class Frusztracio:
    """Egy session frusztráció-számlálója. Az orchestrator
    `_SessionAllapot`-ja tartja; memóriában él, mint a session többi
    része."""

    pont: int = 0
    # Hányszor ajánlottunk már kiutat ebben a beszélgetésben — a
    # másodikra már ember kell, nem újabb szűkítési javaslat.
    kiut_ajanlva: int = 0
    # A küszöb példányonként állítható. Az alapérték tapasztalati, nem
    # mérésből jött (l. modul docstring) — a hangolhatóság ezért nem
    # luxus: ha a próba-napló mást mutat, itt kell átírni. A tesztek is
    # ezt használják, amikor egy MÁSIK mechanizmust (pl. az
    # ismétlésfigyelést) akarnak elszigetelten mérni.
    kuszob: int = KUSZOB
    # Hányszor ment ki a kiút HELYETT bemutatkozás (ADR-032). Egyszer
    # van értelme: a felsorolás arra válasz, hogy „mit lehet itt?" — ha
    # a vásárló ezután SEM választ boltot, a listát megismételni nem
    # segítség, hanem ugyanaz a körbe-körbe, amit el akartunk kerülni.
    # A FEJ NÉLKÜLI VÉGIGJÁTSZÁS találta meg: az „ismétlés → kiút"
    # beszélgetés második és harmadik fordulójára szó szerint ugyanaz a
    # felsorolás ment ki.
    bemutatkozas_szama: int = 0

    def fordulo(self, mondat: str, valasz_tipus: str | None) -> None:
        """Egy lezárt forduló beszámítása. `valasz_tipus` a `fordulo()`
        válaszának `tipus` mezője."""
        if valasz_tipus == "ajanlat" or valasz_tipus == "visszaigazolas":
            self.pont = 0
            return
        if kimondott_jel(mondat):
            self.pont += _KIMONDOTT_JEL_PONT
        if valasz_tipus in _EREDMENYTELEN_TIPUSOK:
            self.pont += _EREDMENYTELEN_PONT

    def kiutat_kell(self) -> bool:
        return self.pont >= self.kuszob

    def emberhez_kell(self, mondat: str) -> bool:
        """Már ajánlottunk kiutat, és a vásárló MÉGIS kimondja, hogy
        elakadt — ilyenkor nem gyűjtünk újabb pontot, hanem embert
        ajánlunk.

        **Miért van ez külön feltétel.** A pontgyűjtés az ELSŐ kiúthoz
        való: onnan tudjuk meg, hogy baj van. A második kiút kérdése
        más — azt már tudjuk, hogy baj van, és azt is, hogy a
        szűkítési javaslat nem segített. Egy újabb „próbáljunk másik
        hetet" ilyenkor nem információ, hanem makacsság.

        A FEJ NÉLKÜLI VÉGIGJÁTSZÁS találta meg, hogy enélkül a második
        kiút a leggyakoribb esetben SOSEM szólal meg: ha a vásárló
        ugyanazt a mondatot ismétli, a rendszer ugyanazt válaszolja,
        tehát az ismétlésfigyelő kiutat ad ki — a kiút pedig
        szándékosan nem számít „eredménytelen fordulónak", így a
        pontszám sosem éri el újra a küszöböt."""
        return self.kiut_ajanlva >= 1 and kimondott_jel(mondat)

    def bemutatkozhat(self) -> bool:
        """Kiadható-e még a kiút HELYETT bemutatkozás? Csak egyszer —
        utána a rendes kiút jön, a saját fokozataival."""
        return self.bemutatkozas_szama < 1

    def bemutatkozas_kiadva(self) -> None:
        """A kiút HELYETT bemutatkozás ment ki (ADR-032): a beszélgetés
        még egyetlen keresésig sem jutott el.

        A pontszám nullázódik, a `kiut_ajanlva` viszont NEM nő: nem
        kiutat adtunk, hanem elmondtuk, mi van itt. Ha ezután is elakad
        a vásárló, az ELSŐ kiút jár neki, nem rögtön a második (ami már
        embert ajánl)."""
        self.pont = 0
        self.bemutatkozas_szama += 1

    def kiut_kiadva(self) -> None:
        """A kiút felajánlása után nullázunk, hogy ne minden további
        fordulóban ismételjük — de a `kiut_ajanlva` megmarad, mert a
        MÁSODIK kiút már másképp szól."""
        self.pont = 0
        self.kiut_ajanlva += 1

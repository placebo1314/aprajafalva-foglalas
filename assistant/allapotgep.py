"""ÁLLAPOTVEZÉRELT DISZPÉCSER — hol tart a beszélgetés, és mit várunk
most (ADR-028).

**A hiba, amit megszüntet.** Az orchestrator eddig is állapotgép volt
(ADR-007), de az állapotát MAGÁNAK tartotta: a modell nem tudta, hogy
épp felajánlottunk három időpontot, vagy hogy megerősítésre várunk.
Ettől egy csupasz „a második" vagy „igen" kétértelmű volt — a modell a
mondatot önmagában olvasta, és keresésnek értette. Mérve
(`vegigjatszas`, `qwen3.5:9b`): az „igen, foglald le" mondatból új
keresés lett, és a folyamatban lévő megerősítés eltűnt.

## A hat állapot

| állapot | mit jelent | mit várunk |
|---|---|---|
| `INDULAS` | üres beszélgetés | bármilyen kérést |
| `HIANYZO_ADAT` | zárt kérdést tettünk fel | a hiányzó mezőt |
| `AJANLAT_VAR` | felajánlottunk N időpontot | sorszámot vagy időpontot |
| `MEGEROSITES_VAR` | „biztosan lefoglaljam?" | igent vagy nemet |
| `KESZ` | a foglalás létrejött | új kérést |
| `KIUT` | elakadtunk, kiutat ajánlottunk | választást a felkínált irányok közül |

## Három dolgot csinál, és mindhárom külön ér valamit

1. **A promptba egy sor kerül** (`prompt_sor`): hol tartunk, és mit
   várunk. Ez a modellnek szól — nem utasítás, hanem HELYZETLEÍRÁS.
2. **Az átmenetek kódban vannak** (`ATMENETEK`): ami nem szerepel,
   az hiba. Nem kivétellel áll meg (a vásárló nem eshet ki egy
   fejlesztői tévedéstől), hanem naplózza és a biztonságos
   `INDULAS`-ba tér — de a naplóból utólag ki lehet keresni.
3. **A napló minden fordulónál rögzíti** az állapotot és az átmenetet,
   így egy furcsa beszélgetésről utólag meg lehet mondani, hol tévedt
   el — eddig ez csak a válaszok sorrendjéből volt kikövetkeztethető.

## Amit NEM csinál

**Nem váltja ki a determinisztikus rövidzárakat** (`assistant/
sorszam.py`, `assistant/megerosites.py`). Azok a GARANCIA: ha a
felajánlott háromból a másodikat kérik, azt nem a modell dönti el. Az
állapotsor a modellnek akkor segít, amikor a rövidzár nem illeszkedik
(„az a fél kilences jó lesz", „a középső"). A kettő egymás mellett áll,
nem egymás helyett — ahogy az ADR-018 óta a kapuk és a modell is.
"""

from __future__ import annotations

import logging
import os

_LOG = logging.getLogger(__name__)

INDULAS = "INDULAS"
HIANYZO_ADAT = "HIANYZO_ADAT"
AJANLAT_VAR = "AJANLAT_VAR"
MEGEROSITES_VAR = "MEGEROSITES_VAR"
KESZ = "KESZ"
KIUT = "KIUT"

ALLAPOTOK = (INDULAS, HIANYZO_ADAT, AJANLAT_VAR, MEGEROSITES_VAR, KESZ, KIUT)

# ENGEDÉLYEZETT ÁTMENETEK. Ami nincs benne, az hiba — de nem a
# vásárló hibája, ezért nem kivétel (l. `atmenet`).
#
# Két elv olvasható ki belőle:
#
# - **Minden állapotból lehet INDULAS-ba menni.** A vásárló bármikor
#   kezdhet új témát („mégis inkább a Szundihoz"), és ezt nem
#   akadályozzuk meg — a beszélgetés nem űrlap.
# - **KESZ-ből nem megy vissza semmi a foglalási ágra.** Egy lezárt
#   foglalás után az új kérés ÚJ beszélgetés (INDULAS): a lefoglalt
#   időpontot nem lehet „még egyszer" megerősíteni.
# - **AJANLAT_VAR és MEGEROSITES_VAR NEM megy vissza HIANYZO_ADAT-ba**
#   (ADR-035). Az idegen próba 10. fordulója mutatta meg, miért: a
#   „Így nem haladunk előre. Miafasz van veled?" mondatra a rendszer
#   visszakérdezett, hogy MELYIK BOLTBA szeretne menni — pedig két
#   fordulóval korábban maga ajánlott fel időpontokat ugyanabban a
#   boltban. **Egy frusztrált mondat nem törli az ajánlatokat.** Aki
#   tényleg új adatot akar megadni, az új KÉRÉST mond, és az
#   AJANLAT_VAR-ba vagy INDULAS-ba visz.
ATMENETEK: dict[str, frozenset[str]] = {
    INDULAS: frozenset({INDULAS, HIANYZO_ADAT, AJANLAT_VAR, KIUT, KESZ}),
    HIANYZO_ADAT: frozenset({INDULAS, HIANYZO_ADAT, AJANLAT_VAR, KIUT}),
    AJANLAT_VAR: frozenset({INDULAS, AJANLAT_VAR, MEGEROSITES_VAR, KIUT}),
    MEGEROSITES_VAR: frozenset({INDULAS, AJANLAT_VAR, MEGEROSITES_VAR, KESZ, KIUT}),
    KESZ: frozenset({INDULAS, KESZ}),
    KIUT: frozenset({INDULAS, HIANYZO_ADAT, AJANLAT_VAR, KIUT}),
}

# VÁLASZTÍPUS → a forduló UTÁNI állapot. A válasz típusa az egyetlen
# megbízható jel: azt a felület is látja, és az orchestrator is ebből
# építi a képernyőt — ha az állapotot máshonnan vezetnénk, a kettő
# szétcsúszhatna.
_VALASZ_ALLAPOT = {
    "ajanlat": AJANLAT_VAR,
    "megerositest_ker": MEGEROSITES_VAR,
    "visszakerdezes": HIANYZO_ADAT,
    "kiut": KIUT,
    "visszaigazolas": KESZ,
    "elvetve": AJANLAT_VAR,
}

# Ezek a válaszok NEM mozdítják az állapotot: egy tényválasz vagy egy
# elhárítás közben a folyamatban lévő ajánlat/megerősítés érvényben
# marad. Ez a „közbevetett kérdés" esete (beszédhelyzetek golden halmaz,
# `kozbevetes` réteg): a vásárló megkérdezi, meddig tart, és utána
# ugyanoda tér vissza.
#
# A `meta_valasz` (a rendszerről szóló kérdés) ugyanígy: az ÉLES PRÓBA
# mutatta meg, miért fontos — ott a „csak a választ beszéled?" mondat a
# KESZ állapotból AJANLAT_VAR-ba rántotta vissza a beszélgetést, egy már
# lezárt foglalás után.
#
# Az `ajanlat_emlekezteto` (ADR-035) ugyanebből a családból való: a
# visszakérdezés HELYETT megy ki, amikor már állnak ajánlataink — és
# épp az a dolga, hogy NE mozdítsa el a beszélgetést arról a pontról,
# ahova eljutott.
_ALLAPOTTARTO = frozenset(
    {
        "elutasitas",
        "eszkoz_hiba",
        "hiba",
        "meta_valasz",
        "koszones",
        "kinalat",
        "ajanlat_emlekezteto",
        # AZ AJÁNLATRÓL SZÓLÓ KÉRDÉS felelete (ADR-035) sem mozdít: a
        # vásárló nem választott és nem is kért újat — kérdezett.
        "ajanlat_valasz",
    }
)

_KORNYEZETI_VALTOZO = "APRAJAFALVA_ALLAPOT_SOR"


def kovetkezo_allapot(jelenlegi: str, valasz: dict) -> str:
    """A forduló utáni állapot a VÁLASZ típusából.

    Ismeretlen válasz-típusnál az állapot marad — a hallgatás itt
    kevesebb kárt okoz, mint egy találgatott átmenet."""
    tipus = valasz.get("tipus")
    if tipus in _ALLAPOTTARTO:
        return jelenlegi
    if tipus == "sikeres" or (tipus is None and valasz.get("sikeres")):
        # Tényválasz (`bolt_info`) — nem mozdít.
        return jelenlegi
    return _VALASZ_ALLAPOT.get(tipus, jelenlegi)


def atmenet(honnan: str, hova: str) -> str:
    """A ténylegesen felvett állapot. Nem engedélyezett átmenetnél
    NAPLÓZ és a biztonságos `INDULAS`-ba tér.

    **Miért nem kivétel.** Egy nem engedélyezett átmenet fejlesztői
    tévedés — a vásárló viszont nem eshet ki tőle a beszélgetésből
    (blueprint 7.: a vesztes ág is legyen kellemes). A naplóban ott
    marad, tehát nem néma.

    **Miért MARAD az állapot, és miért nem INDULAS-ba tér** (ADR-035
    óta). Az `INDULAS` első ránézésre a biztonságos választás: üres lap,
    semmi nem romolhat el. Csakhogy a beszélgetésben épp az a
    legdrágább, ha elfelejtjük, hol tartunk — az idegen próba 10.
    fordulójában a rendszer így vesztette el a saját ajánlatait egy
    frusztrált mondat miatt. A maradás nem "kisebb rossz": a tiltott
    átmenet azt jelenti, hogy a levezetés hibás, nem azt, hogy a
    beszélgetés elölről kezdődik."""
    if hova in ATMENETEK.get(honnan, frozenset()):
        return hova
    _LOG.warning("nem engedélyezett állapotátmenet: %s -> %s (az állapot marad)", honnan, hova)
    return honnan


def bekapcsolva() -> bool:
    """Megy-e az állapotsor a promptba. Kikapcsolható
    (`APRAJAFALVA_ALLAPOT_SOR=ki`) — a MÉRÉSÉRT: enélkül nem lehetne
    A/B-zni, hogy segít-e egyáltalán."""
    return os.environ.get(_KORNYEZETI_VALTOZO, "be").lower() not in ("ki", "0", "false", "off")


def prompt_sor(
    allapot: str, jeloltek_szama: int = 0, hianyzo_mezo: str | None = None
) -> str | None:
    """A promptba kerülő EGY sor: hol tartunk, és mit várunk most.
    `None`, ha nincs mit mondani (`INDULAS` — az üres beszélgetésről a
    hallgatás a pontos állítás).

    A sor HELYZETLEÍRÁS, nem utasítás: nem azt mondja meg a modellnek,
    mit adjon vissza, hanem azt, hogy mire válaszol a vásárló. A döntés
    továbbra is az övé, és a determinisztikus kapuké."""
    if not bekapcsolva():
        return None
    if allapot == AJANLAT_VAR and jeloltek_szama:
        return (
            f"Állapot: AJANLAT_VAR — {jeloltek_szama} időpontot ajánlottunk fel, és most "
            "ezek közül várunk választást: sorszám, időpont, vagy visszalépés."
        )
    if allapot == MEGEROSITES_VAR:
        return (
            "Állapot: MEGEROSITES_VAR — feltettük a kérdést, hogy lefoglaljuk-e a "
            "kiválasztott időpontot, és most igent vagy nemet várunk."
        )
    if allapot == HIANYZO_ADAT:
        mezo = f" ({hianyzo_mezo})" if hianyzo_mezo else ""
        return (
            f"Állapot: HIANYZO_ADAT — zárt kérdést tettünk fel egy hiányzó adatról{mezo}, "
            "és most arra várunk választ."
        )
    if allapot == KIUT:
        return (
            "Állapot: KIUT — elakadtunk, és felkínáltunk néhány irányt (másik nap, másik "
            "napszak, legkorábbi időpont); most ezek közül várunk választást."
        )
    if allapot == KESZ:
        return (
            "Állapot: KESZ — az előző foglalás létrejött. Ami most jön, az ÚJ kérés, "
            "nem a lezárt foglalás folytatása."
        )
    return None

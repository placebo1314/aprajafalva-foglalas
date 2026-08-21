"""Szándékindex — session-szintű, memóriában tartott, csúszó TTL-lel
(foglalasi-mag skill, "Szándékindex").

**Soha nem blokkol.** Csak jelzés az ajánlatpontozónak (`ajanlatpontozo.py`)
a `várható_lefedettség` becsléséhez — melyik sávra irányul jelenleg sok
egyidejű érdeklődés, hogy a pontozó szét tudja teríteni az ajánlatokat
(ADR-006, "ajánlatszórás").

**Nem adatbázis, nem tábla.** Folyamat-memóriában él, `dict`-tel — ha a
folyamat újraindul, elvész, ez szándékos (nem kritikus állapot). Ha
később több worker-folyamat kell, ugyanez az interfész (`szandek_frissites`,
`szandek_lekerdezes`) mögé Redis kerülhet, a hívók nem változnak.

**Nem tartalmaz vásárlóazonosítót.** Ez nem stílus, adatvédelmi
követelmény (CLAUDE.md 2. invariáns) — a session_id nem vásárlóazonosító,
csak egy beszélgetés folyamatbeli kulcsa.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

# 5-10 perc a foglalasi-mag skill szerint — az alsó határt választjuk,
# mert egy elavult szándék rosszabb, mint egy korán elfelejtett.
_TTL = timedelta(minutes=5)

# session_id -> bejegyzés. Bejegyzés kulcsai: bolt_id, szolgaltatas_id,
# nap (ISO dátum, "ÉÉÉÉ-HH-NN"), napszak, bizonyossag, utolso_frissites.
_INDEX: dict[str, dict] = {}


def _most() -> datetime:
    return datetime.now(UTC)


def szandek_frissites(
    session_id: str,
    *,
    bolt_id: str | None = None,
    szolgaltatas_id: str | None = None,
    nap: str | None = None,
    napszak: str | None = None,
    bizonyossag: float = 1.0,
) -> None:
    """Frissíti (vagy létrehozza) egy session szándékát. Csak a megadott
    mezőket írja felül — a `None` érték NEM törli a korábbi mezőt, mert a
    célja épp a részleges adat megőrzése (golden set, "megorzott_parameterek"
    elve), nem a session state teljes cseréje."""
    bejegyzes = _INDEX.get(session_id, {})
    if bolt_id is not None:
        bejegyzes["bolt_id"] = bolt_id
    if szolgaltatas_id is not None:
        bejegyzes["szolgaltatas_id"] = szolgaltatas_id
    if nap is not None:
        bejegyzes["nap"] = nap
    if napszak is not None:
        bejegyzes["napszak"] = napszak
    bejegyzes["bizonyossag"] = bizonyossag
    bejegyzes["utolso_frissites"] = _most()
    _INDEX[session_id] = bejegyzes


def szandek_lekerdezes(session_id: str) -> dict | None:
    """Egy session aktuális szándéka, vagy `None`, ha nincs, vagy a TTL
    lejárt. A lejárt bejegyzést itt takarítjuk (olvasáskor), nem külön
    ütemezett feladattal — a szándékindex nem kritikus állapot, nem éri
    meg rá külön takarító-ciklust futtatni."""
    bejegyzes = _INDEX.get(session_id)
    if bejegyzes is None:
        return None
    if _most() - bejegyzes["utolso_frissites"] > _TTL:
        del _INDEX[session_id]
        return None
    return dict(bejegyzes)


def szandek_torles(session_id: str) -> None:
    """Explicit törlés — pl. amikor a beszélgetés véglegesen lezárult
    (foglalás vagy elköszönés), nem kell megvárni a TTL lejártát."""
    _INDEX.pop(session_id, None)


def hasonlo_szandekok_szama(
    *, bolt_id: str, nap: str, napszak: str, kizart_session_id: str | None = None
) -> int:
    """Hány MÁS, még érvényes session szándéka mutat ugyanarra a
    bolt+nap+napszak sávra. Az ajánlatpontozó ebből becsüli a `várható
    lefedettséget` (blueprint 6. szakasz) — minél többen érdeklődnek egy
    sáv iránt, annál inkább érdemes onnan elterelni a következő ajánlatot.

    `napszak == "barmikor"` esetén a napszak-egyezést nem vizsgáljuk —
    egy "bármikor"-szándék bármelyik napszak-specifikus kereséssel
    átfedésben van, ha a nap egyezik."""
    most = _most()
    talalat = 0
    for session, bejegyzes in list(_INDEX.items()):
        if session == kizart_session_id:
            continue
        if most - bejegyzes["utolso_frissites"] > _TTL:
            continue
        if bejegyzes.get("bolt_id") != bolt_id or bejegyzes.get("nap") != nap:
            continue
        masik_napszak = bejegyzes.get("napszak", "barmikor")
        if napszak != "barmikor" and masik_napszak not in ("barmikor", napszak):
            continue
        talalat += 1
    return talalat

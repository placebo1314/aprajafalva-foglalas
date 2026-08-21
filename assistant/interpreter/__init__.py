"""Az `Ertelmezo` protokoll — mondat → `{eszkoz, parameterek}`, LLM
nélkül is, LLM-mel is ugyanígy (ADR-002: "Az LLM nem foglal, hanem
fordít"; ADR-007: az orchestrator dönt, nem az értelmező).

Ma egyetlen implementáció áll mögötte (`assistant/interpreter/
rule_based.py`, determinisztikus) — egy jövőbeli LLM-es értelmező
ugyanezt a protokollt tölti ki, az `assistant/orchestrator.py` kódja
emiatt NEM változik.

Az `eszkoz` mező három fajta érték egyike:

- egy valódi eszköznév (`assistant/tools/`) — az orchestrator hívja a
  megfelelő `hivas()`-t;
- `"visszakerdez"` — az orchestrator kérdést tesz fel, nem hív eszközt;
- `"nincs"` — kapuőr-döntés: a kérés nem foglalással kapcsolatos.

A `parameterek` dict **sosem tartalmaz `session_id`-t** — azt az
orchestrator fűzi hozzá, mert ő ismeri a beszélgetés állapotát, nem az
értelmező (ez a golden set `varhato.parameterek` mezőiből is
levezethető: `session_id` egyikben sem szerepel)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class ErtelmezesKontextus:
    """Amit az értelmezőnek tudnia kell a session korábbi állapotából —
    a golden set "megorzott_parameterek" elve: a korábban megadott, de
    még fel nem használt adatot NEM szabad elveszíteni egy újabb
    fordulóban (pl. a dátum megmarad, miközben a boltot újrakérdezzük)."""

    megorzott_parameterek: dict = field(default_factory=dict)


@runtime_checkable
class Ertelmezo(Protocol):
    def ertelmez(self, mondat: str, *, most: str, kontextus: ErtelmezesKontextus) -> dict:
        """`most`: ISO-8601 UTC — a relatív dátumkifejezések (holnap,
        jövő hét kedd) ehhez képest oldódnak fel, NEM a valódi
        rendszeróra szerint (a golden set esetei fagyasztott `most`-tal
        futnak, `golden-set` skill).

        Visszatérési érték: `{"eszkoz": str, "parameterek": dict}`."""
        ...

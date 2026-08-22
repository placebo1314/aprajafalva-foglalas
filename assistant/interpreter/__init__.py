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

        Visszatérési érték:

        ```python
        {"eszkoz": str,
         "parameterek": dict,
         "bizonyossag": {"eszkoz": 0.9, "bolt_id": 0.6, "datum": 1.0}}
        ```

        A `bizonyossag` (blueprint 10. szakasz: "Bizalmi jelzés a kötött
        dekódolás logprobjaiból, kritikus mezőkre") **opcionális** —
        aki nem adja, azt az orchestrator ismeretlennek tekinti, és nem
        von le belőle következtetést. Értékei `0.0`–`1.0` közti számok
        VAGY `None`. A `None` jelentése "erről nem tudok nyilatkozni",
        ami NEM ugyanaz, mint a `0.0` ("biztosan rossz") — a
        determinisztikus értelmező pont ezt a különbséget használja:
        `1.0`-t ad arra, amit szabályból tud, `None`-t arra, amit nem.

        **A visszakérdezésről az orchestrator dönt, nem az értelmező**
        (blueprint 10. szakasz) — az értelmező csak számot ad."""
        ...


def aktiv_modell_neve() -> str | None:
    """A konfigurált modell neve (`APRAJAFALVA_LLM_MODELL`), vagy `None`,
    ha nincs beállítva — ilyenkor az `alapertelmezett_ertelmezo()`
    tisztán determinisztikus értelmezőt épít.

    **Nem** azt mondja meg, hogy a háttérszolgáltatás fut-e: azt csak egy
    tényleges hívás derítené ki, és ez a függvény nem hív semmit. A
    hívók (`ui/vasarlo.py` indító sora) ezt így is fogalmazzák meg —
    a ténylegesen dolgozó réteget a próba-napló `reteg` mezője mutatja."""
    from assistant.interpreter.llm_based import LLMSzolgaltato

    try:
        return LLMSzolgaltato().modell
    except ValueError:
        return None


def alapertelmezett_ertelmezo() -> Ertelmezo:
    """A projekt SZABVÁNYOS értelmezője — a FORDÍTOTT kaszkád
    (`forditott_kaszkad.py`, ADR-018: a normalizáló fut előbb, a modell
    értelmez kötött dekódolással, a determinisztikus rétegek a kapuk),
    csendes (hiba nélküli) visszaeséssel a tisztán szabály-alapú
    rétegre, ha nincs konfigurált modell (`APRAJAFALVA_LLM_MODELL` —
    `llm_based.py::LLMSzolgaltato`) vagy nem elérhető a szolgáltatás.

    Az ADR-016 sorrendje (`kaszkad.py`: determinisztikus előbb) a
    repóban maradt, és `python feladat.py golden --ertelmezo kaszkad`
    paranccsal bármikor újramérhető — ez a visszaút (ADR-018, "Kiváltó
    feltétel").

    Ez a belépési pont, amit a hívók (pl. `ui/vasarlo.py`) használnak —
    ők nem importálják és nem is tudják, hogy LLM van-e a kaszkádban
    (CLAUDE.md, "Modulhatárok": "a ui/ nem hívhat LLM-et közvetlenül").
    A lusta (függvényen belüli) importok szándékosak: elkerülik a
    körkörös importot a csomag `__init__`-je és az itt importált
    testvérmodulok között, amik maguk is ebből az `__init__`-ből
    importálnak (`Ertelmezo`, `ErtelmezesKontextus`)."""
    from assistant.interpreter.forditott_kaszkad import ForditottKaszkadErtelmezo
    from assistant.interpreter.llm_based import LLMErtelmezo, LLMSzolgaltato
    from assistant.interpreter.rule_based import SzabalyAlapuErtelmezo

    try:
        llm = LLMErtelmezo(LLMSzolgaltato())
    except ValueError:
        llm = None
    return ForditottKaszkadErtelmezo(SzabalyAlapuErtelmezo(), llm)

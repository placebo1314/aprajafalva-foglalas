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

# Az `elozmenyek` első elemének megengedett értékei — ki mondta.
KI_VASARLO = "vasarlo"
KI_RENDSZER = "rendszer"


@dataclass(frozen=True)
class ErtelmezesKontextus:
    """Amit az értelmezőnek tudnia kell a session korábbi állapotából.

    **Két, egymástól élesen elváló mező, és a sorrendjük számít:**

    `elozmenyek` — a beszélgetés utolsó néhány fordulója `(ki, mit)`
    párokként, ahol `ki` a `KI_VASARLO` vagy a `KI_RENDSZER`. Ez az
    ELSŐDLEGES forrás: az LLM-alapú értelmező ezt párbeszédként kapja
    meg, és a teljes kérést egyetlen hívásban adja vissza. Ha a
    beszélgetésből az derül ki, hogy egy korábbi adat már nem érvényes
    (a vásárló mást kér, vagy azt mondja, mindegy), a modell egyszerűen
    NEM tölti ki azt a mezőt — nincs külön "elengedés"-fogalom, nincs
    külön hívás rá (ADR-019).

    `megorzott_parameterek` — a korábbi fordulóból megőrzött, MÁR
    FELOLDOTT paraméterek. A szerepe **tartalék**, nem bemenet: akkor
    tölt ki egy mezőt, ha a modell nem látta a beszélgetést (nincs
    `elozmenyek` — pl. determinisztikus út, gombnyomás, első forduló).
    Ha a modell LÁTTA a beszélgetést és mégis üresen hagyott egy mezőt,
    az a döntése — a `None` erősebb, mint a megőrzött érték.

    Ez a megkülönböztetés az ADR-019 lényege: korábban a megőrzött
    paraméterek adatként mentek a promptba, és a modellnek külön, zárt
    kérdésben kellett megmondania, mit "enged el". Az a gépezet
    megszűnt."""

    megorzott_parameterek: dict = field(default_factory=dict)
    elozmenyek: list[tuple[str, str]] = field(default_factory=list)
    # ÁLLAPOTSOR (ADR-028, `assistant/allapotgep.py::prompt_sor`): hol
    # tart a beszélgetés, és mit várunk most — egyetlen mondat, amit az
    # ORCHESTRATOR állít elő, mert egyedül ő ismeri a session állapotát.
    #
    # Miért kell: a modell eddig a mondatot ÖNMAGÁBAN olvasta, tehát egy
    # csupasz „a második" vagy „igen" kétértelmű volt. A beszélgetés
    # (`elozmenyek`) ezt csak közvetve mutatja; az állapot kimondva
    # egyértelmű.
    allapot_sor: str | None = None


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


def indito_ellenorzes():
    """Az éles út INDÍTÁSI ellenőrzése — `ModellAllapot`
    (`llm_based.modell_allapot`): konfigurálva van-e a modell, válaszol-e
    az Ollama, és le van-e töltve a kért modell.

    Ez a függvény azért van itt, a csomag `__init__`-jében, mert a
    felület hívja (`ui/vasarlo.py`), a felület pedig nem importálhat
    modell-specifikus modult (CLAUDE.md, „Modulhatárok"). Ugyanaz a
    minta, mint az `aktiv_modell_neve()`-nél — annyi különbséggel, hogy
    ez TÉNYLEGESEN megkérdezi a szolgáltatást, nem csak a konfigurációt
    nézi."""
    from assistant.interpreter.llm_based import modell_allapot

    return modell_allapot()


# Az önkonzisztencia-ellenőrzés ALAPÉRTELMEZETT állapota (ADR-021,
# `assistant/interpreter/onkonzisztencia.py`). A `False` MÉRÉSBŐL
# következik, nem óvatosságból — a számok az ADR-021-ben vannak. A
# kapcsolót az `APRAJAFALVA_ONKONZISZTENCIA` környezeti változó
# felülírja mindkét irányba, tehát bekapcsolni nem kódmódosítás.
ONKONZISZTENCIA_ALAPERTELMEZES = False


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
    from assistant.interpreter.onkonzisztencia import OnkonzisztensErtelmezo, bekapcsolva
    from assistant.interpreter.rule_based import SzabalyAlapuErtelmezo

    try:
        llm = LLMErtelmezo(LLMSzolgaltato())
    except ValueError:
        llm = None
    ertelmezo = ForditottKaszkadErtelmezo(SzabalyAlapuErtelmezo(), llm)

    # ÖNKONZISZTENCIA (ADR-021) — alapból KI, mérés alapján. Bekapcsolva
    # az értelmező háromszor fut, és a JSON eszközhívások pontos
    # egyenlőségét szavaztatjuk (blueprint 10.). A burkoló a
    # determinisztikus úton (llm=None) magától egyszer futtat, tehát ott
    # a bekapcsolás sem jár költséggel.
    if bekapcsolva(ONKONZISZTENCIA_ALAPERTELMEZES):
        return OnkonzisztensErtelmezo(ertelmezo)
    return ertelmezo

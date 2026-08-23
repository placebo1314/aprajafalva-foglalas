"""Kaszkád értelmező (ADR-016) — a determinisztikus fut előbb, a modell
csak akkor segít, ha az nem boldogul.

```
mondat → SzabalyAlapuErtelmezo
             │
             ├─ "visszakerdez", hiányzó mező = bolt_id
             │      → KIEGÉSZÍTÉS: az LLM egy ZÁRT HALMAZBELI bolt_id-t
             │        javasol, majd a SzabalyAlapuErtelmezo ÚJRAFUT a
             │        kiegészített bolttal
             │
             └─ döntött (nem visszakerdez), de VAN megőrzött kontextus
                    → ELENGEDÉS: az LLM megmondja, a korábbi
                      paraméterekből mi ESIK KI az új mondat után
                      (csak MEZŐNEVEK, soha nem érték), majd a
                      SzabalyAlapuErtelmezo ÚJRAFUT a szűkített
                      kontextussal

mindkét ágon: nincs LLM / nem elérhető / nem változtat
                    → marad a szabály-alapú válasz
```

Az **elengedés** ág azért kell, mert a "mégis mindegy, mikor" típusú
mondatokat a mintaillesztés nem látja: nincs bennük olyan szó, amit egy
szabály kereshetne, és kulcsszólistát írni rájuk ráigazítás lenne a
mérési halmazra. A modell itt egy ellenőrizhető, zárt kérdésre válaszol
("melyik korábbi adat nem érvényes már?"), nem az egész értelmezést
végzi.

**Miért ez a sorrend, nem fordítva** (ADR-016 részletezi a kiváltó
feltétellel együtt): a determinisztikus réteg olcsó, gyors, és soha nem
hallucinál zárt halmazon kívüli boltot/szolgáltatást — ha ez elég, a
modellhívás felesleges költség és latencia. A modell csak ott ad
hozzáadott értéket, ahol a szabályalapú mintaillesztés ténylegesen
elakad (pl. a bolt körülírva, elgépelve, vagy szokatlan szórenddel
említve) — ez a mérhető, indokolt hozzájárulása, nem az egész döntés.

**Három korlát, amit ez a modul kikényszerít, nem csak dokumentál:**

1. **A dátum mindig a determinisztikus parserből jön.** Az LLM válasza
   dátumot is tartalmazhat — ezt a kaszkád EL SEM OLVASSA. A
   kiegészítés után a `SzabalyAlapuErtelmezo` fut újra, ugyanazon a
   mondaton — a dátumot ez, és mindig ez adja.
2. **A bolt és a szolgáltatás zárt halmazon marad.** Az LLM javasolt
   `bolt_id`-ját a `katalogus.BOLT_SLUGOK` zárt halmaza ellen
   ellenőrizzük, mielőtt bármit kezdenénk vele — érvénytelen/kitalált
   értéket eldobunk, nem engedünk tovább. A szolgáltatás sosem jön az
   LLM-től: az újrafuttatott determinisztikus parser tölti ki (vagy
   nem), ugyanazzal a `BOLT_EGYERTELMU_SZOLGALTATAS` logikával, mint
   egyébként.
3. **Naplózva van, melyik réteg oldotta meg** (`utolso_reteg`,
   `"szabaly"` vagy `"llm"`) — ez a mérőszám arra, mennyit tesz hozzá a
   modell a determinisztikus alapvonalhoz (`python feladat.py golden
   --ertelmezo kaszkad`, réteges bontással)."""

from __future__ import annotations

import logging

from assistant.interpreter import ErtelmezesKontextus, Ertelmezo
from assistant.interpreter.llm_based import LLMErtelmezo
from assistant.interpreter.normalizalo import normalizal
from assistant.interpreter.rule_based import SzabalyAlapuErtelmezo
from assistant.tools.katalogus import BOLT_SLUGOK

_LOG = logging.getLogger(__name__)

# Csak erre a hiányzó mezőre próbál a modell kiegészíteni. A
# `foglalasi_kod` (lemondás/áthelyezés) szándékosan kimarad: a
# rule_based.py lemondás/áthelyezés ága a kódot mindig a MONDATBÓL,
# frissen olvassa ki (nem a kontextusból) — az "újrafuttatás bővített
# kontextussal" trükk emiatt ott nem működne, ehhez a hiányzó eszközhöz
# külön kiegészítő mechanizmus kellene. v1 hatókör-korlát, ugyanabban a
# szellemben, mint az áthelyezés egyfordulós korlátja
# (assistant/orchestrator.py docstring).
_KIEGESZITHETO_MEZOK = frozenset({"bolt_id"})


class KaszkadErtelmezo:
    """Az `Ertelmezo` protokoll kaszkád implementációja — l. modul
    docstring. `llm=None` esetén (nincs configurált modell) tisztán a
    determinisztikus réteg válaszát adja, SOHA nem próbál Ollamát hívni."""

    def __init__(self, szabaly: Ertelmezo | None = None, llm: LLMErtelmezo | None = None):
        self.szabaly = szabaly or SzabalyAlapuErtelmezo()
        self.llm = llm
        # Az utolsó `ertelmez()` hívást melyik réteg oldotta meg —
        # "szabaly" vagy "llm". Ez a mérőszám (modul docstring, 3. pont).
        self.utolso_reteg: str | None = None
        # Az utolsó mondat normalizált alakja — megfigyelhetőséghez
        # (l. `forditott_kaszkad.py` azonos mezője).
        self.utolso_normalizalt: str | None = None

    def ertelmez(self, mondat: str, *, most: str, kontextus: ErtelmezesKontextus) -> dict:
        self.utolso_normalizalt = normalizal(mondat)
        szabaly_eredmeny = self.szabaly.ertelmez(mondat, most=most, kontextus=kontextus)
        self.utolso_reteg = "szabaly"

        if self.llm is None:
            _LOG.info("kaszkád: réteg=szabaly eszköz=%s", szabaly_eredmeny.get("eszkoz"))
            return szabaly_eredmeny

        if szabaly_eredmeny.get("eszkoz") != "visszakerdez":
            # A determinisztikus réteg döntött — ebben a felállásban a
            # modellnek nincs több dolga.
            _LOG.info("kaszkád: réteg=szabaly eszköz=%s", szabaly_eredmeny.get("eszkoz"))
            return szabaly_eredmeny

        hianyzo_mezo = (szabaly_eredmeny.get("parameterek") or {}).get("hianyzo_mezo")
        if hianyzo_mezo not in _KIEGESZITHETO_MEZOK:
            _LOG.info(
                "kaszkád: réteg=szabaly eszköz=visszakerdez (%s, LLM nem próbálja)", hianyzo_mezo
            )
            return szabaly_eredmeny

        llm_eredmeny = self.llm.ertelmez(mondat, most=most, kontextus=kontextus)
        if self.llm.utolso_hiba is not None:
            _LOG.info("kaszkád: réteg=szabaly (az LLM nem elérhető: %s)", self.llm.utolso_hiba)
            return szabaly_eredmeny

        bolt_id = (llm_eredmeny.get("parameterek") or {}).get("bolt_id")
        if bolt_id not in BOLT_SLUGOK:
            _LOG.info("kaszkád: réteg=szabaly (az LLM nem adott érvényes bolt_id-t)")
            return szabaly_eredmeny

        # A determinisztikus parser ÚJRAFUT, a kiegészített bolttal a
        # kontextusban — a dátum/napszak/szolgáltatás innentől is
        # kizárólag innen jön (l. modul docstring, 1-2. korlát).
        bovitett_kontextus = ErtelmezesKontextus(
            megorzott_parameterek={**kontextus.megorzott_parameterek, "bolt_id": bolt_id}
        )
        vegleges = self.szabaly.ertelmez(mondat, most=most, kontextus=bovitett_kontextus)
        if vegleges.get("eszkoz") == "visszakerdez":
            # A kiegészített bolttal is visszakérdezésre jutott a
            # determinisztikus parser (más okból) — nem erőltetjük, az
            # eredeti válasz marad mérvadó.
            _LOG.info("kaszkád: réteg=szabaly (bolt kiegészítve, de újra visszakerdez)")
            return szabaly_eredmeny

        self.utolso_reteg = "llm"
        _LOG.info(
            "kaszkád: réteg=llm eszköz=%s (bolt_id=%s kiegészítve)", vegleges.get("eszkoz"), bolt_id
        )
        return vegleges

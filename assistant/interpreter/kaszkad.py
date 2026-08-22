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

from assistant.interpreter import ErtelmezesKontextus, Ertelmezo, rule_based
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

# A szándék KEMÉNY része (ADR-016, `orchestrator.kovetkezo_kontextus`) —
# ezt egy időről szóló mondat nem engedheti el, l. `_kemeny_reszt_vedd`.
_KEMENY_MEZOK = frozenset({"bolt_id", "szolgaltatas_id"})


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
            # VAN kontextus és a determinisztikus réteg döntött — de a
            # döntése némán MEGTARTHATOTT olyan korábbi paramétert, amit
            # a mondat valójában elenged ("mégis mindegy, mikor"). Ezt a
            # mintaillesztés nem látja: nincs benne olyan szó, amit egy
            # szabály kereshetne. Kulcsszólistát írni rá ráigazítás
            # lenne — ezért ezt a modell dönti el, ZÁRT kimenettel.
            return self._elengedes_finomitas(mondat, most, kontextus, szabaly_eredmeny)

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

    def _elengedes_finomitas(
        self,
        mondat: str,
        most: str,
        kontextus: ErtelmezesKontextus,
        szabaly_eredmeny: dict,
    ) -> dict:
        """A modell megmondja, a megőrzött kontextusból mi ESIK KI az új
        mondat után; a determinisztikus parser ezután újrafut a szűkített
        kontextussal.

        A modell szerepe itt szigorúan zárt: **mezőneveket** ad vissza,
        soha nem értéket (`LLMErtelmezo.valtozas_elemzes`). A dátum
        továbbra is a parserből jön, a bolt a zárt katalógusból — a
        modell csak azt befolyásolja, MELYIK korábbi adatot ne vigyük
        tovább.

        Ez a "bármelyik másik boltban" típusú mondatok kezelése
        kulcsszólista NÉLKÜL: nem felsoroljuk a lehetséges
        megfogalmazásokat (az ráigazítás lenne a mérési halmazra), hanem
        a modellre bízzuk a döntést egy ellenőrizhető, zárt kimenettel."""
        megorzott = kontextus.megorzott_parameterek
        if not megorzott:
            _LOG.info("kaszkád: réteg=szabaly (nincs megőrzött kontextus)")
            return szabaly_eredmeny

        valtozas = self.llm.valtozas_elemzes(mondat, megorzott)
        if not valtozas or not valtozas.get("elenged"):
            _LOG.info("kaszkád: réteg=szabaly (a modell szerint semmi nem esik ki)")
            return szabaly_eredmeny

        elenged = self._kemeny_reszt_vedd(mondat, most, valtozas["elenged"])
        if not elenged:
            _LOG.info("kaszkád: réteg=szabaly (a javasolt elengedést a védőháló kiszűrte)")
            return szabaly_eredmeny

        szukitett = {k: v for k, v in megorzott.items() if k not in elenged}
        vegleges = self.szabaly.ertelmez(
            mondat, most=most, kontextus=ErtelmezesKontextus(megorzott_parameterek=szukitett)
        )
        if vegleges == szabaly_eredmeny:
            # Az elengedés nem változtatott az eredményen — akkor a
            # modell érdemben nem járult hozzá, ne is állítsuk azt.
            _LOG.info("kaszkád: réteg=szabaly (az elengedés nem változtatott)")
            return szabaly_eredmeny

        self.utolso_reteg = "llm"
        _LOG.info("kaszkád: réteg=llm (elengedve: %s)", elenged)
        return vegleges

    @staticmethod
    def _kemeny_reszt_vedd(mondat: str, most: str, elenged: list[str]) -> list[str]:
        """Védőháló a modell túl-elengedése ellen: ha a mondat POZITÍV
        időbeli jelzést tartalmaz (a determinisztikus parser dátumot vagy
        napszakot old fel belőle), akkor a mondat IDŐRŐL szól — ilyenkor
        a KEMÉNY rész (bolt, szolgáltatás) nem eshet ki miatta.

        Ez nem kulcsszólista és nem a mérési halmazhoz igazítás: a
        szándék-rétegzés doktrínájának (ADR-016,
        `orchestrator.kovetkezo_kontextus`) közvetlen alkalmazása — a
        kemény rész csak akkor mozdul, ha a mondat POZITÍVAN mást állít
        róla, nem pusztán attól, hogy nem említi.

        Miért kell: három különböző promptmegfogalmazással mérve a
        qwen3.5:9b vagy MINDENT elengedett (a "bármikor a jövő héten"
        mondatra a boltot is), vagy semmit — a "melyik adatnak mond
        ellent a mondat" osztályozás ezen a modellméreten önmagában nem
        megbízható. A védőháló azt a hibaosztályt zárja ki, ami a
        determinisztikus alapvonalat RONTANÁ."""
        if not rule_based.idobeli_jelzes(mondat, most):
            return list(elenged)
        szurt = [m for m in elenged if m not in _KEMENY_MEZOK]
        if szurt != list(elenged):
            _LOG.info("kaszkád: a kemény rész védve (a mondat időről szól)")
        return szurt

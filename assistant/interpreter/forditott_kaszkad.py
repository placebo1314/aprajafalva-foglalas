"""Fordított kaszkád — a modell értelmez, a determinisztikus réteg a
kapu és a tartalék.

**ÁLLAPOT: MÉRT KÍSÉRLET, NEM AZ ALAPÉRTELMEZÉS** (ADR-018, elvetve).
Ez a modul azért maradt a repóban, hogy a kísérlet reprodukálható
legyen (`python feladat.py golden --ertelmezo forditott`) — az éles út
továbbra is a determinisztikus-előbb `kaszkad.py` (ADR-016).

A 2026-08-22-i mérés (36 eset, qwen3.5:9b) szerint ez a felállás
ÖSSZESÍTETTEN rosszabb: 69,4% a determinisztikus-előbb 80,6%-ával
szemben. Pontosan ott javít, ahol vártuk (nyelvi változatosság
20% -> 60%, kemény rész elengedése 0% -> 66,7%), és mindenütt ront,
amit a szabályok már jól kezeltek (köznyelvi 100% -> 40%, kapuőr
100% -> 50%). Részletek és a visszatérés feltétele: ADR-018.

```
mondat
  │
  ├─ 1. NORMALIZÁLÓ (determinisztikus szótár, normalizalo.py)
  │      tájszólás/szleng/csapdaszó → köznyelvi alak
  │
  ├─ 2. LLM ÉRTELMEZŐ (llm_based.py), kötött dekódolással
  │      az enumok tartják a zárt halmazokat (bolt, szolgáltatás,
  │      napszak, mit) — kitalált érték strukturálisan kizárva;
  │      a dátumot a modell SZÖVEGESEN idézi (`datum_kifejezes`)
  │
  ├─ 3. DÁTUM-KAPU (rule_based.datum_ablak_feloldas)
  │      a `datum_kifejezes`-t a hun-date-parser oldja fel. Ha a modell
  │      mégis ISO-dátumot adott, azt is ellenőrizzük a parserrel —
  │      ELTÉRÉSNÉL A PARSER NYER.
  │
  ├─ 4. BIZONYOSSÁG-KAPU — küszöb alatt zárt kérdés. Ez NEM itt van,
  │      hanem az orchestratorban (blueprint 10.: "a visszakérdezésről
  │      az orchestrator dönt, nem az LLM"); ez a modul csak továbbadja
  │      a `bizonyossag` mezőt.
  │
  └─ TARTALÉK: ha az Ollama nem elérhető / időtúllépés / értelmezhetetlen
        válasz → a `SzabalyAlapuErtelmezo` válasza megy, HIBA NÉLKÜL
```

**Miért fordult meg a sorrend** (ADR-018 részletezi): az ADR-016 döntése
egy félrevezető mérésen állt. A látható golden halmaz a szabályokhoz
igazodott (ezért adott a determinisztikus réteg 100%-ot — ez sosem volt
általánosítási mutató, ahogy a `docs/ALLAPOT.md` mindig is jelezte), az
LLM-mérés pedig few-shot példák, normalizálás és determinisztikus
dátumfeloldás NÉLKÜL futott. A determinisztikus réteg időközben
mintaillesztéssé nőtt (bolt-, napszak-, lemondás-, áthelyezés-minták
listája), és a nyelvi változatosságot elvi okból nem tudja lefedni:
minden új megfogalmazás új mintát igényelne.

**Amit a fordítás NEM változtat meg** — ezek továbbra is
determinisztikusak, és a modell nem kerülheti meg őket:

1. **A dátum a parserből jön.** A modell szöveges kifejezést ad; a
   feloldás a `hun-date-parser`. ISO-válasz esetén a parser felülbírál.
2. **A bolt és a szolgáltatás zárt halmazon marad** — az enum a kötött
   dekódolás szintjén zárja ki a kitalált értéket, és a feloldás után
   is ellenőrizzük.
3. **A foglalási kódot a mondatból olvassuk vissza**, nem a modelltől —
   ott egy elrontott karakter néma hibát okozna.
4. **Naplózva van, melyik réteg oldotta meg** (`utolso_reteg`) — ez a
   mérőszám (`python feladat.py golden --ertelmezo kaszkad`).
"""

from __future__ import annotations

import logging

from assistant.interpreter import ErtelmezesKontextus, Ertelmezo, rule_based
from assistant.interpreter.llm_based import LLMErtelmezo
from assistant.interpreter.normalizalo import normalizal
from assistant.interpreter.rule_based import SzabalyAlapuErtelmezo
from assistant.tools.katalogus import (
    BOLT_EGYERTELMU_SZOLGALTATAS,
    BOLT_SLUGOK,
    SZOLGALTATAS_SLUGOK,
)

_LOG = logging.getLogger(__name__)

# Amit a modell kimenetéből ELDOBUNK, mert determinisztikus forrásból
# kell jönnie (a dátumkifejezés csak nyersanyag a parsernek, a
# session_id az orchestratoré).
_MODELLTOL_NEM_FOGADOTT = frozenset({"datum_kifejezes", "datum_kifejezes_2", "session_id"})


class ForditottKaszkadErtelmezo:
    """Az `Ertelmezo` protokoll fordított kaszkád implementációja — l.
    modul docstring.

    `llm=None` esetén (nincs konfigurált modell) tisztán a
    determinisztikus réteget használja, és SOHA nem próbál Ollamát
    hívni — ez teszi lehetővé, hogy a felület modell nélkül is működjön
    (`ui/vasarlo.py`)."""

    def __init__(self, szabaly: Ertelmezo | None = None, llm: LLMErtelmezo | None = None):
        self.szabaly = szabaly or SzabalyAlapuErtelmezo()
        self.llm = llm
        # "llm" | "szabaly" — melyik réteg adta az utolsó választ.
        self.utolso_reteg: str | None = None
        # Az utolsó mondat normalizált alakja — megfigyelhetőséghez
        # (`ui/vasarlo.py` próba-naplója: mit LÁTOTT a modell). Nem a
        # protokoll része, a hívók `getattr`-ral olvassák.
        self.utolso_normalizalt: str | None = None

    def ertelmez(self, mondat: str, *, most: str, kontextus: ErtelmezesKontextus) -> dict:
        # 1. NORMALIZÁLÓ — determinisztikus szótár a modell ELŐTT
        # (blueprint 7., "Négy technika" 1. pont). A tájszólási és
        # szleng-alakokat nem a modellnek kell kitalálnia. A
        # determinisztikus réteg maga is normalizál, ezért a tartalék-ág
        # a NYERS mondatot kapja — a napló mégis a normalizált alakot
        # mutatja, mert a feldolgozás mindkét úton azon történik.
        normalizalt = normalizal(mondat)
        self.utolso_normalizalt = normalizalt

        if self.llm is None:
            self.utolso_reteg = "szabaly"
            return self.szabaly.ertelmez(mondat, most=most, kontextus=kontextus)

        llm_eredmeny = self.llm.ertelmez(normalizalt, most=most, kontextus=kontextus)
        if self.llm.utolso_hiba is not None:
            # TARTALÉK: az Ollama nem elérhető vagy értelmezhetetlen
            # választ adott — a determinisztikus réteg veszi át, HIBA
            # NÉLKÜL (a vásárló ebből semmit nem vesz észre).
            _LOG.info("kaszkád: tartalék=szabaly (%s)", self.llm.utolso_hiba)
            self.utolso_reteg = "szabaly"
            return self.szabaly.ertelmez(mondat, most=most, kontextus=kontextus)

        self.utolso_reteg = "llm"
        return self._determinisztikus_kapuk(llm_eredmeny, mondat, most, kontextus)

    def _determinisztikus_kapuk(
        self, llm_eredmeny: dict, mondat: str, most: str, kontextus: ErtelmezesKontextus
    ) -> dict:
        """A modell kimenetét átengedi a determinisztikus kapukon: zárt
        halmazok ellenőrzése, dátumfeloldás a parserrel, kontextus-
        öröklés. A modell egyik kaput sem kerülheti meg."""
        eszkoz = llm_eredmeny.get("eszkoz")
        nyers = dict(llm_eredmeny.get("parameterek") or {})
        parameterek = {k: v for k, v in nyers.items() if k not in _MODELLTOL_NEM_FOGADOTT}
        bizonyossag = llm_eredmeny.get("bizonyossag", {})

        # ZÁRT HALMAZOK — az enum a dekódolás szintjén véd, de ha egy
        # jövőbeli szolgáltató mégis mást adna vissza, itt is kiesik.
        if parameterek.get("bolt_id") not in BOLT_SLUGOK:
            parameterek.pop("bolt_id", None)
        if parameterek.get("szolgaltatas_id") not in SZOLGALTATAS_SLUGOK:
            parameterek.pop("szolgaltatas_id", None)

        if eszkoz == "nincs":
            return {"eszkoz": "nincs", "parameterek": {}, "bizonyossag": bizonyossag}

        if eszkoz == "bolt_info":
            return self._bolt_info_kapu(parameterek, nyers, most, bizonyossag)

        if eszkoz == "foglalas_lemondas":
            kod = rule_based.foglalasi_kod_kiolvas(mondat) or parameterek.get("foglalasi_kod")
            if not kod:
                return self._visszakerdez("foglalasi_kod", "nyitott", bizonyossag)
            return {
                "eszkoz": "foglalas_lemondas",
                "parameterek": {"foglalasi_kod": kod},
                "bizonyossag": bizonyossag,
            }

        if eszkoz == "visszakerdez":
            hianyzo = parameterek.get("hianyzo_mezo") or "bolt_id"
            return self._visszakerdez(
                hianyzo,
                parameterek.get("varhato_kerdes_tipusa", "zart"),
                bizonyossag,
                megorzott=self._megorzendo(parameterek, nyers, most, kontextus),
            )

        return self._kereses_kapu(parameterek, nyers, most, kontextus, bizonyossag)

    # -- dátum-kapu ----------------------------------------------------

    @staticmethod
    def _datum_ablak(nyers: dict, most: str) -> tuple[str | None, str | None, str | None]:
        """`(datum_tol, datum_ig, napszak_a_kifejezesbol)` — a
        determinisztikus dátumfeloldás.

        A modell `datum_kifejezes` mezője az elsődleges forrás. Ha a
        modell (a prompt ellenére) ISO-dátumot adott `datum_tol`-ban,
        azt is ELLENŐRIZZÜK: a kifejezésből feloldott ablak nyer, mert
        a parser determinisztikus, a modell számolása nem.

        **Vagylagos/feltételes időpont** (`datum_kifejezes_2`): ha a
        mondat két lehetőséget ad ("szerdán, ha nincs, akkor csütörtök"),
        MINDKETTŐT feloldjuk, és a kettőt lefedő ablakot adjuk vissza —
        az ÖSSZEVONÁS is determinisztikus, a modell csak idéz. Ez azért
        helyes, mert a pontozó úgyis a ténylegesen szabad slotokból
        választ: egy tágabb ablakban benne van mindkét kért nap, és a
        vásárló nem veszíti el a második lehetőségét."""
        kifejezes = (nyers.get("datum_kifejezes") or "").strip()
        parser_tol, parser_ig = rule_based.datum_ablak_feloldas(kifejezes, most)
        napszak = rule_based.napszak_feloldas(kifejezes) if kifejezes else None

        masodik = (nyers.get("datum_kifejezes_2") or "").strip()
        if masodik:
            masodik_tol, masodik_ig = rule_based.datum_ablak_feloldas(masodik, most)
            if masodik_tol:
                if parser_tol:
                    parser_tol = min(parser_tol, masodik_tol)
                    parser_ig = max(parser_ig or parser_tol, masodik_ig or masodik_tol)
                else:
                    parser_tol, parser_ig = masodik_tol, masodik_ig
            napszak = napszak or rule_based.napszak_feloldas(masodik)

        if parser_tol:
            modell_tol = nyers.get("datum_tol")
            if modell_tol and modell_tol[:10] != parser_tol[:10]:
                _LOG.info(
                    "kaszkád: a parser felülírja a modell dátumát (%s -> %s)",
                    modell_tol,
                    parser_tol,
                )
            return parser_tol, parser_ig, napszak

        if nyers.get("datum_tol"):
            _LOG.info("kaszkád: a modell ISO-dátuma feloldható kifejezés nélkül maradt, eldobva")
        return None, None, napszak

    def _kereses_kapu(
        self,
        parameterek: dict,
        nyers: dict,
        most: str,
        kontextus: ErtelmezesKontextus,
        bizonyossag: dict,
    ) -> dict:
        bolt_id = parameterek.get("bolt_id") or kontextus.megorzott_parameterek.get("bolt_id")
        if bolt_id is None:
            return self._visszakerdez(
                "bolt_id",
                "zart",
                bizonyossag,
                megorzott=self._megorzendo(parameterek, nyers, most, kontextus),
            )

        datum_tol, datum_ig, kifejezes_napszak = self._datum_ablak(nyers, most)
        napszak = parameterek.get("napszak") or kifejezes_napszak

        vegleges: dict = {"bolt_id": bolt_id}
        if datum_tol:
            vegleges["datum_tol"] = datum_tol
            vegleges["datum_ig"] = datum_ig
        elif kontextus.megorzott_parameterek.get("datum_tol"):
            vegleges["datum_tol"] = kontextus.megorzott_parameterek["datum_tol"]
            vegleges["datum_ig"] = kontextus.megorzott_parameterek.get("datum_ig")
        else:
            vegleges["datum_tol"], vegleges["datum_ig"] = rule_based.altalanos_ablak(most)

        vegleges["napszak"] = napszak or "barmikor"
        if napszak:
            vegleges["datum_ig"] = rule_based.napszak_ablak_vagas(
                vegleges["datum_tol"], vegleges["datum_ig"], napszak
            )

        szolgaltatas = parameterek.get("szolgaltatas_id") or BOLT_EGYERTELMU_SZOLGALTATAS.get(
            bolt_id
        )
        if szolgaltatas:
            vegleges["szolgaltatas_id"] = szolgaltatas
        if "preferalt_ora" in parameterek:
            vegleges["preferalt_ora"] = parameterek["preferalt_ora"]

        return {
            "eszkoz": "szabad_idopontok",
            "parameterek": vegleges,
            "bizonyossag": bizonyossag,
        }

    def _bolt_info_kapu(self, parameterek: dict, nyers: dict, most: str, bizonyossag: dict) -> dict:
        bolt_id = parameterek.get("bolt_id")
        if bolt_id is None:
            return self._visszakerdez("bolt_id", "zart", bizonyossag)
        vegleges = {"bolt_id": bolt_id, "mit": parameterek.get("mit") or "nyitvatartas"}
        datum_tol, _, _ = self._datum_ablak(nyers, most)
        if datum_tol:
            # `bolt_info.datum` csak a naptári nap, idő nélkül.
            vegleges["datum"] = datum_tol[:10]
        return {"eszkoz": "bolt_info", "parameterek": vegleges, "bizonyossag": bizonyossag}

    # -- segédek --------------------------------------------------------

    @staticmethod
    def _megorzendo(
        parameterek: dict, nyers: dict, most: str, kontextus: ErtelmezesKontextus
    ) -> dict:
        """Amit egy visszakérdezésbe át kell vinni, hogy ne kelljen újra
        megkérdezni (golden set, toredekes-03)."""
        megorzott = dict(kontextus.megorzott_parameterek)
        datum_tol, datum_ig, kifejezes_napszak = ForditottKaszkadErtelmezo._datum_ablak(nyers, most)
        if datum_tol:
            megorzott["datum_tol"] = datum_tol
            megorzott["datum_ig"] = datum_ig
        napszak = parameterek.get("napszak") or kifejezes_napszak
        if napszak:
            megorzott["napszak"] = napszak
            if megorzott.get("datum_tol") and megorzott.get("datum_ig"):
                megorzott["datum_ig"] = rule_based.napszak_ablak_vagas(
                    megorzott["datum_tol"], megorzott["datum_ig"], napszak
                )
        for mezo in ("bolt_id", "szolgaltatas_id", "preferalt_ora"):
            if mezo in parameterek:
                megorzott[mezo] = parameterek[mezo]
        return megorzott

    @staticmethod
    def _visszakerdez(
        hianyzo_mezo: str,
        kerdes_tipusa: str,
        bizonyossag: dict,
        megorzott: dict | None = None,
    ) -> dict:
        parameterek: dict = {
            "hianyzo_mezo": hianyzo_mezo,
            "varhato_kerdes_tipusa": kerdes_tipusa,
        }
        if hianyzo_mezo == "bolt_id":
            parameterek["valaszthato_ertekek"] = sorted(BOLT_SLUGOK)
        if megorzott:
            parameterek.update({k: v for k, v in megorzott.items() if k != "hianyzo_mezo"})
        return {
            "eszkoz": "visszakerdez",
            "parameterek": parameterek,
            "bizonyossag": bizonyossag,
        }

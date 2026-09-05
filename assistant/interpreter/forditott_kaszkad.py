"""Fordított kaszkád — a modell értelmez, a determinisztikus réteg a
kapu és a tartalék.

**ÁLLAPOT: EZ AZ ÉLES ÚT** (ADR-018, elfogadva 2026-08-23 — felülírja
az ADR-016 sorrendjét; a beszélgetés-alapú bemenet: ADR-019). Ezt építi
fel az `assistant/interpreter/__init__.py::alapertelmezett_ertelmezo()`,
ezt használja a `ui/vasarlo.py`. A determinisztikus-előbb sorrend
(`kaszkad.py`) a repóban maradt: az a visszaút, `--ertelmezo
kaszkad`-dal mérhető.

**A modell a BESZÉLGETÉST látja** (ADR-019), nem a megőrzött
paramétereket adatként. A bemenete az utolsó néhány forduló
párbeszédként, a végén az aktuális mondattal — és EGY hívásban adja
vissza a teljes kérést. Ami korábban elhangzott és még érvényes, azt
kitölti; ami a beszélgetés szerint már nem érvényes ("és bármelyik
másik boltban?"), azt egyszerűen nem tölti ki. **Nincs "elengedés"
fogalom, és nincs külön hívás rá** — az korábban volt, és sebtapasz
volt: a gyökérok az volt, hogy a modell nem látta a beszélgetést.

```
mondat + előzmények
  │
  ├─ 0. KAPUŐR (assistant/kapuor/, ADR-020) — HATÓKÖR-döntés
  │      zárt, három elemű osztályozás: foglalási szándék /
  │      engedélyezett tényválasz / azon kívüli. Kívül esőnél a
  │      modell MEG SEM SZÓLAL — `nincs` megy vissza, modellhívás
  │      nélkül. Engedélyezett tényválasznál, ha a bolt is
  │      determinisztikusan feloldható, egyenesen a szerkesztett
  │      adathoz megyünk (szintén modellhívás nélkül).
  │
  ├─ 1. NORMALIZÁLÓ (determinisztikus szótár, normalizalo.py)
  │      tájszólás/szleng/csapdaszó → köznyelvi alak
  │
  ├─ 2. LLM ÉRTELMEZŐ (llm_based.py), kötött dekódolással
  │      az enumok tartják a zárt halmazokat (bolt, szolgáltatás,
  │      napszak, mit, hianyzo_mezo) — kitalált érték strukturálisan
  │      kizárva; a dátumot a modell SZÖVEGESEN idézi
  │      (`datum_kifejezes`, vagylagosnál `datum_kifejezes_2`); a
  │      bemenet a BESZÉLGETÉS, nem a kontextus adatként
  │
  ├─ 3. DÁTUM-KAPU (rule_based.datum_ablak_feloldas)
  │      a `datum_kifejezes`-t a hun-date-parser oldja fel, két
  │      kifejezésnél az ablakokat determinisztikusan összevonjuk. Ha a
  │      modell mégis ISO-dátumot adott, azt is ellenőrizzük a
  │      parserrel — ELTÉRÉSNÉL A PARSER NYER.
  │
  ├─ 4. PÓTLÁS-KAPU — amit a modell kihagyott, de determinisztikusan
  │      LÁTSZIK a mondatban (dátum, napszak, szolgáltatás, preferált
  │      óra), azt a szabály-alapú kinyerés pótolja. A modell válasza
  │      MINDIG nyer; a szabály csak hiányt tölt.
  │
  ├─ 5. BIZONYOSSÁG-KAPU — küszöb alatt zárt kérdés. Ez NEM itt van,
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

**A kapuőr azóta determinisztikus** (ADR-020, 2026-08-23). Az ADR-018
"A következő lépés" szakasza ezt jelölte ki nyitott pontnak: a
"Mennyibe kerül a nagy petárda?" mondatra a modell döntött, és a
mérésen 50%-ot adott. Azóta a hatókör-döntés a modell ELŐTT fut
(`assistant/kapuor/`), zárt osztályozással, és a kívül eső kérésnél a
modell meg sem szólal. Ez ténylegesen hibrid architektúra — a fordított
kaszkád a hatókörön BELÜLI kérésekre vonatkozik, nem mindenre.

**Amit a fordítás NEM változtat meg** — ezek továbbra is
determinisztikusak, és a modell nem kerülheti meg őket:

1. **A dátum a parserből jön.** A modell szöveges kifejezést ad; a
   feloldás a `hun-date-parser`. ISO-válasz esetén a parser felülbírál.
2. **A bolt és a szolgáltatás zárt halmazon marad** — az enum a kötött
   dekódolás szintjén zárja ki a kitalált értéket, és a feloldás után
   is ellenőrizzük.
3. **A foglalási kódot a mondatból olvassuk vissza**, nem a modelltől —
   ott egy elrontott karakter néma hibát okozna.
4. **A megőrzött kontextus csak TARTALÉK** (`_tartalek`), nem bemenet:
   akkor tölt ki egy mezőt, ha a modell NEM látta a beszélgetést. Ha
   látta és üresen hagyta, az a döntése (ADR-019).
5. **Naplózva van, melyik réteg oldotta meg** (`utolso_reteg`) — ez a
   mérőszám (`python feladat.py golden --ertelmezo forditott`), és ez
   jelenik meg a felület próba-naplójában is (`naplo/probak.jsonl`).
"""

from __future__ import annotations

import logging
import re
import time

from assistant import kapuor
from assistant.interpreter import ErtelmezesKontextus, Ertelmezo, rule_based
from assistant.interpreter.llm_based import LLMErtelmezo, Mintavetel
from assistant.interpreter.normalizalo import normalizal
from assistant.interpreter.rule_based import SzabalyAlapuErtelmezo
from assistant.tools import katalogus
from assistant.tools.katalogus import (
    BOLT_EGYERTELMU_SZOLGALTATAS,
    BOLT_SLUGOK,
    MINDEGY,
    SZOLGALTATAS_SLUGOK,
)

_LOG = logging.getLogger(__name__)

# Amit a modell kimenetéből ELDOBUNK, mert determinisztikus forrásból
# kell jönnie (a dátumkifejezés csak nyersanyag a parsernek, a
# session_id az orchestratoré).
_MODELLTOL_NEM_FOGADOTT = frozenset({"datum_kifejezes", "datum_kifejezes_2", "session_id"})

# Amire ÉRDEMES visszakérdezni: enélkül a művelet nem indítható el. A
# szolgáltatás (méret) szándékosan NEM ilyen — a keresés elindulhat a
# bolt szintjén, a pontosítás jöhet az ajánlat után (golden set,
# egyszerusitett-04 megjegyzése), és a determinisztikus réteg sem kérdez
# rá soha.
_BLOKKOLO_MEZOK = frozenset({"bolt_id", "foglalasi_kod"})

# MELYIK RÉTEG oldotta meg (`utolso_reteg`) — zárt halmaz.
#
# **A `szabaly` HÁROM okból szólalhat meg, és a három nem ugyanaz.**
# Korábban mindhárom `"szabaly"`-ként naplózódott, és a napló-elemző
# (`tools/naplo_elemzo.py`) emiatt téves riasztást adott: a
# gombnyomásos és a tényválasz-rövidzárat "csendes tartaléknak"
# minősítette, holott mindkettő SZÁNDÉKOS, tervezett út. A megkülönböztetés
# ezért a FORRÁSNÁL van, nem az elemzőben találgatva:
#
# - `szabaly:zart_valasz` — a mondat MAGA egy zárt halmazbeli érték
#   (gombnyomás). Tervezett, gyors, modellhívás nélküli út.
# - `szabaly:tenyvalasz` — a kapuőr engedélyezett tényválaszt látott, és
#   a bolt is feloldható (ADR-020). Tervezett, a blueprint 10. szakasza
#   szerinti.
# - `szabaly:tartalek` — az Ollama NEM elérhető, vagy nincs konfigurált
#   modell. **Ez az egyetlen, ami figyelmet érdemel**: ha modell VAN
#   konfigurálva és mégis ide futunk, valami elromlott.
RETEG_KAPUOR = "kapuor"
RETEG_LLM = "llm"
RETEG_SZABALY_ZART_VALASZ = "szabaly:zart_valasz"
RETEG_SZABALY_TENYVALASZ = "szabaly:tenyvalasz"
RETEG_SZABALY_TARTALEK = "szabaly:tartalek"


class ForditottKaszkadErtelmezo:
    """Az `Ertelmezo` protokoll fordított kaszkád implementációja — l.
    modul docstring.

    `llm=None` esetén (nincs konfigurált modell) tisztán a
    determinisztikus réteget használja, és SOHA nem próbál Ollamát
    hívni — ez teszi lehetővé, hogy a felület modell nélkül is működjön
    (`ui/vasarlo.py`)."""

    # Az önkonzisztencia-burkoló ebből tudja, hogy a mintavétel átmegy
    # rajta a modellig (`onkonzisztencia.py`, ADR-021).
    TAMOGAT_MINTAVETELT = True

    def __init__(self, szabaly: Ertelmezo | None = None, llm: LLMErtelmezo | None = None):
        self.szabaly = szabaly or SzabalyAlapuErtelmezo()
        self.llm = llm
        # Melyik réteg adta az utolsó választ — a fenti `RETEG_*` zárt
        # halmazból. A `kapuor` azt jelenti, hogy a modell meg sem
        # szólalt; a három `szabaly:*` érték három KÜLÖNBÖZŐ okot jelöl.
        self.utolso_reteg: str | None = None
        # Az utolsó kapuőr-döntés — megfigyelhetőséghez (napló,
        # `tools/naplo_elemzo.py`). Nem a protokoll része.
        self.utolso_kapuor: kapuor.KapuorDontes | None = None
        # Az utolsó mondat normalizált alakja — megfigyelhetőséghez
        # (`ui/vasarlo.py` próba-naplója: mit LÁTOTT a modell). Nem a
        # protokoll része, a hívók `getattr`-ral olvassák.
        self.utolso_normalizalt: str | None = None
        # NYOMKÖVETÉS: lépésenkénti idő, dátumfeloldás (modell vs.
        # parser), és mezőnkénti FORRÁS. A beszélgetés-elemző
        # (`tools/beszelgetes_riport.py`) ebből mutatja meg, hogy egy
        # paraméter honnan jött — a modelltől, a parsertől, a zárt
        # halmazból vagy a megőrzött kontextusból. Enélkül a naplóból
        # csak az látszik, MI lett a végeredmény.
        self.utolso_nyomkovetes: dict = {}

    def ertelmez(
        self,
        mondat: str,
        *,
        most: str,
        kontextus: ErtelmezesKontextus,
        mintavetel: Mintavetel | None = None,
    ) -> dict:
        """`mintavetel`: az önkonzisztencia-burkoló
        (`onkonzisztencia.py`, ADR-021) adja át — a MODELLIG megy le
        változatlanul, a determinisztikus kapukat nem érinti. `None`
        esetén minden pontosan úgy fut, mint eddig (`temperature: 0`)."""
        self.utolso_nyomkovetes = {"lepesek": [], "mezo_forras": {}, "datum": {}}
        kezdet = time.monotonic()

        # 0. KAPUŐR — hatókör-döntés a modell ELŐTT (ADR-020, blueprint
        # 10.). Kívül eső kérésnél a modell MEG SEM SZÓLAL: nem hívjuk
        # meg. Ez nem prompt-fegyelem kérdése, hanem architektúráé — és
        # egyben a leggyorsabb ág is (nulla modellhívás).
        kapuor_dontes = kapuor.dontes(mondat)
        self._lepes("kapuőr", kezdet)
        self.utolso_nyomkovetes["kapuor"] = {
            "kategoria": kapuor_dontes.kategoria,
            "ok": kapuor_dontes.ok,
            "minta": kapuor_dontes.minta,
        }
        if kapuor_dontes.kivul:
            self.utolso_reteg = RETEG_KAPUOR
            self.utolso_normalizalt = normalizal(mondat)
            self.utolso_kapuor = kapuor_dontes
            return {
                "eszkoz": "nincs",
                "parameterek": {},
                "bizonyossag": {"eszkoz": 1.0},
                "kapuor_ok": kapuor_dontes.ok,
            }

        # META-KÉRDÉS: magáról a rendszerről kérdez. Ugyanaz a rövidzár,
        # mint a hatókörön kívüli ágé (nulla modellhívás), de MÁS a
        # kimenete: erre van válaszunk. Az éles próba (2026-09-05) mutatta
        # meg, miért kell — a „csak a választ beszéled?" mondatból
        # keresés lett, és a rendszer újra felajánlotta ugyanazokat az
        # időpontokat.
        # KÖSZÖNÉS és KÍNÁLAT-KÉRDÉS (ADR-032) — mindkettő rövidzár,
        # nulla modellhívással. Az első idegen próbában ezekre a
        # mondatokra visszakérdezés, majd kiút jött: a rendszer olyat
        # kérdezett vissza („melyik boltba?"), amit a vásárló épp nem
        # tudhatott.
        if kapuor_dontes.kategoria == kapuor.KOSZONES:
            self.utolso_reteg = RETEG_KAPUOR
            self.utolso_normalizalt = normalizal(mondat)
            self.utolso_kapuor = kapuor_dontes
            return {"eszkoz": "koszones", "parameterek": {}, "bizonyossag": {"eszkoz": 1.0}}

        if kapuor_dontes.ok == kapuor.OK_KINALAT:
            self.utolso_reteg = RETEG_KAPUOR
            self.utolso_normalizalt = normalizal(mondat)
            self.utolso_kapuor = kapuor_dontes
            # A BOLT SZŰKÍTÉSE, ha a mondatból vagy a beszélgetésből
            # kiderül: „és a Szundinál mi van?" — ilyenkor a másik két
            # bolt felsorolása zaj lenne.
            bolt_id = rule_based.bolt_feloldas(mondat) or self._tartalek(kontextus, "bolt_id")
            parameterek = {"bolt_id": bolt_id} if bolt_id else {}
            return {"eszkoz": "kinalat", "parameterek": parameterek, "bizonyossag": {"eszkoz": 1.0}}

        if kapuor_dontes.kategoria == kapuor.META_KERDES:
            self.utolso_reteg = RETEG_KAPUOR
            self.utolso_normalizalt = normalizal(mondat)
            self.utolso_kapuor = kapuor_dontes
            return {
                "eszkoz": "meta_valasz",
                "parameterek": {},
                "bizonyossag": {"eszkoz": 1.0},
            }
        self.utolso_kapuor = kapuor_dontes

        # 1. NORMALIZÁLÓ — determinisztikus szótár a modell ELŐTT
        # (blueprint 7., "Négy technika" 1. pont). A tájszólási és
        # szleng-alakokat nem a modellnek kell kitalálnia. A
        # determinisztikus réteg maga is normalizál, ezért a tartalék-ág
        # a NYERS mondatot kapja — a napló mégis a normalizált alakot
        # mutatja, mert a feldolgozás mindkét úton azon történik.
        normalizalt = normalizal(mondat)
        self.utolso_normalizalt = normalizalt
        self._lepes("normalizáló", kezdet)

        if self.llm is None:
            self.utolso_reteg = RETEG_SZABALY_TARTALEK
            return self._szabaly_uttal(mondat, most, kontextus, kezdet)
        if self._zart_valasz_e(normalizalt):
            self.utolso_reteg = RETEG_SZABALY_ZART_VALASZ
            return self._szabaly_uttal(mondat, most, kontextus, kezdet)

        # A KAPUŐR MÁSODIK KATEGÓRIÁJA: engedélyezett tényválasz, zárt
        # listából. A blueprint 10. szakasza szerint ez "nem hívja az
        # értelmezőt tartalmi kérdésben, egyenesen a szerkedett
        # adathoz megy" — és itt ez ténylegesen megtehető, mert a
        # tényválaszhoz kellő MINDKÉT adat determinisztikus: a `mit`-et
        # a kapuőr adja (a modell válaszát amúgy is felülírtuk vele), a
        # boltot a zárt halmazú `bolt_feloldas`.
        #
        # Ha a bolt NEM oldható fel determinisztikusan (pl. a
        # megjelenésével körülírva — "a csillagos kirakatú bolt"), az ág
        # nem szólal meg, és a mondat megy a modellhez, ahogy eddig.
        if kapuor_dontes.kategoria == kapuor.ENGEDELYEZETT_TENYVALASZ:
            bolt_id = rule_based.bolt_feloldas(mondat)
            if bolt_id is not None:
                self.utolso_reteg = RETEG_SZABALY_TENYVALASZ
                return self._szabaly_uttal(mondat, most, kontextus, kezdet)

        llm_eredmeny = self.llm.ertelmez(
            normalizalt, most=most, kontextus=kontextus, mintavetel=mintavetel
        )
        self._lepes("modellhívás", kezdet)
        if self.llm.utolso_hiba is not None:
            # TARTALÉK: az Ollama nem elérhető vagy értelmezhetetlen
            # választ adott — a determinisztikus réteg veszi át, HIBA
            # NÉLKÜL (a vásárló ebből semmit nem vesz észre).
            _LOG.info("kaszkád: tartalék=szabaly (%s)", self.llm.utolso_hiba)
            self.utolso_reteg = RETEG_SZABALY_TARTALEK
            return self._szabaly_uttal(mondat, most, kontextus, kezdet)

        self.utolso_reteg = RETEG_LLM
        eredmeny = self._determinisztikus_kapuk(llm_eredmeny, mondat, most, kontextus)
        self._lepes("determinisztikus kapuk", kezdet)
        return eredmeny

    def _szabaly_uttal(
        self, mondat: str, most: str, kontextus: ErtelmezesKontextus, kezdet: float
    ) -> dict:
        """A determinisztikus réteg futtatása, a lépés idejével együtt —
        mindhárom `szabaly:*` ág ezen megy át, hogy a nyomkövetésben ne
        maradjon lyuk."""
        eredmeny = self.szabaly.ertelmez(mondat, most=most, kontextus=kontextus)
        self._lepes(f"szabály-alapú réteg ({self.utolso_reteg})", kezdet)
        return eredmeny

    def _lepes(self, nev: str, kezdet: float) -> None:
        """Egy feldolgozási lépés lezárása a nyomkövetésben.

        Az idő a forduló KEZDETÉTŐL mért, tehát a lépések összege nem az
        összidő — a lépésenkénti időt a különbségük adja. Ez szándékos:
        így egy kihagyott lépés sem tud „elveszni" a mérésből."""
        nyom = self.utolso_nyomkovetes.setdefault("lepesek", [])
        eddig = sum(lepes["masodperc"] for lepes in nyom)
        # A `max(0.0, …)` az órafelbontás miatt kell: egy mikroszekundum
        # alatti lépésnél a kivonás apró negatív számot adna, ami a
        # jelentésben zavaró (és értelmetlen).
        telt = max(0.0, time.monotonic() - kezdet - eddig)
        nyom.append({"nev": nev, "masodperc": round(telt, 4)})

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
        #
        # A `MINDEGY` a halmaz RÉSZE (`katalogus.MINDEGY`): nem kitalált
        # érték, hanem a vásárló kimondott döntése, hogy elengedi a
        # mezőt. Ha itt kiesne, a rendszer újra rákérdezne arra, amit
        # épp elengedtek — pontosan az a hiba, amiért a szentinel van.
        if parameterek.get("bolt_id") not in {*BOLT_SLUGOK, MINDEGY}:
            parameterek.pop("bolt_id", None)
        if parameterek.get("szolgaltatas_id") not in {*SZOLGALTATAS_SLUGOK, MINDEGY}:
            parameterek.pop("szolgaltatas_id", None)

        if eszkoz == "nincs":
            return {"eszkoz": "nincs", "parameterek": {}, "bizonyossag": bizonyossag}

        if eszkoz == "dontsd_el_te":
            # NINCS paramétere: a vásárló épp azt mondta, hogy neki
            # mindegy. A tartomány- és állapot-ellenőrzés az
            # orchestratoré (ő ismeri a jelölteket) — l. ott.
            return {
                "eszkoz": "dontsd_el_te",
                "parameterek": {},
                "bizonyossag": bizonyossag,
            }

        if eszkoz == "jelolt_valasztas":
            # A SORSZÁM az egyetlen érdemi mező, és egész számnak kell
            # lennie. A TARTOMÁNYT nem itt ellenőrizzük: az értelmező nem
            # tudja, hány jelöltet ajánlottunk fel — azt az orchestrator
            # tudja, és ő is utasítja vissza a tartományon kívülit
            # (ugyanaz az elv, mint a sorszámos rövidzárnál).
            sorszam = parameterek.get("sorszam")
            if not isinstance(sorszam, int) or sorszam < 1:
                return {"eszkoz": "nincs", "parameterek": {}, "bizonyossag": bizonyossag}
            return {
                "eszkoz": "jelolt_valasztas",
                "parameterek": {"sorszam": sorszam},
                "bizonyossag": bizonyossag,
            }

        if eszkoz == "bolt_info":
            return self._bolt_info_kapu(parameterek, nyers, mondat, most, bizonyossag)

        if eszkoz == "foglalas_lemondas":
            kod = rule_based.foglalasi_kod_kiolvas(mondat) or parameterek.get("foglalasi_kod")
            if not kod:
                return self._visszakerdez("foglalasi_kod", "nyitott", bizonyossag)
            return {
                "eszkoz": "foglalas_lemondas",
                "parameterek": {"foglalasi_kod": kod},
                "bizonyossag": bizonyossag,
            }

        if eszkoz == "legkozelebbi_idopont":
            return self._legkozelebbi_kapu(parameterek, mondat, kontextus, bizonyossag)

        if eszkoz == "visszakerdez":
            hianyzo = parameterek.get("hianyzo_mezo") or "bolt_id"
            if hianyzo not in _BLOKKOLO_MEZOK:
                # A szolgáltatás (méret) NEM blokkoló mező: a keresés
                # elindulhat a bolt szintjén, a pontosítás jöhet az
                # ajánlat után — a determinisztikus réteg sem kérdez rá
                # soha. Ha a modell mégis erre kérdezne, azt keresésre
                # fordítjuk, ÉS eldobjuk a saját szolgáltatás-értékét:
                # ha ő maga mondja, hogy ez a mező hiányzik, akkor az
                # értéke sem használható.
                _LOG.info("kaszkád: nem blokkoló mezőre kérdezne (%s) — keresés megy", hianyzo)
                parameterek.pop("szolgaltatas_id", None)
                return self._kereses_kapu(parameterek, nyers, mondat, most, kontextus, bizonyossag)
            if hianyzo == "bolt_id" and self._tartalek_bolt(parameterek, kontextus):
                # TARTALÉK-KAPU: ha a modell NEM látta a beszélgetést
                # (nincs előzmény — pl. első forduló után egy tisztán
                # determinisztikus úton érkező mondat), de a megőrzött
                # kontextus ismeri a boltot, akkor nem kérdezünk rá újra
                # (a vásárló 6. igénye: javítás, ne újrakezdés).
                #
                # Ha viszont a modell LÁTTA a beszélgetést, és mégis a
                # boltra kérdez, az a DÖNTÉSE — pontosan ez az az eset,
                # amikor a vásárló elvetette a korábbi boltot
                # ("és bármelyik másik boltban?"). Ilyenkor a
                # visszakérdezés a helyes válasz (ADR-019).
                _LOG.info("kaszkád: a modell a boltra kérdezne, de a tartalék ismeri — keresés")
                return self._kereses_kapu(parameterek, nyers, mondat, most, kontextus, bizonyossag)
            return self._visszakerdez(
                hianyzo,
                parameterek.get("varhato_kerdes_tipusa", "zart"),
                bizonyossag,
                megorzott=self._megorzendo(parameterek, nyers, mondat, most, kontextus),
            )

        return self._kereses_kapu(parameterek, nyers, mondat, most, kontextus, bizonyossag)

    @staticmethod
    def _zart_valasz_e(normalizalt: str) -> bool:
        """A mondat MAGA egy zárt halmazbeli érték-e (bolt-slug vagy
        bolt-név), és semmi más?

        Ez egy zárt kérdésre adott gombnyomás: a felület a
        `visszakerdez` `valaszthato_ertekek` listájából küld vissza egy
        elemet új fordulóként (`ui/vasarlo.py::_szo_kuldes`). Az ilyen
        válasz NEM szabad szöveg — egy zárt halmaz eleme —, ezért nincs
        mit értelmeztetni rajta: a determinisztikus réteg pontosan
        tudja, mit jelent.

        **Miért kell külön kapu:** a fej nélküli végigjátszás megfogta,
        hogy a modell a puszta `"torpilla"` szóra ÚJRA visszakérdezett a
        boltra — vagyis a gombnyomásos, akadálymentes út (a felület
        legfontosabb kisegítő eleme) modellel használhatatlan volt.
        Teljes sztring-egyezés zárt halmazon, nem kulcsszólista."""
        jelolt = normalizalt.strip().strip(".!?").lower()
        if not jelolt:
            return False
        return jelolt in BOLT_SLUGOK or jelolt in {
            nev.lower() for nev in katalogus.BOLT_NEVEK.values()
        }

    @staticmethod
    def _tartalek(kontextus: ErtelmezesKontextus, mezo: str):
        """A megőrzött kontextus TARTALÉK értéke egy mezőre — de csak
        akkor, ha a modell NEM látta a beszélgetést (ADR-019).

        Ha látta és mégis üresen hagyta a mezőt, az a döntése: a
        beszélgetésből nyilván az derült ki, hogy az adat már nem
        érvényes. Ilyenkor a megőrzött érték visszacsempészése pontosan
        azt a hibát okozná, ami miatt korábban külön "elengedés"-hívásra
        volt szükség."""
        if kontextus.elozmenyek:
            return None
        return kontextus.megorzott_parameterek.get(mezo)

    @staticmethod
    def _tartalek_bolt(parameterek: dict, kontextus: ErtelmezesKontextus) -> str | None:
        """A bolt a modell válaszából VAGY (előzmények híján) a megőrzött
        kontextusból — a zárt halmaz ellen ellenőrizve."""
        for jelolt in (
            parameterek.get("bolt_id"),
            ForditottKaszkadErtelmezo._tartalek(kontextus, "bolt_id"),
        ):
            if jelolt in {*BOLT_SLUGOK, MINDEGY}:
                return jelolt
        return None

    # -- MINDEGY-VISSZAVONÁS és VISSZAUTALÁS ---------------------------

    @staticmethod
    def _mindegy_visszavonva(mezo_ertek, mondatbeli):
        """Az elengedett mező VISSZAVONVA, ha a mondat konkrét értéket
        mond ki.

        **Az elengedés nem egyirányú ajtó.** A három állapot (nem tudjuk
        / elengedve / tudjuk) között oda-vissza kell tudni mozogni: aki
        azt mondta, „bármelyik petárda jó", később mondhatja azt, hogy
        „mégis inkább a nagyot". Ez a kapu ezt kikényszeríti — nem a
        modellre bízza.

        **Miért kapu, és miért nem prompt.** Prompttal MEGPRÓBÁLTUK
        (2026-09-05, két futáson mérve): a célzott eset továbbra is
        bukott, az összesített szám nem javult. A modell a beszélgetésben
        látott „mindegy"-et viszi tovább — a mondatban kimondott konkrét
        érték viszont determinisztikusan kinyerhető, tehát nem kell
        találgatni."""
        if mezo_ertek == MINDEGY and mondatbeli:
            _LOG.info("kaszkád: a MINDEGY visszavonva a mondatbeli értékkel (%s)", mondatbeli)
            return mondatbeli
        return mezo_ertek

    # VISSZAUTALÁS az előző fordulóra: „és csütörtökön UGYANEZ?", „ugyanaz
    # a méret", „ugyanoda". Zárt, szűk lista — a névmási visszautalás
    # nyelvtanilag zárt osztály, nem bővülő szókincs.
    _VISSZAUTALAS_MINTA = re.compile(
        r"\bugyan(ez|az|azt|ezt|olyan|abban|oda|onnan|akkor)\b|\b(az|ugyanaz) a (méret|fajta)\b"
    )

    @classmethod
    def _visszautalas_e(cls, mondat: str) -> bool:
        """Visszautal-e a mondat az ELŐZŐ fordulóra?

        Ez az egyetlen hely, ahol a megőrzött kemény rész akkor is
        kitölt, ha a modell LÁTTA a beszélgetést és mégis üresen hagyta
        (ADR-019: „a None erősebb"). A kivétel indoka nyelvi, nem
        kényelmi: a „ugyanez" névmás KIMONDOTTAN az előző tartalomra
        mutat — a vásárló nem elhagyta az adatot, hanem hivatkozott rá.

        Mért bukás, amit megszüntet (2026-09-05, `elengedes-05`): a
        „Nagy petárdát szeretnék kedden." / „és csütörtökön ugyanez?"
        menetben a bolt átjött, a MÉRET nem — a keresés csendben
        kitágult minden petárdára."""
        return bool(cls._VISSZAUTALAS_MINTA.search(normalizal(mondat).lower()))

    @staticmethod
    def _visszautalasos_tartalek(kontextus: ErtelmezesKontextus, mezo: str, mondat: str):
        """A megőrzött érték, HA a mondat visszautal az előző fordulóra.
        Egyébként `None` — az ADR-019 szabálya változatlan."""
        if not ForditottKaszkadErtelmezo._visszautalas_e(mondat):
            return None
        ertek = kontextus.megorzott_parameterek.get(mezo)
        if ertek:
            _LOG.info("kaszkád: visszautalás — a megőrzött %s átjön (%s)", mezo, ertek)
        return ertek

    # -- dátum-kapu ----------------------------------------------------

    @staticmethod
    def _mondatbeli_kifejezes(kifejezes: str | None, mondat: str) -> str:
        """A modell dátum-idézete, HA az tényleg az AKTUÁLIS mondatból
        való — különben üres sztring.

        **Miért kell.** A modell mostantól a teljes beszélgetést látja
        (ADR-019), és hajlamos egy KORÁBBI fordulóból idézni a napot:
        a "Szeretnék petárdázni kedden délelőtt." / "bármikor a jövő
        héten" menetben a keddet is, a jövő hetet is beírta, és a
        determinisztikus összevonás egy 12 napos ablakot csinált belőle.
        A szándék-rétegzés doktrínája szerint viszont a PUHA rész (dátum,
        napszak) minden fordulóban frissen dől el
        (`orchestrator.kovetkezo_kontextus`) — az utolsó mondat felülírja
        a korábbit, nem kiegészíti.

        Ez a kapu ezt **kikényszeríti**, nem csak a promptban kéri: az
        idézetet elfogadjuk, ha minden érdemi szava előfordul az
        aktuális mondatban. A magyar toldalékolás a kedvünkre dolgozik:
        az idézet rövidebb alakja ("péntek") részszövege az
        inflektáltnak ("pénteken"). Ha az idézet NEM innen való, eldobjuk
        — a dátum ilyenkor vagy hiányzik, vagy a mondat egészéből oldódik
        fel, ami ugyanennek az elvnek felel meg."""
        if not kifejezes:
            return ""
        tiszta = kifejezes.strip()
        also = normalizal(mondat).lower()
        szavak = [sz for sz in normalizal(tiszta).lower().split() if len(sz) >= 3]
        if not szavak:
            return ""
        if all(sz in also for sz in szavak):
            return tiszta
        _LOG.info("kaszkád: a modell dátum-idézete nem az aktuális mondatból való (%r)", tiszta)
        return ""

    @staticmethod
    def _mondatbeli_napszak(napszak: str | None, mondat: str) -> str | None:
        """A modell napszaka, HA az aktuális mondat egyáltalán beszél
        napszakról — különben `None`.

        A napszak is a szándék PUHA része, ugyanaz a szabály vonatkozik
        rá, mint a dátumra (`_mondatbeli_kifejezes`): nem szivároghat át
        egy korábbi fordulóból. A mérés ezt meg is fogta: a *„kedden
        délelőtt" → „bármikor a jövő héten"* menetben a dátum már
        helyesen a jövő hétre ugrott, de a `delelott` továbbjött, és
        némán leszűkítette a kitágított ablakot.

        **A DÖNTÉST nem vesszük el a modelltől**, csak a forrást
        kötjük meg: ha a mondat beszél napszakról, a modell választása
        érvényes (ez kell az „azért délután, mert délelőtt dolgozom"
        szerkezethez, ahol KÉT napszak-szó van, és a mondattan dönt). Ha
        a mondat egyáltalán nem beszél napszakról, nincs mit
        választania."""
        if not napszak:
            return None
        if napszak == MINDEGY:
            # A NAPSZAKON A HÁROM ÁLLAPOT KETTŐRE ESIK ÖSSZE, ezért itt
            # a MINDEGY „barmikor"-rá normalizálódik.
            #
            # A szentinel akkor ér valamit, ha egy KÉRDÉST némít el: a
            # boltra és a szolgáltatásra rákérdeznénk, a napszakra soha
            # (nincs a `_KRITIKUS_MEZOK` között, nem blokkoló mező). Itt
            # tehát a „mindegy" és az alapértelmezett „bármikor"
            # viselkedésben azonos — két név ugyanarra a dologra, épp az
            # a hibaosztály, amit a szentinel bevezetésekor
            # felszámoltunk (docs/ALTALANOSITAS.md 1.6).
            #
            # **Mérés, ami eldöntötte** (2026-08-30, végigjátszás,
            # `qwen3.5:9b`): 54 fordulóból 6-ban jött `napszak: MINDEGY`
            # — és MINDEGYIK olyan mondatra, amiben egy szó sem esett
            # időpontról („Petárdázni szeretnék.", „Szundihoz mennék.").
            # A modell tehát „nincs megadva" értelemben használta,
            # nem „elengedtem" értelemben. Ha ezt átengednénk, a
            # naplóban egy ki nem mondott vásárlói döntés állna.
            return "barmikor"
        if rule_based.napszak_feloldas(mondat) is None:
            _LOG.info("kaszkád: a modell napszaka nem az aktuális mondatból való (%r)", napszak)
            return None
        return napszak

    @staticmethod
    def _datum_ablak(
        nyers: dict, mondat: str, most: str, nyom: dict | None = None
    ) -> tuple[str | None, str | None, str | None]:
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
        vásárló nem veszíti el a második lehetőségét.

        **Ha a modell egyáltalán nem idézett dátumot**, a MONDAT EGÉSZÉT
        odaadjuk ugyanannak a determinisztikus parsernek. Ez nem a modell
        felülbírálása (akkor lép be, ha a modell semmit nem mondott),
        hanem az az elv, hogy amit determinisztikusan LÁTUNK a
        mondatban, azt ne veszítsük el csak azért, mert a modell
        kihagyta — különben egy visszakérdezés után a vásárlónak újra el
        kellene mondania a már megadott napot."""
        kifejezes = ForditottKaszkadErtelmezo._mondatbeli_kifejezes(
            nyers.get("datum_kifejezes"), mondat
        )
        parser_tol, parser_ig = rule_based.datum_ablak_feloldas(kifejezes, most)
        napszak = rule_based.napszak_feloldas(kifejezes) if kifejezes else None

        masodik = ForditottKaszkadErtelmezo._mondatbeli_kifejezes(
            nyers.get("datum_kifejezes_2"), mondat
        )
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
            ForditottKaszkadErtelmezo._datum_nyom(
                nyom,
                modell_kifejezes=kifejezes or None,
                modell_datum_tol=modell_tol,
                parser_tol=parser_tol,
                parser_ig=parser_ig,
                nyertes="parser (a modell idézetéből)",
            )
            return parser_tol, parser_ig, napszak

        if nyers.get("datum_tol"):
            _LOG.info("kaszkád: a modell ISO-dátuma feloldható kifejezés nélkül maradt, eldobva")

        # A modell nem idézett feloldható kifejezést — a MONDAT EGÉSZE
        # megy ugyanannak a parsernek (l. docstring).
        mondat_tol, mondat_ig = rule_based.datum_ablak_feloldas(mondat, most)
        napszak = napszak or rule_based.napszak_feloldas(mondat)
        if mondat_tol:
            _LOG.info("kaszkád: a dátum a mondat egészéből oldódott fel (%s)", mondat_tol)
        ForditottKaszkadErtelmezo._datum_nyom(
            nyom,
            modell_kifejezes=kifejezes or None,
            modell_datum_tol=nyers.get("datum_tol"),
            parser_tol=mondat_tol,
            parser_ig=mondat_ig,
            nyertes=("parser (a mondat egészéből)" if mondat_tol else "nincs feloldható dátum"),
        )
        return mondat_tol, mondat_ig, napszak

    @staticmethod
    def _datum_nyom(nyom: dict | None, **mezok) -> None:
        """A dátumfeloldás nyomkövetése: mit adott a MODELL, mit adott a
        PARSER, és melyik nyert.

        Ez a rendszer legkevésbé átlátható lépése — a modell szövegesen
        idéz, a parser oldja fel, és eltérésnél a parser nyer. A
        beszélgetés-elemzőben (`tools/beszelgetes_riport.py`) ez a
        három adat egymás mellett áll, mert a dátumhiba a leggyakoribb
        panasz, és a naplóból eddig csak a VÉGEREDMÉNY látszott."""
        if nyom is not None:
            nyom.update(mezok)

    def _kereses_kapu(
        self,
        parameterek: dict,
        nyers: dict,
        mondat: str,
        most: str,
        kontextus: ErtelmezesKontextus,
        bizonyossag: dict,
    ) -> dict:
        bolt_id = (
            self._mindegy_visszavonva(parameterek.get("bolt_id"), rule_based.bolt_feloldas(mondat))
            or self._tartalek(kontextus, "bolt_id")
            or self._visszautalasos_tartalek(kontextus, "bolt_id", mondat)
        )
        if bolt_id is None:
            return self._visszakerdez(
                "bolt_id",
                "zart",
                bizonyossag,
                megorzott=self._megorzendo(parameterek, nyers, mondat, most, kontextus),
            )

        datum_tol, datum_ig, kifejezes_napszak = self._datum_ablak(
            nyers, mondat, most, self.utolso_nyomkovetes.get("datum")
        )
        napszak = self._mondatbeli_napszak(parameterek.get("napszak"), mondat) or kifejezes_napszak

        # MEZŐNKÉNTI FORRÁS — a nyomkövetéshez (`utolso_nyomkovetes`).
        # A beszélgetés-elemzőben minden paraméter mellett ott áll, hogy
        # HONNAN jött: a modelltől, a parsertől, a zárt halmazból, a
        # megőrzött kontextusból vagy a dokumentált tartalékból. Ez az a
        # kérdés, amire a napló eddig nem felelt.
        forras = self.utolso_nyomkovetes.setdefault("mezo_forras", {})
        forras["bolt_id"] = "modell" if parameterek.get("bolt_id") else "megőrzött kontextus"

        vegleges: dict = {"bolt_id": bolt_id}
        if datum_tol:
            vegleges["datum_tol"] = datum_tol
            vegleges["datum_ig"] = datum_ig
            forras["datum"] = "dátumparser"
        elif self._tartalek(kontextus, "datum_tol"):
            vegleges["datum_tol"] = self._tartalek(kontextus, "datum_tol")
            vegleges["datum_ig"] = self._tartalek(kontextus, "datum_ig")
            forras["datum"] = "megőrzött kontextus"
        else:
            vegleges["datum_tol"], vegleges["datum_ig"] = rule_based.altalanos_ablak(most)
            forras["datum"] = "TARTALÉK ablak (egy hét, a mondatban nincs dátum)"

        vegleges["napszak"] = napszak or "barmikor"
        forras["napszak"] = (
            "modell (a mondatból igazolva)"
            if napszak and parameterek.get("napszak")
            else ("dátumkifejezés" if napszak else "alapértelmezés (bármikor)")
        )
        if napszak:
            vegleges["datum_ig"] = rule_based.napszak_ablak_vagas(
                vegleges["datum_tol"], vegleges["datum_ig"], napszak
            )

        # A szolgáltatás zárt halmaz, és a mondatból determinisztikusan
        # kinyerhető ("nagy petárda") — ha a modell kihagyta, NEM a bolt
        # alapértelmezett szolgáltatására esünk vissza azonnal, előbb
        # megnézzük, mit mond a mondat. A sorrend fontos: a modell
        # válasza nyer, a szabály csak pótol.
        # A MINDEGY MEGELŐZI a pótlást: ha a vásárló elengedte a
        # szolgáltatást, nem tölthetjük ki helyette a bolt
        # alapértelmezésével — az épp az ellenkezője annak, amit kért.
        mondatbeli_szolgaltatas = rule_based.szolgaltatas_feloldas(mondat, bolt_id)
        modell_szolgaltatas = self._mindegy_visszavonva(
            parameterek.get("szolgaltatas_id"), mondatbeli_szolgaltatas
        )
        if modell_szolgaltatas == MINDEGY:
            szolgaltatas = MINDEGY
        else:
            szolgaltatas = (
                modell_szolgaltatas
                or mondatbeli_szolgaltatas
                # VISSZAUTALÁS („és csütörtökön ugyanez?") — a megőrzött
                # szolgáltatás átjön, mert a mondat KIMONDOTTAN rá mutat.
                or self._visszautalasos_tartalek(kontextus, "szolgaltatas_id", mondat)
                or BOLT_EGYERTELMU_SZOLGALTATAS.get(bolt_id)
            )
        if szolgaltatas:
            vegleges["szolgaltatas_id"] = szolgaltatas
            forras["szolgaltatas_id"] = (
                "modell"
                if parameterek.get("szolgaltatas_id")
                and szolgaltatas == parameterek.get("szolgaltatas_id")
                else (
                    "szabály-alapú kinyerés"
                    if mondatbeli_szolgaltatas == szolgaltatas
                    else (
                        "visszautalás (megőrzött kontextus)"
                        if szolgaltatas
                        == self._visszautalasos_tartalek(kontextus, "szolgaltatas_id", mondat)
                        else "a bolt egyértelmű szolgáltatása"
                    )
                )
            )
        # A preferált óra ("kb 10 körül") ugyanúgy determinisztikusan
        # kinyerhető, mint a szolgáltatás — a modell kihagyása nem
        # jelenti, hogy nincs is a mondatban.
        preferalt_ora = parameterek.get("preferalt_ora")
        if preferalt_ora is None:
            preferalt_ora = rule_based.preferalt_ora_feloldas(mondat)
        if preferalt_ora is not None:
            vegleges["preferalt_ora"] = preferalt_ora
            forras["preferalt_ora"] = (
                "modell"
                if parameterek.get("preferalt_ora") is not None
                else "szabály-alapú kinyerés"
            )

        return {
            "eszkoz": "szabad_idopontok",
            "parameterek": vegleges,
            "bizonyossag": bizonyossag,
        }

    def _legkozelebbi_kapu(
        self,
        parameterek: dict,
        mondat: str,
        kontextus: ErtelmezesKontextus,
        bizonyossag: dict,
    ) -> dict:
        """„Mikor tudok legkorábban menni?" — ELSŐRENDŰ kérés, nem
        keresés dátumablak nélkül.

        Enélkül a modell `legkozelebbi_idopont` válasza némán
        `szabad_idopontok`-ká alakult (a kapuk végén álló
        `_kereses_kapu` mindent azzá tesz), az pedig a hiányzó dátum
        helyére a tartalék egyhetes ablakot tette — tehát a „bármikor
        jó, ami legközelebb van" kérésre egy önkényes hét jött ki, és
        ha abban a hétben nem volt hely, üres válasz. Pedig épp az
        ellenkezőjét kérték: NE legyen ablak.

        Ezért itt **dátumot nem oldunk fel és nem is kérdezünk vissza**
        (a séma nem is fogad ablakot, `assistant/tools/semak.py`); a
        bolt marad az egyetlen blokkoló mező, ahogy a keresésnél is."""
        bolt_id = parameterek.get("bolt_id") or self._tartalek(kontextus, "bolt_id")
        if bolt_id is None:
            return self._visszakerdez("bolt_id", "zart", bizonyossag)

        forras = self.utolso_nyomkovetes.setdefault("mezo_forras", {})
        forras["bolt_id"] = "modell" if parameterek.get("bolt_id") else "megőrzött kontextus"
        forras["datum"] = "nincs ablak — a legkorábbi szabad időpont a kérdés"

        vegleges: dict = {"bolt_id": bolt_id}

        napszak = self._mondatbeli_napszak(parameterek.get("napszak"), mondat)
        if napszak:
            vegleges["napszak"] = napszak
            forras["napszak"] = "modell (a mondatból igazolva)"

        if parameterek.get("szolgaltatas_id") == MINDEGY:
            szolgaltatas = MINDEGY
        else:
            szolgaltatas = (
                parameterek.get("szolgaltatas_id")
                or rule_based.szolgaltatas_feloldas(mondat, bolt_id)
                or BOLT_EGYERTELMU_SZOLGALTATAS.get(bolt_id)
            )
        if szolgaltatas:
            vegleges["szolgaltatas_id"] = szolgaltatas
            forras["szolgaltatas_id"] = (
                "modell"
                if parameterek.get("szolgaltatas_id")
                else "a bolt egyértelmű szolgáltatása"
            )

        return {
            "eszkoz": "legkozelebbi_idopont",
            "parameterek": vegleges,
            "bizonyossag": bizonyossag,
        }

    def _bolt_info_kapu(
        self, parameterek: dict, nyers: dict, mondat: str, most: str, bizonyossag: dict
    ) -> dict:
        bolt_id = parameterek.get("bolt_id")
        if bolt_id is None:
            return self._visszakerdez("bolt_id", "zart", bizonyossag)
        # A `mit` az EGYETLEN mező, ahol a szabály felülírja a modellt:
        # a kérdéstípus zárt halmaz, és pozitív, nagy pontosságú
        # mintaillesztéssel felismerhető ("hogy néz ki", "meddig van
        # nyitva"). Egy rossz `mit` nem hiányzó adat, hanem MÁS KÉRDÉSRE
        # adott válasz szerkesztett bolti adattal — a végigjátszás
        # megfogta, hogy a "Hogy néz ki a Törpilla bolt?" kérdésre a
        # címet olvasta fel. Ha a szabály nem ismeri fel a kérdést
        # (`None`), akkor a modellé a döntés, ahogy máshol is.
        mit = rule_based.bolt_info_mezo_feloldas(mondat) or parameterek.get("mit") or "nyitvatartas"
        vegleges = {"bolt_id": bolt_id, "mit": mit}
        datum_tol, _, _ = self._datum_ablak(nyers, mondat, most)
        if datum_tol:
            # `bolt_info.datum` csak a naptári nap, idő nélkül.
            vegleges["datum"] = datum_tol[:10]
        return {"eszkoz": "bolt_info", "parameterek": vegleges, "bizonyossag": bizonyossag}

    # -- segédek --------------------------------------------------------

    @staticmethod
    def _megorzendo(
        parameterek: dict, nyers: dict, mondat: str, most: str, kontextus: ErtelmezesKontextus
    ) -> dict:
        """Amit egy visszakérdezésbe át kell vinni, hogy ne kelljen újra
        megkérdezni (golden set, toredekes-03)."""
        megorzott = dict(kontextus.megorzott_parameterek)
        datum_tol, datum_ig, kifejezes_napszak = ForditottKaszkadErtelmezo._datum_ablak(
            nyers, mondat, most
        )
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

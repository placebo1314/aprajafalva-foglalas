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

from assistant import kapuor
from assistant.interpreter import ErtelmezesKontextus, Ertelmezo, rule_based
from assistant.interpreter.llm_based import LLMErtelmezo, Mintavetel
from assistant.interpreter.normalizalo import normalizal
from assistant.interpreter.rule_based import SzabalyAlapuErtelmezo
from assistant.tools import katalogus
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

# Amire ÉRDEMES visszakérdezni: enélkül a művelet nem indítható el. A
# szolgáltatás (méret) szándékosan NEM ilyen — a keresés elindulhat a
# bolt szintjén, a pontosítás jöhet az ajánlat után (golden set,
# egyszerusitett-04 megjegyzése), és a determinisztikus réteg sem kérdez
# rá soha.
_BLOKKOLO_MEZOK = frozenset({"bolt_id", "foglalasi_kod"})


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
        # "kapuor" | "llm" | "szabaly" — melyik réteg adta az utolsó
        # választ. A "kapuor" azt jelenti, hogy a modell meg sem szólalt.
        self.utolso_reteg: str | None = None
        # Az utolsó kapuőr-döntés — megfigyelhetőséghez (napló,
        # `tools/naplo_elemzo.py`). Nem a protokoll része.
        self.utolso_kapuor: kapuor.KapuorDontes | None = None
        # Az utolsó mondat normalizált alakja — megfigyelhetőséghez
        # (`ui/vasarlo.py` próba-naplója: mit LÁTOTT a modell). Nem a
        # protokoll része, a hívók `getattr`-ral olvassák.
        self.utolso_normalizalt: str | None = None

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
        # 0. KAPUŐR — hatókör-döntés a modell ELŐTT (ADR-020, blueprint
        # 10.). Kívül eső kérésnél a modell MEG SEM SZÓLAL: nem hívjuk
        # meg. Ez nem prompt-fegyelem kérdése, hanem architektúráé — és
        # egyben a leggyorsabb ág is (nulla modellhívás).
        kapuor_dontes = kapuor.dontes(mondat)
        if kapuor_dontes.kivul:
            self.utolso_reteg = "kapuor"
            self.utolso_normalizalt = normalizal(mondat)
            self.utolso_kapuor = kapuor_dontes
            return {
                "eszkoz": "nincs",
                "parameterek": {},
                "bizonyossag": {"eszkoz": 1.0},
                "kapuor_ok": kapuor_dontes.ok,
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

        if self.llm is None or self._zart_valasz_e(normalizalt):
            self.utolso_reteg = "szabaly"
            return self.szabaly.ertelmez(mondat, most=most, kontextus=kontextus)

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
                self.utolso_reteg = "szabaly"
                return self.szabaly.ertelmez(mondat, most=most, kontextus=kontextus)

        llm_eredmeny = self.llm.ertelmez(
            normalizalt, most=most, kontextus=kontextus, mintavetel=mintavetel
        )
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
            if jelolt in BOLT_SLUGOK:
                return jelolt
        return None

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
        if rule_based.napszak_feloldas(mondat) is None:
            _LOG.info("kaszkád: a modell napszaka nem az aktuális mondatból való (%r)", napszak)
            return None
        return napszak

    @staticmethod
    def _datum_ablak(
        nyers: dict, mondat: str, most: str
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
            return parser_tol, parser_ig, napszak

        if nyers.get("datum_tol"):
            _LOG.info("kaszkád: a modell ISO-dátuma feloldható kifejezés nélkül maradt, eldobva")

        # A modell nem idézett feloldható kifejezést — a MONDAT EGÉSZE
        # megy ugyanannak a parsernek (l. docstring).
        mondat_tol, mondat_ig = rule_based.datum_ablak_feloldas(mondat, most)
        napszak = napszak or rule_based.napszak_feloldas(mondat)
        if mondat_tol:
            _LOG.info("kaszkád: a dátum a mondat egészéből oldódott fel (%s)", mondat_tol)
        return mondat_tol, mondat_ig, napszak

    def _kereses_kapu(
        self,
        parameterek: dict,
        nyers: dict,
        mondat: str,
        most: str,
        kontextus: ErtelmezesKontextus,
        bizonyossag: dict,
    ) -> dict:
        bolt_id = parameterek.get("bolt_id") or self._tartalek(kontextus, "bolt_id")
        if bolt_id is None:
            return self._visszakerdez(
                "bolt_id",
                "zart",
                bizonyossag,
                megorzott=self._megorzendo(parameterek, nyers, mondat, most, kontextus),
            )

        datum_tol, datum_ig, kifejezes_napszak = self._datum_ablak(nyers, mondat, most)
        napszak = self._mondatbeli_napszak(parameterek.get("napszak"), mondat) or kifejezes_napszak

        vegleges: dict = {"bolt_id": bolt_id}
        if datum_tol:
            vegleges["datum_tol"] = datum_tol
            vegleges["datum_ig"] = datum_ig
        elif self._tartalek(kontextus, "datum_tol"):
            vegleges["datum_tol"] = self._tartalek(kontextus, "datum_tol")
            vegleges["datum_ig"] = self._tartalek(kontextus, "datum_ig")
        else:
            vegleges["datum_tol"], vegleges["datum_ig"] = rule_based.altalanos_ablak(most)

        vegleges["napszak"] = napszak or "barmikor"
        if napszak:
            vegleges["datum_ig"] = rule_based.napszak_ablak_vagas(
                vegleges["datum_tol"], vegleges["datum_ig"], napszak
            )

        # A szolgáltatás zárt halmaz, és a mondatból determinisztikusan
        # kinyerhető ("nagy petárda") — ha a modell kihagyta, NEM a bolt
        # alapértelmezett szolgáltatására esünk vissza azonnal, előbb
        # megnézzük, mit mond a mondat. A sorrend fontos: a modell
        # válasza nyer, a szabály csak pótol.
        szolgaltatas = (
            parameterek.get("szolgaltatas_id")
            or rule_based.szolgaltatas_feloldas(mondat, bolt_id)
            or BOLT_EGYERTELMU_SZOLGALTATAS.get(bolt_id)
        )
        if szolgaltatas:
            vegleges["szolgaltatas_id"] = szolgaltatas
        # A preferált óra ("kb 10 körül") ugyanúgy determinisztikusan
        # kinyerhető, mint a szolgáltatás — a modell kihagyása nem
        # jelenti, hogy nincs is a mondatban.
        preferalt_ora = parameterek.get("preferalt_ora")
        if preferalt_ora is None:
            preferalt_ora = rule_based.preferalt_ora_feloldas(mondat)
        if preferalt_ora is not None:
            vegleges["preferalt_ora"] = preferalt_ora

        return {
            "eszkoz": "szabad_idopontok",
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

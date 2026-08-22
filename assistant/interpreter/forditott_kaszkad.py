"""Fordított kaszkád — a modell értelmez, a determinisztikus réteg a
kapu és a tartalék.

**ÁLLAPOT: EZ AZ ÉLES ÚT** (ADR-018, elfogadva 2026-08-23 — felülírja
az ADR-016 sorrendjét). Ezt építi fel az `assistant/interpreter/
__init__.py::alapertelmezett_ertelmezo()`, ezt használja a
`ui/vasarlo.py`. A determinisztikus-előbb sorrend (`kaszkad.py`) a
repóban maradt: az a visszaút, `--ertelmezo kaszkad`-dal mérhető.

Rövid történet, mert a döntés MEGFORDULT: az ADR-018 első változata
(2026-08-22) ezt a felállást megmérte és elvetette (69,4% vs 86,1%). Az
a mérés egy félkész modult mért — a modell a beszélgetés kontextusát
meg sem kapta, a `--ertelmezo forditott` kapcsoló a futtatóban nem is
volt bekötve. A befejezett modul újramérve (45 eset, qwen3.5:9b) jobb
lett a determinisztikus-előbb sorrendnél, ÉS a leggyengébb rétegen is
jobb. Számok és a visszafordulás feltétele: ADR-018.

```
mondat
  │
  ├─ 1. NORMALIZÁLÓ (determinisztikus szótár, normalizalo.py)
  │      tájszólás/szleng/csapdaszó → köznyelvi alak
  │
  ├─ 2. LLM ÉRTELMEZŐ (llm_based.py), kötött dekódolással
  │      az enumok tartják a zárt halmazokat (bolt, szolgáltatás,
  │      napszak, mit, hianyzo_mezo) — kitalált érték strukturálisan
  │      kizárva; a dátumot a modell SZÖVEGESEN idézi
  │      (`datum_kifejezes`, vagylagosnál `datum_kifejezes_2`); a
  │      beszélgetés KEMÉNY kontextusa (bolt, szolgáltatás) a promptban
  │
  ├─ 3. ELENGEDÉS-KAPU — ha a bolt a kontextusból jön, és a mondat
  │      determinisztikusan nem nevez meg boltot, egy külön, ZÁRT
  │      kérdés dönti el, hogy a mondat elveti-e ("mi esik ki?", csak
  │      mezőnevek); a `kaszkad.kemeny_reszt_vedd` védőhálóval
  │
  ├─ 4. DÁTUM-KAPU (rule_based.datum_ablak_feloldas)
  │      a `datum_kifejezes`-t a hun-date-parser oldja fel, két
  │      kifejezésnél az ablakokat determinisztikusan összevonjuk. Ha a
  │      modell mégis ISO-dátumot adott, azt is ellenőrizzük a
  │      parserrel — ELTÉRÉSNÉL A PARSER NYER.
  │
  ├─ 5. PÓTLÁS-KAPU — amit a modell kihagyott, de determinisztikusan
  │      LÁTSZIK a mondatban (dátum, napszak, szolgáltatás, preferált
  │      óra), azt a szabály-alapú kinyerés pótolja. A modell válasza
  │      MINDIG nyer; a szabály csak hiányt tölt.
  │
  ├─ 6. BIZONYOSSÁG-KAPU — küszöb alatt zárt kérdés. Ez NEM itt van,
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

**Ami MÉG NEM determinisztikus, pedig kellene** (ADR-018, "A következő
lépés"): a **kapuőr**. A "Mennyibe kerül a nagy petárda?" mondatra ma a
modell dönt, és a mérésen 50%-ot ad — a blueprint 10. szakasza szerint a
témán belül tartás kifejezetten NEM múlhat a modell prompt-fegyelmén. A
kapuőr-minták a modell ELÉ emelése külön ADR-t igényel, mert az már
hibrid architektúra, nem "fordított kaszkád".

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
   mérőszám (`python feladat.py golden --ertelmezo forditott`), és ez
   jelenik meg a felület próba-naplójában is (`naplo/probak.jsonl`).
"""

from __future__ import annotations

import logging

from assistant.interpreter import ErtelmezesKontextus, Ertelmezo, rule_based
from assistant.interpreter.kaszkad import kemeny_reszt_vedd
from assistant.interpreter.llm_based import LLMErtelmezo
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

# A szándék KEMÉNY része (ADR-016) — az elengedés-kapu ezt veszi ki a
# kontextusból, ha a mondat elveti a boltot.
_KEMENY_MEZOK = frozenset({"bolt_id", "szolgaltatas_id"})


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

        if self.llm is None or self._zart_valasz_e(normalizalt):
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

        # ELENGEDÉS-KAPU (csak a keresési ágon): a mondat elvetheti a
        # korábbi fordulókból örökölt boltot ("és bármelyik másik
        # boltban?"). Ezt a modell FŐ hívása gyakran elmulasztja, mert a
        # kontextus-sortól inkább megtartásra hajlik — ezért egy külön,
        # SZIGORÚAN ZÁRT kérdést teszünk fel neki (`valtozas_elemzes`:
        # csak mezőneveket ad vissza, értéket soha), ugyanazzal a
        # védőhálóval, amit az ADR-016 kaszkád használ.
        if self._elenged_e_boltot(mondat, most, kontextus):
            _LOG.info("kaszkád: a mondat elengedi a kontextusból örökölt boltot")
            szukitett = ErtelmezesKontextus(
                megorzott_parameterek={
                    k: v
                    for k, v in kontextus.megorzott_parameterek.items()
                    if k not in _KEMENY_MEZOK
                }
            )
            parameterek.pop("bolt_id", None)
            parameterek.pop("szolgaltatas_id", None)
            return self._kereses_kapu(parameterek, nyers, mondat, most, szukitett, bizonyossag)

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
            if hianyzo == "bolt_id" and self._ismert_bolt(parameterek, kontextus):
                # KONTEXTUS-KAPU: a modell minden fordulót nulláról
                # értelmez, ezért egy alkudozó follow-up mondatra ("talán
                # jövő héten") a boltra kérdezne rá — arra, amit a
                # beszélgetés két mondattal korábban már tisztázott, és
                # ami itt, a kontextusban ott is van. Amit
                # determinisztikusan tudunk, arra nem kérdezünk vissza (a
                # vásárló 6. igénye: javítás, ne újrakezdés). Az
                # elengedés esetét a fenti kapu már kiszűrte.
                _LOG.info("kaszkád: a modell a boltra kérdezne, de a kontextus ismeri — keresés")
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
    def _ismert_bolt(parameterek: dict, kontextus: ErtelmezesKontextus) -> str | None:
        """Ismert-e a bolt a modell válaszából VAGY a megőrzött
        kontextusból — a zárt halmaz ellen ellenőrizve."""
        for jelolt in (
            parameterek.get("bolt_id"),
            kontextus.megorzott_parameterek.get("bolt_id"),
        ):
            if jelolt in BOLT_SLUGOK:
                return jelolt
        return None

    def _elenged_e_boltot(self, mondat: str, most: str, kontextus: ErtelmezesKontextus) -> bool:
        """Elveti-e a mondat a KONTEXTUSBÓL örökölt boltot?

        Csak akkor kérdezünk rá egyáltalán, ha érdemes: van örökölt bolt,
        ÉS a mondat determinisztikusan NEM nevez meg boltot (ha megnevez,
        nincs mit elengedni — az felülír). Ez a szűrés tartja a plusz
        modellhívást a valóban kétes fordulókra.

        A kérdés a modellnek szigorúan zárt: mezőneveket ad vissza, soha
        nem értéket (`LLMErtelmezo.valtozas_elemzes`) — és a válaszát a
        `kaszkad.kemeny_reszt_vedd` védőháló szűri, ami a kemény részt
        megvédi, ha a mondat POZITÍV időbeli jelzést hordoz (akkor a
        mondat időről szól, nem a boltról)."""
        if kontextus.megorzott_parameterek.get("bolt_id") is None:
            return False
        if rule_based.bolt_feloldas(mondat) is not None:
            return False
        valtozas = self.llm.valtozas_elemzes(mondat, kontextus.megorzott_parameterek)
        if not valtozas or not valtozas.get("elenged"):
            return False
        return "bolt_id" in kemeny_reszt_vedd(mondat, most, valtozas["elenged"])

    # -- dátum-kapu ----------------------------------------------------

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
        bolt_id = parameterek.get("bolt_id") or kontextus.megorzott_parameterek.get("bolt_id")
        if bolt_id is None:
            return self._visszakerdez(
                "bolt_id",
                "zart",
                bizonyossag,
                megorzott=self._megorzendo(parameterek, nyers, mondat, most, kontextus),
            )

        datum_tol, datum_ig, kifejezes_napszak = self._datum_ablak(nyers, mondat, most)
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

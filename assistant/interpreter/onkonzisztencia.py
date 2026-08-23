"""ÖNKONZISZTENCIA — az értelmező háromszor fut, és a JSON
eszközhívások PONTOS EGYENLŐSÉGÉT vizsgáljuk (blueprint 10. szakasz:
"Önkonzisztencia: az értelmező 3-5×, a JSON eszközhívások pontos
egyenlőségvizsgálatával"; ADR-021).

## Miért pontos egyenlőség, és miért nem szöveg

A blueprint kifejezetten tiltja a "szabad szöveg súlyozott keverését".
Itt sincs keverés: a három futás kimenete egy-egy STRUKTURÁLT
eszközhívás, és a szavazás azon dől el, hogy a `{eszkoz, parameterek}`
pár **bájtra azonos-e** (kulcsok szerint rendezett JSON). Nincs
hasonlóság, nincs küszöb, nincs részleges egyezés — vagy ugyanaz, vagy
nem. Ez azért lehetséges, mert a kimenet zárt halmazokból épül
(`assistant/tools/semak.py`), tehát az azonosság értelmes fogalom rajta.

## A három kimenetel

| Egyetértés | Mi történik | Miért |
|---|---|---|
| **3 / 3** | a válasz megy, VÁLTOZATLAN bizonyossággal | a modell stabil, nincs mit jelezni |
| **2 / 3** | a többségi válasz megy, CSÖKKENTETT bizonyossággal | van válasz, de ingadozott |
| **1+1+1** | ZÁRT KÉRDÉS | három futás, három vélemény — ez nem értés, hanem találgatás |

A csökkentett bizonyosság nem kozmetika: az orchestrator
bizonyosság-kapuja (`BizonyossagKuszobok`: eszköz 0,7, kritikus mező
0,6) ettől ténylegesen visszakérdezésre válthat. **A döntés tehát ott
marad, ahol lennie kell** (blueprint 10.: "a visszakérdezésről az
orchestrator dönt, nem az LLM") — ez a modul csak egy jelet állít elő.

## Miért kell MINTAVÉTEL hozzá

Az éles út `temperature: 0`-val fut. Három ilyen futás (majdnem)
azonos, tehát a szavazás mindig 3/3-at adna, és semmit nem mérnénk. Az
önkonzisztencia csak akkor mond valamit, ha a futások MINTAVÉTELESEK:
az első marad `temperature: 0` (ez a kanonikus válasz, ezt adná a
rendszer enélkül is), a másik kettő mintavételes, rögzített maggal
(`Mintavetel`). A rögzített mag miatt a mérés megismételhető.

## Kikapcsolható — és ez nem mellékes

`APRAJAFALVA_ONKONZISZTENCIA=0` kikapcsolja. Az alapértelmezést a
MÉRÉS dönti el, nem az elmélet (blueprint 12., "A 15 másodperces
keret": "a hívásszám növelése csak méréssel indokolható"). A mérés
számai és a belőlük következő alapértelmezés az **ADR-021**-ben
vannak.

## Ami NEM változik

- A determinisztikus kapuk (dátum, zárt halmazok, foglalási kód) a
  burkolt értelmezőben futnak, futásonként — a szavazás tehát a KÉSZ,
  kapuzott eszközhívásokon dől el, nem a modell nyers kimenetén. Ez
  szándékos: a végleges kimenet számít, nem a köztes állapot.
- A kapuőr (`assistant/kapuor/`) a burkolt értelmezőn belül van, és
  determinisztikus — ha kívül esőnek ítéli a kérést, mindhárom futás
  azonnal, modellhívás nélkül tér vissza ugyanazzal. Az önkonzisztencia
  tehát a hatókörön kívüli kérdéseken INGYEN van.
"""

from __future__ import annotations

import json
import logging
import os
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

from assistant.interpreter import ErtelmezesKontextus, Ertelmezo
from assistant.interpreter.llm_based import Mintavetel

_LOG = logging.getLogger(__name__)

# Az alapértelmezett három futás. Az ELSŐ a kanonikus (`temperature: 0`)
# — pontosan az, amit a rendszer önkonzisztencia nélkül adna —, a másik
# kettő mintavételes, rögzített maggal a megismételhetőségért.
#
# A 0,7 a szokásos mintavételi hőmérséklet: elég magas, hogy a modell
# tényleges bizonytalansága megmutatkozzon, elég alacsony, hogy ne
# generáljon zajt ott, ahol a modell biztos.
ALAP_FUTASOK: tuple[Mintavetel | None, ...] = (
    None,
    Mintavetel(temperature=0.7, seed=1),
    Mintavetel(temperature=0.7, seed=2),
)

# A 2/3 egyetértés esetén alkalmazott bizonyosság-szorzó.
#
# Miért 0,8 és nem kevesebb: egy tipikus, magabiztos modellválasz
# bizonyossága 0,95-0,99 (`llm_based.bizonyossag_szamol`). 0,8-cal
# szorozva ez 0,76-0,79 — az eszköz-küszöb (0,7) FÖLÖTT marad, tehát a
# 2/3 egyetértés önmagában nem kényszerít visszakérdezést. Egy már
# amúgy is bizonytalan mező (0,74 vagy alatta) viszont a kritikus mező
# küszöbe (0,6) ALÁ esik. **A jel tehát a HATÁRESETEKET billenti át,
# nem mindent** — ez a szándék: a 2/3 nem hiba, csak gyengébb
# bizonyíték. A pontos fordulópont 0,75 (0,75 × 0,8 = 0,60, a küszöb
# pedig szigorú kisebb), tesztben rögzítve.
BIZONYOSSAG_SZORZO_KETTO_HARMADNAL = 0.8

_KORNYEZETI_KAPCSOLO = "APRAJAFALVA_ONKONZISZTENCIA"


def bekapcsolva(alapertelmezes: bool) -> bool:
    """Az `APRAJAFALVA_ONKONZISZTENCIA` környezeti változó olvasása.
    `"0"`/`"false"`/`"nem"` kikapcsol; bármi más bekapcsol; hiányzó
    változó esetén az `alapertelmezes` dönt (amit a hívó a mérés
    alapján állít be — l. ADR-021)."""
    ertek = os.environ.get(_KORNYEZETI_KAPCSOLO)
    if ertek is None:
        return alapertelmezes
    return ertek.strip().lower() not in {"0", "false", "nem", "ki", ""}


def eszkozhivas_kulcsa(ertelmezes: dict | None) -> str:
    """A `{eszkoz, parameterek}` pár KANONIKUS szöveges alakja — ezen
    dől el a PONTOS EGYENLŐSÉG.

    A `bizonyossag` szándékosan kimarad: az futásonként ingadozik (a
    logprobok mintavételnél másak), és nem az eszközhívás része. A
    szavazás arról szól, hogy a rendszer UGYANAZT CSINÁLNÁ-e, nem
    arról, hogy ugyanannyira volt-e biztos benne.

    A `kapuor_ok` szintén kimarad — az determinisztikus, tehát nem
    tud eltérni."""
    if not isinstance(ertelmezes, dict):
        return "<nincs>"
    return json.dumps(
        {"eszkoz": ertelmezes.get("eszkoz"), "parameterek": ertelmezes.get("parameterek") or {}},
        ensure_ascii=False,
        sort_keys=True,
    )


class OnkonzisztensErtelmezo:
    """Egy `Ertelmezo`-t burkol, N-szer futtatja, és szavaztat — l.
    modul docstring.

    **Ha a burkolt értelmező nem támogat mintavételt** (nincs
    `TAMOGAT_MINTAVETELT = True`, pl. a determinisztikus réteg), a
    burkoló EGYSZER futtatja, és a viselkedés bitre azonos a
    burkolatlanéval. Ez nem hibakezelés, hanem a helyes válasz: három
    azonos futásból nem lesz információ, csak késleltetés."""

    def __init__(
        self,
        ertelmezo: Ertelmezo,
        futasok: tuple[Mintavetel | None, ...] = ALAP_FUTASOK,
        parhuzamos: bool = True,
    ):
        self.ertelmezo = ertelmezo
        self.futasok = futasok
        self.parhuzamos = parhuzamos
        # Megfigyelhetőség (napló, `tools/naplo_elemzo.py`): hány futás
        # értett egyet, és hány futás volt összesen.
        self.utolso_egyetertes: int | None = None
        self.utolso_futasszam: int = 0

    # A burkoló maga nem kér mintavételt kívülről — ő ADJA.
    TAMOGAT_MINTAVETELT = False

    @property
    def utolso_reteg(self) -> str | None:
        """A burkolt értelmező réteg-jelzésének átjárója — a hívók
        (`ui/vasarlo.py`, golden futtató) ezt olvassák, és nem kell
        tudniuk, hogy burkolat van közben."""
        return getattr(self.ertelmezo, "utolso_reteg", None)

    @property
    def utolso_normalizalt(self) -> str | None:
        return getattr(self.ertelmezo, "utolso_normalizalt", None)

    def ertelmez(self, mondat: str, *, most: str, kontextus: ErtelmezesKontextus) -> dict:
        if not getattr(self.ertelmezo, "TAMOGAT_MINTAVETELT", False):
            self.utolso_egyetertes = None
            self.utolso_futasszam = 1
            return self.ertelmezo.ertelmez(mondat, most=most, kontextus=kontextus)

        eredmenyek = self._futtat(mondat, most, kontextus)
        self.utolso_futasszam = len(eredmenyek)

        kulcsok = [eszkozhivas_kulcsa(e) for e in eredmenyek]
        szamlalo = Counter(kulcsok)
        nyertes_kulcs, egyetertes = szamlalo.most_common(1)[0]
        self.utolso_egyetertes = egyetertes

        if egyetertes == len(eredmenyek):
            return eredmenyek[0]

        if egyetertes >= 2:
            nyertes = eredmenyek[kulcsok.index(nyertes_kulcs)]
            _LOG.info(
                "önkonzisztencia: %d/%d egyetértés — csökkentett bizonyosság",
                egyetertes,
                len(eredmenyek),
            )
            return {**nyertes, "bizonyossag": self._csokkentett(nyertes.get("bizonyossag"))}

        # MIND MÁS: három futás, három vélemény. Ez nem értés, hanem
        # találgatás — a helyes válasz a zárt kérdés, nem a
        # "válasszuk az elsőt".
        _LOG.info("önkonzisztencia: nincs többség (%d futás) — zárt kérdés", len(eredmenyek))
        return self._zart_kerdes(eredmenyek)

    # -- belső ---------------------------------------------------------

    def _futtat(self, mondat: str, most: str, kontextus: ErtelmezesKontextus) -> list[dict]:
        """A futások lebonyolítása. Párhuzamosan, ha lehet: a három
        hívás egymástól független, és a válaszidő a keret (blueprint
        12.) szempontjából a KRITIKUS erőforrás.

        A párhuzamosság tényleges haszna a kiszolgálótól függ (az
        Ollama alapbeállításban egy modellre egyszerre egy kérést
        dolgoz fel) — ezért méréssel dőlt el, hogy megéri-e, l.
        ADR-021."""

        def egy(mintavetel: Mintavetel | None) -> dict:
            return self.ertelmezo.ertelmez(
                mondat, most=most, kontextus=kontextus, mintavetel=mintavetel
            )

        if not self.parhuzamos:
            return [egy(m) for m in self.futasok]
        with ThreadPoolExecutor(max_workers=len(self.futasok)) as pool:
            return list(pool.map(egy, self.futasok))

    @staticmethod
    def _csokkentett(bizonyossag: dict | None) -> dict:
        """A bizonyosság-mezők szorzása. A `None` értékek `None`-ok
        maradnak: a "nem tudok nyilatkozni" nem szorozható, és a
        0,8-szorosa is "nem tudok nyilatkozni" lenne
        (`assistant/interpreter/__init__.py::Ertelmezo`)."""
        if not bizonyossag:
            return {}
        return {
            kulcs: (
                round(ertek * BIZONYOSSAG_SZORZO_KETTO_HARMADNAL, 4)
                if isinstance(ertek, int | float)
                else ertek
            )
            for kulcs, ertek in bizonyossag.items()
        }

    @staticmethod
    def _zart_kerdes(eredmenyek: list[dict]) -> dict:
        """A "mind más" eset válasza: zárt kérdés a SZÁNDÉKRA.

        Miért az `eszkoz` a hiányzó mező: a futások nem egy paraméterben
        tértek el, hanem abban, hogy MIT AKARUNK csinálni (különben
        ugyanaz az eszköz jött volna ki mindháromszor, és a
        `parameterek` eltérése is ide vezetne — de a leggyakoribb és
        legfontosabb kérdés akkor is a szándék). Az orchestrator ezt
        ugyanúgy kezeli, mint a saját `_bizonytalansag_kezel` ágát.

        A `valaszthato_ertekek` a három futás által javasolt, EGYEDI
        eszköznevekkel telik meg — a vásárlónak felkínálható, valódi
        lehetőségek, nem kitalált opciók."""
        eszkozok = []
        for eredmeny in eredmenyek:
            eszkoz = (eredmeny or {}).get("eszkoz")
            if eszkoz and eszkoz not in eszkozok and eszkoz not in ("nincs", "visszakerdez"):
                eszkozok.append(eszkoz)
        return {
            "eszkoz": "visszakerdez",
            "parameterek": {
                "hianyzo_mezo": "eszkoz",
                "varhato_kerdes_tipusa": "zart",
                "valaszthato_ertekek": eszkozok,
            },
            # A `None` itt a helyes érték: nem azt állítjuk, hogy a
            # visszakérdezés bizonytalan (az biztos döntés), hanem azt,
            # hogy a szándékról nem tudunk nyilatkozni.
            "bizonyossag": {"eszkoz": None},
            "onkonzisztencia": "nincs_tobbseg",
        }

"""A `valasz` modul — magyar mondatgenerálás sablonokból (M5, blueprint
13. szakasz "Menekülőút-doktrína", platform-varratok: "sablonok fájlban,
nyelvkulccsal").

**Ez a modul soha nem dönt és soha nem generál új tényt** — a döntést az
orchestrator hozza (ADR-007), a tényt az `assistant/tools/` keresi ki. Ami
itt történik, kizárólag **behelyettesítés**: egy `SABLONOK["hu"][kategoria]`
alatti string sablonba (`"Nyitvatartás: {ertek}"`) a hívó által átadott,
MÁR ismert értéket illeszti be (`.format(...)`). Ha egy sablonnak nincs
behelyettesítendő mezője, a szöveg maga állandó (pl. egy hibaüzenet) — ezt
sem "generálja" a modul, csak felolvassa a szótárból.

Ez a modul a `ui/vasarlo.py`-t ÉS a jövőbeli hangréteget is kiszolgálja —
egyik felület sem fogalmaz saját maga: mindkettő ide hívja a mondatot, és
csak megjeleníti/felolvassa (CLAUDE.md, "Az LLM nem foglal, hanem fordít" —
ugyanez az elv érvényes a válaszoldalra: a felület nem fordít, csak közvetít).

Öt kategória — a sablonok maguk `assistant/valasz/sablonok.py`-ban:

- `hiba`           — hibaüzenet, `uzenet_kulcs` → mondat
- `visszaigazolas` — a folyamat egy lépésének lezárása/kérése
- `zart_kerdes`    — visszakérdezés-mondat, `hianyzo_mezo` → mondat
- `tenyvalasz`     — a `bolt_info` sikeres válaszának mondattá alakítása
- `nyugtazo`       — a hangcsatorna töltelékmondatai, TÖBB változattal,
                      véletlenszerű választással (lásd `nyugtazo_szoveg`)

Nyelvkulcs: ma csak `"hu"` — minden függvény `nyelv="hu"` alapértelmezéssel,
hogy egy jövőbeli második nyelv ne igényeljen hívóoldali módosítást, csak
egy új `SABLONOK["xy"]` bejegyzést."""

from __future__ import annotations

import random

from assistant.tools import katalogus
from assistant.valasz.sablonok import SABLONOK

_NYELV_ALAPERTELMEZETT = "hu"

_NAPSZAK_SZOVEG = {"delelott": "délelőtt", "delutan": "délután", "este": "este"}


def hiba_szoveg(uzenet_kulcs: str, *, nyelv: str = _NYELV_ALAPERTELMEZETT) -> str:
    """`uzenet_kulcs` egy eszköz (`assistant/tools/hiba.py`) vagy az
    orchestrator saját, zárt hibakulcsa. Ismeretlen kulcsnál a kulcsot
    magát írja ki — ez NEM hallgatólagos hibaelnyelés, hanem jól látható
    jelzés, hogy a sablon hiányzik, pótlásra vár."""
    return SABLONOK[nyelv]["hiba"].get(uzenet_kulcs, f"Hiba: {uzenet_kulcs}")


def megerosites_ker_szoveg(*, nyelv: str = _NYELV_ALAPERTELMEZETT) -> str:
    return SABLONOK[nyelv]["visszaigazolas"]["megerosites_ker"]


def sikeres_foglalas_szoveg(foglalasi_kod: str, *, nyelv: str = _NYELV_ALAPERTELMEZETT) -> str:
    return SABLONOK[nyelv]["visszaigazolas"]["sikeres_foglalas"].format(foglalasi_kod=foglalasi_kod)


def elvetve_szoveg(*, nyelv: str = _NYELV_ALAPERTELMEZETT) -> str:
    return SABLONOK[nyelv]["visszaigazolas"]["elvetve"]


def ajanlat_bevezetes_szoveg(*, nyelv: str = _NYELV_ALAPERTELMEZETT) -> str:
    return SABLONOK[nyelv]["visszaigazolas"]["ajanlat_bevezetes"]


def kiut_szoveg(
    dimenziok: list[str], *, nyelv: str = _NYELV_ALAPERTELMEZETT
) -> tuple[str, list[tuple[str, str]]]:
    """`(bevezető mondat, [(dimenzió, gombfelirat), ...])` az
    ismétlés-kiúthoz. A `dimenziok` az orchestrator zárt kimenete
    (`_KIUT_DIMENZIOK`) — ismeretlen elemet kihagyunk, nem találunk ki
    hozzá feliratot."""
    sablonok = SABLONOK[nyelv]["kiut"]
    gombok = [(d, sablonok["dimenzio"][d]) for d in dimenziok if d in sablonok["dimenzio"]]
    return sablonok["bevezetes"], gombok


def alternativa_szoveg(
    dimenzio: str | None, *, nyelv: str = _NYELV_ALAPERTELMEZETT
) -> tuple[str, str] | None:
    """`(bevezető mondat, gombfelirat)` a felajánlott alternatívához,
    vagy `None`, ha nincs mit felajánlani.

    A `dimenzio` az `assistant/tools/szabad_idopontok.py::
    _alternativ_dimenzio` zárt kimenete (`napszak` | `nap` | `het`) — ez
    a függvény csak megfogalmazza, nem dönt: azt, hogy VAN-e alternatíva,
    a determinisztikus eszköz állapította meg egy tényleges kereséssel."""
    sablonok = SABLONOK[nyelv]["alternativa"]
    if dimenzio not in sablonok["bevezetes"]:
        return None
    return sablonok["bevezetes"][dimenzio], sablonok["gomb"][dimenzio]


def visszakerdezes_szoveg(hianyzo_mezo: str | None, *, nyelv: str = _NYELV_ALAPERTELMEZETT) -> str:
    """A visszakérdezés mondata — a `hianyzo_mezo` (eszkoz-szerzodes skill
    mezőneve) emberi megfogalmazását illeszti a sablonba. Ismeretlen vagy
    hiányzó mezőnévnél a nyers mezőnevet használja tartalékként — kevésbé
    folyékony, de sosem hamis."""
    sablonok = SABLONOK[nyelv]["zart_kerdes"]
    mezo_szoveg = sablonok["mezo_neve"].get(hianyzo_mezo, hianyzo_mezo or "mit szeretnél")
    return sablonok["bevezetes"].format(mezo_szoveg=mezo_szoveg)


def tenyvalasz_szoveg(valasz: dict, *, nyelv: str = _NYELV_ALAPERTELMEZETT) -> str:
    """A `bolt_info` sikeres válaszát olvasható mondatba fogalmazza. A
    tényt maga a `bolt_info` kereste ki egy szerkesztett mezőből
    (docs/blueprint.md 10. szakasz, "Bolti tudás") — ez a függvény csak
    megfogalmazza, nem generál új tartalmat: minden kiírt érték
    szó szerint a `valasz` dict-ből jön."""
    sablonok = SABLONOK[nyelv]["tenyvalasz"]
    mezok = {k: v for k, v in valasz.items() if k != "sikeres"}

    if "nyitvatartas" in mezok:
        return sablonok["nyitvatartas"].format(
            ertek=mezok["nyitvatartas"] or sablonok["ismeretlen_ertek"]
        )
    if "cim" in mezok:
        return sablonok["cim"].format(ertek=mezok["cim"] or sablonok["ismeretlen_ertek"])
    if "megjelenes" in mezok:
        return mezok["megjelenes"] or sablonok["megjelenes_ures"]
    if "szolgaltatasok" in mezok:
        szolgaltatasok = mezok["szolgaltatasok"]
        if not szolgaltatasok:
            return sablonok["szolgaltatasok_ures"]
        sorok = []
        for sz in szolgaltatasok:
            reszek = [sz["nev"]]
            if sz.get("termekleiras"):
                reszek.append(sz["termekleiras"])
            if sz.get("ar"):
                reszek.append(f"({sz['ar']})")
            if "idotartam_perc" in sz:
                reszek.append(f"{sz['idotartam_perc']} perc")
            sorok.append(" — ".join(reszek))
        return "; ".join(sorok)
    return str(mezok)


def _ablak_datum_szoveg(datum_tol: str, datum_ig: str, napszak: str) -> str:
    nap_resz = _NAPSZAK_SZOVEG.get(napszak, "")
    if datum_tol[:10] == datum_ig[:10]:
        alap = datum_tol[:10]
    else:
        alap = f"{datum_tol[:10]} és {datum_ig[:10]} között"
    return f"{alap} {nap_resz}".strip()


def nyugtazo_szoveg(
    felismert_ablak: dict,
    *,
    nyelv: str = _NYELV_ALAPERTELMEZETT,
    veletlen: random.Random | None = None,
) -> str:
    """A keresés elindítása UTÁN, az eredmény megérkezése ELŐTT
    felolvasható sor — a hangcsatorna töltelékmondatának próbája (docs/
    blueprint.md 7. szakasz, "Kétlépcsős válasz").

    Csak azt mondja, amit MÁR biztosan tud — a blueprint 7. szakasz
    "mondható" oszlopa szerint: a felismert dátumablakot (a
    dátumparserből) és a zárt halmazból beazonosított boltot. Konkrét
    szabad időpontot vagy darabszámot SOSEM tartalmaz, mert azok csak a
    tényleges keresés lefutása után derülnek ki.

    `veletlen`: opcionális `random.Random` — a tesztek ezzel tudják
    determinisztikussá tenni a változat-választást; alapból a modul
    szintű `random` sorsol."""
    valaszto = veletlen.choice if veletlen is not None else random.choice
    sablonok = SABLONOK[nyelv]["nyugtazo"]

    if not felismert_ablak:
        return valaszto(sablonok["altalanos"])

    reszek = []
    bolt_slug = felismert_ablak.get("bolt_id")
    if bolt_slug:
        reszek.append(f"a(z) {katalogus.BOLT_NEVEK.get(bolt_slug, bolt_slug)} boltban")
    datum_tol = felismert_ablak.get("datum_tol")
    datum_ig = felismert_ablak.get("datum_ig")
    if datum_tol and datum_ig:
        reszek.append(
            _ablak_datum_szoveg(datum_tol, datum_ig, felismert_ablak.get("napszak", "barmikor"))
        )

    if not reszek:
        return valaszto(sablonok["altalanos"])
    sablon = valaszto(sablonok["ablakkal"])
    return sablon.format(resz=", ".join(reszek))

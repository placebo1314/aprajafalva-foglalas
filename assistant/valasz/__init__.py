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
egy új `SABLONOK["xy"]` bejegyzést.

## KÉT KIMENETI MÓD (M6, hang-előkészítés)

Minden mondatot előállító függvény `mod=` kulcsszót fogad:

- `MOD_SZOVEGES` (alapértelmezett) — a mai viselkedés, változatlanul.
- `MOD_BESZELHETO` — felolvasható alak: egész mondatok, kimondott
  számokkal, fordulónként legfeljebb két mondattal és egy kérdéssel.
  A szabályok és az indoklásuk: `assistant/valasz/beszelheto.py`.

A **mód nem stílusváltás**: a beszélhető alak más tényt sosem mond, mint
a szöveges — ugyanabból az adatból ugyanaz az állítás lesz, csak
felolvasható alakban. Ahol a megfogalmazás hangon másképp helyes (két
kérdés helyett egy, felület helyett bolt), ott a `sablonok.py`
`beszelheto` szótára írja felül a mondatot; ahol csak a formázás
zavarna (számjegy, zárójel, gondolatjel), ott a kimeneti kapu
(`beszelheto.beszelhetove`) intézi el.

**Ami MINDKÉT módban ugyanaz:** a `rendszersor_szoveg` (a próbálgatónak
szóló helyzetjelentés, nem a vásárló válasza) és a `nyugtazo_szoveg` (az
már eleve felolvasásra készült, blueprint 7.)."""

from __future__ import annotations

import random

from assistant.tools import katalogus
from assistant.valasz import beszelheto as beszelheto_modul
from assistant.valasz import szamok
from assistant.valasz.sablonok import SABLONOK

_NYELV_ALAPERTELMEZETT = "hu"

# A két kimeneti mód zárt halmaza. Zárt, mert a felület (`ui/vasarlo.py`)
# és a végigjátszás (`tools/vegigjatszas.py`) is ezekre kapcsol, és egy
# elgépelt módnév némán a szöveges ágra esne vissza.
MOD_SZOVEGES = "szoveges"
MOD_BESZELHETO = "beszelheto"
MODOK = (MOD_SZOVEGES, MOD_BESZELHETO)

_NAPSZAK_SZOVEG = {"delelott": "délelőtt", "delutan": "délután", "este": "este"}


def _beszelheto_e(mod: str) -> bool:
    if mod not in MODOK:
        raise ValueError(f"ismeretlen kimeneti mód: {mod!r} (a lehetségesek: {MODOK})")
    return mod == MOD_BESZELHETO


def _beszelheto_sablon(nyelv: str, kategoria: str, *kulcsok: str) -> str | None:
    """Egy felülíró beszélhető sablon, vagy `None`, ha ehhez a kulcshoz
    nincs — akkor a szöveges alak megy át a kimeneti kapun."""
    csomopont = SABLONOK[nyelv].get("beszelheto", {}).get(kategoria, {})
    for kulcs in kulcsok:
        if not isinstance(csomopont, dict):
            return None
        csomopont = csomopont.get(kulcs)
        if csomopont is None:
            return None
    return csomopont if isinstance(csomopont, str) else None


def kimenet(szoveg: str, mod: str = MOD_SZOVEGES) -> str:
    """A KIMENETI KAPU: szöveges módban változatlanul enged át, beszélhető
    módban átvezet a `beszelhetove()`-n.

    Minden ebben a modulban előálló vásárlói mondat ezen megy keresztül —
    így egy új, elfelejtett sablon sem tud számjegyet vagy zárójelet
    kijuttatni a hangcsatornára."""
    return beszelheto_modul.beszelhetove(szoveg) if _beszelheto_e(mod) else szoveg


def fordulo_szoveg(reszek: list[str], mod: str = MOD_SZOVEGES) -> str:
    """Egy forduló ÖSSZES rendszer-mondatából egy megjeleníthető/
    felolvasható válasz.

    Szöveges módban ez egyszerű összefűzés (a felület ma is több sort ír
    ki egy fordulóban). Beszélhető módban itt érvényesül a fordulónkénti
    két mondat és az egy kérdés — l. `beszelheto.fordulo_szoveg`."""
    if _beszelheto_e(mod):
        return beszelheto_modul.fordulo_szoveg(reszek)
    return "\n".join(r for r in reszek if r)


def hiba_szoveg(
    uzenet_kulcs: str, *, nyelv: str = _NYELV_ALAPERTELMEZETT, mod: str = MOD_SZOVEGES
) -> str:
    """`uzenet_kulcs` egy eszköz (`assistant/tools/hiba.py`) vagy az
    orchestrator saját, zárt hibakulcsa. Ismeretlen kulcsnál a kulcsot
    magát írja ki — ez NEM hallgatólagos hibaelnyelés, hanem jól látható
    jelzés, hogy a sablon hiányzik, pótlásra vár."""
    if _beszelheto_e(mod):
        felulir = _beszelheto_sablon(nyelv, "hiba", uzenet_kulcs)
        if felulir is not None:
            return felulir
        # A hiányzó sablon jelzése hangon is olvasható marad, de a
        # kulcs aláhúzásjelei szóközre válnak — a kimeneti kapu
        # különben markdown-jelölésként törölné őket, és a
        # `sose_volt_kulcs`-ból egy szó nélküli „sosevoltkulcs" lenne.
        tartalek = f"Hiba: {uzenet_kulcs.replace('_', ' ')}"
    else:
        tartalek = f"Hiba: {uzenet_kulcs}"
    return kimenet(SABLONOK[nyelv]["hiba"].get(uzenet_kulcs, tartalek), mod)


def megerosites_ker_szoveg(
    idopont_iso: str | None = None,
    *,
    nyelv: str = _NYELV_ALAPERTELMEZETT,
    mod: str = MOD_SZOVEGES,
) -> str:
    """A megerősítést kérő mondat.

    `idopont_iso`: a választott slot kezdete. Szöveges módban nem
    használjuk (a képernyőn ott áll a kiválasztott gomb felirata),
    **beszélhető módban viszont ez a visszaolvasás** (blueprint 7.,
    „Visszaolvasásos megerősítés mindig"): hangon a „biztosan
    lefoglaljam EZT?" mutató névmása értelmetlen, mert nincs, amire
    mutasson."""
    sablonok = SABLONOK[nyelv]["visszaigazolas"]
    if _beszelheto_e(mod):
        if idopont_iso:
            sablon = _beszelheto_sablon(nyelv, "visszaigazolas", "megerosites_ker_idoponttal")
            return kimenet(sablon.format(idopont=szamok.ido_iso_szoval(idopont_iso)), mod)
        return kimenet(_beszelheto_sablon(nyelv, "visszaigazolas", "megerosites_ker"), mod)
    return sablonok["megerosites_ker"]


def sikeres_foglalas_szoveg(
    foglalasi_kod: str, *, nyelv: str = _NYELV_ALAPERTELMEZETT, mod: str = MOD_SZOVEGES
) -> str:
    """A foglalás visszaigazolása. Beszélhető módban a kód
    KARAKTERENKÉNT hangzik el (`szamok.betuzve`) — a `28SFL8RZ`-t
    „huszonnyolc"-ként kimondani használhatatlanná tenné azt, amiért a
    kód egyáltalán van: hogy a vásárló le tudja írni."""
    if _beszelheto_e(mod):
        sablon = _beszelheto_sablon(nyelv, "visszaigazolas", "sikeres_foglalas")
        return sablon.format(foglalasi_kod=szamok.betuzve(foglalasi_kod))
    return SABLONOK[nyelv]["visszaigazolas"]["sikeres_foglalas"].format(foglalasi_kod=foglalasi_kod)


def elvetve_szoveg(*, nyelv: str = _NYELV_ALAPERTELMEZETT, mod: str = MOD_SZOVEGES) -> str:
    return kimenet(SABLONOK[nyelv]["visszaigazolas"]["elvetve"], mod)


def ajanlat_bevezetes_szoveg(*, nyelv: str = _NYELV_ALAPERTELMEZETT) -> str:
    return SABLONOK[nyelv]["visszaigazolas"]["ajanlat_bevezetes"]


def ajanlat_mondat(
    jeloltek: list[dict],
    *,
    legkozelebbi: bool = False,
    nyelv: str = _NYELV_ALAPERTELMEZETT,
    mod: str = MOD_SZOVEGES,
) -> str:
    """Az ajánlat mondata.

    **A két mód itt tér el a legjobban, és ez a lényeg.** Szöveges
    csatornán a jelöltek KOPPINTHATÓ gombok, a mondat csak bevezeti
    őket („Ezeket az időpontokat találtam — melyik jó?"). Hangon nincs
    gomb, és nincs listázás sem: három felolvasott időpont
    megjegyezhetetlen. Ezért beszélhető módban **a legkorábbi és EGY
    alternatíva** hangzik el, kimondott órákkal, egyetlen kérdéssel:

        „A legkorábbi nyolc órakor van, de van kilenc harminckor is.
         Melyik jó?"

    A többi jelölt nem vész el — a következő fordulóban kérhető
    („valami későbbit"), és a képernyőn ott is marad. Amit a hang nem
    bír el, azt nem mondjuk ki, nem pedig gyorsabban mondjuk el."""
    if not _beszelheto_e(mod):
        return (
            ajanlat_bevezetes_legkozelebbi_szoveg(nyelv=nyelv)
            if legkozelebbi
            else ajanlat_bevezetes_szoveg(nyelv=nyelv)
        )

    kezdetek = [j["kezdet"] for j in jeloltek if j.get("kezdet")]
    if not kezdetek:
        # Nem hallgatunk el egy üres ajánlatot, de nem is találunk ki
        # időpontot hozzá: a bevezető mondat megy át a kimeneti kapun.
        return kimenet(ajanlat_bevezetes_szoveg(nyelv=nyelv), mod)

    elso = szamok.ido_iso_szoval(kezdetek[0], kor=True)
    if legkozelebbi or len(kezdetek) == 1:
        kulcs = "ajanlat_legkozelebbi" if legkozelebbi else "ajanlat_egy"
        sablon = _beszelheto_sablon(nyelv, "visszaigazolas", kulcs)
        return kimenet(sablon.format(elso=elso), mod)

    # AZONOS NAPON a dátum nem hangzik el kétszer. „December
    # huszonkettedikén nyolc órakor, de van december huszonkettedikén
    # kilenc harminckor is" — ez írásban is rossz, hangon pedig azt a
    # látszatot kelti, hogy a két időpont két KÜLÖNBÖZŐ napra szól, és
    # a vásárló a dátumot kezdi hallgatni a lényeg helyett.
    if kezdetek[1][:10] == kezdetek[0][:10]:
        masodik = szamok.idopont_kor(int(kezdetek[1][11:13]), int(kezdetek[1][14:16]))
    else:
        masodik = szamok.ido_iso_szoval(kezdetek[1], kor=True)
    sablon = _beszelheto_sablon(nyelv, "visszaigazolas", "ajanlat_ketto")
    return kimenet(sablon.format(elso=elso, masodik=masodik), mod)


def kiut_szoveg(
    dimenziok: list[str], *, nyelv: str = _NYELV_ALAPERTELMEZETT, mod: str = MOD_SZOVEGES
) -> tuple[str, list[tuple[str, str]]]:
    """`(bevezető mondat, [(dimenzió, gombfelirat), ...])` az
    ismétlés-kiúthoz. A `dimenziok` az orchestrator zárt kimenete
    (`_KIUT_DIMENZIOK`) — ismeretlen elemet kihagyunk, nem találunk ki
    hozzá feliratot.

    Beszélhető módban a gombfeliratok **beleépülnek a mondatba** („másik
    boltot, másik hetet vagy másik napszakot") — a gomblista attól még
    visszajön, mert a szöveges felület beszélhető módban is gombot rajzol
    belőle. A hangcsatornán ugyanez a lista lesz a felismerendő
    válaszok halmaza."""
    sablonok = SABLONOK[nyelv]["kiut"]
    gombok = [(d, sablonok["dimenzio"][d]) for d in dimenziok if d in sablonok["dimenzio"]]
    if not _beszelheto_e(mod):
        return sablonok["bevezetes"], gombok

    beszelt = SABLONOK[nyelv]["beszelheto"]["kiut"]
    nevek = [beszelt["dimenzio"][d] for d, _ in gombok if d in beszelt["dimenzio"]]
    if not nevek:
        return kimenet(beszelt["bevezetes"], mod), gombok
    return (
        kimenet(
            f"{beszelt['bevezetes']} {beszelt['kerdes'].format(dimenziok=_felsorolas(nevek))}", mod
        ),
        gombok,
    )


def _felsorolas(elemek: list[str]) -> str:
    """Kimondható felsorolás: `„a, b vagy c"`. Ez NEM az a felsorolás,
    amit a beszélhető mód tilt — a tiltás a felsorolás-JELÖLÉSRE
    (pontok, sortörések) vonatkozik, nem a magyar mondatra."""
    if len(elemek) == 1:
        return elemek[0]
    return f"{', '.join(elemek[:-1])} vagy {elemek[-1]}"


def alternativa_szoveg(
    dimenzio: str | None, *, nyelv: str = _NYELV_ALAPERTELMEZETT, mod: str = MOD_SZOVEGES
) -> tuple[str, str] | None:
    """`(bevezető mondat, gombfelirat)` a felajánlott alternatívához,
    vagy `None`, ha nincs mit felajánlani.

    A `dimenzio` az `assistant/tools/szabad_idopontok.py::
    _alternativ_dimenzio` zárt kimenete (`napszak` | `nap` | `het`) — ez
    a függvény csak megfogalmazza, nem dönt: azt, hogy VAN-e alternatíva,
    a determinisztikus eszköz állapította meg egy tényleges kereséssel.

    Beszélhető módban a mondat a kérdést is tartalmazza („Megnézzem?") —
    hangon a gombfelirat nem látszik, tehát a felajánlásnak a mondatban
    kell megtörténnie."""
    sablonok = SABLONOK[nyelv]["alternativa"]
    if dimenzio not in sablonok["bevezetes"]:
        return None
    if not _beszelheto_e(mod):
        return sablonok["bevezetes"][dimenzio], sablonok["gomb"][dimenzio]
    beszelt = SABLONOK[nyelv]["beszelheto"]["alternativa"]
    return (
        f"{beszelt['bevezetes'][dimenzio]} {beszelt['kerdes']}",
        sablonok["gomb"][dimenzio],
    )


def visszakerdezes_szoveg(
    hianyzo_mezo: str | None, *, nyelv: str = _NYELV_ALAPERTELMEZETT, mod: str = MOD_SZOVEGES
) -> str:
    """A visszakérdezés mondata — a `hianyzo_mezo` (eszkoz-szerzodes skill
    mezőneve) emberi megfogalmazását illeszti a sablonba. Ismeretlen vagy
    hiányzó mezőnévnél a nyers mezőnevet használja tartalékként — kevésbé
    folyékony, de sosem hamis.

    Beszélhető módban a mondat KÉRDÉS („Melyik boltba szeretnél
    menni?"), nem bevezetett kijelentés: a szöveges alak felolvasva
    olyan mondat, amire a vásárló hallgatással felel."""
    if _beszelheto_e(mod):
        kerdes = _beszelheto_sablon(nyelv, "zart_kerdes", "mezo_neve", hianyzo_mezo or "")
        return kerdes or _beszelheto_sablon(nyelv, "zart_kerdes", "tartalek")
    sablonok = SABLONOK[nyelv]["zart_kerdes"]
    mezo_szoveg = sablonok["mezo_neve"].get(hianyzo_mezo, hianyzo_mezo or "mit szeretnél")
    return sablonok["bevezetes"].format(mezo_szoveg=mezo_szoveg)


def tenyvalasz_szoveg(
    valasz: dict, *, nyelv: str = _NYELV_ALAPERTELMEZETT, mod: str = MOD_SZOVEGES
) -> str:
    """A `bolt_info` sikeres válaszát olvasható mondatba fogalmazza. A
    tényt maga a `bolt_info` kereste ki egy szerkesztett mezőből
    (docs/blueprint.md 10. szakasz, "Bolti tudás") — ez a függvény csak
    megfogalmazza, nem generál új tartalmat: minden kiírt érték
    szó szerint a `valasz` dict-ből jön.

    Beszélhető módban a szerkesztett érték IS átmegy a kimeneti kapun —
    egy admin által beírt „H-P 8:00-16:00" felolvasva értelmezhetetlen
    lenne. Ez az egyetlen hely, ahol a kapu nem a mi mondatunkat, hanem
    idegen adatot alakít: a tényt nem változtatja meg, csak kimondhatóvá
    teszi."""
    sablonok = SABLONOK[nyelv]["tenyvalasz"]
    beszelt = _beszelheto_e(mod)
    mezok = {k: v for k, v in valasz.items() if k != "sikeres"}

    if "nyitvatartas" in mezok:
        sablon = (
            _beszelheto_sablon(nyelv, "tenyvalasz", "nyitvatartas")
            if beszelt
            else sablonok["nyitvatartas"]
        )
        return kimenet(
            sablon.format(ertek=mezok["nyitvatartas"] or sablonok["ismeretlen_ertek"]), mod
        )
    if "cim" in mezok:
        sablon = _beszelheto_sablon(nyelv, "tenyvalasz", "cim") if beszelt else sablonok["cim"]
        return kimenet(sablon.format(ertek=mezok["cim"] or sablonok["ismeretlen_ertek"]), mod)
    if "megjelenes" in mezok:
        return kimenet(mezok["megjelenes"] or sablonok["megjelenes_ures"], mod)
    if "szolgaltatasok" in mezok:
        szolgaltatasok = mezok["szolgaltatasok"]
        if not szolgaltatasok:
            return kimenet(sablonok["szolgaltatasok_ures"], mod)
        if beszelt:
            # Hangon a szolgáltatás-lista NEVEKRE szűkül: a leírás és az
            # időtartam felolvasva három mondatnyi, és a kérdés (melyiket
            # kéri) elveszne a végén. A részletet a következő forduló
            # kérdezheti vissza.
            nevek = [sz["nev"] for sz in szolgaltatasok]
            sablon = _beszelheto_sablon(nyelv, "tenyvalasz", "szolgaltatasok")
            return kimenet(sablon.format(nevek=_felsorolas(nevek)), mod)
        sorok = []
        for sz in szolgaltatasok:
            reszek = [sz["nev"]]
            if sz.get("termekleiras"):
                reszek.append(sz["termekleiras"])
            # AZ ÁR SZÁNDÉKOSAN KIMARAD. Az ár nem engedélyezett
            # tényválasz a vásárlói csatornán (blueprint 7. és 10.
            # szakasz; golden set `kapuor-02`) — az eszköz adata
            # tartalmazza (admin-oldali használatra), ez a mondat nem.
            #
            # A fej nélküli végigjátszás fogta meg, miért nem elég a
            # kapuőr: a "Mennyibe kerül a nagy petárda?" kérdésre a
            # modell `mit: "termek"`-et adott — érvényes tényválasz-
            # típus —, és a termékleírás mellett az ÁR is kiment volna.
            # A tiltást ezért nem az útvonal elején, hanem itt, a
            # kimeneti oldalon is érvényesítjük: bárhonnan is jön a
            # kérés, ár nem hagyja el a rendszert.
            if "idotartam_perc" in sz:
                reszek.append(f"{sz['idotartam_perc']} perc")
            sorok.append(" — ".join(reszek))
        return "; ".join(sorok)
    # ISMERETLEN mezőalak — védőág. Szöveges csatornán a nyers dict
    # kiírása a leggyorsabb hibakeresés; hangon viszont felolvashatatlan
    # (kapcsos zárójel, aposztróf), és nem is segít senkin. Ott inkább
    # bevalljuk, hogy nem tudjuk megfogalmazni.
    if beszelt:
        return hiba_szoveg("ismeretlen_valasz", nyelv=nyelv, mod=mod)
    return str(mezok)


def _ablak_datum_szoveg(datum_tol: str, datum_ig: str, napszak: str) -> str:
    nap_resz = _NAPSZAK_SZOVEG.get(napszak, "")
    if datum_tol[:10] == datum_ig[:10]:
        alap = datum_tol[:10]
    else:
        alap = f"{datum_tol[:10]} és {datum_ig[:10]} között"
    return f"{alap} {nap_resz}".strip()


def ajanlat_bevezetes_legkozelebbi_szoveg(*, nyelv: str = _NYELV_ALAPERTELMEZETT) -> str:
    """A `legkozelebbi_idopont` válaszának bevezetője — l. sablon."""
    return SABLONOK[nyelv]["visszaigazolas"]["ajanlat_bevezetes_legkozelebbi"]


def rendszersor_szoveg(
    idoszak: dict | None,
    horgony: str,
    valodi_most: str,
    modell_nev: str | None = None,
    *,
    nyelv: str = _NYELV_ALAPERTELMEZETT,
) -> str:
    """Az ablak tetején álló tájékoztató sor: melyik időszakra és melyik
    boltba van beosztás, mit jelent itt a "ma", és melyik értelmező
    dolgozik.

    Ez nem a vásárlónak szóló válasz, hanem a **próbálgatónak szóló
    helyzetjelentés** (`docs/TESZTELES.md`, "Beszélgetés-próba") — de
    ugyanúgy magyar mondat, ezért ugyanúgy sablonból jön, nem a
    felületen fogalmazódik meg.

    `idoszak`: a `core/repo/muszak_repo.py::slot_range` kimenete vagy
    `None`. `horgony`/`valodi_most`: teljes ISO-8601 UTC időbélyeg.
    `modell_nev`: a konfigurált modell neve vagy `None`."""
    sablonok = SABLONOK[nyelv]["rendszersor"]
    if idoszak is None:
        return sablonok["nincs_beosztas"]

    boltok = idoszak.get("boltok") or []
    if boltok:
        szoveg = sablonok["idoszak_boltokkal"].format(
            elso_nap=idoszak["elso_nap"],
            utolso_nap=idoszak["utolso_nap"],
            boltok=", ".join(boltok),
        )
    else:
        szoveg = sablonok["idoszak"].format(
            elso_nap=idoszak["elso_nap"], utolso_nap=idoszak["utolso_nap"]
        )
    szoveg += "."

    if horgony[:10] == valodi_most[:10]:
        szoveg += sablonok["ma_bent"]
    else:
        szoveg += sablonok["ma_kint"].format(ma=valodi_most[:10], horgony_nap=horgony[:10])

    if modell_nev:
        szoveg += sablonok["ertelmezo_modell"].format(modell=modell_nev)
    else:
        szoveg += sablonok["ertelmezo_szabaly"]
    return szoveg


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

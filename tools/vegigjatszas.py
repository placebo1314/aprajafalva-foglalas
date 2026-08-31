"""Fej nélküli végigjátszás — a vásárlói felület (`ui/vasarlo.py`)
szöveges útját hajtja végig Tkinter `mainloop()` NÉLKÜL, közvetlen
metódushívásokkal.

Miért van erre külön eszköz: a felületet kézzel végigkattintani lassú és
nem reprodukálható, egy egységteszt viszont a felület helyett a
függvényeit méri. Ez a köztes lépés — a VALÓDI `VasarloApp` fut (ugyanaz
az orchestrator, ugyanaz az értelmező, ugyanaz a próba-napló), csak nincs
felhasználó és nincs eseményhurok. Ez az **önellenőrzés, mielőtt bárki
leül a felület elé**.

    python feladat.py vegigjatszas
    python feladat.py vegigjatszas --db proba.db
    python feladat.py vegigjatszas --robusztus     # + a teljes robusztussági halmaz
    python feladat.py vegigjatszas --csak-robusztus
    python feladat.py vegigjatszas --mod beszelheto
    python feladat.py vegigjatszas --mod mindketto  # ugyanaz KÉTSZER, két módban

**A `--mod` a kimeneti módot választja** (M6, hang-előkészítés): a
`szoveges` a mai viselkedés, a `beszelheto` az, amit egy felolvasó
kapna. A `mindketto` mindkettőt végigfuttatja, egymás után — ez az,
amiből látszik, hogy a KÉT MÓD UGYANAZT A DÖNTÉST hozza, csak másképp
mondja: a réteg, az eszköz és a paraméterek soronként azonosak, a
megjelenített mondat nem.

**A `--robusztus` a robusztussági halmaz (`tests/golden/robusztus.yaml`,
44 eset) MINDEN esetét végigjátssza a VALÓDI felületen.** Ez másra jó,
mint a `python feladat.py golden --halmaz robusztus`: az az ÉRTELMEZŐT
méri (mondat → eszközhívás), ez pedig a teljes utat — orchestrator,
ismétlésfigyelés, frusztráció-kiút, bizonyosság-kapu, magyar
mondatgenerálás, próba-napló. A golden mérés szerkezetileg nem tudja
megmutatni, hogy egy üres bemenetre MI JELENIK MEG a képernyőn; ez
igen.

Amit kiír, fordulónként: a bemenet, melyik réteg oldotta meg, a felismert
eszköz és paraméterek, a válasz típusa, és a felület által ténylegesen
megjelenített mondatok. A `naplo/probak.jsonl` közben ugyanúgy telik,
mint kézi próbánál.

**VALÓDI foglalást hoz létre** a megadott adatbázisban (a végigjátszás
utolsó menete végigmegy a megerősítésig) — ez szándékos, mert épp azt
ellenőrzi, hogy a felület elvezet-e a foglalási kódig. A demóadaton ez
ártalmatlan: `python feladat.py seed --ujra` visszaállítja, vagy adj meg
egy külön fájlt a `--db` kapcsolóval.

**Ollama nélkül is lefut**: az értelmező ilyenkor csendben a
determinisztikus rétegre esik vissza (`assistant/interpreter/__init__.py::
alapertelmezett_ertelmezo`), és a végigjátszás ugyanúgy végigmegy — a
kiírt `réteg` oszlopból látszik, melyik esetben mi történt.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

GYOKER = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(GYOKER))

from seed.betolt import ALAP_DB_PATH  # noqa: E402

# A végigjátszott beszélgetések. Az első nyolc a golden set `mintan_tul`
# rétegének mondatai (a felületen, nem a mérésben — itt az a kérdés, mit
# LÁT belőle a vásárló), utána öt saját próba, ami a mérésben nincs benne:
# gombnyomás utáni forduló, kapuőr, tényválasz, lemondás kód nélkül, és
# egy teljes foglalási menet.
BESZELGETESEK: list[tuple[str, list[str]]] = [
    ("vagylagos", ["Petárdázni szeretnék.", "jövő héten, vagy 28-án tudok menni?"]),
    ("üres szándék", ["Valamikor mennék, ha lehet."]),
    (
        "feltételes",
        [
            "Szeretnék időpontot a Szundiba.",
            "ha van hely szerdán, akkor az jó, ha nincs, csütörtök",
        ],
    ),
    ("indoklás mellékmondattal", ["Azért kellene délelőtt, mert délután dolgozom."]),
    ("kettős kérés", ["A Törpillánál mikor van nyitva, és tudok-e ma menni?"]),
    (
        "visszavonás",
        [
            "Petárdázni szeretnék kedden.",
            "és jövő héten péntek?",
            "mégsem, inkább maradjunk a keddnél",
        ],
    ),
    ("bizonytalan", ["Szundihoz mennék.", "talán jövő héten, még nem tudom biztosan"]),
    (
        "köznyelvi töltelék",
        ["Törpillához mennék.", "hát izé, valamikor a jövő hét elején lenne jó"],
    ),
    # -- saját próbák, a mérésen kívül --------------------------------
    # Ezek szándékosan a TÖRPILLÁT célozzák: a demóadat csak oda generál
    # műszakot, tehát csak itt fut végig a tényleges keresés → ajánlat →
    # foglalás út. A fenti nyolc a nyelvi értelmezést méri, ez az ötös
    # azt, hogy a felület ténylegesen elvezet-e a foglalási kódig.
    # A gombnyomás UTÁN egy sorszámos hivatkozás: a felajánlott
    # jelöltek közül a másodikat kéri. Ez a leggyakoribb természetes
    # válasz egy listára (`assistant/sorszam.py`), és a végigjátszásban
    # eddig egyetlen forduló sem hajtotta meg.
    (
        "zárt kérdés + gombnyomás + sorszámos választás",
        ["szeretnék időpontot holnapra", "torpilla", "a másodikat kérem"],
    ),
    ("kapuőr", ["Mennyibe kerül a nagy petárda?"]),
    ("tényválasz", ["Hogy néz ki a Törpilla bolt?"]),
    ("lemondás kód nélkül", ["Le szeretném mondani a foglalásomat."]),
    ("ismétlés → kiút", ["mennék", "szeretnék menni", "menni szeretnék"]),
    # A frusztráció-figyelő MÁSODIK kiútja: emberhez irányít (a vásárló
    # 8. igénye). Négy forduló kell hozzá — ez a `docs/TESZTELES.md` 12.
    # kézi próbája, ami eddig CSAK kézzel volt végigjátszható. A
    # végigjátszás enélkül azt állította magáról, hogy a teljes utat
    # méri, holott a beszélgetés legrosszabb végkimenetelét kihagyta.
    (
        "frusztráció → emberhez",
        [
            "nem értem, mit kell csinálni",
            "nem értem, mit kell csinálni",
            "nem értem, mit kell csinálni",
            "nem értem, mit kell csinálni",
        ],
    ),
]

# A teljes foglalási menet (keresés → jelölt → megerősítés → kód) — ezt
# nem mondatlistával, hanem gombnyomásokkal kell végigvinni, ezért külön
# függvényben van (`_foglalasi_menet`).
FOGLALASI_MENET_MONDAT = "Törpillához mennék holnap"


def _naplo_ujdonsag(app, korabbi_hossz: int) -> tuple[list[str], int]:
    """A felület szöveges naplójának ÚJ sorai az előző mérés óta — ez az,
    amit a vásárló ténylegesen lát a képernyőn."""
    teljes = app.szo_naplo.get("1.0", "end").rstrip("\n")
    sorok = teljes.split("\n") if teljes else []
    return sorok[korabbi_hossz:], len(sorok)


def _feliratok(keret) -> list[str]:
    """Egy keret gyerekeinek FELIRATAI — ami nem felirattal rendelkező
    widget (beviteli mező, beágyazott keret), az kimarad.

    **Nem lehet feltételezni, hogy csak gombok vannak benne.** A
    végigjátszás pontosan ezen szállt el: a sorszámos hivatkozás után
    („a másodikat kérem") a jelöltkeretben nem gombok állnak, hanem a
    megerősítő űrlap — címke, beviteli mező, gombsor. Egy `cget("text")`
    a beviteli mezőn `TclError`-t dob, és a végigjátszás félbeszakad
    azon a fordulón, amit épp ellenőrizni akartunk."""
    feliratok = []
    for widget in keret.winfo_children():
        # Csak a FELIRATOS widgetek (címke, gomb). A beviteli mezőnek
        # is van `-text` opciója egyes Tk-verziókban, de az a
        # `textvariable` NEVÉT adja vissza (`PY_VAR5`), nem a
        # tartalmát — a zaj rosszabb, mint a hiány.
        if widget.winfo_class() not in ("TLabel", "TButton", "Label", "Button"):
            continue
        felirat = widget.cget("text")
        if felirat:
            feliratok.append(felirat)
    return feliratok


def _gombfeliratok(app) -> list[str]:
    """A forduló után felkínált gombok feliratai (zárt kérdés, kiút,
    alternatíva) — a szöveges naplóban ezek nem látszanak, pedig a
    vásárló élményének a fele."""
    return _feliratok(app.szo_gombsor)


def _jelolt_gombok(app) -> list[str]:
    return _feliratok(app.szo_jelolt_keret)


def _widgetek(keret, osztaly: str) -> list:
    """Egy widgetfa MINDEN adott osztályú eleme, mélységben — a
    megerősítő gombok egy beágyazott `Frame`-ben ülnek, tehát a
    `winfo_children()` önmagában nem találná meg őket."""
    talalatok = []
    for widget in keret.winfo_children():
        if widget.winfo_class() == osztaly:
            talalatok.append(widget)
        talalatok.extend(_widgetek(widget, osztaly))
    return talalatok


def vegigjatszas(
    db_path: str,
    robusztus: bool = False,
    csak_robusztus: bool = False,
    mod: str = "szoveges",
) -> int:
    from assistant import valasz as valasz_szoveg
    from assistant.interpreter import indito_ellenorzes
    from ui.vasarlo import VasarloApp

    if mod == "mindketto":
        kodok = [
            vegigjatszas(db_path, robusztus, csak_robusztus, egy_mod)
            for egy_mod in (valasz_szoveg.MOD_SZOVEGES, valasz_szoveg.MOD_BESZELHETO)
        ]
        return max(kodok)

    # A modális indítási ellenőrzés (`ui/vasarlo.py::_indito_ellenorzes`)
    # gombnyomást vár — fej nélkül nincs, aki megnyomja. Ezért itt
    # kikapcsoljuk, de a HELYZETET kiírjuk: a végigjátszás ugyanúgy
    # futhat tartalékágon, és ugyanúgy félrevezető, ha ez nem látszik.
    os.environ.setdefault("APRAJAFALVA_INDITO_ELLENORZES", "ki")
    app = VasarloApp(db_path)
    # Nincs `mainloop()` — az ablakot el is rejtjük, hogy a végigjátszás
    # ne villantson fel semmit.
    app.withdraw()
    print(f"Adatbázis: {db_path}")
    allapot = indito_ellenorzes()
    if allapot.rendben:
        print(f"Modell: {allapot.modell} (éles út)")
    else:
        print(
            f"FIGYELEM: TARTALÉKÁGON fut ({allapot.hiany}) — ez a végigjátszás NEM a modellt méri."
        )

    # ÜRES ADATBÁZIS: a felület ilyenkor egyetlen figyelmeztető
    # címkét épít fel, fülek és beviteli mező nélkül
    # (`ui/vasarlo.py::_build` korai visszatérése) — nincs mit
    # végigjátszani. Enélkül az ellenőrzés `AttributeError`-ral állna
    # meg egy olyan widgeten, ami létre sem jött, és a próbálgató a
    # tracebackből nem tudná meg, hogy csak a `seed` hiányzik.
    if app.org_id is None:
        print(
            "\nNincs betöltött demóadat ebben az adatbázisban — "
            "futtasd előbb: python feladat.py seed"
        )
        app._close()
        return 1

    # A kimeneti mód a felület KAPCSOLÓJÁN át áll be, nem egy külön
    # ágon: így a végigjátszás pontosan azt méri, amit egy próbálgató
    # kapna, aki átkattint a beszélhető módra.
    app.kimeneti_mod.set(mod)

    # NINCS MODELL — ugyanaz a figyelmeztetés, mint az ablakban. Itt
    # legalább annyira kell: a végigjátszás percekig fut, és a végén a
    # számok ugyanúgy néznek ki, akár a modell dolgozott, akár a
    # tartalék ág.
    figyelmeztetes = getattr(app, "modell_figyelmeztetes", None)
    if figyelmeztetes is not None:
        print("\n" + "!" * 72)
        print(figyelmeztetes.cget("text"))
        print("!" * 72 + "\n")

    print(f"Beosztás:  {app.idoszak}")
    print(f"Indító sor: {app.idoszak_cimke.cget('text')}")
    print(f"Értelmező: {type(app.orchestrator.ertelmezo).__name__}")
    print(f"KIMENETI MÓD: {mod}")
    print(f'"most" a szöveges úton: {app._most_iso()}\n')

    kilepokod = 0
    if not csak_robusztus:
        _sajat_probak(app)
        _foglalasi_menet(app)
        _foglalasi_menet_irasban(app)
    if robusztus or csak_robusztus:
        kilepokod = _robusztus_halmaz(app)

    app._close()
    return kilepokod


def _sajat_probak(app) -> None:
    naplo_hossz = 0
    for cimke, mondatok in BESZELGETESEK:
        print("=" * 72)
        print(f"# {cimke}")
        # Friss session ÉS friss előzmény — az `_uj_beszelgetes` mindkettőt
        # elintézi (ADR-019: az előzmény a beszélgetés bemenete, nem
        # szabad átcsordulnia a következő próbába).
        app._uj_beszelgetes()
        # Az `_uj_beszelgetes` a szöveges naplót is üríti — az
        # újdonság-számlálót ezért nullázni kell, különben a következő
        # beszélgetés rendszer-sorai kimaradnának a kiírásból.
        naplo_hossz = 0
        for mondat in mondatok:
            app._szo_kuldes(mondat)
            uj_sorok, naplo_hossz = _naplo_ujdonsag(app, naplo_hossz)
            ertelmezes = app.orchestrator.utolso_ertelmezes or {}
            # A réteget elsősorban az ÉRTELMEZÉS mondja meg: a
            # sorszámos rövidzárnál az orchestrator dönt, és az
            # értelmező `utolso_reteg`-je az ELŐZŐ fordulóé lenne.
            reteg = ertelmezes.get("reteg") or getattr(
                app.orchestrator.ertelmezo, "utolso_reteg", None
            )
            print(f"\n  > {mondat}")
            print(f"    réteg:       {reteg}")
            print(f"    eszköz:      {ertelmezes.get('eszkoz')}")
            print(f"    paraméterek: {ertelmezes.get('parameterek')}")
            for sor in uj_sorok:
                print(f"    | {sor}")
            gombok = _gombfeliratok(app) + _jelolt_gombok(app)
            if gombok:
                print(f"    gombok:      {gombok}")
        print()


def _robusztus_halmaz(app) -> int:
    """A robusztussági halmaz MINDEN esete a valódi felületen.

    Amit ez mér, és a `python feladat.py golden --halmaz robusztus`
    nem: mi JELENIK MEG a képernyőn. Egy üres bemenetre a felület
    egyáltalán el sem küldi a fordulót (`ui/vasarlo.py::_szo_kuldes`
    üres szövegnél visszatér) — ez helyes viselkedés, de a golden
    mérésben láthatatlan, mert ott nincs felület.

    Az elfogadási elv itt egyetlen dologra szűkül, mert a többit a
    golden mérés már lefedte: **egyetlen eset sem okozhat kivételt**.
    A kilépőkód ezt jelenti."""
    import time

    from tests.golden.futtato import ROBUSZTUS_UTVONAL, betolt

    _, esetek = betolt(ROBUSZTUS_UTVONAL)
    print("\n" + "#" * 72)
    print(f"# ROBUSZTUSSÁGI HALMAZ A FELÜLETEN — {len(esetek)} eset")
    print("#" * 72)

    kivetelek: list[tuple[str, str]] = []
    nema_fordulok: list[str] = []
    valasz_tipusok: dict[str, int] = {}
    leglassabb = (0.0, "")

    for eset in esetek:
        print("\n" + "=" * 72)
        print(f"# {eset.id}  [{', '.join(eset.cimkek)}]")
        app._uj_beszelgetes()
        naplo_hossz = 0
        for mondat in eset.fordulok:
            kezdet = time.monotonic()
            try:
                app._szo_kuldes(mondat)
            except Exception as exc:  # noqa: BLE001 - épp a kivételt keressük
                kivetelek.append((eset.id, f"{type(exc).__name__}: {exc}"))
                print(f"\n  > {mondat!r}")
                print(f"    KIVÉTEL:     {type(exc).__name__}: {exc}")
                continue
            telt = time.monotonic() - kezdet
            if telt > leglassabb[0]:
                leglassabb = (telt, eset.id)

            uj_sorok, naplo_hossz = _naplo_ujdonsag(app, naplo_hossz)
            ertelmezes = app.orchestrator.utolso_ertelmezes or {}
            # A réteget elsősorban az ÉRTELMEZÉS mondja meg: a
            # sorszámos rövidzárnál az orchestrator dönt, és az
            # értelmező `utolso_reteg`-je az ELŐZŐ fordulóé lenne.
            reteg = ertelmezes.get("reteg") or getattr(
                app.orchestrator.ertelmezo, "utolso_reteg", None
            )
            print(f"\n  > {mondat!r}")
            if not uj_sorok:
                # A felület el sem küldte a fordulót (üres/whitespace
                # bemenet) — nincs se napló-sor, se válasz.
                nema_fordulok.append(eset.id)
                print("    (a felület nem küldte el — üres bemenet)")
                continue
            print(f"    réteg:       {reteg}   ({telt:.2f} s)")
            print(f"    eszköz:      {ertelmezes.get('eszkoz')}")
            print(f"    paraméterek: {ertelmezes.get('parameterek')}")
            for sor in uj_sorok:
                print(f"    | {sor}")
            gombok = _gombfeliratok(app) + _jelolt_gombok(app)
            if gombok:
                print(f"    gombok:      {gombok}")

        from ui.vasarlo import proba_naplo_olvas

        utolso = proba_naplo_olvas(1)
        if utolso:
            tipus = utolso[0].get("valasz_tipus") or "?"
            valasz_tipusok[tipus] = valasz_tipusok.get(tipus, 0) + 1

    print("\n" + "#" * 72)
    print("# ÖSSZEGZÉS — robusztussági halmaz a felületen")
    print("#" * 72)
    print(f"  esetek:           {len(esetek)}")
    print(f"  KIVÉTELEK:        {len(kivetelek)}   (elfogadási elv: 0)")
    for eset_id, uzenet in kivetelek:
        print(f"      {eset_id}: {uzenet}")
    print(f"  néma forduló:     {len(nema_fordulok)}   (üres bemenet, a felület nem küldte el)")
    if nema_fordulok:
        print(f"      {', '.join(nema_fordulok)}")
    print(f"  leglassabb:       {leglassabb[0]:.2f} s  ({leglassabb[1]})")
    print("  válasz-típusok (utolsó forduló):")
    for tipus, darab in sorted(valasz_tipusok.items(), key=lambda p: -p[1]):
        print(f"      {tipus:22s} {darab}")
    return 1 if kivetelek else 0


def _foglalasi_menet(app) -> None:
    """A teljes út a foglalási kódig, gombnyomásokkal — ugyanazokat a
    `command`-eket hívja, amiket egy kattintás hívna (`Button.invoke()`),
    tehát a felület valódi útját járja be, nem egy mellékbejáratot."""
    print("=" * 72)
    print("# teljes foglalási menet (keresés → jelölt → megerősítés → kód)")
    app._uj_beszelgetes()
    app._szo_kuldes(FOGLALASI_MENET_MONDAT)
    print(f"\n  > {FOGLALASI_MENET_MONDAT}")

    jeloltek = app.szo_jelolt_keret.winfo_children()
    if not jeloltek:
        print("    NINCS jelölt — a menet itt megáll (nézd meg a beosztás időszakát).")
        return
    print(f"    jelöltek:    {[w.cget('text') for w in jeloltek]}")

    jeloltek[0].invoke()  # az első időpont-gomb
    keret = app.szo_jelolt_keret
    mezok = _widgetek(keret, "TEntry")
    if not mezok:
        print("    NINCS azonosító-mező a megerősítés után — a menet megáll.")
        return
    # A megerősítés MONDATA is látszódjon: beszélhető módban ez a
    # visszaolvasás (blueprint 7.), és épp az a kérdés, hogy kimondja-e
    # a választott időpontot.
    for cimke in _widgetek(keret, "TLabel"):
        if cimke.cget("text"):
            print(f"    megerősítés: {cimke.cget('text')}")

    mezok[0].delete(0, "end")
    mezok[0].insert(0, "proba-azonosito-123")
    igen = next((g for g in _widgetek(keret, "TButton") if "foglalom" in g.cget("text")), None)
    if igen is None:
        print("    NINCS 'Igen, foglalom' gomb — a menet megáll.")
        return
    igen.invoke()

    eredmeny = [w.cget("text") for w in _widgetek(keret, "TLabel")]
    print(f"    eredmény:    {eredmeny}")
    if app.szo_uzenet.cget("text"):
        print(f"    hibasor:     {app.szo_uzenet.cget('text')}")


def _foglalasi_menet_irasban(app) -> None:
    """UGYANAZ az út, de VÉGIG ÍRÁSBAN — gombnyomás nélkül.

    **Miért külön menet.** A `_foglalasi_menet` az időpontot GOMBBAL
    választja ki; a kézi próbában viszont az derült ki, hogy írásban
    nem megy végig a foglalás. Az a próba tartalékágon futott, tehát a
    hibáról nem lehetett megmondani, kié: a szövegértésé vagy a
    felületé. Ez a menet ezt választja szét — kiírja, MELYIK RÉTEG
    döntött minden lépésben, és hogy hol áll meg az út.

    Négy lépés, mindegyik egy külön állítás:

    1. keresés írásban → jönnek-e jelöltek;
    2. SORSZÁMOS választás („a másodikat kérem") → megerősítés-kérés
       lesz-e belőle (ezt determinisztikusan az orchestrator dönti el,
       `assistant/sorszam.py` — modell nélkül is mennie kell);
    3. írásbeli IGEN („igen, foglald le") → ma NINCS ilyen út: az
       azonosítót űrlap kéri be, és a mondat a szokásos értelmezőre fut.
       Ez a lépés azt méri meg, MI TÖRTÉNIK helyette;
    4. az azonosító megadása az űrlapon → létrejön-e a foglalás.
    """
    print("=" * 72)
    print("# foglalási menet ÍRÁSBAN (gombnyomás nélkül, a 4. lépés kivételével)")
    app._uj_beszelgetes()

    def fordulo(mondat: str) -> None:
        app._szo_kuldes(mondat)
        ertelmezes = app.orchestrator.utolso_ertelmezes or {}
        reteg = ertelmezes.get("reteg") or getattr(app.orchestrator.ertelmezo, "utolso_reteg", None)
        print(f"\n  > {mondat}")
        print(f"    réteg:       {reteg}")
        print(f"    eszköz:      {ertelmezes.get('eszkoz')}")
        print(f"    jelöltek:    {_jelolt_gombok(app)}")
        for cimke in _widgetek(app.szo_jelolt_keret, "TLabel"):
            if cimke.cget("text"):
                print(f"    kérdés:      {cimke.cget('text')}")
        if app.szo_uzenet.cget("text"):
            print(f"    üzenetsor:   {app.szo_uzenet.cget('text')}")

    fordulo(FOGLALASI_MENET_MONDAT)
    if not app.szo_jelolt_keret.winfo_children():
        print("    NINCS jelölt — a menet itt megáll (nézd meg a beosztás időszakát).")
        return

    fordulo("a másodikat kérem")
    fordulo("igen, foglald le")
    print("\n  (a megerősítés után az azonosítót a felület űrlapja kéri be —")
    print("   a foglaláshoz vásárlói kulcs kell, azt egy mondat nem pótolja)")

    mezok = _widgetek(app.szo_jelolt_keret, "TEntry")
    if not mezok:
        print("    Az azonosító-mező eltűnt — írásban itt szakad meg az út.")
        return
    mezok[0].delete(0, "end")
    mezok[0].insert(0, "proba-azonosito-123")
    igen = next(
        (g for g in _widgetek(app.szo_jelolt_keret, "TButton") if "foglalom" in g.cget("text")),
        None,
    )
    if igen is None:
        print("    NINCS 'Igen, foglalom' gomb — a menet megáll.")
        return
    igen.invoke()
    print(f"    eredmény:    {[w.cget('text') for w in _widgetek(app.szo_jelolt_keret, 'TLabel')]}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Fej nélküli végigjátszás a vásárlói felületen.")
    parser.add_argument("--db", default=str(ALAP_DB_PATH), help="adatbázis útvonala")
    parser.add_argument(
        "--robusztus",
        action="store_true",
        help="a saját próbák UTÁN a teljes robusztussági halmaz is (tests/golden/robusztus.yaml)",
    )
    parser.add_argument(
        "--csak-robusztus",
        action="store_true",
        help="CSAK a robusztussági halmaz — a saját próbák és a foglalási menet kihagyva",
    )
    parser.add_argument(
        "--mod",
        choices=["szoveges", "beszelheto", "mindketto"],
        default="szoveges",
        help=(
            "kimeneti mód: szoveges (mai viselkedés), beszelheto (felolvasásra), "
            "mindketto (ugyanaz kétszer, összevethetően)"
        ),
    )
    args = parser.parse_args(argv)
    return vegigjatszas(
        args.db,
        robusztus=args.robusztus,
        csak_robusztus=args.csak_robusztus,
        mod=args.mod,
    )


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())

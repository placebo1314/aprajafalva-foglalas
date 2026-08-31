"""Few-shot példák az LLM-értelmezőhöz — külön fájlban, adatként
(ugyanaz a minta, mint `assistant/valasz/sablonok.py`: a szöveg nem a
kódba ágyazva él).

**Miért kellenek.** Az M-1 spike és a 2026-08-22-i mérés is few-shot
példák NÉLKÜL futott — a modell csak a séma enumjait és egy rövid
prózai leírást látott. A mért 27,4% ezért nem a modell képességének
felső korlátja, hanem egy hiányos promptnak a mérése.

**Rétegenként egy.** A golden set öt nyelvi rétegéből (köznyelvi,
tájszólás, töredékes, szleng, kognitívan egyszerűsített) mindegyikből
szerepel egy pár, plusz a két kapuőr-kategória és a visszakérdezés.
Így a példakészlet nem egy stílusra tanít rá.

**Két SZERKEZETI példa is van** (vagylagos időpont, indoklás
mellékmondattal) — ezek nem egy nyelvi réteget, hanem egy mondattani
alakzatot mutatnak be, amit a mintaillesztés elvileg nem tud kezelni
(mindkét alakzatban két, egyenrangúnak LÁTSZÓ érték szerepel, és a
szerkezet dönti el, melyik a kért). A mondatok itt is másak, mint a
golden set esetei.

**A példák NEM a golden set esetei.** Szándékosan más mondatok, más
boltokkal és napokkal — ha a golden set eseteit másolnánk ide, a mérés
önmagát mérné (golden-set skill: "Ne a modell kimenetéből írj
tesztesetet" — ennek a párja: ne a tesztesetből írj promptot).

**A dátum itt is szöveges** (`datum_kifejezes`): a példák azt tanítják
meg, hogy a modell a dátumot IDÉZZE a mondatból, ne számolja ki — a
feloldás a `hun-date-parser` dolga (ADR-018).
"""

from __future__ import annotations

# (mondat, várt kimenet) párok. A `most` a példákban nincs feloldva —
# épp ez a lényeg: a modell szöveges dátumkifejezést ad vissza.
PELDAK: list[tuple[str, dict]] = [
    # köznyelvi — teljes, egyértelmű kérés
    (
        "Szeretnék időpontot foglalni szerdára az Ügyifogyiba.",
        {
            "eszkoz": "szabad_idopontok",
            "parameterek": {"bolt_id": "ugyifogyi", "datum_kifejezes": "szerda"},
        },
    ),
    # köznyelvi — tényválasz (nem foglalás!)
    (
        "Hány órakor nyit a Törpilla?",
        {"eszkoz": "bolt_info", "parameterek": {"bolt_id": "torpilla", "mit": "nyitvatartas"}},
    ),
    # tájszólás / régies — a bolt körülírva, nem néven nevezve
    (
        "Az altatósho szeretnék bemenni szombaton dílelőtt.",
        {
            "eszkoz": "szabad_idopontok",
            "parameterek": {
                "bolt_id": "szundi",
                "datum_kifejezes": "szombat",
                "napszak": "delelott",
            },
        },
    ),
    # töredékes — táviratstílus, hiányos mondat
    (
        "csütörtök… boldogság… lehetne?",
        {
            "eszkoz": "szabad_idopontok",
            "parameterek": {"bolt_id": "torpilla", "datum_kifejezes": "csütörtök"},
        },
    ),
    # szleng — rövidítés, laza regiszter
    (
        "hali, van hely holnap este a petárdásnál?",
        {
            "eszkoz": "szabad_idopontok",
            "parameterek": {
                "bolt_id": "ugyifogyi",
                "datum_kifejezes": "holnap",
                "napszak": "este",
            },
        },
    ),
    # kognitívan egyszerűsített — udvariassági bevezetés, körülírás,
    # és NINCS bolt: a helyes válasz a visszakérdezés, nem a találgatás
    (
        "Jó napot. Én a Ferike vagyok. Szeretnék menni valamikor. Lehet?",
        {
            "eszkoz": "visszakerdez",
            "parameterek": {"hianyzo_mezo": "bolt_id", "varhato_kerdes_tipusa": "zart"},
        },
    ),
    # "legkorábban" — saját eszköz, nem időszak-keresés. A különbség a
    # kérdésben van: itt nincs időszak, egyetlen válasz jár rá
    # (`assistant/tools/legkozelebbi_idopont.py`).
    (
        "Mikor tudok leghamarabb bemenni a Szundihoz?",
        {"eszkoz": "legkozelebbi_idopont", "parameterek": {"bolt_id": "szundi"}},
    ),
    # vagylagos/feltételes időpont — KÉT dátumkifejezés egy mondatban.
    # A modell mindkettőt IDÉZI; az ablakot a determinisztikus dátum-kapu
    # vonja össze (`forditott_kaszkad.py::_datum_ablak`), nem a modell.
    (
        "Hétfőn, vagy ha nem megy, akkor kedden mennék a Szundihoz.",
        {
            "eszkoz": "szabad_idopontok",
            "parameterek": {
                "bolt_id": "szundi",
                "datum_kifejezes": "hétfőn",
                "datum_kifejezes_2": "kedden",
            },
        },
    ),
    # indoklás mellékmondattal — a mellékmondatban szereplő napszak az,
    # amit a vásárló KIZÁR, nem amit kér. Ezt egy szólistás illesztés
    # elvileg nem tudja megkülönböztetni (mindkét napszak-szó ott van a
    # mondatban); a példa a szerkezetre tanít, nem egy konkrét mondatra.
    (
        "A Törpillához délután mennék csütörtökön, mert délelőtt dolgozom.",
        {
            "eszkoz": "szabad_idopontok",
            "parameterek": {
                "bolt_id": "torpilla",
                "datum_kifejezes": "csütörtökön",
                "napszak": "delutan",
            },
        },
    ),
    # lemondás — a kód a mondatban van
    (
        "A foglalásomat törölném, a kódja B4T7R2WQ.",
        {"eszkoz": "foglalas_lemondas", "parameterek": {"foglalasi_kod": "B4T7R2WQ"}},
    ),
    # kapuőr — nem foglalási kérdés
    (
        "Hány fok van odakint?",
        {"eszkoz": "nincs", "parameterek": {}},
    ),
    # MINDEGY — a vásárló ELENGEDI a szolgáltatást. A mező nem marad
    # üresen: az azt jelentené, hogy nem tudjuk, és a rendszer újra
    # rákérdezne arra, amit a vásárló épp az imént engedett el.
    (
        "Mindegy, melyik petárda, csak legyen szerdán.",
        {
            "eszkoz": "szabad_idopontok",
            "parameterek": {
                "bolt_id": "ugyifogyi",
                "szolgaltatas_id": "MINDEGY",
                "datum_kifejezes": "szerdán",
            },
        },
    ),
    # MINDEGY a napszakra — „ami van" ugyanaz az elengedés, más szóval.
    (
        "A Szundiba mennék csütörtökön, nekem tényleg mindegy, hány órakor.",
        {
            "eszkoz": "szabad_idopontok",
            "parameterek": {
                "bolt_id": "szundi",
                "napszak": "MINDEGY",
                "datum_kifejezes": "csütörtökön",
            },
        },
    ),
    # ELLENPRÓBA a MINDEGY-re: a „mindegyik" NEM elengedés, hanem
    # lista-kérés. A kettőt egy szólista nem tudja megkülönböztetni (a
    # szótő ugyanaz) — a mondattan igen, és ez a modell dolga.
    (
        "Mindegyik petárda érdekel, mit árulnak?",
        {"eszkoz": "bolt_info", "parameterek": {"bolt_id": "ugyifogyi", "mit": "termek"}},
    ),
    # A LEGKORÁBBI időpont mint önálló kérés — nincs benne időszak,
    # tehát nem is szabad rákérdezni: egyetlen válasz van rá.
    (
        "Bármikor jó, ami legközelebb van a Törpillánál.",
        {"eszkoz": "legkozelebbi_idopont", "parameterek": {"bolt_id": "torpilla"}},
    ),
]


# ---------------------------------------------------------------------
# V2 PÉLDAKÉSZLET — a rendszerprompt v2 változatához (ADR-026).
#
# **Sokféleség > darabszám.** A v1 tizenöt példája rétegenként egy
# mondatot mutat, de a példák nagy része UGYANAZT az alakzatot tanítja
# (bolt + nap → keresés) más szavakkal. A v2 hatot tart meg, egymástól
# a lehető legtávolabbi HELYZETEKKEL: hatókörön kívüli kérdés, hiányzó
# adat, elengedett mező, mondattani csapda és tényválasz-kérés — a
# legjellemzőbb eset (egyszerű keresés) pedig a LEGUTOLSÓ, mert a
# sorozat végét súlyozza a legerősebben a modell.
#
# Ami kimaradt és MIÉRT: a tájszólás, a szleng és a töredékes stílus
# külön példája. Nem azért, mert nem számítanak, hanem mert a
# stílusréteg a mondat FELSZÍNE — a hat megtartott példa mind más
# DÖNTÉST tanít, a stílust pedig a modell nyelvi tudása hozza. Hogy ez
# a csere ténylegesen nem ront-e, azt a v1/v2 A/B mérés dönti el
# (docs/PROMPT_AB.md), nem ez a megjegyzés.
# ---------------------------------------------------------------------
PELDAK_V2: list[tuple[str, dict]] = [
    # 1. hatókörön kívül — a kapuőr-döntés a legolcsóbb helyes válasz
    ("Hány fok van odakint?", {"eszkoz": "nincs", "parameterek": {}}),
    # 2. hiányzó kritikus adat — a helyes válasz a kérdés, nem a
    #    találgatás (a mondat udvariassági körrel és névvel jön)
    (
        "Jó napot. Én a Ferike vagyok. Szeretnék menni valamikor. Lehet?",
        {
            "eszkoz": "visszakerdez",
            "parameterek": {"hianyzo_mezo": "bolt_id", "varhato_kerdes_tipusa": "zart"},
        },
    ),
    # 3. ELENGEDETT mező — a MINDEGY szentinel, nem üres mező
    (
        "Mindegy, melyik petárda, csak legyen szerdán.",
        {
            "eszkoz": "szabad_idopontok",
            "parameterek": {
                "bolt_id": "ugyifogyi",
                "szolgaltatas_id": "MINDEGY",
                "datum_kifejezes": "szerdán",
            },
        },
    ),
    # 4. MONDATTANI CSAPDA — a mellékmondat napszaka a KIZÁRT, nem a
    #    kért; két napszak-szó van a mondatban, a szerkezet dönt
    (
        "A Törpillához délután mennék csütörtökön, mert délelőtt dolgozom.",
        {
            "eszkoz": "szabad_idopontok",
            "parameterek": {
                "bolt_id": "torpilla",
                "datum_kifejezes": "csütörtökön",
                "napszak": "delutan",
            },
        },
    ),
    # 5. TÉNYVÁLASZ és egyben ellenpróba a MINDEGY-re: a „mindegyik"
    #    listát kér, nem enged el semmit
    (
        "Mindegyik petárda érdekel, mit árulnak?",
        {"eszkoz": "bolt_info", "parameterek": {"bolt_id": "ugyifogyi", "mit": "termek"}},
    ),
    # 6. A LEGJELLEMZŐBB eset, szándékosan utolsóként: egyszerű keresés,
    #    idézett dátummal
    (
        "Szeretnék időpontot foglalni szerdára az Ügyifogyiba.",
        {
            "eszkoz": "szabad_idopontok",
            "parameterek": {"bolt_id": "ugyifogyi", "datum_kifejezes": "szerda"},
        },
    ),
]

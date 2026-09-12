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

from assistant.tools import ajanlat_kerdes, katalogus
from assistant.valasz import beszelheto as beszelheto_modul
from assistant.valasz import helyi_ido, ragozas, szamok
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
    rendszer_valasztott: bool = False,
    zona: str | None = None,
) -> str:
    """A megerősítést kérő mondat.

    `idopont_iso`: a választott slot kezdete, UTC-ben. Szöveges módban
    nem használjuk (a képernyőn ott áll a kiválasztott gomb felirata),
    **beszélhető módban viszont ez a visszaolvasás** (blueprint 7.,
    „Visszaolvasásos megerősítés mindig"): hangon a „biztosan
    lefoglaljam EZT?" mutató névmása értelmetlen, mert nincs, amire
    mutasson.

    `zona`: a szervezet időzónája — a kimondott óra HELYI idő
    (`helyi_ido.py`). Enélkül a visszaolvasás télen egy, nyáron két
    órával téved, és épp abban a mondatban, amire a vásárló igent
    mond."""
    sablonok = SABLONOK[nyelv]["visszaigazolas"]
    if idopont_iso:
        idopont_iso = helyi_ido.helyi_iso(idopont_iso, zona)

    # AMIKOR MI VÁLASZTOTTUNK a vásárló helyett („válassz te"): az
    # időpontot MINDKÉT módban ki kell mondani. Szöveges módban is, mert
    # a jelölt-gombok ilyenkor eltűnnek a képernyőről — nincs mire
    # mutatnia a „ezt az időpontot" kifejezésnek.
    if rendszer_valasztott and idopont_iso:
        kulcs = "megerosites_ker_rendszer_valasztott"
        if _beszelheto_e(mod):
            sablon = _beszelheto_sablon(nyelv, "visszaigazolas", kulcs)
            return kimenet(sablon.format(idopont=szamok.ido_iso_szoval(idopont_iso)), mod)
        return sablonok[kulcs].format(idopont=szamok.idopont_rovid(idopont_iso))

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


def _napokra_bont(kezdetek: list[str]) -> list[tuple[str, list[str]]]:
    """`[(nap, [kezdet, …]), …]` — a jelöltek NAPONKÉNT csoportosítva,
    az eredeti sorrendet megtartva.

    Azonos kezdet csak egyszer: a pontozó egy időpontra több jelöltet is
    adhat (más hosszúságú szolgáltatásokra), a gombokon a hossz
    megkülönbözteti őket, a mondatban nem."""
    napok: dict[str, list[str]] = {}
    for kezdet in kezdetek:
        nap = napok.setdefault(kezdet[:10], [])
        if kezdet[11:16] not in [meglevo[11:16] for meglevo in nap]:
            nap.append(kezdet)
    return list(napok.items())


def ajanlat_idopontok_szoveg(
    kezdetek: list[str], *, nyelv: str = _NYELV_ALAPERTELMEZETT, mod: str = MOD_SZOVEGES
) -> str:
    """A felajánlott időpontok felsorolása, NAPONKÉNT csoportosítva:

        Kedden, december huszonkettedikén: nyolc óra, kilenc harminc,
        tíz húsz.

    **Miért kell kimondani a napot** (ADR-035). Az idegen próba 7.
    fordulója ez volt: „akkor a legkésőbbit. De melyik nap?" — a
    vásárló három időpontot kapott óra szerint, és nem tudta, melyik
    napra szólnak. A dátum ott volt a gombokon, de a MONDATBAN nem, és
    hangon gomb sincs.

    A `kezdetek` HELYI idejű ISO-időbélyegek (`helyi_ido.py`) — a
    konverzió a hívóé.
    """
    csoportok = _napokra_bont(kezdetek)
    if not csoportok:
        return ""
    beszelt = _beszelheto_e(mod)
    reszek = []
    for nap, napi_kezdetek in csoportok:
        # A NAPNÉV is elhangzik („kedden, december huszonkettedikén"):
        # a vásárló a hét napját tartja fejben, nem a dátumot.
        nap_szoveg = szamok.datum_szoval(nap, napnevvel=True)
        if beszelt:
            # AZ ELSŐ időpont mondja ki az „óra" szót, a többi nem:
            # „nyolc óra, kilenc harminc, tíz húsz". Kimondva ez a
            # természetes — az „óra" minden tagban ismételve darabos,
            # elhagyva viszont az elsőnél nem derülne ki, hogy időpontok
            # következnek.
            idok = [
                szamok.ora_perc_szoval(int(kezdet[11:13]), int(kezdet[14:16]))
                if index == 0
                else szamok.ora_perc_szoval_rovid(int(kezdet[11:13]), int(kezdet[14:16]))
                for index, kezdet in enumerate(napi_kezdetek)
            ]
        else:
            nap_szoveg = nap_szoveg.capitalize()
            idok = [szamok.ora_perc_rovid(kezdet) for kezdet in napi_kezdetek]
        reszek.append(f"{nap_szoveg}: {_felsorolas(idok)}")
    # TÖBB NAP esetén pontosvessző választ: a felsorolásban már van
    # vessző, és a kettő egymásba folyna.
    return "; ".join(reszek) if len(reszek) > 1 else reszek[0]


def ajanlat_mondat(
    jeloltek: list[dict],
    *,
    legkozelebbi: bool = False,
    nyelv: str = _NYELV_ALAPERTELMEZETT,
    mod: str = MOD_SZOVEGES,
    zona: str | None = None,
) -> str:
    """Az ajánlat mondata.

    **Mindkét mód KIMONDJA az időpontokat**, csak másképp. Ez 2026-09-20
    óta van így: addig a szöveges mondat csak bevezette a gombokat
    („Ezeket az időpontokat találtam — melyik jó?"), és az időpont
    kizárólag gombfeliratként létezett. Egy gombfelirat viszont nem
    része a beszélgetésnek: nem olvasható vissza, nem kerül az
    előzménybe, és aki felolvastatja a képernyőt, annak egyszerűen
    nincs ott. A gombok megmaradtak — a mondat nem helyettük szól,
    hanem mellettük.

    Szöveges csatornán MINDEN jelölt kezdete elhangzik, `8:00`
    alakban; a gombokon ugyanaz áll, plusz a hossz. Hangon viszont
    nincs listázás: három felolvasott időpont megjegyezhetetlen, ezért
    **a legkorábbi és EGY alternatíva** hangzik el, kimondott órákkal:

        „A legkorábbi nyolc órakor van, de van kilenc harminckor is.
         Melyik jó?"

    A többi jelölt ott sem vész el — a következő fordulóban kérhető
    („valami későbbit"), és a képernyőn ott is marad. Amit a hang nem
    bír el, azt nem mondjuk ki, nem pedig gyorsabban mondjuk el.

    `zona`: a szervezet időzónája. **Az órák HELYI időben hangzanak el**
    (`helyi_ido.py`) — enélkül a rendszer a tárolt UTC-t mondaná, ami
    télen egy, nyáron két órával téves időpont."""
    kezdetek = [helyi_ido.helyi_iso(j["kezdet"], zona) for j in jeloltek if j.get("kezdet")]

    if not _beszelheto_e(mod):
        if legkozelebbi:
            return ajanlat_bevezetes_legkozelebbi_szoveg(nyelv=nyelv)
        if not kezdetek:
            return ajanlat_bevezetes_szoveg(nyelv=nyelv)
        # AZONOS KEZDET csak egyszer: a pontozó egy időpontra több
        # jelöltet is adhat (más hosszúságú szolgáltatásokra). A
        # gombokon a hossz megkülönbözteti őket, a mondatban nem —
        # „8:00, 8:00 vagy 8:20" felsorolás lenne belőle.
        # A NAP IS ELHANGZIK, naponként csoportosítva (ADR-035):
        # „Kedden, december huszonkettedikén: 8:00, 9:30 vagy 10:20."
        # Az azonos kezdeteket a csoportosító vonja össze.
        return SABLONOK[nyelv]["visszaigazolas"]["ajanlat_bevezetes_idokkel"].format(
            idok=ajanlat_idopontok_szoveg(kezdetek, nyelv=nyelv, mod=mod)
        )

    if not kezdetek:
        # Nem hallgatunk el egy üres ajánlatot, de nem is találunk ki
        # időpontot hozzá: a bevezető mondat megy át a kimeneti kapun.
        return kimenet(ajanlat_bevezetes_szoveg(nyelv=nyelv), mod)

    elso = szamok.ido_iso_szoval(kezdetek[0], kor=True, napnevvel=True)
    # A MÁSODIK időpont az első ELTÉRŐ kezdetű jelölt, nem egyszerűen a
    # következő. A fej nélküli végigjátszás fogta meg, miért: a
    # pontozó egy időpontra több jelöltet is adhat (más hosszúságú
    # szolgáltatásokra), és így a mondat „a legkorábbi hét órakor, de
    # van hét órakor is" lett — kimondva értelmetlen. Írásban ez a
    # gombokon nem tűnt fel, mert ott a hossz megkülönbözteti őket.
    elterok = [k for k in kezdetek[1:] if k[11:16] != kezdetek[0][11:16]]
    if legkozelebbi or not elterok:
        kulcs = "ajanlat_legkozelebbi" if legkozelebbi else "ajanlat_egy"
        sablon = _beszelheto_sablon(nyelv, "visszaigazolas", kulcs)
        return kimenet(sablon.format(elso=elso), mod)

    # AZONOS NAPON a dátum nem hangzik el kétszer. „December
    # huszonkettedikén nyolc órakor, de van december huszonkettedikén
    # kilenc harminckor is" — ez írásban is rossz, hangon pedig azt a
    # látszatot kelti, hogy a két időpont két KÜLÖNBÖZŐ napra szól, és
    # a vásárló a dátumot kezdi hallgatni a lényeg helyett.
    kovetkezo = elterok[0]
    if kovetkezo[:10] == kezdetek[0][:10]:
        masodik = szamok.idopont_kor(int(kovetkezo[11:13]), int(kovetkezo[14:16]))
    else:
        masodik = szamok.ido_iso_szoval(kovetkezo, kor=True)
    sablon = _beszelheto_sablon(nyelv, "visszaigazolas", "ajanlat_ketto")
    return kimenet(sablon.format(elso=elso, masodik=masodik), mod)


def ajanlat_emlekezteto_szoveg(
    jeloltek: list[dict],
    *,
    nyelv: str = _NYELV_ALAPERTELMEZETT,
    mod: str = MOD_SZOVEGES,
    zona: str | None = None,
) -> str:
    """„Az imént ezeket ajánlottam — …. Melyik jó, vagy nézzek mást?"

    A visszakérdezés HELYETT megy ki, ha már állnak ajánlataink
    (ADR-035). Nem új ajánlat: ugyanazokat az időpontokat mondja
    vissza, tehát az „imént" szó pontos állítás.

    Hangon rövidebb: ott nincs képernyő, amire a felsorolás
    visszanézhető lenne, és a „vagy nézzek mást?" a második kérdés
    lenne egy fordulóban (`assistant/valasz/beszelheto.py`)."""
    kezdetek = [helyi_ido.helyi_iso(j["kezdet"], zona) for j in jeloltek if j.get("kezdet")]
    idok = ajanlat_idopontok_szoveg(kezdetek, nyelv=nyelv, mod=mod)
    if _beszelheto_e(mod):
        sablon = _beszelheto_sablon(nyelv, "visszaigazolas", "ajanlat_emlekezteto")
        return kimenet(sablon.format(idok=idok), mod)
    return SABLONOK[nyelv]["visszaigazolas"]["ajanlat_emlekezteto"].format(idok=idok)


def ajanlat_valasz_szoveg(
    valasz: dict,
    *,
    nyelv: str = _NYELV_ALAPERTELMEZETT,
    mod: str = MOD_SZOVEGES,
    zona: str | None = None,
) -> str:
    """Felelet a felajánlott időpontokról szóló kérdésre (ADR-035).

    Nem új ajánlat: ugyanazokból a jelöltekből felel, amiket az imént
    kimondtunk. Ezért kezdődik az „Ezek…" névmással — a vásárló épp
    azokról kérdezett."""
    sablonok = SABLONOK[nyelv]["ajanlat_valasz"]
    mit = valasz.get("mit")

    if mit == ajanlat_kerdes.MIKOR_VAN:
        kezdet = helyi_ido.helyi_iso((valasz.get("jelolt") or {}).get("kezdet", ""), zona)
        if _beszelheto_e(mod):
            idopont = szamok.ido_iso_szoval(kezdet, napnevvel=True)
        else:
            nap = szamok.datum_szoval(kezdet[:10], napnevvel=True)
            idopont = f"{nap}, {szamok.ora_perc_rovid(kezdet)}"
        # A SORSZÁM kimondva szó, írásban szám: „a második időpont"
        # vs. „A 2. időpont". A pont utáni szám felolvasva
        # értelmezhetetlen („a kettő pont időpont").
        sorszam = valasz.get("sorszam") or 1
        sorszam_alak = szamok.sorszam_szoval(sorszam) if _beszelheto_e(mod) else f"{sorszam}."
        return kimenet(sablonok["mikor_van"].format(sorszam=sorszam_alak, idopont=idopont), mod)

    # MELYIK_NAP: a napok, az ajánlat sorrendjében — és ha csak egy nap
    # van, azt mondjuk ki, nem azt, hogy „ezeken a napokon".
    napok = [szamok.datum_szoval(nap, napnevvel=True) for nap in valasz.get("napok") or []]
    if not napok:
        return kimenet(sablonok["nincs_adat"], mod)
    kulcs = "melyik_nap_egy" if len(napok) == 1 else "melyik_nap_tobb"
    return kimenet(sablonok[kulcs].format(napok=_felsorolas(napok, "és")), mod)


def kiut_szoveg(
    dimenziok: list[str],
    *,
    nyelv: str = _NYELV_ALAPERTELMEZETT,
    mod: str = MOD_SZOVEGES,
    bevezetessel: bool = True,
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
        # Dimenzió nélkül (keresés még nem futott) MÁS a mondat: a
        # három dimenzió felsorolása olyat ígérne, amit nem kínálunk.
        kulcs = "bevezetes" if gombok else "bevezetes_bolt"
        return sablonok[kulcs], gombok

    beszelt = SABLONOK[nyelv]["beszelheto"]["kiut"]
    nevek = [beszelt["dimenzio"][d] for d, _ in gombok if d in beszelt["dimenzio"]]
    if not nevek:
        return kimenet(beszelt["bevezetes_bolt"], mod), gombok
    kerdes = beszelt["kerdes"].format(dimenziok=_felsorolas(nevek))
    # `bevezetessel=False`: a hívó MÁR kimondott egy tényt ebben a
    # fordulóban (pl. „ezen a héten nincs időpont"), és hangon két
    # mondat fér bele. Ilyenkor a tény fontosabb, mint a saját
    # bevezetőnk — az csak azt ismételné meg, amit a helyzet úgyis
    # elárul.
    mondat = f"{beszelt['bevezetes']} {kerdes}" if bevezetessel else kerdes
    return kimenet(mondat, mod), gombok


def _felsorolas(elemek: list[str], kotoszo: str = "vagy") -> str:
    """Kimondható felsorolás: `„a, b vagy c"`. Ez NEM az a felsorolás,
    amit a beszélhető mód tilt — a tiltás a felsorolás-JELÖLÉSRE
    (pontok, sortörések) vonatkozik, nem a magyar mondatra.

    A kötőszó azért állítható, mert nem mindegy: a VÁLASZTÁSNÁL („melyik
    boltba?") a „vagy" a helyes, egy EGYÜTT létező halmaznál (a bolt
    pultosai) az „és" — a „Kati vagy Jani fogad" azt ígérné, hogy csak
    az egyikük van ott."""
    if len(elemek) == 1:
        return elemek[0]
    return f"{', '.join(elemek[:-1])} {kotoszo} {elemek[-1]}"


def alternativa_szoveg(
    dimenzio: str | None, *, nyelv: str = _NYELV_ALAPERTELMEZETT, mod: str = MOD_SZOVEGES
) -> tuple[str, str] | None:
    """`(bevezető mondat, gombfelirat)` a felajánlott alternatívához,
    vagy `None`, ha nincs mit felajánlani.

    A `dimenzio` az `assistant/tools/szabad_idopontok.py::
    _alternativ_dimenzio` zárt kimenete (`LAZITAS_DIMENZIOK`) — ez a
    függvény csak megfogalmazza, nem dönt: azt, hogy VAN-e alternatíva,
    a determinisztikus eszköz állapította meg egy tényleges kereséssel.
    A mondat mindig kimondja, MELYIK dimenzióban engedtünk (ADR-024).

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
    hianyzo_mezo: str | None,
    *,
    valasztek: list[str] | None = None,
    nyelv: str = _NYELV_ALAPERTELMEZETT,
    mod: str = MOD_SZOVEGES,
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
        kerdes = kerdes or _beszelheto_sablon(nyelv, "zart_kerdes", "tartalek")
        # HANGON NINCS GOMB (ADR-032): ha van választék, a kérdésnek
        # magának kell felsorolnia — különben a vásárló nem tudja, mi
        # közül választhat. Ez az első idegen próba tanulsága: a
        # „Melyik boltba szeretnél menni?" annak szól, aki ismeri a
        # boltokat.
        if valasztek:
            sablon = _beszelheto_sablon(nyelv, "zart_kerdes", "valasztekkal")
            return kimenet(
                sablon.format(kerdes=kerdes.rstrip("?"), valasztek=_felsorolas(valasztek)), mod
            )
        return kerdes
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
    if "pultosok" in mezok:
        nevek = mezok["pultosok"]
        if not nevek:
            return kimenet(sablonok["pultosok_ures"], mod)
        return kimenet(sablonok["pultosok"].format(nevek=_felsorolas(nevek, "és")), mod)
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


def _ablak_datum_szoveg(
    datum_tol: str, datum_ig: str, napszak: str, zona: str | None = None
) -> str:
    """A felismert ablak dátumrésze, HELYI naptár szerint.

    A `[:10]` vágás önmagában nem elég: egy `23:30Z` kezdetű ablak
    Budapesten már a KÖVETKEZŐ napon kezdődik (`helyi_ido.py`)."""
    nap_resz = _NAPSZAK_SZOVEG.get(napszak, "")
    tol = helyi_ido.helyi_datum(datum_tol, zona)
    ig = helyi_ido.helyi_datum(datum_ig, zona)
    alap = tol if tol == ig else f"{tol} és {ig} között"
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


def modell_figyelmeztetes_szoveg(
    modell_nev: str | None, *, nyelv: str = _NYELV_ALAPERTELMEZETT
) -> str | None:
    """A NINCS MODELL figyelmeztetés, vagy `None`, ha van konfigurált
    modell.

    Külön függvény és külön sor a felületen, nem a `rendszersor_szoveg`
    végén álló zárójeles megjegyzés: azt át lehet siklani, és a
    próbálgató végigcsinál egy egész beszélgetést abban a hitben, hogy
    a modellt méri, holott a tartalék ágat látja. A mondat ezért
    megmondja, mi fut, és mit kell beírni a bekapcsoláshoz.

    **Nem** azt állítja, hogy az Ollama fut-e — azt csak egy tényleges
    hívás derítené ki (`assistant/interpreter/__init__.py::
    aktiv_modell_neve`). Ez a sor a KONFIGURÁCIÓ hiányát jelzi, ami a
    gyakoribb és olcsóbban orvosolható eset; ha a modell be van
    állítva, de nem fut, azt a próba-napló `reteg` mezője
    (`szabaly:tartalek`) és a napló-elemző `csendes_tartalek`
    detektora mutatja meg."""
    if modell_nev:
        return None
    return SABLONOK[nyelv]["rendszersor"]["nincs_modell_figyelmeztetes"]


def indito_ellenorzes_szoveg(
    hiany: str | None, modell_nev: str | None = None, *, nyelv: str = _NYELV_ALAPERTELMEZETT
) -> tuple[str, str, str, str] | None:
    """A modális indítási figyelmeztetés: `(cím, üzenet, folytatás-gomb,
    kilépés-gomb)` — vagy `None`, ha minden rendben, és nincs mit
    mondani.

    A HÁROM ok három külön mondat, mert három külön teendő tartozik
    hozzájuk (nincs beállítva a modell / nem válaszol az Ollama / nincs
    letöltve a modell). Egy összevont „nem működik" üzenet abban a
    pillanatban lenne udvarias, amikor haszontalan.

    A szöveg ITT van és nem a felületen (`ui/vasarlo.py` docstring: „a
    felület sosem fogalmaz"), a döntés pedig a próbálgatóé: a
    tartalékággal FOLYTATNI érvényes választás (pl. amikor épp a
    determinisztikus réteget próbálja) — csak nem lehet véletlen."""
    if hiany is None:
        return None
    sablonok = SABLONOK[nyelv]["rendszersor"]
    kulcs = {
        "nincs_modell": "indito_nincs_modell",
        "nincs_szolgaltatas": "indito_nincs_szolgaltatas",
        "nincs_letoltve": "indito_nincs_letoltve",
    }.get(hiany)
    if kulcs is None:
        return None
    return (
        sablonok["indito_cim"],
        sablonok[kulcs].format(modell=modell_nev or "?"),
        sablonok["indito_folytatom"],
        sablonok["indito_kilepek"],
    )


def hang_allapot_szoveg(
    hianyok, hang_neve: str | None = None, *, nyelv: str = _NYELV_ALAPERTELMEZETT
) -> str:
    """A felületen álló egy sor a hangkimenetről (ADR-029).

    Ha minden megvan, azt is kimondja („Felolvasás: hu_HU-anna-medium")
    — a csendnek ilyenkor MÁS oka van, és ezt tudni kell. Ha hiányzik
    valami, felsorolja, MI: a „nincs hang" önmagában nem teendő."""
    sablonok = SABLONOK[nyelv]["rendszersor"]
    if not hianyok:
        return sablonok["hang_kesz"].format(hang=hang_neve or "kész")
    nevek = {
        "nincs_piper": sablonok["hang_hiany_piper"],
        "nincs_hang": sablonok["hang_hiany_hang"],
        "nincs_lejatszo": sablonok["hang_hiany_lejatszo"],
    }
    felsorolas = ", ".join(nevek.get(h, h) for h in hianyok)
    return sablonok["hang_hianyzik"].format(hianyok=felsorolas)


def bolt_tetel_mondva(
    nev: str, szolgaltatasok: list[dict], *, nyelv: str = _NYELV_ALAPERTELMEZETT
) -> str:
    """Egy bolt KIMONDHATÓ alakja: „a Szundiba altatóért".

    Ugyanaz a tétel kell a köszönéshez, a kínálat-felsoroláshoz és a
    beszélhető zárt kérdéshez — egy helyen, hogy a három ne
    driftelhessen szét. A ragozás a `ragozas.py`-é, a szórend a
    sabloné, a NEVEK az adatbázisé."""
    sablon = SABLONOK[nyelv]["bemutatkozas"]["bolt_tetel"]
    return (
        sablon.format(
            bolt=f"{ragozas.nevelo(nev)} {ragozas.hova(nev)}",
            szolgaltatas=ragozas.ert(szolgaltatasok[0]["nev"]) if szolgaltatasok else "",
        )
    ).strip()


def bemutatkozas_szoveg(
    boltok: list[dict],
    *,
    koszones: bool = False,
    nyelv: str = _NYELV_ALAPERTELMEZETT,
    mod: str = MOD_SZOVEGES,
) -> str:
    """KÖSZÖNÉS és KÍNÁLAT válasza (ADR-032): mi van itt egyáltalán.

    `boltok`: a `kinalat` eszköz kimenete — bolt-slug, NÉV és a
    szolgáltatások (név + rövid leírás). **Minden adat az
    adatbázisból**; ez a függvény csak mondattá fűzi, és ragoz
    (`ragozas.py`).

    Két alak, két helyzet:

    - **röviden** (köszönés, vagy több bolt): „a Szundiba altatóért, az
      Ügyifogyiba petárdáért…" — a listát a vásárló azért kapja, hogy
      VÁLASSZON, nem azért, hogy elolvassa;
    - **részletesen** (EGY bolt): a leírás is elhangzik, mert ott már
      nem választásról van szó, hanem arról, mit kap.
    """
    sablonok = SABLONOK[nyelv]["bemutatkozas"]
    if not boltok:
        return kimenet(SABLONOK[nyelv]["hiba"]["ervenytelen_kereses"], mod)

    if len(boltok) == 1:
        bolt = boltok[0]
        sorok = [
            sablonok["bolt_tetel_reszletes"]
            .format(bolt=bolt["nev"], szolgaltatas=sz["nev"], leiras=sz["leiras"])
            .rstrip(": ")
            for sz in bolt["szolgaltatasok"]
        ]
        return kimenet(" ".join(sorok) if sorok else bolt["nev"], mod)

    tetelek = [
        bolt_tetel_mondva(bolt["nev"], bolt["szolgaltatasok"], nyelv=nyelv) for bolt in boltok
    ]
    kulcs = "koszones" if koszones else "kinalat"
    return kimenet(sablonok[kulcs].format(boltok=", ".join(tetelek)), mod)


def meta_szoveg(*, nyelv: str = _NYELV_ALAPERTELMEZETT, mod: str = MOD_SZOVEGES) -> str:
    """A RENDSZERRŐL szóló kérdés válasza — rövid bemutatkozás
    (kapuőr `META_KERDES`).

    Sablonból jön, mint minden más mondat: a felület nem fogalmaz, és a
    modell meg sem szólal ezen az ágon (a kapuőr a modell előtt dönt).
    Így az, amit a rendszer magáról állít, SZERKESZTETT adat — nem a
    modell aznapi kedve."""
    return kimenet(SABLONOK[nyelv]["meta"]["bemutatkozas"], mod)


def nyugtazo_szoveg(
    felismert_ablak: dict,
    *,
    nyelv: str = _NYELV_ALAPERTELMEZETT,
    veletlen: random.Random | None = None,
    mod: str = MOD_SZOVEGES,
    zona: str | None = None,
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
    szintű `random` sorsol.

    **Beszélhető módban ez a sor is átalakul** — a fej nélküli
    végigjátszás fogta meg, hogy elmarad: „Nézem, mi van a(z) Ügyifogyi
    boltban, 2026-12-21 és 2026-12-28 között…" felolvasva három hibát
    tartalmaz egyszerre (zárójel, két ISO-dátum, rossz névelő). Az, hogy
    ez KÜLÖN megszólalás (a kétlépcsős válasz első lépcsője), nem
    jelenti azt, hogy nem kell beszélhetőnek lennie."""
    beszelt = _beszelheto_e(mod)
    valaszto = veletlen.choice if veletlen is not None else random.choice
    sablonok = SABLONOK[nyelv]["nyugtazo"]

    if not felismert_ablak:
        return kimenet(valaszto(sablonok["altalanos"]), mod)

    reszek = []
    bolt_slug = felismert_ablak.get("bolt_id")
    if bolt_slug:
        bolt_nev = katalogus.BOLT_NEVEK.get(bolt_slug, bolt_slug)
        # Az „a(z)" írásban elfogadott rövidítés, kimondva viszont
        # nem létezik: vagy „a", vagy „az". Beszélhető módban ezért a
        # névelőt a bolt nevének első hangja dönti el.
        nevelo = _hatarozott_nevelo(bolt_nev) if beszelt else "a(z)"
        reszek.append(f"{nevelo} {bolt_nev} boltban")
    datum_tol = felismert_ablak.get("datum_tol")
    datum_ig = felismert_ablak.get("datum_ig")
    if datum_tol and datum_ig:
        reszek.append(
            _ablak_datum_szoveg(
                datum_tol, datum_ig, felismert_ablak.get("napszak", "barmikor"), zona
            )
        )

    if not reszek:
        return kimenet(valaszto(sablonok["altalanos"]), mod)
    sablon = valaszto(sablonok["ablakkal"])
    return kimenet(sablon.format(resz=", ".join(reszek)), mod)


# Magánhangzóval kezdődő szó előtt „az". Ékezetes magánhangzókkal
# együtt — a bolt nevek magyarok (Ügyifogyi).
_MAGANHANGZOK = "aáeéiíoóöőuúüű"


def _hatarozott_nevelo(szo: str) -> str:
    return "az" if szo[:1].lower() in _MAGANHANGZOK else "a"

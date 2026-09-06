"""A BESZÉLHETŐ kimeneti mód tesztjei (`assistant/valasz/beszelheto.py`,
`assistant/valasz/szamok.py`, M6 hang-előkészítés).

Két rétegben mérünk, és a második a fontosabb:

1. **Egyedi szabályok** — számkimondás, dátum, betűzés, mondathatár.
2. **A TELJES kimenet formai vizsgálata**: MINDEN beszélhető mondat,
   amit a `valasz` modul elő tud állítani, átmegy ugyanazon a záró
   ellenőrzésen (`beszelheto.szabalyos`). Ez az, ami egy jövőbeli, ide
   nem gondolt sablont is elkap — a hangcsatornán a hiba nem
   „csúnyán néz ki", hanem felolvasva értelmetlen.
"""

from __future__ import annotations

import pytest

from assistant import valasz
from assistant.tools import szabad_idopontok
from assistant.valasz import beszelheto, szamok
from assistant.valasz.sablonok import SABLONOK

BESZELHETO = valasz.MOD_BESZELHETO
SZOVEGES = valasz.MOD_SZOVEGES

# Egy tipikus ajánlat: két időpont ugyanazon a napon, egy harmadik
# másnap — épp az a felállás, ahol a felolvasott felsorolás elesne.
JELOLTEK = [
    {"slot_id": "a", "kezdet": "2026-12-22T08:00:00Z", "veg": "2026-12-22T08:30:00Z"},
    {"slot_id": "b", "kezdet": "2026-12-22T09:30:00Z", "veg": "2026-12-22T10:00:00Z"},
    {"slot_id": "c", "kezdet": "2026-12-23T11:00:00Z", "veg": "2026-12-23T11:30:00Z"},
]


# =====================================================================
# 1. SZÁMOK KIMONDVA
# =====================================================================


@pytest.mark.parametrize(
    ("szam", "varhato"),
    [
        (0, "nulla"),
        (1, "egy"),
        (2, "kettő"),
        (8, "nyolc"),
        (10, "tíz"),
        (11, "tizenegy"),
        (15, "tizenöt"),
        (20, "húsz"),
        (22, "huszonkettő"),
        (30, "harminc"),
        (45, "negyvenöt"),
        (80, "nyolcvan"),
        (99, "kilencvenkilenc"),
        (100, "száz"),
        (200, "kétszáz"),
        (365, "háromszázhatvanöt"),
        (1000, "ezer"),
        (2026, "kétezer huszonhat"),
    ],
)
def test_szam_szoval(szam: int, varhato: str) -> None:
    assert szamok.szam_szoval(szam) == varhato


def test_a_ketto_onalloan_hosszu_alak_osszetetelben_rovid() -> None:
    """A „kettő" és a „hét" félrehallása a leggyakoribb magyar telefonos
    hiba — önállóan ezért mindig a hosszú alak megy ki. Összetételben
    viszont a „két" a helyes („kétszáz"), és ott nincs félrehallási
    kockázat, mert a szám nem áll magában."""
    assert szamok.szam_szoval(2) == "kettő"
    assert szamok.szam_szoval(200) == "kétszáz"
    assert szamok.szam_szoval(2000) == "kétezer"


def test_tartomanyon_kivuli_szam_hangosan_elszall() -> None:
    """A némán rossz kimenet rosszabb, mint a hangos hiba: egy
    csonkolt szám felolvasva helyesnek HANGZANA."""
    with pytest.raises(ValueError):
        szamok.szam_szoval(szamok.MAX_SZAM + 1)
    with pytest.raises(ValueError):
        szamok.szam_szoval(-1)


def test_datum_es_ora_kimondva() -> None:
    assert szamok.datum_szoval("2026-12-22") == "december huszonkettedikén"
    assert szamok.ora_perc_szoval(8, 15) == "nyolc óra tizenöt"
    assert szamok.ora_perc_szoval(8, 0) == "nyolc óra"
    assert szamok.idopont_kor(8, 0) == "nyolc órakor"
    assert szamok.idopont_kor(9, 30) == "kilenc harminckor"
    assert szamok.ido_iso_szoval("2026-12-22T08:00:00Z") == "december huszonkettedikén nyolc órakor"


def test_a_kod_betuzve_hangzik_el_nem_szamkent() -> None:
    """A `28SFL8RZ`-t „huszonnyolc"-ként kimondani használhatatlanná
    teszi azt, amiért a kód egyáltalán van: hogy a vásárló le tudja
    írni."""
    assert szamok.betuzve("28SFL8RZ") == "kettő nyolc es ef el nyolc er zé"


# =====================================================================
# 2. A KIMENETI KAPU
# =====================================================================


def test_iso_idobelyeg_teljes_alakja_feloldodik() -> None:
    assert (
        beszelheto.beszelhetove("A foglalás 2026-12-22T08:00:00Z időpontra szól.")
        == "A foglalás december huszonkettedikén nyolc órakor időpontra szól."
    )


def test_idotartomany_ragozott_alakot_kap() -> None:
    assert beszelheto.beszelhetove("08:00-08:30") == "Nyolc órától nyolc óra harmincig"
    assert "nyolc órától tizenhat óraig" in beszelheto.beszelhetove("Nyitva: 8:00-16:00")


def test_zarojeles_resz_eldobodik() -> None:
    """A zárójel definíció szerint mellékes megjegyzés — hangon pedig a
    mellékes megjegyzés a legdrágább."""
    assert beszelheto.beszelhetove("Nyitva vagyunk (a hátsó bejáraton).") == "Nyitva vagyunk."


def test_felsorolas_es_markdown_eltunik() -> None:
    szoveg = beszelheto.beszelhetove("- első pont\n- **második** pont")
    assert "-" not in szoveg
    assert "*" not in szoveg


def test_nagy_kezdobetu_behelyettesites_utan_is() -> None:
    """A beszélhető mondatok jó része behelyettesítéssel kezdődik, és a
    kimondott dátum kisbetűs."""
    assert valasz.megerosites_ker_szoveg("2026-12-22T08:00:00Z", mod=BESZELHETO).startswith("Dec")


# =====================================================================
# 3. FORDULÓNKÉNTI SZABÁLYOK: két mondat, egy kérdés
# =====================================================================


def test_fordulonkent_legfeljebb_ket_mondat() -> None:
    szoveg = beszelheto.fordulo_szoveg(
        ["Egy pillanat, nézem.", "Találtam időpontokat.", "A legkorábbi nyolc órakor van."]
    )
    assert len(beszelheto.mondatok(szoveg)) <= beszelheto.MAX_MONDAT


def test_fordulonkent_egy_kerdes_es_az_utolso() -> None:
    """Két kérdésre a vásárló az egyikre felel, és nem tudjuk, melyikre.
    Az UTOLSÓ marad, mert a beszélgetés ott tart."""
    szoveg = beszelheto.fordulo_szoveg(
        ["Melyik boltba szeretnél menni?", "Találtam időpontot.", "Melyik jó?"]
    )
    assert szoveg.count("?") == 1
    assert szoveg.endswith("Melyik jó?")
    # Az állítás a kérdés ELÉ kerül — az hordozza a tényt.
    assert szoveg.startswith("Találtam időpontot.")


def test_a_kerdes_akkor_is_a_vegen_all_ha_nem_o_volt_az_utolso_sor() -> None:
    szoveg = beszelheto.fordulo_szoveg(["Melyik jó?", "Ezeket találtam."])
    assert szoveg.endswith("?")


# =====================================================================
# 4. AJÁNLAT — nincs felsorolás
# =====================================================================


def test_ajanlat_beszelhetoen_ket_idopontot_mond_nem_tobbet() -> None:
    """Három felolvasott időpont megjegyezhetetlen. A többi jelölt nem
    vész el: a képernyőn ott marad, és a következő fordulóban kérhető."""
    szoveg = valasz.ajanlat_mondat(JELOLTEK, mod=BESZELHETO)
    assert szoveg == (
        "A legkorábbi december huszonkettedikén nyolc órakor, "
        "de van kilenc harminckor is. Melyik jó?"
    )
    assert "tizenegy" not in szoveg


def test_ajanlat_azonos_napon_nem_ismetli_a_datumot() -> None:
    szoveg = valasz.ajanlat_mondat(JELOLTEK, mod=BESZELHETO)
    assert szoveg.count("december") == 1


def test_ajanlat_kulonbozo_napon_kimondja_a_masodik_datumot_is() -> None:
    szoveg = valasz.ajanlat_mondat([JELOLTEK[0], JELOLTEK[2]], mod=BESZELHETO)
    assert "december huszonharmadikán" in szoveg


def test_ajanlat_nem_mondja_ketszer_ugyanazt_az_orat() -> None:
    """A FEJ NÉLKÜLI VÉGIGJÁTSZÁS találta: a pontozó egy időpontra több
    jelöltet is adhat (különböző hosszúságú szolgáltatásokra), és a
    mondat ettől „a legkorábbi hét órakor, de van hét órakor is" lett.
    Írásban ez a gombokon nem tűnt fel, mert ott a hossz
    megkülönbözteti őket — kimondva viszont értelmetlen."""
    azonos_ora = [
        {"kezdet": "2026-12-21T07:00:00Z", "veg": "2026-12-21T07:10:00Z"},
        {"kezdet": "2026-12-21T07:00:00Z", "veg": "2026-12-21T07:20:00Z"},
    ]
    szoveg = valasz.ajanlat_mondat(azonos_ora, mod=BESZELHETO)
    assert szoveg.count("hét órakor") == 1
    assert "de van" not in szoveg

    # …de ha VAN eltérő időpont, az megy ki másodikként, akkor is, ha
    # nem közvetlenül a második helyen áll.
    vegyes = [*azonos_ora, {"kezdet": "2026-12-21T09:30:00Z", "veg": "2026-12-21T10:00:00Z"}]
    assert "kilenc harminckor" in valasz.ajanlat_mondat(vegyes, mod=BESZELHETO)


def test_a_nyugtazo_sor_is_beszelheto() -> None:
    """Szintén a végigjátszás találata: a nyugtázó sor KÜLÖN
    megszólalás (a kétlépcsős válasz első lépcsője), de attól még
    beszélhetőnek kell lennie. A szöveges alakban egyszerre volt
    zárójel, két ISO-dátum és rossz névelő."""
    ablak = {
        "bolt_id": "ugyifogyi",
        "datum_tol": "2026-12-21T00:00:00Z",
        "datum_ig": "2026-12-28T23:59:59Z",
        "napszak": "barmikor",
    }
    szoveg = valasz.nyugtazo_szoveg(ablak, mod=BESZELHETO)
    assert beszelheto.tiltott_jelek(szoveg) == [], szoveg
    # „a(z) Ügyifogyi" helyett „az Ügyifogyi" — az „a(z)" kimondva nem
    # létezik.
    assert "az Ügyifogyi" in szoveg
    assert "a Törpilla" in valasz.nyugtazo_szoveg({"bolt_id": "torpilla"}, mod=BESZELHETO)


def test_ajanlat_szovegesen_is_KIMONDJA_az_idopontokat() -> None:
    """A szöveges mondat 2026-09-20-ig csak BEVEZETTE a gombokat
    („Ezeket az időpontokat találtam — melyik jó?"), és az időpont
    kizárólag gombfeliratként létezett.

    **Egy gombfelirat nem része a beszélgetésnek**: nem olvasható
    vissza, nem kerül az előzménybe, és aki felolvastatja a képernyőt,
    annak egyszerűen nincs ott. A gombok megmaradtak — a mondat nem
    helyettük szól, hanem mellettük."""
    szoveg = valasz.ajanlat_mondat(JELOLTEK, mod=SZOVEGES)

    for jelolt in JELOLTEK:
        ora = int(jelolt["kezdet"][11:13])
        perc = int(jelolt["kezdet"][14:16])
        assert f"{ora}:{perc:02d}" in szoveg, szoveg
    assert szoveg.endswith("?"), "választani kell — tehát kérdés"


def test_ajanlat_szovegesen_az_AZONOS_kezdet_egyszer_hangzik_el() -> None:
    """A pontozó egy időpontra több jelöltet is adhat (más hosszúságú
    szolgáltatásokra). A gombokon a HOSSZ megkülönbözteti őket, a
    mondatban nem — „8:00, 8:00 vagy 8:20" lenne belőle."""
    ketto = [
        {"kezdet": "2026-12-22T08:00:00Z", "veg": "2026-12-22T08:10:00Z"},
        {"kezdet": "2026-12-22T08:00:00Z", "veg": "2026-12-22T08:20:00Z"},
    ]
    assert valasz.ajanlat_mondat(ketto, mod=SZOVEGES).count("8:00") == 1


def test_ajanlat_ures_jeloltlistara_a_regi_bevezeto() -> None:
    """Nincs mit felsorolni — de a mondat nem maradhat el."""
    assert valasz.ajanlat_mondat([], mod=SZOVEGES) == valasz.ajanlat_bevezetes_szoveg()


def test_legkozelebbi_idopont_egy_mondatban() -> None:
    szoveg = valasz.ajanlat_mondat(JELOLTEK[:1], legkozelebbi=True, mod=BESZELHETO)
    assert szoveg.startswith("A legkorábbi szabad időpont")
    assert szoveg.endswith("?")


# =====================================================================
# 5. A KÉT MÓD VISZONYA
# =====================================================================


def test_a_ket_mod_ugyanazt_a_TENYT_mondja() -> None:
    """A mód nem stílusváltás: a foglalási kód mindkét módban ugyanaz,
    csak az egyikben betűzve."""
    szoveges = valasz.sikeres_foglalas_szoveg("28SFL8RZ", mod=SZOVEGES)
    beszelt = valasz.sikeres_foglalas_szoveg("28SFL8RZ", mod=BESZELHETO)
    assert "28SFL8RZ" in szoveges
    assert szamok.betuzve("28SFL8RZ") in beszelt


def test_a_szoveges_mod_valtozatlan() -> None:
    """Regressziós védőháló: a mai viselkedésnek egyetlen karaktere sem
    változhatott — a beszélhető mód HOZZÁADÁS, nem átalakítás."""
    assert valasz.hiba_szoveg("ar_nem_adhato") == SABLONOK["hu"]["hiba"]["ar_nem_adhato"]
    assert valasz.visszakerdezes_szoveg("bolt_id") == (
        "Ehhez még kellene tudnom: melyik boltba szeretnél menni."
    )
    assert valasz.megerosites_ker_szoveg() == "Biztosan lefoglaljam ezt az időpontot?"


def test_ismeretlen_mod_hangosan_elszall() -> None:
    with pytest.raises(ValueError):
        valasz.hiba_szoveg("ar_nem_adhato", mod="sugdos")


# =====================================================================
# 6. A ZÁRÓ FORMAI ELLENŐRZÉS — MINDEN kimeneten
# =====================================================================


def _minden_beszelheto_mondat() -> list[tuple[str, str]]:
    """`(honnan, mondat)` — minden vásárlói mondat, amit a `valasz`
    modul beszélhető módban elő tud állítani.

    A hibakulcsok a TELJES sablonkészletből jönnek, nem egy kézzel
    válogatott mintából: épp az a kérdés, hogy egy ide nem gondolt
    sablon is átmegy-e a szabályokon."""
    darabok: list[tuple[str, str]] = []
    for kulcs in SABLONOK["hu"]["hiba"]:
        darabok.append((f"hiba:{kulcs}", valasz.hiba_szoveg(kulcs, mod=BESZELHETO)))
    for mezo in [*SABLONOK["hu"]["zart_kerdes"]["mezo_neve"], None, "ismeretlen_mezo"]:
        darabok.append(
            (f"visszakerdezes:{mezo}", valasz.visszakerdezes_szoveg(mezo, mod=BESZELHETO))
        )
    darabok += [
        ("megerosites", valasz.megerosites_ker_szoveg(mod=BESZELHETO)),
        (
            "megerosites_idoponttal",
            valasz.megerosites_ker_szoveg("2026-12-22T08:00:00Z", mod=BESZELHETO),
        ),
        ("foglalas", valasz.sikeres_foglalas_szoveg("28SFL8RZ", mod=BESZELHETO)),
        ("elvetve", valasz.elvetve_szoveg(mod=BESZELHETO)),
        ("ajanlat_1", valasz.ajanlat_mondat(JELOLTEK[:1], mod=BESZELHETO)),
        ("ajanlat_3", valasz.ajanlat_mondat(JELOLTEK, mod=BESZELHETO)),
        ("ajanlat_0", valasz.ajanlat_mondat([], mod=BESZELHETO)),
        (
            "legkozelebbi",
            valasz.ajanlat_mondat(JELOLTEK[:1], legkozelebbi=True, mod=BESZELHETO),
        ),
        ("kiut", valasz.kiut_szoveg(["bolt", "het", "napszak"], mod=BESZELHETO)[0]),
        ("kiut_egy", valasz.kiut_szoveg(["het"], mod=BESZELHETO)[0]),
        ("kiut_ures", valasz.kiut_szoveg([], mod=BESZELHETO)[0]),
        (
            "tenyvalasz_nyitvatartas",
            valasz.tenyvalasz_szoveg(
                {"sikeres": True, "nyitvatartas": "H-P 8:00-16:00"}, mod=BESZELHETO
            ),
        ),
        (
            "tenyvalasz_cim",
            valasz.tenyvalasz_szoveg(
                {"sikeres": True, "cim": "Fő utca 12. (a templom mellett)"}, mod=BESZELHETO
            ),
        ),
        (
            "tenyvalasz_szolgaltatasok",
            valasz.tenyvalasz_szoveg(
                {
                    "sikeres": True,
                    "szolgaltatasok": [
                        {"nev": "petárda", "idotartam_perc": 30, "termekleiras": "nagy durranás"},
                        {"nev": "csillagszóró", "idotartam_perc": 15},
                    ],
                },
                mod=BESZELHETO,
            ),
        ),
        (
            "tenyvalasz_ismeretlen",
            valasz.tenyvalasz_szoveg({"sikeres": True, "valami_uj": "x"}, mod=BESZELHETO),
        ),
    ]
    # A zárt halmazból, nem kézzel felsorolva: ha új lazítási dimenzió
    # kerül be, a beszélhetőség-ellenőrzés magától kiterjed rá.
    for dimenzio in szabad_idopontok.LAZITAS_DIMENZIOK:
        darabok.append(
            (f"alternativa:{dimenzio}", valasz.alternativa_szoveg(dimenzio, mod=BESZELHETO)[0])
        )
    return darabok


@pytest.mark.parametrize(("honnan", "mondat"), _minden_beszelheto_mondat())
def test_minden_beszelheto_mondat_szabalyos(honnan: str, mondat: str) -> None:
    """A feladat négy formai tilalma: **számjegy, kötőjel, zárójel,
    felsorolásjel** — plusz a két mondat és az egy kérdés."""
    assert beszelheto.tiltott_jelek(mondat) == [], f"{honnan}: {mondat!r}"
    assert len(beszelheto.mondatok(mondat)) <= beszelheto.MAX_MONDAT, f"{honnan}: {mondat!r}"
    assert mondat.count("?") <= 1, f"{honnan}: {mondat!r}"
    assert beszelheto.szabalyos(mondat), f"{honnan}: {mondat!r}"


def test_a_tiltott_jelek_valoban_fognak() -> None:
    """Ha ez a vizsgálat elromlik, az összes fenti teszt NÉMÁN zöld
    lenne — ezért méri külön, hogy a detektor egyáltalán megszólal."""
    assert "számjegy" in beszelheto.tiltott_jelek("8 órakor")
    assert "kötőjel vagy gondolatjel" in beszelheto.tiltott_jelek("nyolc-kilenc")
    assert "zárójel" in beszelheto.tiltott_jelek("nyolc órakor (délelőtt)")
    assert "felsorolásjel" in beszelheto.tiltott_jelek("• nyolc órakor")
    assert beszelheto.tiltott_jelek("Nyolc órakor van szabad időpont.") == []


def test_a_szabalyossag_a_mondatszamot_es_a_kerdest_is_meri() -> None:
    assert not beszelheto.szabalyos("Egy. Kettő. Három.")
    assert not beszelheto.szabalyos("Melyik bolt? Melyik nap?")
    assert beszelheto.szabalyos("Találtam időpontot. Melyik jó?")


# =====================================================================
# 7. A KIÚT nem nyelheti el a tényt
# =====================================================================


def test_kiut_bevezeto_nelkul_ha_mar_elhangzott_a_teny() -> None:
    """A VÉGIGJÁTSZÁS találata: a vásárló megadott egy új napot, a
    keresés megint üres lett, és a rendszer egyből azt mondta, hogy „így
    nem jutunk előre" — a vásárló meg sem tudta, hogy a jövő héten sincs
    időpont.

    A tény a kiút ELÉ kerül; hangon viszont két mondat fér bele, tehát
    ilyenkor a kiút SAJÁT bevezetője marad ki. Az csak azt ismételné
    meg, amit a helyzet úgyis elárul."""
    teljes, _ = valasz.kiut_szoveg(["bolt", "nap", "napszak"], mod=BESZELHETO)
    csak_kerdes, _ = valasz.kiut_szoveg(
        ["bolt", "nap", "napszak"], mod=BESZELHETO, bevezetessel=False
    )

    assert teljes.startswith("Úgy látom")
    assert not csak_kerdes.startswith("Úgy látom")
    assert csak_kerdes.endswith("?")

    # A kettő EGYÜTT a tény mondatával: pontosan két mondat, egy kérdés.
    fordulo = beszelheto.fordulo_szoveg(
        [valasz.hiba_szoveg("nincs_meghirdetett_idopont", mod=BESZELHETO), csak_kerdes]
    )
    assert "nem hirdetett meg időpontokat" in fordulo
    assert fordulo.endswith("?")
    assert beszelheto.szabalyos(fordulo)

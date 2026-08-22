"""A magyar mondatsablonok, nyelvkulcs alatt (blueprint 13. szakasz,
"Menekülőút-doktrína", platform-varratok: "sablonok fájlban, nyelvkulccsal").

Ez a fájl **csak adat** — string sablonok és a hozzájuk tartozó egyszerű
lookup-táblák, semmi döntési logika. A behelyettesítést és a
kategóriánkénti választást az `assistant/valasz/__init__.py` végzi.

Öt kategória (a feladat szerint):

- `hiba`            — hibaüzenetek, `uzenet_kulcs` → mondat
- `visszaigazolas`  — a folyamat lezárását/megerősítését kérő/jelző mondatok
- `zart_kerdes`     — visszakérdezés-mondatok (a hiányzó mezőre kérdeznek)
- `tenyvalasz`      — a `bolt_info` sikeres válaszának mondattá alakítása
- `nyugtazo`        — a hangcsatorna töltelékmondatai (blueprint 7. szakasz,
                       "Kétlépcsős válasz") — TÖBB változat soronként,
                       véletlenszerű választással, hogy hangcsatornán ne
                       tűnjön fel az ismétlődés

Új nyelv hozzáadása = egy új kulcs a `SABLONOK` szótár tetején, ugyanezekkel
az alkategóriákkal — a hívó kód (`assistant/valasz/__init__.py`) nem
nyelvspecifikus."""

from __future__ import annotations

SABLONOK: dict[str, dict[str, object]] = {
    "hu": {
        # ------------------------------------------------------------
        # hiba — uzenet_kulcs -> mondat. Ugyanazok a kulcsok, amiket az
        # `assistant/tools/hiba.py::hiba_eredmeny()` ad vissza, plusz az
        # orchestrator saját belső hibakulcsai (pl.
        # "nincs_folyamatban_levo_valasztas").
        # ------------------------------------------------------------
        "hiba": {
            "nem_foglalasi_kerdes": (
                "Ez a kérdés nem foglalással kapcsolatos, ebben nem tudok segíteni."
            ),
            "nincs_szabad_hely_az_ablakban": "Sajnos nincs szabad időpont ebben az ablakban.",
            "jeloltek_kozben_elfogytak": (
                "Éppen lefoglalták előlünk ezeket az időpontokat — próbáld újra."
            ),
            "ismeretlen_bolt": "Ezt a boltot nem ismerem.",
            "ismeretlen_szolgaltatas": "Ezt a szolgáltatást nem ismerem ebben a boltban.",
            "ervenytelen_kereses": "Ezt a kérést nem tudtam értelmezni.",
            "slot_elfogyott": "Sajnos közben elfogyott ez az időpont.",
            "nincs_ilyen_slot": "Ez az időpont már nem érvényes — keress újat.",
            "ervenytelen_foglalasi_kod": "Nem találtam ilyen foglalási kódot.",
            "mar_lemondott_foglalas": "Ez a foglalás már le van mondva.",
            "uj_slot_elfogyott": "Az új időpontot közben elfoglalták.",
            "nem_ajanlott_jelolt": "Ez az időpont már nem szerepel az ajánlatban.",
            "nincs_folyamatban_levo_valasztas": "Előbb válassz egy időpontot.",
            "ervenytelen_kod": "Nem találtam ilyen foglalási kódot.",
            "nincs_ilyen_foglalas": "Nem találtam ilyen foglalási kódot.",
            "mar_lemondva": "Ez a foglalás már le van mondva.",
            "megeloztek": "Éppen lefoglalták előlünk ezt az időpontot — próbáld újra.",
            "nincs_szabad_hely": "Sajnos nincs szabad időpont ebben az ablakban.",
            "tul_sok_keres": "Túl sok kérést küldtél röviden — kérlek, várj egy kicsit.",
            "hianyzo_bolt_es_nap": "Válassz boltot és napot.",
            "hianyzo_azonosito_bevitel": "Add meg az azonosítót a foglaláshoz.",
            "ismeretlen_valasz": "Nem értettem, próbáld másképp megfogalmazni.",
        },
        # ------------------------------------------------------------
        # visszaigazolas — a folyamat egy lépésének lezárását/kérését
        # jelző mondatok. `{mezo}`-stílusú helyek a behelyettesítendő
        # tényadatnak (pl. a foglalási kód) — ezt sosem a sablon adja,
        # csak a hívó (lásd modul docstring: "a sablon soha nem generál
        # tényt, csak behelyettesít").
        # ------------------------------------------------------------
        "visszaigazolas": {
            "megerosites_ker": "Biztosan lefoglaljam ezt az időpontot?",
            "sikeres_foglalas": "Foglalás létrejött! Foglalási kód: {foglalasi_kod}",
            "elvetve": "Rendben, nem foglaltuk le. Kereshetsz újra.",
            "ajanlat_bevezetes": "Ezeket az időpontokat találtam — melyik jó?",
        },
        # ------------------------------------------------------------
        # zart_kerdes — a visszakérdezés mondata. `mezo_neve` a
        # `hianyzo_mezo` (eszkoz-szerzodes skill mezőnevei) -> emberi
        # megfogalmazás leképezés; ismeretlen mezőnél a nyers mezőnév a
        # tartalék (nem hiba, csak kevésbé folyékony).
        # ------------------------------------------------------------
        "zart_kerdes": {
            "bevezetes": "Ehhez még kellene tudnom: {mezo_szoveg}.",
            "mezo_neve": {
                "bolt_id": "melyik boltba szeretnél menni",
                "szolgaltatas_id": "melyik szolgáltatást szeretnéd",
                "foglalasi_kod": "mi a foglalási kódod",
                "datum_tol": "mikorra szeretnél időpontot",
                "uj_datum": "melyik napra tennéd át",
            },
        },
        # ------------------------------------------------------------
        # tenyvalasz — a `bolt_info` sikeres válaszának olvasható
        # mondattá fogalmazása. A tényt maga az eszköz kereste ki egy
        # szerkesztett mezőből (docs/blueprint.md 10. szakasz, "Bolti
        # tudás") — ez a kategória csak megfogalmazza, sosem generál.
        # ------------------------------------------------------------
        "tenyvalasz": {
            "nyitvatartas": "Nyitvatartás: {ertek}",
            "cim": "Cím: {ertek}",
            "ismeretlen_ertek": "ezt még nem adtuk meg",
            "megjelenes_ures": "Erről még nincs leírásunk.",
            "szolgaltatasok_ures": "Erről nincs adatunk.",
        },
        # ------------------------------------------------------------
        # nyugtazo — a hangcsatorna töltelékmondatai (blueprint 7.
        # szakasz, "Kétlépcsős válasz"). TÖBB változat soronként — a
        # `__init__.py::nyugtazo_szoveg()` `random.choice()`-csal választ
        # közülük, hogy szöveges naplóban átfutva vagy hangban egymás
        # után hallva ne legyen feltűnő az ismétlődés.
        # ------------------------------------------------------------
        "nyugtazo": {
            "altalanos": [
                "Egy pillanat, nézem…",
                "Mindjárt megmondom…",
                "Egy pillanat…",
                "Máris nézem…",
            ],
            "ablakkal": [
                "Nézem, mi van {resz}…",
                "Mindjárt megmondom, mi van {resz}…",
                "Egy pillanat, körülnézek {resz}…",
                "Máris nézem, mi van {resz}…",
            ],
        },
    }
}

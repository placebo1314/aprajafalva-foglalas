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
- `beszelheto`      — a BESZÉLHETŐ kimeneti mód felülíró változatai, a fenti
                       kategóriák szerint tagolva (`assistant/valasz/
                       beszelheto.py`). Csak az van benne, ami hangon
                       MÁSKÉNT hangzik jól — a formázást (szám, zárójel,
                       gondolatjel) a kimeneti kapu intézi, nem a sablon.

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
            # A KAPUŐR három elhárító mondata (ADR-020,
            # `assistant/orchestrator.py::_ELUTASITAS_UZENET`). Mind a
            # három megmondja, MIRE tudunk válaszolni — az elhárítás
            # attól udvarias, hogy kiutat is ad (blueprint 7. szakasz,
            # "Négy technika"), nem attól, hogy szépen fogalmaz.
            "nem_foglalasi_kerdes": (
                "Ez a kérdés nem foglalással kapcsolatos, ebben nem tudok segíteni. "
                "Időpontot viszont szívesen keresek — melyik boltba és mikorra szeretnél?"
            ),
            # Üres, zajos vagy értelmezhetetlen bemenet. Itt a vásárló
            # nem kérdezett rosszat — nem kérdezett SEMMIT. A "nem
            # foglalással kapcsolatos" mondat erre értelmetlen volna.
            "ertelmezhetetlen_bemenet": (
                "Ezt nem sikerült értelmeznem. Mondd meg, melyik boltba szeretnél "
                "menni és körülbelül mikor — a többit elintézem."
            ),
            # Ár. Kimondjuk, hogy MIÉRT nem válaszolunk (nem "nem
            # tudom" — nem is szabad), és hogy hol lehet megtudni.
            # Konkrét árat ez a mondat sem tartalmaz, és nem is
            # tartalmazhat: az ár nem engedélyezett tényválasz ezen a
            # csatornán (blueprint 10.).
            "ar_nem_adhato": (
                "Az árakról itt nem tudok tájékoztatást adni — azt a boltban mondják meg. "
                "Időpontot viszont szívesen keresek."
            ),
            "nincs_szabad_hely_az_ablakban": "Sajnos nincs szabad időpont ebben az ablakban.",
            # NEM szűkösség — a bolt nem hirdetett meg beosztást. Ezt
            # tévesen "megtelt"-ként fogalmazni félrevezetés lenne
            # (blueprint 7. szakasz, "Szűkösség jelzése").
            "nincs_meghirdetett_idopont": (
                "Erre az időszakra a bolt még nem hirdetett meg időpontokat — "
                "ez nem azt jelenti, hogy megtelt. Próbáld később, vagy nézz meg másik boltot."
            ),
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
            "nincs_korabbi_kereses": "Előbb keress időpontot, utána tudok alternatívát mutatni.",
            # A kiút saját, bővebb megfogalmazása a `kiut` kategóriában
            # van (gombokkal együtt) — ez a tartalék, ha a hívó csak a
            # hibakulcsot tudja megjeleníteni.
            "ismetlodo_valasz_kiut": "Úgy látom, itt körbe-körbe járunk — próbáljuk másképp.",
            # Frusztráció-felismerés MÁSODIK kiútja (a vásárló 8.
            # igénye: "legyen kiút emberhez vagy sorbanálláshoz").
            # Nem ígér visszahívást és nem kér elérhetőséget — olyat
            # nem ígérhetünk, amit a rendszer nem tud teljesíteni
            # (ADR-012: értesítés előáll, de nem megy ki).
            "emberhez_iranyitas": (
                "Úgy látom, ez így nem vezet sehova — ne kínlódj vele tovább. "
                "A boltban élőben is fel tudnak venni időpontot, és a koppintós "
                "úton (a másik fülön) is végig lehet menni pár kattintással."
            ),
            "ervenytelen_alternativa": "Ezt az alternatívát most nem tudom megmutatni.",
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
            # A `legkozelebbi_idopont` eszköz válasza: EGY időpont,
            # a feltett kérdésre adott közvetlen felelet. Külön
            # mondat, mert a "melyik jó?" itt félrevezető lenne —
            # nincs miből választani, és nem is kértek választékot.
            "ajanlat_bevezetes_legkozelebbi": "A legkorábbi szabad időpont:",
        },
        # ------------------------------------------------------------
        # alternativa — "ha nincs hely, alternatíva jöjjön" (blueprint
        # 1. szakasz, a vásárló 5. igénye). A `dimenzio` kulcs az
        # `assistant/tools/szabad_idopontok.py::_alternativ_dimenzio`
        # zárt kimenete: napszak | nap | het. A `gomb_*` a felületnek
        # szóló, koppintható felajánlás felirata — nem a modell
        # fogalmazza, sablon.
        # ------------------------------------------------------------
        # ------------------------------------------------------------
        # kiut — ha ugyanaz a válasz harmadszor jönne ki, nem ismételjük
        # meg: más mondat, és zárt, koppintható választás. A `dimenzio`
        # kulcsai az `assistant/orchestrator.py::_KIUT_DIMENZIOK` zárt
        # halmaza.
        # ------------------------------------------------------------
        # kiut — ZÁRT kérdés, a gombokkal SZÓ SZERINT egyező
        # lehetőségekkel (blueprint 7., "Négy technika" 2. pont:
        # "két sikertelen értelmezés után ne nyitottan kérdezzen újra").
        #
        # A korábbi mondat („Min tudsz lazítani?") két hibát vétett
        # egyszerre: NYITOTT kérdés volt (bármit lehetett rá válaszolni,
        # tehát ugyanoda vezetett, ahonnan jöttünk), és TECHNIKAI
        # (a „lazítás" a mi szavunk a keresési ablakra, nem a
        # vásárlóé). A mai alak megnevezi a három választható dolgot,
        # ugyanazokkal a szavakkal, amik a gombokon állnak.
        "kiut": {
            "bevezetes": (
                "Úgy látom, így nem jutunk előre. Melyiket próbáljuk: "
                "másik napot, másik napszakot vagy a legkorábbi szabad időpontot?"
            ),
            "dimenzio": {
                "nap": "Másik nap",
                "napszak": "Másik napszak",
                "legkorabbi": "A legkorábbi szabad időpont",
            },
        },
        # A kulcsok a `szabad_idopontok.LAZITAS_DIMENZIOK` zárt halmaza
        # — bolton BELÜLI dimenziók (ADR-024). **Mindegyik mondat
        # kimondja, MELYIK dimenzióban engedtünk**: az "van egy másik
        # időpont" önmagában nem válasz, mert a vásárló nem tudja,
        # mit adott fel érte.
        "alternativa": {
            "bevezetes": {
                "napszak": "Ebben a napszakban nincs, de aznap más napszakban van szabad időpont.",
                "nap": "Ezen a napon nincs, de a héten másik napon van szabad időpont.",
                "kesobb": "Ebben az időszakban nincs, de később van szabad időpont.",
                "varians": "Erre a változatra nincs, de a boltban másikra van szabad időpont.",
            },
            "gomb": {
                "napszak": "Mutasd az aznapi többi időpontot",
                "nap": "Mutasd a hét többi napját",
                "kesobb": "Mutasd a legkorábbi szabad időpontot",
                "varians": "Mutasd a többi változatot",
            },
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
            # PULTOSOK — a vásárló 2. igénye ("tudjam, kihez megyek").
            # Csak NEVEK: hogy melyikük mikor dolgozik, az munkavállalói
            # adat, és nem is a kérdés.
            "pultosok": "A pultnál ők fogadnak: {nevek}.",
            "pultosok_ures": "Erről nincs adatunk.",
        },
        # ------------------------------------------------------------
        # nyugtazo — a hangcsatorna töltelékmondatai (blueprint 7.
        # szakasz, "Kétlépcsős válasz"). TÖBB változat soronként — a
        # `__init__.py::nyugtazo_szoveg()` `random.choice()`-csal választ
        # közülük, hogy szöveges naplóban átfutva vagy hangban egymás
        # után hallva ne legyen feltűnő az ismétlődés.
        # ------------------------------------------------------------
        # ------------------------------------------------------------
        # rendszersor — az ablak tetején álló, TÁJÉKOZTATÓ sor: melyik
        # időszakra és melyik boltba van beosztás, mit jelent itt a "ma",
        # és melyik értelmező dolgozik. Nem a vásárlónak szóló válasz,
        # hanem a próbálgatónak szóló helyzetjelentés — de ugyanúgy
        # magyar mondat, ezért ugyanúgy ITT van, nem a felületen
        # (`ui/vasarlo.py` docstring: "a felület sosem fogalmaz").
        # ------------------------------------------------------------
        "rendszersor": {
            "nincs_beosztas": "Nincs betöltött beosztás — futtasd: python feladat.py seed",
            "idoszak": "A demóadat {elso_nap} – {utolso_nap} hetére szól",
            "idoszak_boltokkal": (
                "A demóadat {elso_nap} – {utolso_nap} hetére szól, "
                "beosztás ezekben a boltokban van: {boltok}"
            ),
            "ma_bent": " A mai nap ebbe az időszakba esik.",
            "ma_kint": (
                " A mai nap ({ma}) kívül esik ezen, ezért a „ma” ezen a felületen "
                "{horgony_nap}-t jelent — nem kell dátumot fejben tartanod."
            ),
            "ertelmezo_modell": " Értelmező: {modell} (ha nem fut, csendben szabály-alapú).",
            "ertelmezo_szabaly": (
                " Értelmező: szabály-alapú (nincs APRAJAFALVA_LLM_MODELL beállítva)."
            ),
            # NINCS MODELL — külön, feltűnő sor, nem zárójeles megjegyzés.
            #
            # A tartalék ág csendben átveszi a fordulót (`assistant/
            # interpreter/forditott_kaszkad.py`), és ez a helyes
            # viselkedés: a vásárló nem eshet ki attól, hogy egy
            # háttérszolgáltatás nem fut. A PRÓBÁLGATÓNAK viszont pont
            # ez a legdrágább félreértés — végigpróbál egy
            # beszélgetést, és a szabály-alapú réteget hiszi a
            # modellnek. A mondat ezért megmondja, MI FUT, és azt is,
            # hogy MIT KELL BEÍRNI a bekapcsoláshoz.
            # INDÍTÁSI ELLENŐRZÉS — modális ablak, három ok, három
            # teendő (`ui/vasarlo.py::_indito_ellenorzes`). A sárga sáv
            # (`nincs_modell_figyelmeztetes`) MEGMARAD, de bizonyítottan
            # nem elég: háromszor futott végig kézi próba a tartalék
            # ágon úgy, hogy csak utólag derült ki. Amit át lehet
            # siklani, azt át is siklik az ember — ezért itt már
            # DÖNTENI kell, mielőtt a szöveges fül elindul.
            "indito_cim": "Nem az éles úton indulnál",
            "indito_nincs_modell": (
                "Nincs beállítva nyelvi modell, ezért a beszélgetés a TARTALÉK "
                "(szabály-alapú) ágon futna — az eredmények NEM a modellt mérnék.\n\n"
                "Teendő: állítsd be a modellt, és indítsd újra ezt az ablakot:\n"
                '    PowerShell:  $env:APRAJAFALVA_LLM_MODELL="qwen3.5:9b"\n'
                "    cmd:         set APRAJAFALVA_LLM_MODELL=qwen3.5:9b\n"
                "    bash:        export APRAJAFALVA_LLM_MODELL=qwen3.5:9b"
            ),
            "indito_nincs_szolgaltatas": (
                "A modell be van állítva ({modell}), de az Ollama nem válaszol — "
                "a beszélgetés a TARTALÉK (szabály-alapú) ágon futna, és az "
                "eredmények NEM a modellt mérnék.\n\n"
                "Teendő: indítsd el a szolgáltatást (ollama serve), majd indítsd "
                "újra ezt az ablakot."
            ),
            "indito_nincs_letoltve": (
                "Az Ollama fut, de a beállított modell ({modell}) nincs letöltve — "
                "a beszélgetés a TARTALÉK (szabály-alapú) ágon futna.\n\n"
                "Teendő: ollama pull {modell}   (vagy állíts be egy már meglévő "
                "modellt), majd indítsd újra ezt az ablakot."
            ),
            # HANGKIMENET (ADR-029). A beszélhető mód eddig CSENDBEN nem
            # szólalt meg — nem volt bekötve TTS, és ez a felületen nem
            # látszott. A sor megmondja, mi hiányzik, és hol lehet
            # megnézni részletesen.
            "hang_hianyzik": (
                "A beszélhető mód most csak a képernyőn olvasható — hang nincs: {hianyok}. "
                "Részletek és teendő: python feladat.py hangproba"
            ),
            "hang_kesz": "Felolvasás: {hang}",
            "hang_hiany_piper": "nincs telepítve a Piper",
            "hang_hiany_hang": "nincs magyar hangmodell",
            "hang_hiany_lejatszo": "nincs lejátszó program",
            "indito_folytatom": "Folytatom tartalékággal",
            "indito_kilepek": "Kilépek",
            "nincs_modell_figyelmeztetes": (
                "FIGYELEM: nincs beállítva nyelvi modell — a beszélgetés a TARTALÉK "
                "(szabály-alapú) ágon fut, nem az éles úton.\n"
                "Bekapcsolás: set APRAJAFALVA_LLM_MODELL=qwen3.5:9b   (PowerShell: "
                '$env:APRAJAFALVA_LLM_MODELL="qwen3.5:9b"), fusson az Ollama, '
                "majd indítsd újra ezt az ablakot."
            ),
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
        # ------------------------------------------------------------
        # BESZÉLHETŐ MÓD — felülíró változatok (M6, hang-előkészítés,
        # `assistant/valasz/beszelheto.py`).
        #
        # **Csak az van itt, ami hangon MÁSKÉNT hangzik jól.** Aminek a
        # szöveges alakja felolvasva is helyes, az nem duplázódik: a
        # kimeneti kapu (`beszelhetove()`) a számokat, zárójeleket és
        # gondolatjeleket úgyis elintézi. Ez a szótár a MEGFOGALMAZÁSÉ,
        # nem a formázásé — azt automatikusan nem lehet előállítani.
        #
        # Három visszatérő ok, amiért egy mondat ide kerül:
        #
        # 1. **Két kérdés egy mondatban** („melyik boltba és mikorra?").
        #    Írásban átfutható, hangon a vásárló az egyikre felel, és
        #    nem tudjuk, melyikre (blueprint 7., „Egy kérdés egy
        #    fordulóban").
        # 2. **A felületre hivatkozik** („a másik fülön"). Hangon nincs
        #    fül.
        # 3. **Túl hosszú.** Hangon a harmadik tagmondatnál a vásárló
        #    már belevág (barge-in), és a saját hangunkat is az ASR-be
        #    küldi.
        # ------------------------------------------------------------
        "beszelheto": {
            "hiba": {
                # Egy kérdés, nem kettő.
                "nem_foglalasi_kerdes": (
                    "Ebben nem tudok segíteni, csak időpontfoglalásban. "
                    "Melyik boltba szeretnél menni?"
                ),
                "ertelmezhetetlen_bemenet": (
                    "Ezt nem sikerült értenem. Melyik boltba szeretnél menni?"
                ),
                "ar_nem_adhato": (
                    "Az árakról a boltban tudnak felvilágosítást adni. "
                    "Időpontot viszont szívesen keresek."
                ),
                "nincs_meghirdetett_idopont": (
                    "Erre az időszakra a bolt még nem hirdetett meg időpontokat. "
                    "Megnézzem a következő hetet?"
                ),
                # A szöveges alak a MÁSIK FÜLET ajánlja — hangon nincs
                # fül. Ami marad: a bolt, élőben.
                "emberhez_iranyitas": (
                    "Úgy látom, ez így nem vezet sehova. "
                    "A boltban élőben is fel tudnak venni időpontot."
                ),
                "tul_sok_keres": "Túl sok kérés érkezett rövid idő alatt. Kérlek, várj egy kicsit.",
                "nincs_szabad_hely_az_ablakban": (
                    "Ebben az időszakban nincs szabad időpont. Nézzünk másik napot?"
                ),
                "nincs_szabad_hely": (
                    "Ebben az időszakban nincs szabad időpont. Nézzünk másik napot?"
                ),
            },
            "visszaigazolas": {
                # VISSZAOLVASÁSOS megerősítés (blueprint 7.): hangon a
                # „biztosan lefoglaljam ezt?" mutató névmása értelmetlen,
                # mert nincs, amire mutasson — az időpontot ki kell
                # mondani. Ha a hívó mégsem tudja átadni, marad a
                # névmás nélküli, rövid alak.
                "megerosites_ker": "Lefoglaljam?",
                "megerosites_ker_idoponttal": "{idopont} foglalnám le. Rendben?",
                "sikeres_foglalas": "Megvan a foglalás. A kódod {foglalasi_kod}.",
                "ajanlat_egy": "A legkorábbi {elso}. Jó lesz?",
                # KETTŐ időpont, nem több — l. `beszelheto.py`, 5.
                # szabály: három felolvasott időpont megjegyezhetetlen.
                "ajanlat_ketto": "A legkorábbi {elso}, de van {masodik} is. Melyik jó?",
                "ajanlat_legkozelebbi": "A legkorábbi szabad időpont {elso}. Jó lesz?",
            },
            # A visszakérdezés hangon KÉRDÉS, nem bevezetett felsorolás:
            # a „Ehhez még kellene tudnom: melyik boltba szeretnél
            # menni." kijelentő mondat, amire a vásárló hallgatással
            # felel.
            "zart_kerdes": {
                "mezo_neve": {
                    "bolt_id": "Melyik boltba szeretnél menni?",
                    "szolgaltatas_id": "Melyik szolgáltatást szeretnéd?",
                    "foglalasi_kod": "Mi a foglalási kódod?",
                    "datum_tol": "Mikorra szeretnél időpontot?",
                    "uj_datum": "Melyik napra tegyem át?",
                },
                "tartalek": "Mondd el, pontosan mit szeretnél.",
            },
            "kiut": {
                # A szöveges alak „körbe-körbe járunk" — kötőjeles
                # összetétel, ami hangon szünetet szül a szó közepén. A
                # kimeneti kapu szóközre cserélné („körbe körbe"), de
                # egy jó mondatot nem javítgatni kell, hanem megírni.
                "bevezetes": "Úgy látom, így nem jutunk előre.",
                "kerdes": "Próbáljunk {dimenziok}?",
                "dimenzio": {
                    "nap": "másik napot",
                    "napszak": "másik napszakot",
                    "legkorabbi": "a legkorábbi szabad időpontot",
                },
            },
            "alternativa": {
                "bevezetes": {
                    "napszak": "Ebben a napszakban nincs, de aznap máskor van szabad időpont.",
                    "nap": "Ezen a napon nincs, de a héten másik napon van.",
                    "kesobb": "Ebben az időszakban nincs, de később van szabad időpont.",
                    "varians": "Erre a változatra nincs, de a boltban másikra van.",
                },
                "kerdes": "Megnézzem?",
            },
            "tenyvalasz": {
                "nyitvatartas": "A bolt nyitvatartása {ertek}.",
                "cim": "A bolt címe {ertek}.",
                "szolgaltatasok": "Ezeket lehet nálunk kérni: {nevek}.",
            },
        },
    }
}

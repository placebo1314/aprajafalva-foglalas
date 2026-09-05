# Állapot — 2026-09-05 (frissítve: ÚJABB MODELLEK MEGMÉRVE — Gemma 4
család; a golden halmazok bővítve; két új korlát megtalálva és egy
prompt-javítás megbukva. Előzőleg: explicit num_ctx — ADR-027,
állapotvezérelt diszpécser — ADR-028, hangkimenet — ADR-029)

**A 2026-09-05-i kör négy mondata:**

1. **A 2026-os mezőnyből EGYETLEN új család fér a kártyánkba: a Gemma
   4.** A Qwen3.6 legkisebb változata 17 GB, a Qwen3.8 27B, a
   Nemotron-3.5-Lightning 23 GB — ezek 8 GB-on nem mérhetők
   tisztességesen. A Gemma 4 viszont Apache-2.0 (a Gemma 3 még saját
   feltételekkel jött), tehát az ADR-013 szerint akár ELSŐDLEGES modell
   is lehetne.
2. **A két halmaz ELLENTÉTESEN rangsorol.** A `gemma4:12b-it-qat` a
   beszédhelyzeteken 96,4% — a valaha mért legjobb —, a nyelvi halmazon
   viszont 83,6% a `qwen3.5:9b` 86,4%-ával szemben. A Gemma 4 a
   pragmatikában erősebb, a magyar nyelvi rétegekben gyengébb. Marad a
   `qwen3.5:9b`: a projekt mérőszáma a LEGGYENGÉBB RÉTEG (ott 40% vs.
   20%), és a 12B ára +58% válaszidő 30%-os kiszervezéssel
   (`docs/MODELLKERESES_20260905.md`).
3. **Egy 3 GB-os modell jobb a pragmatikában, mint egy háromszor
   nagyobb.** A `gemma4:e4b` a beszédhelyzeteken 89,3%, a `qwen3.5:9b`
   85,7% — miközben a nyelvi halmazon 19 ponttal rosszabb. A méret nem
   képesség, és nem is egyféle képesség.
4. **A bővített halmazok azonnal két hibát találtak, és egy javítási
   kísérlet megbukott.** A MINDEGY RAGADÓS (elengedés után konkrét
   értéket kérni nem lehet), a szolgáltatás pedig nem él túl egy
   fordulót. A prompt-javítást megmértük: nem javított, tehát nincs a
   promptban. Mindkét bukás korlátként rögzítve
   (`docs/ALTALANOSITAS.md` 2.9c–2.9d).

**A halmazok bővültek:** nyelvi 51 → **55** (elengedés-ellenpróbák és a
MINDEGY visszavonhatósága), beszédhelyzetek 23 → **28** (sürgetés,
másik csatornára hivatkozás), az állapotsor-próbák 4 → **8** (időrendi
hivatkozások és egy ellenpróba). Az utóbbi megcáfolta a korábbi
következtetésünket: az időrendi hivatkozások többsége MEGY („a
legkésőbbit", „az utolsó előtti"), csak a szokatlan szóalak („késeibb")
bukik.

**A 2026-09-01-i kör hat mondata:**

1. **A „csendes CPU-visszaesés" feltevés MEGDŐLT ezen a gépen.** Az
   Ollama 0.33.2 alapértelmezése épp 8192, a modell 100%-ban a GPU-n
   fut (5368 MB a 8188-ból) — kiszervezés nem volt. Az explicit
   `num_ctx` ezért ma nem javít semmit; attól még helyes, mert a
   szolgáltatói alapértelmezés nem a miénk (ADR-027).
2. **A kiszervezés ára IDŐ, nem pontosság — legalábbis 36%-ig.**
   `num_ctx=65536`-tal a modell 36%-a a CPU-ra került: a válaszidő
   +35%, a pontosság viszont KÉT futásból egyszer 86,3%, egyszer
   91,2% — vagyis a romlás nem reprodukálódott. A séma-kényszerítés
   végig tartott: JSON parse-hiba egyetlen futásban sem volt
   (`docs/NUM_CTX_ES_VRAM.md`).
3. **A `temperature: 0` nem jelent futásonkénti azonosságot.** Ugyanaz
   a kód, ugyanaz a modell, ugyanaz a beállítás 1-2 esetnyit ingadozik
   — ezért kell két futás egy 4 pontos különbséghez. Ez a kör
   legfontosabb módszertani tanulsága.
4. **A nagy modellek nem hoztak áttörést.** `gemma3:12b`: 88,2%, de
   **kétszer lassabb** (p50 7,39 s vs. 3,67 s), 41%-os kiszervezéssel.
   `qwen2.5:14b`: 70,6%, 8,61 s. Marad a `qwen3.5:9b`.
5. **A modell eddig NEM TUDTA kifejezni, hogy a vásárló a felajánlott
   listából választott.** Nem prompt-hiba volt, hanem szerződéshiány: a
   `{eszkoz, parameterek}` alakban nem volt rá érték. Az új
   `jelolt_valasztas` (sorszámmal, két determinisztikus kapuval) ezt
   pótolja — a „fél kilences jó lesz" típusú mondatok 0/4-ről 3/4-re
   javultak (ADR-028, `docs/ALLAPOTSOR_MERES.md`).
6. **A felolvasás soha nem szólalt meg — mert TTS nem is volt bekötve.**
   A beszélhető mód (ADR-023) a SZÖVEGET formázta felolvasásra. Most van
   hangkimenet (Piper, `assistant/hang.py`), `python feladat.py
   hangproba` paranccsal, és ami a fontosabb: ha bármi hiányzik, a
   rendszer MEGMONDJA — három hiány, három teendő —, a felület pedig a
   mód-kapcsoló mellett kiírja (ADR-029).

**Az állapotgép mostantól kimondott:** hat állapot (`INDULAS`,
`HIANYZO_ADAT`, `AJANLAT_VAR`, `MEGEROSITES_VAR`, `KESZ`, `KIUT`),
kódban rögzített átmenetekkel, a promptba tett egysoros helyzetleírással
és fordulónkénti naplózással. A `python feladat.py naplo` külön blokkban
összesíti, mely állapotokban áll meg a beszélgetés.

**A 2026-08-30-i kör ÖTÖDIK mondata (az ADR-024 köre):**

5. **Egy működő, tesztelt funkciót vontunk vissza, mert rossz fogalmon
   állt.** A „itt nincs, de a szomszédban van" bolt-ajánlás ugyanaznap
   készült el, és ugyanaznap tűnt el: Aprajafalva három boltja nem egy
   szolgáltatás három telephelye, hanem három TERMÉK, tehát aki
   petárdát kér, annak a boldogság-bolt nem gyengébb találat, hanem
   más kérdésre adott válasz. A helyére a bolton BELÜLI lazítási
   sorrend lépett (napszak → nap → később → variáns), és minden válasz
   kimondja, melyik dimenzióban engedett. Ezzel együtt lett a
   „mindegy" ÉRTÉK a hiány helyett (`MINDEGY` szentinel), és lett a
   „mikor tudok legkorábban menni?" elsőrendű kérés — a modell
   `legkozelebbi_idopont` válasza eddig némán `szabad_idopontok`-ká
   alakult, egy önkényes egyhetes ablakkal.

**A 2026-08-30-i kör NEGYEDIK mondata (a demóadat köre):**

4. **A kiutak harmada nem párbeszédhiba volt, hanem ADATHIÁNY.** A
   demóadat korábban csak a Törpillába adott beosztást; mostantól
   mindhárom bolt kap, három különböző ritmusban. Ugyanazon a kódon,
   ugyanazon a 204 fordulón mérve a kiút 26 → 18, az ajánlat 34,3% →
   46,6%. A maradék 18 kiút MIND információ nélküli fordulóból jön —
   a részletes bontás: `docs/ALTALANOSITAS.md` 3. szakasz.

**A 2026-08-30-i kör három mondata:**

1. **A KÉZI PRÓBA négy hibát talált, amit sem a teszt, sem a mérés nem
   fogott meg** — mind a négy a képernyőn látszott: kétszer ugyanaz a
   válasz, kétszer ugyanaz a „körbe-körbe" mondat, nyitott és technikai
   kiút-kérdés, és egy időablak, ami egy nappal túlnyúlt a beosztáson.
   Az ötödiket (a sorszámos választás a naplóban jó, a képernyőn „Nem
   értettem") a fej nélküli végigjátszás fogta meg, miután a
   funkció elkészült.
2. **A sorszámos hivatkozás („a másodikat", „az utolsó jó lesz") a
   leggyakoribb természetes válasz egy listára** — eddig egyiket sem
   értettük. Determinisztikus, a modell ELŐTT fut, és a jelöltek
   sorszámozva bekerülnek a beszélgetés-előzménybe is.
3. **A napló megnézhetősége eszközt kapott**: `python feladat.py
   riport` — egyetlen, offline megnyitható HTML, fordulónként a teljes
   prompttal, a nyers modellválasszal, a dátumfeloldással és a kimenő
   válasszal MINDKÉT módban.

**Az előző kör (2026-08-26) két mondata változatlanul áll:**

1. **A hang előkészítése szövegben is mérhető.** A `valasz` modulnak két
   kimeneti módja van (`szoveges` | `beszelheto`), és a beszélhető alak
   formai szabályait teszt őrzi — hang nélkül, ma.
2. **Két mérési hiba miatt a saját számainkat kellett helyesbíteni.** A
   stabilitás-vizsgálat az éles úton sosem futott le, és amikor lefutott,
   a rossz dolgot hasonlította össze. Mindkettő úgy tévedett, hogy a
   rendszert JOBBNAK mutatta — l. lent, az A/2 szakasz.

Egy oldalas pillanatkép: hol tartunk. A terv és a "miért" a
`docs/blueprint.md`-ben és a `docs/roadmap.md`-ben van, ez itt nem
ismétli meg őket, csak rájuk mutat és számol.

A `docs/PLATFORM_TANULSAGOK.md` (Cal.com/Vapi-tanulságok) és a
`docs/CLAUDE_KISOKOS.md` (Claude Code-jegyzet) a projektgyökérből ide
költözött, felvéve a `README.md` dokumentum-táblájába — a
PLATFORM_TANULSAGOK.md konkrét teendői a `docs/roadmap.md` M4/M5/M6
mérföldköveihez vannak jelölve, még nincs belőlük semmi megépítve.

**Új dokumentum: `docs/ALTALANOSITAS.md`** — mi javul elvileg, és mi
marad ismert korlát. A robusztussági kör melléktermékéből lett önálló:
minden mérés, ami bukást talál, strukturális javítás és ráigazítás
közül választ, és a ráigazítást nem csináljuk meg — a bukás oda kerül
ismert korlátként. Az "Ismert korlátok" szakasz lent ezért rövidebb,
mint amennyi korlátunk van: a NYELVI/viselkedési korlátok oda
költöztek.

## Mérföldkövek

| Mérföldkő | Állapot | Megjegyzés |
|---|---|---|
| M-1 — Spike | **kész** | Lezárva 2026-08-16. A négy szám megvan, egyik sem hozta a tervezett SLO-t — lásd lent, "Ismert korlátok". |
| M0 — Foglalási mag | **kész** | Séma, migrációk, slotgenerátor, hold, foglalás, áthelyezés, lemondás, mentés+helyreállítás, CLI, konkurencia-tesztek — mind megvan és tesztelt. |
| M1 — Admin beosztásszerkesztő | **részben kész** | Naptárnézet, műszak felvitele, sablon-műszakok, hét másolása, törzsadat-szerkesztés, ütközéslista megvan. A törzsadat-szerkesztés kibővült a "Bolti tudás" mezőkkel (megjelenés/termékleírás/ár, `core/api/adminszolgaltatas.py::shop_description_update`/`service_description_update`) — a `bolt_info` eszköz ezeket olvassa vissza. Ami hiányzik: lásd lent. |
| M2 — Eszközszerződés | **kész** | A hat eszköz (`assistant/tools/`) megvan: JSON-séma v1-gyel, `additionalProperties: false`, egységes hiba-formátummal, LLM nélkül hívható és tesztelt (23 teszt). |
| M3 — Golden set és értékelő | **részben kész** | **HÁROM halmaz, három mérésfajta** (`--halmaz nyelvi\|robusztus\|beszedhelyzetek`), 2026-09-05-től **151 eset** (nyelvi 55, robusztussági 68, beszédhelyzetek 28). **(1) Nyelvi**, 45 eset, 10 réteg — EGY helyes válasz esetenként, a mérőszám a rétegenkénti pontosság. **(2) ROBUSZTUSSÁGI, 68 eset, 14 kategória** (`tests/golden/robusztus.yaml`): üres bemenet és zaj, 500+ karakteres többtémájú mondat, nyelvi váltás, több szándék egyszerre, egy mondaton belüli ellentmondás, hatókörön kívüli kérdés, prompt injection és séma-kényszerítés, érzelmi töltet, félbehagyott mondat, ötszörös ismétlés, abszurd kérés, kéretlen személyes adat — és **ÚJ: ASR-hibák** (13. kategória, 19 eset hat fajtában: szám, tulajdonnév, egybefolyás, szóvég, ékezet, hallucináció; külön mérési bontással, l. lent az A) szakaszban). Ott a `varhato` nem EGY helyes választ ír elő, hanem az elfogadható VISELKEDÉSEK listáját, és a mérőszám NÉGY biztonsági szám (kivétel / hatókörön kívüli válasz / kitalált tény / instabil ismétlés), mind 0-s kemény küszöbbel — a futás ezektől bukik, nem a pontosságtól. Az elfogadási elv a halmaz fejlécében: *egyetlen eset sem okozhat kivételt, végtelen ciklust, kitalált tényt vagy hatókörön kívüli választ; a pontosság MÁSODLAGOS.* A nyelvi halmazról változatlanul: a `mintan_tul` réteg mondattani ALAKZATOKAT mér (vagylagos, feltételes, indoklás mellékmondattal, kettős kérés, visszavonás, bizonytalanság, töltelék) — a magja a **04–09. tükörpár**: ugyanaz a szerkezet, a két napszak felcserélve, amire egy szólistás réteg szükségszerűen ugyanazt adja, tehát az egyiket elrontja. **Őszintén: a kilencből a determinisztikus réteg többet is megold, véletlenül** (a „28-án" beleesik a „jövő hét" ablakába; a napszak-minták sorrendje éppen jó irányba dől) — a réteg értéke a tükörpárban van, nem az esetek nehézségében. A roadmap 150-200 esetet ír elő kilépési feltételként, ez messze nincs meg; szituációs esetek (naptárállapot → ajánlás) egyáltalán nincsenek. A `python feladat.py golden` mind a négy felállást méri (`--ertelmezo szabaly|llm|kaszkad|forditott`), a kiértékelő egy tartós modulban (`tests/golden/futtato.py`), amit a `spike/golden_futtato.py` és a determinisztikus regressziós védőháló (`tests/egyseg/test_rule_based_golden_set.py`) is hív — nincs két másolat. **ÖT mérési hiba javítva eddig** (a negyedik és az ötödik ebben a körben, l. lent az A/2 szakaszban): (1) a `kitalalt_ar` tiltott-minta vizsgálat részszöveget keresett, ezért a `varhato_kerdes_tipusa` mezőt is „kitalált árnak" minősítette; (2) a robusztussági mérés a dokumentált TARTALÉK dátumablakot (most → +7 nap) kitalált dátumnak vette, holott az a hiány bevallott pótlása — a valóban kitalált dátum egy KONKRÉT, félreolvasott ablak; (3) a `datum_kifejezes`/`datum_kifejezes_2` hiányzott az ismert mezőnevek közül, ezért a kapuk NÉLKÜLI `llm` felállás 19 „kitalált tényt" kapott, holott az a két mező a modell szerződésének része — a hiba iránya fontos: a mérés ROSSZABBNAK mutatta a modellt, mint amilyen; (4) a fordulónkénti kimenetek nem jutottak el a futtatóig a modell-utakon, ezért az ismétlés-STABILITÁS vizsgálata némán kimaradt; (5) a stabilitás a TELJES kimenetet hasonlította össze, a `bizonyossag` logprob-zajával együtt. A negyedik és az ötödik a rendszert mutatta JOBBNAK, mint amilyen. |
| M4 — Asszisztens | **részben kész** | A **determinisztikus fele kész**, és **az éles út mostantól a MODELL-ELSŐBBSÉGŰ (fordított) kaszkád** (ADR-018, felülírja az ADR-016-ot): `assistant/orchestrator.py` (ADR-007 állapotgép), `assistant/interpreter/` — `rule_based.py` (determinisztikus alapvonal és tartalék), `llm_based.py` (Ollama `/api/chat`, `format` séma-kényszerrel, few-shot példák, `think: false` explicit, logprob-alapú bizonyosság, `LLMSzolgaltato` absztrakció konfigból jövő modellnévvel — ADR-013), `forditott_kaszkad.py` (**éles**). **ADR-020: az éles út mostantól KAPUŐRREL kezdődik** — `assistant/kapuor/` → normalizáló → modell → determinisztikus kapuk → szabály-alapú tartalék. A kapuőr ZÁRT, három elemű osztályozással dönti el, hogy a kérés egyáltalán a miénk-e (foglalási szándék / engedélyezett tényválasz / azon kívüli), a modell ELŐTT fut, és kívül eső kérésnél **a modell meg sem szólal**. A legfontosabb szabálya: **a bizonytalanság nem elzárás** — csak pozitív bizonyítékra zár ki, mert a téves átengedést a mögöttes rétegek még fogják, a tévesen kizárt vásárló viszont hálót nem talál. **ADR-021: önkonzisztencia** (`interpreter/onkonzisztencia.py`) — megépült (blueprint 10., addig sosem létezett), megmérve, és **alapból KIKAPCSOLVA** (`APRAJAFALVA_ONKONZISZTENCIA=1` bekapcsolja): 0 pontot javít, 63-71%-kal lassít. **Redaktálás tárolás előtt** (`privacy/redakcio/`): a próba-napló eddig a vásárló mondatát NYERSEN írta lemezre — egy kéretlenül bediktált telefonszám azonnal invariánssértés volt (CLAUDE.md 2.). **ADR-019: a modell a BESZÉLGETÉST látja** — az utolsó fordulók párbeszédként mennek a promptba (`ErtelmezesKontextus.elozmenyek`, a felület vezeti), a modell EGY hívásban adja vissza a teljes kérést, és ami már nem érvényes, azt egyszerűen nem tölti ki. Az "elengedés" fogalma és a hozzá tartozó külön modellhívás TÖRÖLVE. A megőrzött kontextus szerepe tartalékra szűkült: a modell null-ja erősebb nála. Két új kapu védi a szándék PUHA részét: a dátum-idézetet és a napszakot csak akkor fogadjuk el, ha az aktuális mondatból való, `kaszkad.py` (ADR-016 sorrendje, **a visszaút**). **Mérve** mindkét halmazon (`qwen3.5:9b`, l. lent „Konkrét számok"): nyelvi `szabaly` 80,0%, **`forditott` 83,3%**; robusztussági `szabaly` 100,0%, **`forditott` 100,0% / 0 biztonsági sértés**. A **kapuőr-réteg 50% → 100%**, és a robusztussági halmazon a hatókörön kívüli válaszok száma **3 → 0** — ez volt az ADR-018 óta a legfontosabb nyitott pont, lezárva. Válaszidő: **p50 4,62 s / p95 5,08 s** a robusztussági halmazon (ADR-022 eloszlás-elvárás), mert a 68 esetből 15 modellhívás nélkül fordul vissza. A koppintós út (M4 terv 7. pontja) megvan: `ui/vasarlo.py`, két egyenrangú úttal (koppintós + szöveges) egy ablakban, mindkettő végigjátszható (keresés → jelölt-választás → „biztosan lefoglaljam?" → foglalási kód) — és mostantól **fej nélkül is** (`python feladat.py vegigjatszas`, `tools/vegigjatszas.py`: 14 beszélgetés + a teljes foglalási menet, Tkinter-eseményhurok nélkül, `--mod` kapcsolóval mindkét kimeneti módban) — **a `--robusztus` kapcsolóval a teljes robusztussági halmaz is végigmegy a VALÓDI felületen**, ami mást mér, mint a golden futtató: ott az értelmezőt (mondat → eszközhívás), itt a teljes utat (orchestrator, ismétlésfigyelés, frusztráció-kiút, magyar mondatgenerálás, próba-napló). A felület **a beosztáshoz horgonyoz, nem a rendszerórához** (`horgony_most`), az ablak tetején kiírja, melyik hétre és melyik boltba van beosztás, mit jelent itt a „ma", és melyik értelmező dolgozik. A **próba-napló** (`naplo/probak.jsonl`) fordulónként rögzíti a bemenetet, a normalizált alakot, a réteget, az eszközt, a paramétereket, a bizonyosságot, a válasz típusát és üzenetkulcsát, a kapuőr okát, az önkonzisztencia-egyetértést, a VÁLASZIDŐT és az időbélyeget — mindezt **redaktálva** (`privacy/redakcio`). A szöveges fülön a „Napló megnyitása" gomb olvashatóan kiírja, és **új eszköz elemzi**: `python feladat.py naplo` (`tools/naplo_elemzo.py`) — fordulószám, réteg-megoszlás, válaszidő-ELOSZLÁS (p50/p95/átlag/max) a kétpontos elváráshoz mérve, PLUSZ a tendencia (ADR-022), bizonyosság-eloszlás (a sávhatárok pontosan az orchestrator küszöbei, így leolvasható, hány forduló esett ténylegesen visszakérdezésbe), és a leggyakoribb hibaminták zárt detektor-készlettel. A `--golden <sor>` egy naplósorból golden teszteset-vázat ír, a `varhato` mezőt ÜRESEN hagyva — ezzel a golden-set skill hurkának („valós hiba → redaktált trace → annotálás → golden set") az első fele megépült. L. `docs/TESZTELES.md`, „Beszélgetés-próba". A blueprint rögzíti a „Bolti tudás" elvet (10. szakasz): a bolt-szintű tény szerkesztett adat, a modell sosem generálja — a `bolt_info` eszköz `v2` sémát kapott (`megjelenes`/`termek`/`ar`, `migrations/0004_bolt_szolgaltatas_tudas.sql`). A **`valasz` modul** (`assistant/valasz/`) adja MINDEN magyar mondatot, a felület egyet sem fogalmaz — beleértve az új „rendszersor" kategóriát (az indító sor). **Szándék rétegzés** (`kovetkezo_kontextus`): a kemény rész (bolt, szolgáltatás) túléli a fordulót, a puha (dátum/napszak/óra) nem; a fordított kaszkádban a kemény rész a MODELL PROMPTJÁBA is bekerül, az elengedést pedig egy külön, zárt kérdés dönti el. **Enumeráció-védelem és rate limiting** a `foglalas_lekerdezes` ágon. **Bizonyosság-küszöbök** (`BizonyossagKuszobok`: eszköz 0,7, kritikus mező 0,6) → zárt kérdés küszöb alatt. **Ismétlésfigyelés**: ugyanaz a válaszfajta legfeljebb kétszer; a harmadikra kiút. **Új eszköz: `legkozelebbi_idopont`** ("mikor tudok legkorábban menni?") — EGY időpont, holddal, pontozás nélkül: erre a kérdésre egyetlen objektív helyes válasz van, és ott az ajánlatpontozó torzítana. **Frusztráció-felismerés** (`assistant/frusztracio.py`): a kimondott panasz, az eredménytelen fordulók és a hossz együtt visz kiúthoz, a MÁSODIK kiút pedig emberhez irányít (a vásárló 8. igénye) — az eddigi ismétlésfigyelő csak a SAJÁT válaszaink ismétlődését látta. **Hiányzik**: kötött dekódolás GBNF/XGrammar szinten (ma az Ollama `format` JSON-séma-kényszere adja, ami nem ugyanaz), és a bolti tudás (megjelenés/termék) a promptban — enélkül a „csillagos kirakatú bolt" típusú körülírást a modell nem tudja feloldani. A korábban itt szereplő két hiány LEZÁRULT: a determinisztikus kapuőr (ADR-020) megépült és mérve javít; az önkonzisztencia (ADR-021) megépült, mérve NEM javít, ezért kikapcsolva marad. |
| M5 — Dolgozói nézet | **nem kezdődött el** | — |
| M6 — Dev mód és finomhangolás | **a HANGCSATORNA előkészítése elkezdődött** | Maga az M6 (trace-böngésző, finomhangolás) nem indult el. Ami elkészült, az a hang két SZÖVEGOLDALI fele: **(1) beszélhető kimeneti mód** (`assistant/valasz/beszelheto.py`, `szamok.py`) — egész mondatok, kimondott számokkal (`„nyolc óra tizenöt"`, `„december huszonkettedikén"`), fordulónként legfeljebb két mondattal és EGY kérdéssel, időpont-felsorolás helyett a legkorábbi + egy alternatíva; a felületen kapcsolható (`ui/vasarlo.py`, „Kimenet" választó), a végigjátszásban `--mod mindketto`. **(2) ASR-hibatűrés mérése** (`tests/golden/robusztus.yaml` 13. szakasz, 19 eset hat hibafajtában): a Whisper magyar hibái (szám, tulajdonnév, egybefolyás, szóvég, ékezet, hallucináció) szövegként előállítva, külön mérési bontással. **(3) BESZÉLGETÉS-ELEMZŐ** (`tools/beszelgetes_riport.py`, `python feladat.py riport`): a próba-naplóból egyetlen, offline megnyitható HTML — fordulónként összecsukható blokk a teljes prompttal, a nyers modellválasszal, a séma-ellenőrzéssel, a dátumfeloldás három adatával (modell / parser / melyik nyert), a mezőnkénti forrással, a lépésenkénti idővel és a kimenő válasszal MINDKÉT módban. Ez az M6 trace-böngésző tételének első fele; a felület „Napló megnyitása” gombja ezt nyitja. **Ami hiányzik** — ASR, TTS, turn-detection, barge-in: mind **konfiguráció, nem építés** (`docs/roadmap.md`, M6). |

## Konkrét számok

- **Tesztek:** 956 zöld + 1 `xfail` (`tests/egyseg/test_alapsema.py::test_cross_org_reference_ma_not_bukik_el`, `strict=True`). A 2026-08-31-i kör négy új tesztfájlt hozott: **`test_ablak.py`** (a csúszó előzmény-ablak — rövidít, NEM felejt, és nem szivárogtat időpontot), **`test_indito_ellenorzes.py`** (a három hiány-ok és a hozzájuk tartozó három teendő), **`test_megerosites.py`** (írásbeli igen/nem — a felismerés SZŰK: „igen, de inkább szerdán" nem igenlés), **`test_beszedhelyzetek_halmaz.py`** (a harmadik golden halmaz szerkezeti őrzése). A 2026-09-01-i kör három továbbit: **`test_allapotgep.py`** (zárt átmenetek, állapot a válaszból, az állapotsor mint helyzetleírás), **`test_hang.py`** (a felolvasás diagnózisa — sosem szólal meg és nem telepít semmit), plusz az orchestrator állapot- és `jelolt_valasztas`-tesztjei.
- **Migrációk:** 4 (`0001_alapsema`, `0002_muszak_slot`, `0003_muszak_sablon`, `0004_bolt_szolgaltatas_tudas` — bolti tudás mezők, lásd lent). A `bolt_info` eszköz sémája **v3**-ra bővült (`pultosok`) — ez nem migráció: a nevek az `alkalmazott` táblából jönnek, ami az alapséma óta megvan.
- **ADR-ek:** 28 dokumentum (001–014, 016–029) + 1 sablon. Ebből **27
  elfogadott**, **1 felülírva**: az ADR-016 (kaszkád sorrendje) —
  felülírta az **ADR-018**, amelynek első, elvető változata 2026-08-22-én
  született, és 2026-08-23-án ÁTFORDULT. Az **ADR-019** az ADR-018-at
  KIEGÉSZÍTI: a sorrend marad, a modell BEMENETE változott meg (a
  beszélgetés, nem a kontextus adatként), és ezzel az "elengedés"
  fogalma megszűnt. Az **ADR-020** (determinisztikus kapuőr) az ADR-018
  „A következő lépés" szakaszát váltja be; az **ADR-021**
  (önkonzisztencia) a blueprint 10. szakaszának egy addig soha meg nem
  épült előírását — megépítve, megmérve, és **kikapcsolva**, mert a
  mérés szerint nem javít. Az **ADR-025** (csúszó előzmény-ablak) az ADR-019-et EGÉSZÍTI KI: a modell továbbra is a beszélgetést látja, csak a régebbi fordulók helyett egy összefoglaló sort. Az **ADR-026** verziózza a rendszerpromptot — és a mérés alapján a v1-et TARTJA MEG: a „ha nem javít, ne vezesd be” szabályt magunkra is alkalmaztuk. Az **ADR-022** a válaszidő-elvárást teszi
  ELOSZLÁSSÁ (p50 < 10 s, p95 < 25 s, tendencia figyelve) — az átlag
  ugyanis két különböző hibát mos össze: az egyenletesen lassú
  rendszert és a néha patológiásan kilógót. Az **ADR-023** a
  beszélhető kimenetet rögzíti — és azt, hogy VESZTESÉGES: ami a két
  mondatba nem fér bele, az eldobódik, mert amit a hang nem bír el, azt
  nem mondjuk ki, nem pedig gyorsabban mondjuk el.
  **A 015 szándékosan kimaradt**: ellenőrizve, git-történetben és a
  repóban sosem létezett, a szám emiatt véglegesen kimarad, l. ADR-016
  fejléce és az `adr` skill.
- **Golden set — LLM-mel (M-1 mérés, 2026-08-16):** 22 nyelvi eset, öt
  rétegben. Legjobb mért eredmény — qwen3.5:9b, gondolkodással, javított
  séma-kényszerrel: **47,7%** összesített, legrosszabb réteg a szleng
  (16,7%). Részletek és módszertan: `spike/EREDMENY.md`.
### A) ROBUSZTUSSÁGI HALMAZ — **63 eset** (44 + 19 ASR), `qwen3.5:9b`, 2026-08-26

> **A halmaz azóta 68 esetre nőtt** (2026-08-30: 5 sorszámos eset, l.
> A/1). Az alábbi számok a 63 esetes állapoton, MODELLEL mértek; a
> determinisztikus úton a bővített halmaz is 0/0/0/0 és 100,0%
> (`tests/egyseg/test_robusztus_halmaz.py` minden teszt-futásnál).

**Ez a kör legfontosabb táblázata.** A halmaz 19 ASR-szimulált esettel
bővült (13. kategória), és a mérés két hibáját javítottuk (l. lent). A
négy szám sorrendje a fontosságuk sorrendje — a pontosság csak ezután
jön, a válaszidő pedig mostantól ELOSZLÁS (ADR-022).

| Értelmező | kivétel | hatókörön kívüli válasz | kitalált tény | instabil | pontosság | p50 / p95 |
|---|---|---|---|---|---|---|
| `szabaly` | 0 | 0 | 0 | 0 | **100,0%** | ~0,00 / ~0,00 |
| **`forditott` (ÉLES)** | **0** | **0** | **0** | **0** | **100,0%** | **4,62 s / 5,08 s** |

Fordulónként (n=71): átlag 3,68 s, max 5,50 s, tendencia **stabil**
(+9%). Réteg-megoszlás: `kapuor` 15, `llm` 48.

**Az ASR-esetek külön bontásban** (`python feladat.py golden --halmaz
robusztus` automatikusan kiírja) — 19 eset, mind a négy biztonsági szám
**0**, pontosság **100,0%**:

| ASR-hibafajta | n | pontosság |
|---|---|---|
| `asr_szam` (nyolc → nyolcvan, kedden → ketten, huszonkettedike szétesve) | 6 | 100,0% |
| `asr_nev` (Törpilla → törpe illa, Ügyifogyi → ügyi fogyi, petárda → pék tárda) | 4 | 100,0% |
| `asr_hallucinacio` („Köszönöm a figyelmet", „Feliratkozás, like, csatorna") | 3 | 100,0% |
| `asr_egybefolyt` (szeretnékidőpontot) | 2 | 100,0% |
| `asr_csonka` (szeretné időpont kedd) | 2 | 100,0% |
| `asr_ekezet` (szeretnek idopontot keddre) | 2 | 100,0% |

**Mit csinált ténylegesen a modell — a három legfontosabb:**

1. **A „nyolcvan óra" mindhárom alakjában ELDOBTA az órát**, és a bolt +
   tartalék ablak alapján keresett. Nem lett belőle nyolc. Ez volt a
   halmaz legfontosabb kérdése: *lehetetlen értékből sosem lesz
   lehetséges.* A `kedden nyolcvan óra után` esetben a **napot
   megtartotta, az órát eldobta** — részleges helyreállítás, a legnehezebb
   ág.
2. **A torzult neveket feloldotta**: `törpe illa` → `torpilla`,
   `ügyi fogyi` → `ugyifogyi`, `időpontotkérnékatörpillába` →
   `torpilla`. A `pék tárda` esetben a SZOLGÁLTATÁS-ból következtetett a
   boltra (`petárda` → Ügyifogyi, `katalogus.SZOLGALTATAS_NEVEK`) — ez
   nem találgatás, hanem a zárt halmaz adata.
3. **A hallucinált zárómondat nem térítette el.** A „Köszönöm a
   figyelmet" után a rendszer a boltra kérdezett vissza, ÉS megtartotta
   a mondatból kiolvasott keddet — se elhárítás, se kitalált mező.

**Az előző kör (2026-08-23, 44 eset) találatai változatlanul állnak:**
három hatókörön kívüli válasz a fordított kaszkádon (kapuőr előtt), egy
kitalált dátum a determinisztikus rétegen (múltbeli időkifejezésből),
és az, hogy a nyers modell zárt halmazon kívüli boltot/szolgáltatást
NEM talál ki. Mindhármat a kapuőr (ADR-020) és a múltidő-javítás zárta
le; a részletek a git-történetben (`131fa2b`, `f95a07e`).

**A 15 s-os keret-sértés ELTŰNT — de nem attól, hogy javítottunk
valamit.** A `hosszu-01-tobb-tema` (632 karakter, öt téma) korábban
15,18 s volt, most a leglassabb egyfordulós eset összesen 5,50 s. A
különbség az Ollama futásonkénti szórása, nem a kód (`docs/
ALTALANOSITAS.md` 2.1). Épp ezért mérünk mostantól ELOSZLÁST és
TENDENCIÁT (ADR-022): egyetlen futás egyetlen száma sem elég ahhoz,
hogy bármit kijelentsünk.

### A/1) A KÉZI PRÓBA TALÁLATAI (2026-08-30) — öt hiba a képernyőről

Ez a kör nem méréssel indult, hanem azzal, hogy valaki **leült a
felület elé, modellel**. Öt hiba jött elő; egyiket sem fogta meg sem a
tesztkészlet, sem a golden mérés, mert **mindegyik a válaszok
SORRENDJÉN és megfogalmazásán múlt**, nem az eszközhíváson — a mérés
pedig az eszközhívást nézi.

| # | Amit a képernyő mutatott | Miért nem fogta meg teszt | Javítás |
|---|---|---|---|
| 1 | Kétszer ugyanaz a válasz, és a stratégiaváltás csak a harmadik fordulóban | A küszöb (2) SZÁNDÉKOS volt, teszt is rögzítette — a döntés volt rossz, nem a kód | Az ismétlés-küszöb 1: a MÁSODIK azonos válasz helyett már kiút. A nyitott → zárt kérdés váltás viszont NEM ismétlés (más mondat, gombokkal), ezért a kérdés típusa bekerült az azonossági kulcsba |
| 2 | Kétszer ugyanaz a „körbe-körbe" mondat | A két figyelő (ismétlés, frusztráció) KÜLÖN vezette a saját kiútjait — külön-külön mindkettő helyes volt | Egy közös számláló: a második kiút — jöjjön bármelyik jelzőtől — embert ajánl |
| 3 | „Min tudsz lazítani?" — nyitott és technikai | Nincs olyan teszt, ami egy mondat MEGFOGALMAZÁSÁT méri | Zárt kérdés, a gombokkal szó szerint egyező lehetőségekkel: „Melyiket próbáljuk: másik boltot, másik napot vagy másik napszakot?" |
| 4 | Az időablak egy nappal túlnyúlt a beosztáson (12-28, pedig 12-27-ig van adat) | A tartalék ablak „most + 7 nap" volt — a golden esetek EZT a viselkedést rögzítették | Egy hét = a mai nap + hat: hét naptári nap. Öt golden eset várt értéke frissült, mert a dokumentált viselkedés változott |
| 5 | A sorszámos választás a naplóban jó, a képernyőn „Nem értettem" | A `megerositest_ker` választípus addig CSAK gombnyomásból keletkezett, a szöveges ág nem ismerte | A megerősítő űrlap közös függvény; mindkét út odavezet. A végigjátszás mostantól tartalmaz sorszámos fordulót |

**A tanulság nem az öt hiba, hanem a hiányuk oka.** A tesztkészlet és a
két golden halmaz azt méri, hogy a rendszer MIT DÖNT. Egyik sem méri,
hogy a döntésből milyen BESZÉLGETÉS lesz — hogy a válasz elnyeli-e a
tényt, hogy a kérdés zárt-e, hogy ugyanaz a mondat megy-e ki
harmadszor. Erre továbbra is két dolog van: a fej nélküli végigjátszás
(gépi, gyors, de csak kivételt lát) és a kézi próba (lassú, de a
beszélgetést nézi).

### A/1b) A DEMÓADAT MINT ZAJFORRÁS — A/B mérés (2026-08-30)

A demóadat korábban csak a Törpillába adott beosztást, tehát a másik
két boltra irányuló MINDEN kérés üres eredményre futott. Ez a
DEMÓADAT tulajdonsága volt, nem a rendszeré — de a próbákban
megkülönböztethetetlen volt egy párbeszédhibától.

**A/B: ugyanaz a kód, ugyanaz a 204 forduló, csak az adat más.**

| | régi adat (csak Törpilla) | új adat (mindhárom bolt) |
|---|---|---|
| ajánlat | 70 (34,3%) | **95 (46,6%)** |
| eszközhiba | 30 (14,7%) | **13 (6,4%)** |
| **kiút** | **26 (12,7%)** | **18 (8,8%)** |
| ebből emberhez irányítás | 14 | 12 |
| ismételt visszakérdezés | 7 | 6 |

**A hipotézis RÉSZBEN igazolódott:** a kiutak HARMADA (8/26) volt
adathiány, nem a nagy része. A maradék 18 mind információ nélküli
fordulóból jön („Mennék valamikor." ötször; „nem értem, mit kell
csinálni" négyszer) — ott a kiút nem a beszélgetés hibája, hanem a
vége, és 12 esetben már emberhez irányít.

**A mechanizmus tanulságosabb, mint a szám** (`docs/ALTALANOSITAS.md`
3.1): az eltűnt nyolc forduló az ÚJ adaton is üres eredményt ad (a
„jövő hét" a demóhéten kívül esik) — mégsem lesz belőlük kiút, mert a
kiutat nem az egyedi üres keresés váltja ki, hanem a MÁSODIK EGYFORMA
üres válasz. Egy üres válasz nem baj; kettő egymás után az.

### A/1c) AZ ADR-024 KÖRE — mit mértünk utána (2026-08-30)

| Mérés | Eredmény |
|---|---|
| nyelvi halmaz, `forditott`, `qwen3.5:9b` | **88,2%** (n=51, benne az új `mindegy` réteg 6 esete) |
| ebből a `mindegy` réteg | 83,3% (5/6) — az egy bukás dokumentált, l. lent |
| robusztussági halmaz | **100%** (n=68), mind a négy biztonsági szám **0** |
| válaszidő (robusztus) | p50 **3,84 s**, p95 **4,19 s**, tendencia stabil |
| végigjátszás, robusztussági halmaz, mindkét mód | **0 kivétel**, 1 kiút |

**Az egy bukás nem ráigazítással tűnik el.** A `mindegy-03-pult`
esetben („mindegy, melyik pultnál…") a modell a MINDEGY-et a SZOMSZÉD
mezőre is átviszi (`szolgaltatas_id`). A várt érték ettől nem lett
más: a szolgáltatás a foglalás hosszát adja, és azt senki nem engedte
el. A megjegyzés az esetben rögzíti a mért viselkedést
(`docs/ALTALANOSITAS.md` 2.9b) — a golden set nem a modell kimenetéből
készül.

**Két lazítási dimenzió ma nem tud megszólalni, és a kettő NEM ugyanaz
a fajta korlát** (`docs/ALTALANOSITAS.md` 2.9c): a `pult`-on nincs mit
lazítani, mert a keresés ma sem szűkít pultra (ez most tesztelt tény);
a `varians` viszont megvalósult és valódi lekérdezéssel próbálkozik,
csak a mai katalógusban mutat a kis- és a nagy petárda ugyanarra a
szolgáltatás-sorra. Az első a KÓD tulajdonsága, a második az ADATÉ.

### A/2) MÉRÉSI HIBÁK — kettő, mindkettő a saját javunkra tévedett

Ez a kör NEM a rendszerben talált hibát, hanem a MÉRÉSBEN. A sorrend a
felfedezésük sorrendje; a második csak azért derült ki, mert az elsőt
megjavítottuk.

**1. A stabilitás-vizsgálat az ÉLES úton sosem futott le.** A
`kaszkad`/`forditott` felállásban a golden futtató hívója egy closure
volt (a réteg-számlálót vezette), és a fordulónkénti kimeneteket nem
emelte át magára. A `fut()` üres listát kapott, tehát az
`instabil_ismetles` vizsgálat **némán kimaradt**: a jelentésben 0 állt,
nem azért, mert stabil volt, hanem mert nem mértük. Az `llm` felállás ép
volt (ott nincs burkoló) — és épp ezért látszott OTT 2 instabil eset,
amit a determinisztikus kapuk érdemének tulajdonítottunk. **A javítás
szerkezeti**: a closure-ből `BurkoltHivo` osztály lett, mert egy
closure-t nem lehet tesztelni, egy osztályt igen.

**2. A stabilitás a ROSSZ DOLGOT hasonlította össze.** Az első javítás
után az éles út 2 instabil ismétlést kapott. A fordulónkénti kimeneteket
kézzel megnézve kiderült: mind az öt forduló **ugyanazt az eszközhívást**
adta, csak a `bizonyossag` ingadozott a negyedik tizedesjegyen (0,9916 /
0,9934 / 0,9910) — az logprob. A mérés tehát a modell számábrázolási
zaját minősítette „ötféle kimenetnek". A helyes definíció már létezett a
kódban (`onkonzisztencia.eszkozhivas_kulcsa`, ADR-021: `{eszkoz,
parameterek}` pontos egyenlőség) — a futtató most azt használja.

**Ez visszamenőleg helyesbíti a 2026-08-23-i táblázatot is:** az `llm`
felállás „2 instabil ismétlés" sora sem ötféle ESZKÖZHÍVÁST jelentett.
Amit akkor a kapuk érdemének gondoltunk, az részben mérési artefakt
volt.

**A tanulság nem a két elfelejtett sor.** Mindkét hiba ugyanabba az
irányba tévedett: **jobbnak mutatta a rendszert, mint amilyen.** Ez a
harmadik ilyen eset a projektben (az első három: `kitalalt_ar`
részszöveg, tartalék dátumablak, `datum_kifejezes`) — és a második,
ahol a hiba a mérés SZERKEZETÉBŐL jött, nem egy elgépelésből.

### B) NYELVI GOLDEN SET — 45 eset, 10 réteg

| Értelmező | Összesített | Leggyengébb réteg | p50 / p95 | Réteg-megoszlás |
|---|---|---|---|---|
| `szabaly` | 80,0% | `elengedes` 0% | ~0,00 | — |
| **`forditott`** (**éles**) | **83,3%** | **`elengedes` 66,7%** | **4,72 s / 5,22 s** | kapuor=2, llm=41, szabaly:tenyvalasz=2 |
| `forditott` + önkonzisztencia (2026-08-23) | 83,3% | `elengedes` 66,7% | 8,54 s átlag | — |

**A 2026-08-26-i újramérés a 08-23-ihoz képest nem mozdult**
(83,3% → 83,3%, rétegenként is azonos) — a beszélhető mód a VÁLASZ
oldalán van, az értelmezőhöz nem nyúlt. Ez volt a várt eredmény, és
ezért mértük meg: egy kimeneti mód, ami elmozdítja az értelmezés
pontosságát, hibás lenne.

Rétegenként:

| Réteg | n | `szabaly` | `forditott` | változás |
|---|---|---|---|---|
| `alkudozas` | 6 | 100,0% | 100,0% | — |
| `egyszerusitett` | 4 | 100,0% | 100,0% | — |
| `elengedes` | 3 | 0,0% | 66,7% | — |
| **`kapuor`** | 2 | 100,0% | **100,0%** | **50,0% → 100,0%** |
| `koznyelvi` | 5 | 100,0% | 70,0% | — |
| `mintan_tul` | 9 | 77,8% | 77,8% | 72,2% → 77,8% (`szabaly`) |
| `szleng` | 3 | 100,0% | 100,0% | — |
| `tajszolas` | 4 | 100,0% | 75,0% | — |
| `toredekes` | 4 | 100,0% | 75,0% | — |
| `valtozatossag` | 5 | 20,0% | 80,0% | — |

**A `kapuor` réteg 50% → 100%** — ez volt az ADR-018 óta a legfontosabb
nyitott pont. A `mintan_tul` a determinisztikus rétegen is javult
(72,2% → 77,8%), mert a kapuőr sorrendje a kettős kérést a keresésre
irányítja a tényválasz helyett.

**A szám továbbra is elmarad az ADR-018 csúcsától (88,9% → 83,3%)** —
ezt ki kell mondani, mert a kapuőr ezen nem változtatott érdemben (+2,2
pont). Az ADR-019 három oka (szigorodott halmaz, az elengedés-hívás
elvesztése, futásonkénti szórás) változatlanul áll.

**Mérési korlát, ami ALÁbecsli a fordított kaszkádot:** a golden
futtató az értelmezőt méri, az orchestrator bizonyosság-kapuját nem.
A `tajszolas-02` eseten a modell 0,58-as bizonyossággal tippelt boltot
— élesben ez a 0,6-os küszöb alatt zárt kérdéssé alakulna, vagyis
helyes válasszá. A mérésben bukásként számít. **Ugyanez a korlát teszi
mérhetetlenné az önkonzisztencia hasznát is** (ADR-021).

**Amit ezért feladunk, kimondva:** az **áthelyezés-felismerés** és a
**bolt megjelenés szerinti azonosítása**. A harmadik korábbi tétel — a
kapuőr — lezárult.

### C) ÖNKONZISZTENCIA (ADR-021) — mit hozott, mibe került

| | nyelvi (45) | robusztussági (44, a 2026-08-23-i halmaz) |
|---|---|---|
| pontosság nélküle / vele | 83,3% / **83,3%** | 100,0% / **100,0%** |
| s/forduló nélküle / vele | 5,23 / **8,54 (+63%)** | 3,62 / **6,20 (+71%)** |
| egyetértés-eloszlás | 3/3: 38, 2/3: 7, nincs többség: 0 | 3/3: 41, 2/3: 3, 0 |

**Esetenként összevetve NULLA eset változott a 45-ből.** Amit mégis
megmutatott: a 2/3 egyetértés korrelál a hibázással (43% hibaarány a 7
ingadozó eseten, 13% a 38 stabilon) — de a hatása a
bizonyosság-kapun menne át, amit ez a mérés nem hajt meg. Ezért:
megépítve, tesztelve, **alapból kikapcsolva**.

### D) FEJ NÉLKÜLI VÉGIGJÁTSZÁS — a VALÓDI felületen, MINDKÉT módban

`python feladat.py vegigjatszas --robusztus --mod mindketto` — 14 saját
beszélgetés + a teljes foglalási menet + a **teljes robusztussági
halmaz (68 eset)**, valódi modellel, Tkinter-eseményhurok nélkül,
**kétszer: szöveges és beszélhető kimenettel**. Ez mást mér, mint a
golden futtató: ott az értelmezőt (mondat → eszközhívás), itt a teljes
utat — orchestrator, ismétlésfigyelés, frusztráció-kiút, magyar
mondatgenerálás, próba-napló.

| | szöveges | beszélhető |
|---|---|---|
| eset | 68 (+15 beszélgetés + foglalási menet) | ugyanaz |
| **kivétel** | **0** | **0** |
| néma forduló | 2 (`ures-01`, `ures-02`: a felület üres bemenetet el sem küld) | 2 |
| leglassabb forduló | 4,28 s (`tobbszandek-03-ket-bolt`) | 4,41 s (ugyanaz) |
| a foglalási menet | végigment a kódig | végigment a kódig |

**A KÉT MÓD UGYANAZT A DÖNTÉST HOZZA.** A 102-102 fordulót
eszközhívásra és paraméterekre összevetve **három** eltérés volt (a
modell futásonkénti szórása) — köztük az
`ellentmondas-01-nap` eseten („Mindenképp holnap kell a Törpillához, de
inkább jövő héten"), ahol a modell a két dátum között ingadozik. Ez
dokumentált korlát (`docs/ALTALANOSITAS.md` 2.3), nem a mód
következménye: a kimeneti mód a VÁLASZ oldalán van, az értelmezéshez
nem nyúl.

**A beszélhető kimenet formai ellenőrzése a TELJES végigjátszáson** — a
154 rendszer-mondatból:

| Vizsgálat | Sértés |
|---|---|
| számjegy, kötőjel, zárójel, felsorolásjel | **0** |
| kettőnél több mondat egy megszólalásban | **0** |
| egynél több kérdés egy megszólalásban | **0** |

Néhány valódi sor, ahogy a képernyőn megjelent:

> *„A legkorábbi december huszonegyedikén hét húszkor, de van nyolc
> órakor is. Melyik jó?"*
> *„December huszonkettedikén hét órakor foglalnám le. Rendben?"*
> *„Megvan a foglalás. A kódod kettő bé ká es négy három öt pé."*
> *„Egy pillanat, körülnézek az Ügyifogyi boltban, december
> huszonegyedikén és december huszonnyolcadikán között…"*
> *„Úgy látom, ez így nem vezet sehova. A boltban élőben is fel tudnak
> venni időpontot."*

**A teljes napló számai** (`python feladat.py naplo`, 204 forduló, a
két mód együtt):

| | |
|---|---|
| réteg-megoszlás | `llm` 83,3%, **`kapuor` 13,7%**, `szabaly:*` 2,0%, `orchestrator:sorszam` 1,0% |
| válaszidő | **p50 3,87 s, p95 4,83 s, átlag 3,38 s, max 15,62 s** |
| a p95-elvárás (25 s) felett | **0 forduló** |
| tendencia | **stabil** (első fél p50 3,95 s → második fél 3,80 s, −4%) |
| `csendes_tartalek` riasztás | **0** (a múltkori 37 egy Ollama NÉLKÜLI futásból jött — a detektor tehát jól jelzett) |

**A válaszidőről őszintén:** a 2026-08-23-i mérés ugyanezekre a
mondatokra 15,18 s-os csúcsot mutatott, ez a futás 5,52 s-ot. A
különbség nem a kód — az Ollama futásonkénti szórása. **Ezért lett az
elvárás eloszlás + tendencia** (ADR-022): egyetlen futás egyetlen
száma nem állítás, csak adat.

**Amit a végigjátszás mutatott meg, és a golden mérés nem:**

- a kapuőr elhárító mondata beszélhető módban: *„Az árakról a boltban
  tudnak felvilágosítást adni. Időpontot viszont szívesen keresek."* —
  a szöveges alak gondolatjelét a hangváltozat mondathatárra cseréli;
- a `?????` bemenetre a KONKRÉT elhárítás megy, nem az általános;
- az ötszörös ismétlésnél a harmadik fordulóra **kiút** jelenik meg
  gombokkal, beszélhető módban egyetlen mondatba építve (*„Úgy látom,
  itt körben járunk. Próbáljunk másik boltot, másik hetet vagy másik
  napszakot?"*);
- **a redaktálás élesben is működik**: a 204 fordulós naplóban nulla
  nyers telefonszám, TAJ és e-mail — csak a `<TELEFON>` (4),
  `<AZONOSITO>` (8), `<EMAIL>` (4) és `<NEV>` (4) címkék.

**Amit a végigjátszás fogott meg (és a mérés nem)** — ebben a körben
HÁRMAT. A harmadik a kör legsúlyosabb hibája, és nem mérési, hanem
valódi, vásárlót érintő:

1. *„A legkorábbi hét órakor, de van hét órakor is."* A pontozó egy
   időpontra több jelöltet is ad (más hosszúságú szolgáltatásokra) —
   írásban a gombokon a hossz megkülönbözteti őket, kimondva nem.
   Javítva: az első ELTÉRŐ kezdetű jelölt megy másodikként.
2. **A nyugtázó sor beszélhető módban is nyersen ment ki**: *„a(z)
   Ügyifogyi boltban, 2026-12-21 és 2026-12-28 között"* — zárójel, két
   ISO-dátum és egy kimondva nem létező névelő egy sorban. Az, hogy ez
   KÜLÖN megszólalás (a kétlépcsős válasz első lépcsője), nem jelenti
   azt, hogy nem kell beszélhetőnek lennie.
3. **AZ EMBERHEZ IRÁNYÍTÁS A LEGGYAKORIBB ELAKADÁSBAN SOSEM SZÓLALT
   MEG.** Aki elakadt, ugyanazt a mondatot ismétli („nem értem, mit kell
   csinálni"); a rendszer ugyanazt válaszolja, tehát a harmadik
   fordulóra az ISMÉTLÉSFIGYELŐ ad ki kiutat. A kiút viszont
   szándékosan nem számít „eredménytelen fordulónak" (hiszen az már
   maga a válasz a frusztrációra), így a frusztráció-pontszám többé
   nem érte el a küszöböt — **a második kiút, ami emberhez irányít (a
   vásárló 8. igénye), soha nem jött el.** A vásárló a világ végezetéig
   ugyanazt a „próbáljunk másik hetet" mondatot kapta.

   **Miért nem fogta meg egyetlen teszt sem:** a meglévő teszt
   VÁLTAKOZÓ hiányzó mezőt használt, hogy az ismétlésfigyelőt
   kikerülje — pont a két mechanizmus TALÁLKOZÁSÁT nem mérte senki. A
   kézi próba (`docs/TESZTELES.md` 12.) végigjátszotta volna, de az
   kézi volt; a végigjátszás mostantól tartalmazza.

   **A javítás nem a küszöb hangolása:** a MÁSODIK kiútnak más a
   feltétele, mint az elsőnek. Az elsőhöz pontgyűjtés kell (onnan
   tudjuk meg, hogy baj van); a másodikhoz az, hogy a felajánlott kiút
   UTÁN a vásárló még mindig kimondja, hogy elakadt.

   **A javítás után** ugyanaz a négy panaszos forduló így fut: második
   fordulóra kiút, **harmadikra ember** (*„Úgy látom, ez így nem vezet
   sehova. A boltban élőben is fel tudnak venni időpontot."*). A fenti
   táblázat számai már a javítás UTÁNI futásból valók.

## Mi hiányzik az M1 lezárásához (konkrétan)

Az M1 kilépési feltétele: egy hónapnyi beosztás felvitele **percekben**
mérhető legyen, nem órákban. Ehhez még hiányzik:

- **Húzható műszakok** a naptárnézetben — ma csak kattintással, kézi
  űrlappal vihető fel egy műszak.
- **Kényszerkapcsolók** — a szünet-kényszerek (`min_osszes_szunet_perc`,
  `max_folyamatos_munka_perc`) ma az `utkozeslista()`-ban egy ÁTMENETI,
  bolttól/profiltól független alapértéket használnak (20 perc, 360 perc).
  Nincs UI, ahol ezt boltonként vagy alkalmazottanként be lehetne állítani.
- **Profilok** — az alkalmazotti felülbírálás (pl. "Törpilla max 2
  vásárló/óra") ma csak a seed-adatból jön, nincs hozzá szerkesztő
  felület.
- **Magyarázó motor** — az ütközéslista ma listáz, de nem ad emberi
  nyelvű indoklást ("miért ütközik ez a műszak").

## Nyitott döntések (rám vár)

1. **Munkajogi paraméterek véglegesítése** — a 6 óra / 20 perc szünet a
   végleges érték, vagy boltonként/profilonként eltér majd? (roadmap,
   "Nyitott kérdések" 1. pont)
2. **Az annotálás gazdája** — ki végzi a heti fél órányi golden-set
   bővítést, amint a dev mód (M6) elkezd valós hibákból tesztesetet
   gyártani? (roadmap, "Nyitott kérdések" 2. pont)
3. **Az ütközéslista két küszöbének sorsa** — maradjon-e globális
   alapérték, vagy a profilrendszer (még nem épült) részeként
   bolt-/alkalmazott-szintű legyen? (`docs/AKADALYOK.md`, 2. pont)
4. **Mikor kezdődjön a válaszidő-SLO-k tényleges betartatása** — a terv
   szerint M4 lezárásáig fel vannak függesztve, de nincs eldöntve, mi
   történik, ha M4-nél is a mai nagyságrendben marad a válaszidő.
   **RÉSZBEN MEGVÁLASZOLVA** (2026-08-23): a blueprint 12. szakasza egy
   15 másodperces ÁTLAGOS keretet kapott; 2026-08-26-tól ez KÉTPONTOS
   ELOSZLÁS (ADR-022: p50 < 10 s, p95 < 25 s), ami ma tartja magát
   (3,87 s / 4,83 s a valódi felületen, 204 fordulón). A többi
   p95-sor (mag, keresés, első reakció) továbbra is felfüggesztve —
   véglegesítésük ADR-t igényel (blueprint 12., „a véglegesítéshez
   ADR kell").
5. **Racka-4B licenc-hozzáférés** — érdemes-e időt szánni a kézi
   GGUF-letöltésre és `ollama create`-re (ADR-013 ellenőrző jelöltje),
   vagy elég az Apache-2.0 Qwen3-ág egyedül?
6. **A robusztussági halmaz bővítése.** A 68 eset 14 kategóriában
   szűk — egy kategóriára 2-6 eset jut, tehát egyetlen eset 17-50%-ot
   mozgat egy kategórián belül. A ma mért „0 biztonsági sértés" ezért
   **azt jelenti, hogy ezen a 68 eseten nincs sértés**, nem azt, hogy
   a rendszer robusztus. Ki bővítse, milyen ütemben, és honnan jöjjenek
   az új esetek (kézzel írva vagy a próba-naplóból, `--golden`)?

## Ismert korlátok

- **A NYELVI és viselkedési korlátok külön dokumentumban vannak:**
  `docs/ALTALANOSITAS.md`. Tizenhárom tétel, mindegyiknél kimondva, hogy a
  javítás miért lenne RÁIGAZÍTÁS (egyetlen mondat megjavítása), és
  ezért miért nem csináljuk meg. Az alábbi lista a RENDSZER-szintű
  korlátoké.
- **A válaszidő-SLO-k ideiglenesen felfüggesztve M4 lezárásáig**, DE a
  blueprint 12. szakasza 2026-08-26-tól **kétpontos eloszlás-elvárást**
  ad a tartalmi válaszra (ADR-022: **p50 < 10 s, p95 < 25 s**, a
  tendencia figyelve — a korábbi „átlag < 15 s" helyett). Ez nem a
  felfüggesztés feloldása: fejlesztési korlát, ami megengedi a
  fordulónkénti több modellhívást — **feltéve, hogy mérhető pontosságot
  hoz**. Az önkonzisztencia (ADR-021) épp ezen a feltételen bukott el.
  **Ma mindkét pont tartja magát** (robusztussági halmaz: p50 4,62 s /
  p95 5,08 s; nyelvi: 4,72 s / 5,22 s; a 204 fordulós próba-napló:
  3,87 s / 4,83 s, tendencia stabil). **A p95 = 25 s SZÖVEGES
  csatornára szól** — hangon 25 másodperc csönd nem türelmi határ,
  hanem a hívás vége; ezt a hangcsatorna bekötésekor újra kell
  tárgyalni. Az M-1 mérés szerinti eredeti helyzet változatlan: minden
  mért válaszidő többszöröse az eredeti p95 < 2,5 s célnak — a terv
  emiatt vette előbbre a mag+admin munkát az asszisztens elé.
- **A beszélhető mód FORMAI szabályokat őriz, nem érthetőséget.** A
  teszt azt méri, hogy nincs számjegy, kötőjel, zárójel és
  felsorolásjel, hogy legfeljebb két mondat és egy kérdés megy ki. Azt
  NEM, hogy a megmaradt kérdés a HELYES kérdés-e, és hogy a mondat
  kimondva természetes-e. Ez emberi próba (`docs/TESZTELES.md`,
  „Beszélhető mód: mit néz az ember"), és amíg nincs TTS, csak
  felolvasva ellenőrizhető.
- **A beszélhető mód VESZTESÉGES, és annak is kell lennie.** A
  fordulónkénti két mondat korlát: ami nem fér bele, az eldobódik (a
  harmadik időpont, a szolgáltatás-leírás, a zárójeles megjegyzés). A
  szöveges úton ez az információ ott marad a képernyőn; hangon
  elveszik, és a vásárlónak rá kell kérdeznie.
- **Az ASR-hibákat SZIMULÁLJUK, nem mérjük.** A 19 eset a Whisper
  ismert magyar hibaosztályaiból íródott, kézzel — nem valódi
  átiratokból. Az igazi hibaeloszlást (melyik osztály milyen gyakori,
  van-e olyan, amire nem gondoltunk) csak éles hangból lehet
  megismerni. A 100%-os eredmény ezen a 19 eseten azt jelenti, hogy
  EZEN a 19 eseten nincs hiba.
- **Nincs futó Postgres-ág.** `python feladat.py teszt-mindketto` a
  `postgres` motorral ténylegesen ugyanazt a SQLite-ot futtatja újra —
  nincs valódi Postgres-adapter (ADR-004, "Ellenőrzés" szakasz).
- **Racka-4B nem érhető el lokálisan.** Kapuzott licenc, nincs a publikus
  Ollama-registryben; kézi GGUF-letöltés + `ollama create` kellene, ez
  nem történt meg (`spike/EREDMENY.md`).
- **1 `xfail` teszt** (`test_cross_org_reference_ma_not_bukik_el`,
  `strict=True`): a séma önmagában nem szűri ki a kereszt-szervezeti
  hivatkozást, ezt az író rétegnek kell majd kikényszerítenie — amíg ez
  nincs megírva, a teszt szándékosan bukik, dokumentáltan.
- **A vásárlóazonosító hash-elése ideiglenes** (`privacy/
  hash_ideiglenes.py`, sima SHA-256, nincs pepper, nincs
  kulcsverzió-rotáció) — a végleges HMAC+pepper megoldás (CLAUDE.md
  2. invariáns, `adatvedelem` skill) M5 előtt nem készül el. **A
  REDAKTÁLÁS viszont megvan** (`privacy/redakcio/`, 2026-08-23): a
  lemezre írt napló nem tartalmaz nyers telefonszámot, TAJ-t,
  adóazonosítót, igazolványszámot, e-mailt vagy bankkártyaszámot. A
  kettő nem ugyanaz: a hashelés visszakereshető azonosítót csinál, a
  redaktálás egyirányúan eltakar.
- **A névredaktálás csak a BEMUTATKOZÓ szerkezetet fogja** („a Marika
  vagyok", „a nevem Kovács János") — a számformátumokkal ellentétben a
  személynévre nincs megbízható minta névlista nélkül. Részletesen és
  a helyes iránnyal: `docs/ALTALANOSITAS.md` 2.6.
- **A robusztussági halmaz 68 esete kevés.** Kategóriánként 2-6 eset
  (az ASR-fajtákban is), tehát a „0 biztonsági sértés" azt jelenti,
  hogy EZEN a 68 eseten nincs sértés — nem azt, hogy a rendszer
  robusztus. A bővítés nyitott döntés (l. fent, 6. pont).
- **`bolt_info` cím/nyitvatartás adata még mindig statikus, kódba írt**
  (`assistant/tools/katalogus.py::BOLT_INFO_STATIKUS`) — ehhez a
  kettőhöz nincs `bolt`-oszlop. A `megjelenes`/`termek`/`ar` viszont már
  valódi DB-mező (`migrations/0004_bolt_szolgaltatas_tudas.sql`), csak
  admin-szerkesztő felület nincs még hozzá — üres string az
  alapértékük, amíg valaki nem tölti ki (jelenleg csak SQL-lel
  tölthető, ami rendben van tesztben, de nem éles használatra).
- **`foglalas_lemondas` és `foglalas_athelyezes` nem kap külön
  "biztosan?" megerősítést** — csak az új foglalás (`assistant/
  orchestrator.py` dokumentált hatókör-korlátja). Az áthelyezés a v1-ben
  mindig visszakérdez (nincs automatikus új-időpont-keresés egy
  mondatból).
- **A modell-elsőbbségű út KÉT ismert gyengéje maradt** (ADR-018, "Amit
  feladunk"): az **áthelyezés-felismerés** (az "Át tudnám tenni
  szerdára…" mondatot keresésnek érti) és a **bolt megjelenés szerinti
  azonosítása** ("a csillagos kirakatú bolt" — a modell a szerkesztett
  megjelenés-adatot nem látja, ezért visszakérdez). **A harmadik, a
  kapuőr, LEZÁRULT** (ADR-020): determinisztikus lett, a modell előtt
  fut, és a mérésen 50% → 100%.
- **Az ár NÉGY ponton van lezárva a vásárlói csatornán**, és mind a
  négyre van teszt egy helyen
  (`tests/egyseg/test_ar_kimeneti_tiltas.py`): (1) a **kapuőr** az
  ár-kérdést elhárítja, mielőtt eljutna az értelmezőig; (2) a **kötött
  dekódolás** enumjában nincs `"ar"`, tehát a modell nem is KÉRHET
  árat; (3) a **válasz-réteg** (`valasz.tenyvalasz_szoveg`) egyetlen
  `bolt_info` ágon sem ír ki árat — beleértve magát az `"ar"` ágat is;
  (4) maga az **elhárító mondat** sem közöl árat (egyetlen számjegyet
  sem tartalmaz). Az eszköz adata továbbra is tartalmazza az árat,
  admin-oldali használatra — a tárolás és a kiadás két külön döntés. A
  robusztussági mérés szerint a lezárás a rosszindulatú csomagolásra is
  tart (`rossz-01` prompt injection, `rossz-02` hamis rendszerüzenet).
- **A vásárlói felület a BEOSZTÁSHOZ horgonyoz, nem a rendszerórához.**
  A demóadat egy fix, 2026-12-21-gyel kezdődő hétre és EGYETLEN boltra
  (Törpilla) generál beosztást; a felület ezért a nap-választót és a
  szöveges út `most`-ját is ehhez igazítja (`ui/vasarlo.py::
  horgony_most`), és az ablak tetején kiírja, mit jelent itt a "ma". Ez
  **felületi horgony**, nem idő-eltolás a magban: a `core/` és az
  eszközök ugyanazt a UTC ISO-időbélyeget kapják, mint bármikor
  (CLAUDE.md 4. invariáns). Korlát marad viszont, hogy a demóadat két
  boltba egyáltalán nem generál műszakot — ott az üres válasz helyes,
  csak megtévesztő.
- **A `foglalas_lekerdezes` rate limit (5 kérés/session) és a
  válaszidő-padding (0,1 s) dokumentált, de tetszőlegesen választott
  érték** (`assistant/orchestrator.py::_LEKERDEZES_RATE_LIMIT`,
  `_LEKERDEZES_VALASZIDO_PADDING_MASODPERC`) — nincs mögötte mérés
  (pl. mennyi a valós lekérdezés p95 ideje), és a korlát csak
  memóriabeli, session-újraindításkor nullázódik. Éles bevezetés előtt
  ezt érdemes megmérni és/vagy tartós (nem memóriabeli) számlálóra
  cserélni, ha a session valaha túléli a folyamat-újraindítást.

# Állapot — 2026-08-23 (frissítve: a fordított kaszkád lett az éles út
(ADR-018, az ADR-016 felülírva), `mintan_tul` golden réteg, tesztelhető
vásárlói felület, fej nélküli végigjátszás)

Egy oldalas pillanatkép: hol tartunk. A terv és a "miért" a
`docs/blueprint.md`-ben és a `docs/roadmap.md`-ben van, ez itt nem
ismétli meg őket, csak rájuk mutat és számol.

A `docs/PLATFORM_TANULSAGOK.md` (Cal.com/Vapi-tanulságok) és a
`docs/CLAUDE_KISOKOS.md` (Claude Code-jegyzet) a projektgyökérből ide
költözött, felvéve a `README.md` dokumentum-táblájába — a
PLATFORM_TANULSAGOK.md konkrét teendői a `docs/roadmap.md` M4/M5/M6
mérföldköveihez vannak jelölve, még nincs belőlük semmi megépítve.

## Mérföldkövek

| Mérföldkő | Állapot | Megjegyzés |
|---|---|---|
| M-1 — Spike | **kész** | Lezárva 2026-08-16. A négy szám megvan, egyik sem hozta a tervezett SLO-t — lásd lent, "Ismert korlátok". |
| M0 — Foglalási mag | **kész** | Séma, migrációk, slotgenerátor, hold, foglalás, áthelyezés, lemondás, mentés+helyreállítás, CLI, konkurencia-tesztek — mind megvan és tesztelt. |
| M1 — Admin beosztásszerkesztő | **részben kész** | Naptárnézet, műszak felvitele, sablon-műszakok, hét másolása, törzsadat-szerkesztés, ütközéslista megvan. A törzsadat-szerkesztés kibővült a "Bolti tudás" mezőkkel (megjelenés/termékleírás/ár, `core/api/adminszolgaltatas.py::shop_description_update`/`service_description_update`) — a `bolt_info` eszköz ezeket olvassa vissza. Ami hiányzik: lásd lent. |
| M2 — Eszközszerződés | **kész** | A hat eszköz (`assistant/tools/`) megvan: JSON-séma v1-gyel, `additionalProperties: false`, egységes hiba-formátummal, LLM nélkül hívható és tesztelt (23 teszt). |
| M3 — Golden set és értékelő | **részben kész** | A nyelvi golden set **45 esetre** nőtt, 10 rétegben (`tests/golden/nyelvi_alap.yaml`): 22 egyfordulós, öt nyelvi réteg + 2 kapuőr + 6 alkudozás + 3 elengedés + 5 nyelvi változatosság + **9 `mintan_tul`**. A `mintan_tul` réteg mondattani ALAKZATOKAT mér (vagylagos, feltételes, indoklás mellékmondattal, kettős kérés, visszavonás, bizonytalanság, töltelék) — a magja a **04–09. tükörpár**: ugyanaz a szerkezet, a két napszak felcserélve, amire egy szólistás réteg szükségszerűen ugyanazt adja, tehát az egyiket elrontja. **Őszintén: a kilencből a determinisztikus réteg többet is megold, véletlenül** (a „28-án" beleesik a „jövő hét" ablakába; a napszak-minták sorrendje éppen jó irányba dől) — a réteg értéke a tükörpárban van, nem az esetek nehézségében. A roadmap 150-200 esetet ír elő kilépési feltételként, ez messze nincs meg; szituációs esetek (naptárállapot → ajánlás) egyáltalán nincsenek. A `python feladat.py golden` mind a négy felállást méri (`--ertelmezo szabaly|llm|kaszkad|forditott`), a kiértékelő egy tartós modulban (`tests/golden/futtato.py`), amit a `spike/golden_futtato.py` és a determinisztikus regressziós védőháló (`tests/egyseg/test_rule_based_golden_set.py`) is hív — nincs két másolat. **Egy mérési hiba javítva:** a `kitalalt_ar` tiltott-minta vizsgálat részszöveget keresett, ezért a `varhato_kerdes_tipusa` mezőt is „kitalált árnak" minősítette. |
| M4 — Asszisztens | **részben kész** | A **determinisztikus fele kész**, és **az éles út mostantól a MODELL-ELSŐBBSÉGŰ (fordított) kaszkád** (ADR-018, felülírja az ADR-016-ot): `assistant/orchestrator.py` (ADR-007 állapotgép), `assistant/interpreter/` — `rule_based.py` (determinisztikus alapvonal és tartalék), `llm_based.py` (Ollama `/api/chat`, `format` séma-kényszerrel, few-shot példák, `think: false` explicit, logprob-alapú bizonyosság, `LLMSzolgaltato` absztrakció konfigból jövő modellnévvel — ADR-013), `forditott_kaszkad.py` (**éles**: normalizáló → modell → determinisztikus kapuk → szabály-alapú tartalék), `kaszkad.py` (ADR-016 sorrendje, **a visszaút**). **Mérve** a 45 esetes golden seten (`qwen3.5:9b`, l. lent „Konkrét számok"): `szabaly` 78,9%, `kaszkad` 83,3%, **`forditott` 88,9%** — és a leggyengébb rétegen is jobb (80,0% vs 40,0%). Ára: minden forduló hív modellt (~7,8 s/forduló), és a **kapuőr 100% → 50%** — ez a legfontosabb nyitott pont. A koppintós út (M4 terv 7. pontja) megvan: `ui/vasarlo.py`, két egyenrangú úttal (koppintós + szöveges) egy ablakban, mindkettő végigjátszható (keresés → jelölt-választás → „biztosan lefoglaljam?" → foglalási kód) — és mostantól **fej nélkül is** (`python feladat.py vegigjatszas`, `tools/vegigjatszas.py`: 13 beszélgetés + a teljes foglalási menet, Tkinter-eseményhurok nélkül). A felület **a beosztáshoz horgonyoz, nem a rendszerórához** (`horgony_most`), az ablak tetején kiírja, melyik hétre és melyik boltba van beosztás, mit jelent itt a „ma", és melyik értelmező dolgozik. A **próba-napló** (`naplo/probak.jsonl`) fordulónként nyolc mezőt rögzít (bemenet, normalizált alak, réteg, eszköz, paraméterek, bizonyosság, a válasz típusa, időbélyeg), és a szöveges fülön a „Napló megnyitása" gomb olvashatóan kiírja — l. `docs/TESZTELES.md`, „Beszélgetés-próba". A blueprint rögzíti a „Bolti tudás" elvet (10. szakasz): a bolt-szintű tény szerkesztett adat, a modell sosem generálja — a `bolt_info` eszköz `v2` sémát kapott (`megjelenes`/`termek`/`ar`, `migrations/0004_bolt_szolgaltatas_tudas.sql`). A **`valasz` modul** (`assistant/valasz/`) adja MINDEN magyar mondatot, a felület egyet sem fogalmaz — beleértve az új „rendszersor" kategóriát (az indító sor). **Szándék rétegzés** (`kovetkezo_kontextus`): a kemény rész (bolt, szolgáltatás) túléli a fordulót, a puha (dátum/napszak/óra) nem; a fordított kaszkádban a kemény rész a MODELL PROMPTJÁBA is bekerül, az elengedést pedig egy külön, zárt kérdés dönti el. **Enumeráció-védelem és rate limiting** a `foglalas_lekerdezes` ágon. **Bizonyosság-küszöbök** (`BizonyossagKuszobok`: eszköz 0,7, kritikus mező 0,6) → zárt kérdés küszöb alatt. **Ismétlésfigyelés**: ugyanaz a válaszfajta legfeljebb kétszer; a harmadikra kiút. **Hiányzik**: determinisztikus kapuőr a modell előtt (l. fent), kötött dekódolás GBNF/XGrammar szinten (ma az Ollama `format` JSON-séma-kényszere adja, ami nem ugyanaz), önkonzisztencia-ellenőrzés, és a bolti tudás (megjelenés/termék) a promptban — enélkül a „csillagos kirakatú bolt" típusú körülírást a modell nem tudja feloldani. |
| M5 — Dolgozói nézet | **nem kezdődött el** | — |
| M6 — Dev mód és finomhangolás | **nem kezdődött el** | — |

## Konkrét számok

- **Tesztek:** 467 zöld + 1 `xfail` (`tests/egyseg/test_alapsema.py::test_cross_org_reference_ma_not_bukik_el`, `strict=True`).
- **Migrációk:** 4 (`0001_alapsema`, `0002_muszak_slot`, `0003_muszak_sablon`, `0004_bolt_szolgaltatas_tudas` — bolti tudás mezők, lásd lent).
- **ADR-ek:** 17 dokumentum (001–014, 016–018) + 1 sablon. Ebből **16
  elfogadott**, **1 felülírva**: az ADR-016 (kaszkád sorrendje) —
  felülírta az **ADR-018**, amelynek első, elvető változata 2026-08-22-én
  született, és 2026-08-23-án ÁTFORDULT (l. lent, "A négy felállás").
  **A 015 szándékosan kimaradt**: ellenőrizve, git-történetben és a
  repóban sosem létezett, a szám emiatt véglegesen kimarad, l. ADR-016
  fejléce és az `adr` skill.
- **Golden set — LLM-mel (M-1 mérés, 2026-08-16):** 22 nyelvi eset, öt
  rétegben. Legjobb mért eredmény — qwen3.5:9b, gondolkodással, javított
  séma-kényszerrel: **47,7%** összesített, legrosszabb réteg a szleng
  (16,7%). Részletek és módszertan: `spike/EREDMENY.md`.
- **Golden set — a négy felállás egymás mellett** (2026-08-23,
  `qwen3.5:9b`, **45 eset**, 10 réteg: 22 egyfordulós + 6 alkudozás +
  3 elengedés + 5 nyelvi változatosság + **9 `mintan_tul`**):

  | Értelmező | Összesített | Leggyengébb réteg | Válaszidő | Réteg-megoszlás |
  |---|---|---|---|---|
  | `szabaly` | 78,9% | `elengedes` 0% | ~0,00 s | — |
  | `llm` (kapuk nélkül) | 25,6% | `alkudozas` 0,0% | ~6,44 s | — |
  | `kaszkad` (ADR-016, felülírva) | 83,3% | `valtozatossag` 40,0% | ~3,07 s | llm=6, szabaly=39 |
  | **`forditott`** (ADR-018, **éles**) | **88,9%** | **`koznyelvi` 80,0%** | ~7,83 s | llm=45 |

  Rétegenként:

  | Réteg | n | `szabaly` | `kaszkad` | `forditott` |
  |---|---|---|---|---|
  | `alkudozas` | 6 | 100,0% | 100,0% | 100,0% |
  | `egyszerusitett` | 4 | 100,0% | 100,0% | 87,5% |
  | `elengedes` | 3 | 0,0% | 100,0% | 100,0% |
  | `kapuor` | 2 | 100,0% | 100,0% | **50,0%** |
  | `koznyelvi` | 5 | 100,0% | 100,0% | 80,0% |
  | `mintan_tul` | 9 | 72,2% | 72,2% | 83,3% |
  | `szleng` | 3 | 100,0% | 100,0% | 100,0% |
  | `tajszolas` | 4 | 100,0% | **50,0%** | 100,0% |
  | `toredekes` | 4 | 100,0% | 100,0% | 100,0% |
  | `valtozatossag` | 5 | 20,0% | 40,0% | 80,0% |

  **A döntés MEGFORDULT** (ADR-018). A 2026-08-22-i mérés a fordított
  kaszkádot elvetette (69,4%) — az a mérés egy **félkész** modult mért:
  a `--ertelmezo forditott` kapcsoló a futtatóban nem is volt bekötve,
  és a modell a beszélgetés kontextusát meg sem kapta. A befejezett
  modul (kontextus a promptban, kontextus-kapu, elengedés-kapu,
  vagylagos dátum, determinisztikus pótlások, zárt visszakérdezés-
  halmaz) újramérve **88,9%**, és a leggyengébb rétegen is jobb
  (80,0% vs 40,0%) — ezért **ez lett az éles út**, az ADR-016 sorrendje
  pedig a visszaút.

  **Amit ezért feladunk, kimondva:**
  - **Kapuőr 100% → 50%.** A hibázás módja a kevésbé káros fajta (nem
    talál ki árat, hanem feleslegesen visszakérdez), de a blueprint
    10. szakasza szerint a témán belül tartás NEM múlhat a modell
    prompt-fegyelmén. **Ez a legfontosabb nyitott pont**; a
    determinisztikus kapuőr a modell elé emelése külön ADR-t igényel,
    mert az már hibrid architektúra.
  - **Válaszidő ~3,07 s → ~7,83 s**, és minden forduló hív modellt
    (llm=45/45). A hangcsatorna SLO-ja (blueprint §12) ma felfüggesztve
    van — amint érvénybe lép, ez a felállás nem tartható.
  - **Áthelyezés-felismerés**: a "Át tudnám tenni szerdára…" mondatot a
    modell keresésnek érti (koznyelvi-05). Nem káros, de rossz élmény.

  **Mérési figyelmeztetés:** a szórás nem elhanyagolható. A `forditott`
  `mintan_tul` rétege UGYANAZZAL a kóddal két futáson 94,4% és 83,3%
  volt (`temperature: 0` mellett is). Egy 45 eses halmazon egy eset 2,2
  százalékpont — a fenti számok ±1 eset pontossággal olvasandók, és a
  roadmap 150-200 eses kilépési feltétele emiatt is fontos.

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
   szerint M4 lezárásáig fel vannak függesztve (lásd lent), de nincs
   eldöntve, mi történik, ha M4-nél is a mai nagyságrendben marad a
   válaszidő.
5. **Racka-4B licenc-hozzáférés** — érdemes-e időt szánni a kézi
   GGUF-letöltésre és `ollama create`-re (ADR-013 ellenőrző jelöltje),
   vagy elég az Apache-2.0 Qwen3-ág egyedül?

## Ismert korlátok

- **A válaszidő-SLO-k ideiglenesen felfüggesztve M4 lezárásáig.** Az M-1
  mérés szerint minden mért válaszidő 6–73×-osa a blueprint §12 célnak
  (p95 < 2,5 s) — a terv emiatt előbbre vette a mag+admin munkát az
  asszisztens elé.
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
  2. invariáns, `adatvedelem` skill) M5 előtt nem készül el.
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
- **A modell-elsőbbségű út három ismert gyengéje** (ADR-018, "Amit
  feladunk"): a **kapuőr** (50% — a "Mennyibe kerül?" kérdésre
  visszakérdez, ahelyett hogy elhárítaná; nem talál ki árat, de
  feleslegesen kérdez), az **áthelyezés-felismerés** (az "Át tudnám tenni
  szerdára…" mondatot keresésnek érti), és a **bolt megjelenés szerinti
  azonosítása** ("a csillagos kirakatú bolt" — a modell a szerkesztett
  megjelenés-adatot nem látja, ezért visszakérdez). Az első kettőre a
  determinisztikus réteg mintája már megvan; a modell ELÉ emelésük külön
  ADR-t igényel, mert az már hibrid architektúra.
- **Az ár a modell felé strukturálisan le van zárva.** A fej nélküli
  végigjátszás megfogta, hogy a modell egy megjelenés-kérdésre
  `mit: "ar"`-t adott, és a felület az árat olvasta fel. Az `"ar"` azóta
  nincs benne a modellnek adott `mit` enumban (`llm_based.py`) — az
  eszköz maga továbbra is tud árat adni admin-oldali használatra.
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

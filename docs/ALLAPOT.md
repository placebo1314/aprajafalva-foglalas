# Állapot — 2026-08-22 (frissítve: LLM- és kaszkád értelmező, első
valódi modellmérés, seed --ujra, szándék rétegzés, `valasz` modul)

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
| M3 — Golden set és értékelő | **részben kész** | A nyelvi golden set 28 esetre nőtt (22 egyfordulós, öt réteg + 6 többfordulós "alkudozás" eset, `tests/golden/nyelvi_alap.yaml`), de a roadmap 150-200 esetet ír elő kilépési feltételként — ez messze nincs meg. A szituációs esetek (naptárállapot → ajánlás) egyáltalán nincsenek felvéve. **A `python feladat.py golden` parancs mostantól fut**, és `--ertelmezo szabaly\|llm\|kaszkad` kapcsolóval mindhárom értelmezőt tudja mérni (alapértelmezett `szabaly`, nincs Ollama-hívás, hacsak explicit nem kéred a másik kettőt) — a kiértékelő logika egy tartós modulba került (`tests/golden/futtato.py`). A `spike/golden_futtato.py` (LLM-specifikus mérési részletek, promptok) és a `tests/egyseg/test_rule_based_golden_set.py` (regressziós védőháló, csak a `szabaly` úton) ugyanezt a modult hívja, nincs többé két másolat. |
| M4 — Asszisztens | **részben kész** | A **determinisztikus fele kész**, és **most már valódi LLM-integráció is van, mérve**: `assistant/orchestrator.py` (ADR-007 állapotgép), `assistant/interpreter/` — `rule_based.py` (determinisztikus alapvonal), `llm_based.py` (Ollama `/api/chat`, `format` séma-kényszerrel, rövid rendszerprompt, `think: false` explicit, `LLMSzolgaltato` absztrakció konfigból jövő modellnévvel — ADR-013), `kaszkad.py` (ADR-016: a determinisztikus fut előbb, a modell csak egy hiányzó bolt kiegészítésére hívódik, a dátum és a zárt halmazok sosem az LLM-től jönnek). **Első valódi mérés** a látható golden seten (`qwen3.5:9b`, l. lent "Konkrét számok"): `szabaly` 100%, `llm` önmagában 26,8%, `kaszkad` 100% — a kaszkádon a modell a látható halmaz egyetlen esetében sem volt a döntő réteg (a determinisztikus réteg mindet önállóan megoldja), ez a mérés korlátja (ADR-016 részletezi). A koppintós út (M4 terv 7. pontja) is megvan: `ui/vasarlo.py`, két egyenrangú úttal (koppintós + szöveges) egy ablakban, mindkettő ténylegesen végigjátszható (keresés → jelölt-választás → "biztosan lefoglaljam?" → foglalási kód). A blueprint most explicit rögzíti a "Bolti tudás" elvet (10. szakasz): a bolt-szintű tény szerkesztett adat, a modell sosem generálja — a `bolt_info` eszköz `v2` sémát kapott (`megjelenes`/`termek`/`ar`, `migrations/0004_bolt_szolgaltatas_tudas.sql`), az értelmező felismeri ezeket a kérdéseket, és a felület olvashatóan (nem nyers dict-ként) jeleníti meg (`assistant/valasz/::tenyvalasz_szoveg`). A **`valasz` modul elkészült** (`assistant/valasz/`): öt kategóriájú magyar mondatsablon, nyelvkulcs alatt (`sablonok.py`), a nyugtázó sablonokból több változat véletlenszerű választással — `ui/vasarlo.py` (és a jövőbeli hangréteg) innentől semmilyen mondatot nem fogalmaz meg helyben. A "nyugtázó sor" (blueprint 7. szakasz, "Kétlépcsős válasz") is megvan: a keresés elindulásakor a felismert ablakot (bolt + dátum) írja ki, mielőtt a tényleges találatok megjönnének — ez a hangcsatorna töltelékmondatának szöveges próbája. **Szándék rétegzés** (`assistant/orchestrator.py::kovetkezo_kontextus`): egy lezárt keresés (siker vagy kudarc) után a kemény rész (bolt, szolgáltatás) megmarad a következő fordulóra, a puha rész (dátum/napszak/óra) nem — ez teszi lehetővé az alkudozást (szűkítés, tágítás, napszak-/boltváltás, visszalépés korábbi ajánlathoz, elutasítás-után-alternatíva) a kemény rész újramondása nélkül; az elutasítás azt is megmondja, melyik dimenzióban (napszak/nap/hét) van alternatíva (`assistant/tools/szabad_idopontok.py::_alternativ_dimenzio`) — a `nap`/`het` próba a kért napszakot VÁLTOZATLANUL hagyja (pl. "péntek délelőtt jövő héten": a napszak kemény, csak a hét puha), csak a `napszak` dimenzió próbája engedi el magát a napszak-kötöttséget, hogy ne ajánljon hamis alternatívát más napszakban. **Enumeráció-védelem és rate limiting** a `foglalas_lekerdezes` ágon (`assistant/orchestrator.py::_foglalas_lekerdezes`): session-szintű kérésszám-korlát, azonos válaszidő létező/nem létező azonosítóra. **Hiányzik**: kötött dekódolás GBNF/XGrammar szinten (ma az Ollama `format` JSON-séma-kényszere adja ezt, ami nem ugyanaz), önkonzisztencia-ellenőrzés, bizalmi jelzés logprobokból, a modell tényleges bevezetése a `ui/vasarlo.py`-ba (ma még csak `SzabalyAlapuErtelmezo`-t példányosít). |
| M5 — Dolgozói nézet | **nem kezdődött el** | — |
| M6 — Dev mód és finomhangolás | **nem kezdődött el** | — |

## Konkrét számok

- **Tesztek:** 337 zöld + 1 `xfail` (`tests/egyseg/test_alapsema.py::test_cross_org_reference_ma_not_bukik_el`, `strict=True`).
- **Migrációk:** 4 (`0001_alapsema`, `0002_muszak_slot`, `0003_muszak_sablon`, `0004_bolt_szolgaltatas_tudas` — bolti tudás mezők, lásd lent).
- **ADR-ek:** 15 elfogadva (001–014, 016 — **015 szám kimaradt**, nincs
  hozzá fájl, ellenőrizni kell, hogy szándékos-e) + 1 sablon.
- **Golden set — LLM-mel (M-1 mérés, 2026-08-16):** 22 nyelvi eset, öt
  rétegben. Legjobb mért eredmény — qwen3.5:9b, gondolkodással, javított
  séma-kényszerrel: **47,7%** összesített, legrosszabb réteg a szleng
  (16,7%). Részletek és módszertan: `spike/EREDMENY.md`.
- **Golden set — determinisztikus alapvonallal (`--ertelmezo szabaly`):**
  28 eset (22 egyfordulós + 6 többfordulós, alkudozás),
  `assistant/interpreter/rule_based.py`-vel: **100,0%**, minden réteg
  tartja a küszöbét. **Ez nem általánosítási mutató** — ezt a
  szabályrendszert erre a pontos esethalmazra építettük, kézzel
  egyeztetve mindegyikkel. A valódi próba egy jövőbeli, bővebb
  (150-200 eses) golden seten dől el (M3 kilépési feltétel).
- **Golden set — LLM-mel, ugyanazon a látható halmazon (`--ertelmezo
  llm`, 2026-08-22, `qwen3.5:9b`, rövid rendszerprompt, `think: false`):**
  **26,8%** összesített, leggyengébb réteg az alkudozás (0%). Ez az
  ELSŐ mérés a mai (rövidített, Vapi-tanulságot követő) rendszerprompttal
  — útközben két, ÁLTALÁNOS (nem eset-specifikus) hibát találtunk és
  javítottunk mérés közben: az eszközök leírása teljesen hiányzott a
  promptból (csak az enum-nevek voltak ott), és a `datum` mező
  (`bolt_info`-nak) összekeveredett a `datum_tol`/`datum_ig` mezőkkel
  (`szabad_idopontok`-nak) — mindkettő minden hívást rontott, nem csak
  egy-egy esetet, ezért javítottuk, nem hagytuk "mérési eredménynek".
  **A séma "description" mezői önmagukban NEM voltak elegendők** — ez
  konkrét cáfolata annak a feltevésnek, hogy a ritkán kellő részletek
  büntetlenül a sémába költöztethetők (l. `assistant/interpreter/
  llm_based.py` modul docstring).
- **Golden set — kaszkáddal (`--ertelmezo kaszkad`, ugyanaz a modell):**
  **100,0%**, válaszidő átlag 1,76s (szemben a tiszta LLM-mód 7,12
  másodpercével). **A modell a látható 28 eset EGYIKÉBEN sem volt a
  döntő réteg** (`Réteg-megoszlás: szabaly=28, llm=0`) — a
  determinisztikus réteg mindet önállóan megoldja, a kaszkád a
  modell hibás/hiányzó javaslatait minden esetben eldobta vagy
  felülbírálta. Ez a mérés korlátja: a látható halmaz pontosan azokra a
  mintákra épül, amiken a szabály-alapú réteg már bizonyítottan jól
  teljesít — a modell tényleges hozzáadott értékét (elgépelés,
  körülírás) egy bővebb/valós halmaz mutatná meg. Részletek és a
  kiváltó feltétel (mikor fordulna meg a sorrend): `docs/adr/
  016-kaszkad-ertelmezo-determinisztikus-elobb.md`.

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
- **A koppintós UI "Nap" választója a valódi rendszerórától számol**,
  a demóadat viszont egy fix, 2026-12-21-gyel kezdődő hétre generál
  beosztást — kézi kipróbáláskor ezért más dátumot kell választani,
  mint a mai nap (`ui/vasarlo.py` dokumentálja).
- **A `foglalas_lekerdezes` rate limit (5 kérés/session) és a
  válaszidő-padding (0,1 s) dokumentált, de tetszőlegesen választott
  érték** (`assistant/orchestrator.py::_LEKERDEZES_RATE_LIMIT`,
  `_LEKERDEZES_VALASZIDO_PADDING_MASODPERC`) — nincs mögötte mérés
  (pl. mennyi a valós lekérdezés p95 ideje), és a korlát csak
  memóriabeli, session-újraindításkor nullázódik. Éles bevezetés előtt
  ezt érdemes megmérni és/vagy tartós (nem memóriabeli) számlálóra
  cserélni, ha a session valaha túléli a folyamat-újraindítást.

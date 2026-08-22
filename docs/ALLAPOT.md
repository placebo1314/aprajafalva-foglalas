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
| M3 — Golden set és értékelő | **részben kész** | A nyelvi golden set 36 esetre nőtt (22 egyfordulós, öt réteg + 6 "alkudozás" + 3 "elengedés" + 5 "nyelvi változatosság" eset, `tests/golden/nyelvi_alap.yaml`). Az **elengedés-réteg az első, ami ténylegesen megkülönbözteti a szabály-alapú és a kaszkád értelmezőt** (`igenyel_llm: true` — a determinisztikus regressziós védőháló kihagyja őket, a mérés nem), de a roadmap 150-200 esetet ír elő kilépési feltételként — ez messze nincs meg. A szituációs esetek (naptárállapot → ajánlás) egyáltalán nincsenek felvéve. **A `python feladat.py golden` parancs mostantól fut**, és `--ertelmezo szabaly\|llm\|kaszkad\|forditott` kapcsolóval mind a négy felállást tudja mérni (alapértelmezett `szabaly`, nincs Ollama-hívás, hacsak explicit nem kéred a többit) — a kiértékelő logika egy tartós modulba került (`tests/golden/futtato.py`). A `spike/golden_futtato.py` (LLM-specifikus mérési részletek, promptok) és a `tests/egyseg/test_rule_based_golden_set.py` (regressziós védőháló, csak a `szabaly` úton) ugyanezt a modult hívja, nincs többé két másolat. |
| M4 — Asszisztens | **részben kész** | A **determinisztikus fele kész**, és **most már valódi LLM-integráció is van, mérve**: `assistant/orchestrator.py` (ADR-007 állapotgép), `assistant/interpreter/` — `rule_based.py` (determinisztikus alapvonal), `llm_based.py` (Ollama `/api/chat`, `format` séma-kényszerrel, rövid rendszerprompt, `think: false` explicit, `LLMSzolgaltato` absztrakció konfigból jövő modellnévvel — ADR-013), `kaszkad.py` (ADR-016: a determinisztikus fut előbb, a modell csak egy hiányzó bolt kiegészítésére hívódik, a dátum és a zárt halmazok sosem az LLM-től jönnek). **Mérve** a 36 esetes golden seten (`qwen3.5:9b`, l. lent "Konkrét számok"): `szabaly` 80,6%, `llm` önmagában 27,8%, `kaszkad` **86,1%** (réteg-megoszlás `llm=6, szabaly=30`), a fordított felállás 69,4% — utóbbit megmértük és elvetettük (ADR-018). A koppintós út (M4 terv 7. pontja) is megvan: `ui/vasarlo.py`, két egyenrangú úttal (koppintós + szöveges) egy ablakban, mindkettő ténylegesen végigjátszható (keresés → jelölt-választás → "biztosan lefoglaljam?" → foglalási kód). A blueprint most explicit rögzíti a "Bolti tudás" elvet (10. szakasz): a bolt-szintű tény szerkesztett adat, a modell sosem generálja — a `bolt_info` eszköz `v2` sémát kapott (`megjelenes`/`termek`/`ar`, `migrations/0004_bolt_szolgaltatas_tudas.sql`), az értelmező felismeri ezeket a kérdéseket, és a felület olvashatóan (nem nyers dict-ként) jeleníti meg (`assistant/valasz/::tenyvalasz_szoveg`). A **`valasz` modul elkészült** (`assistant/valasz/`): öt kategóriájú magyar mondatsablon, nyelvkulcs alatt (`sablonok.py`), a nyugtázó sablonokból több változat véletlenszerű választással — `ui/vasarlo.py` (és a jövőbeli hangréteg) innentől semmilyen mondatot nem fogalmaz meg helyben. A "nyugtázó sor" (blueprint 7. szakasz, "Kétlépcsős válasz") is megvan: a keresés elindulásakor a felismert ablakot (bolt + dátum) írja ki, mielőtt a tényleges találatok megjönnének — ez a hangcsatorna töltelékmondatának szöveges próbája. **Szándék rétegzés** (`assistant/orchestrator.py::kovetkezo_kontextus`): egy lezárt keresés (siker vagy kudarc) után a kemény rész (bolt, szolgáltatás) megmarad a következő fordulóra, a puha rész (dátum/napszak/óra) nem — ez teszi lehetővé az alkudozást (szűkítés, tágítás, napszak-/boltváltás, visszalépés korábbi ajánlathoz, elutasítás-után-alternatíva) a kemény rész újramondása nélkül; az elutasítás azt is megmondja, melyik dimenzióban (napszak/nap/hét) van alternatíva (`assistant/tools/szabad_idopontok.py::_alternativ_dimenzio`) — a `nap`/`het` próba a kért napszakot VÁLTOZATLANUL hagyja (pl. "péntek délelőtt jövő héten": a napszak kemény, csak a hét puha), csak a `napszak` dimenzió próbája engedi el magát a napszak-kötöttséget, hogy ne ajánljon hamis alternatívát más napszakban. **Enumeráció-védelem és rate limiting** a `foglalas_lekerdezes` ágon (`assistant/orchestrator.py::_foglalas_lekerdezes`): session-szintű kérésszám-korlát, azonos válaszidő létező/nem létező azonosítóra. **`ui/vasarlo.py` mostantól a kaszkádot használja** (`assistant/interpreter/__init__.py::alapertelmezett_ertelmezo()` — a felület nem importál LLM-specifikus osztályt közvetlenül, CLAUDE.md "Modulhatárok"; ha nincs konfigurált modell vagy nem fut a háttérszolgáltatás, csendben a szabály-alapú viselkedésre esik vissza). **Próba-napló** (`naplo/probak.jsonl`, `.gitignore`-ban): a szöveges úton minden bemenetet és a rá adott értelmezést naplózza (bemenet, eszköz, paraméterek, melyik réteg oldotta meg, időbélyeg) — ez lesz a jövőbeli rejtett golden halmaz nyersanyaga. **Szándék-osztályozás bizonyossággal** (blueprint 10.): az `Ertelmezo` protokoll `bizonyossag` mezője (a determinisztikus réteg 1.0-t ad arra, amit szabályból tud, `None`-t arra, amit csak alapértelmezésként tölt ki; az LLM a TÉNYLEGES token-logprobokból számol, nem önbevallásból), az orchestrator konfigurálható küszöbökkel (`BizonyossagKuszobok`: eszköz 0,7, kritikus mező 0,6) zárt kérdésre vált küszöb alatt, és két közeli szándéknál rákérdez ("Lemondani vagy áthelyezni?"). **Ismétlésfigyelés**: ugyanaz a válaszfajta legfeljebb kétszer mehet ki; a harmadikra kiút zárt választással (bolt/hét/napszak). **Hiányzik**: kötött dekódolás GBNF/XGrammar szinten (ma az Ollama `format` JSON-séma-kényszere adja ezt, ami nem ugyanaz), önkonzisztencia-ellenőrzés. |
| M5 — Dolgozói nézet | **nem kezdődött el** | — |
| M6 — Dev mód és finomhangolás | **nem kezdődött el** | — |

## Konkrét számok

- **Tesztek:** 417 zöld + 1 `xfail` (`tests/egyseg/test_alapsema.py::test_cross_org_reference_ma_not_bukik_el`, `strict=True`).
- **Migrációk:** 4 (`0001_alapsema`, `0002_muszak_slot`, `0003_muszak_sablon`, `0004_bolt_szolgaltatas_tudas` — bolti tudás mezők, lásd lent).
- **ADR-ek:** 16 elfogadva (001–014, 016–017) + **1 elvetve** (018 —
  a fordított kaszkád mért kísérlete, l. lent) — **a 015 szándékosan
  kimaradt**: ellenőrizve, git-történetben és a repóban sosem létezett,
  a szám emiatt véglegesen kimarad, l. ADR-016 fejléce és az `adr`
  skill. Plusz 1 sablon.
- **Golden set — LLM-mel (M-1 mérés, 2026-08-16):** 22 nyelvi eset, öt
  rétegben. Legjobb mért eredmény — qwen3.5:9b, gondolkodással, javított
  séma-kényszerrel: **47,7%** összesített, legrosszabb réteg a szleng
  (16,7%). Részletek és módszertan: `spike/EREDMENY.md`.
- **Golden set — a négy felállás egymás mellett** (2026-08-22,
  `qwen3.5:9b`, 36 eset: 22 egyfordulós + 6 alkudozás + 3 elengedés +
  5 nyelvi változatosság):

  | Értelmező | Összesített | Leggyengébb réteg | Válaszidő | Réteg-megoszlás |
  |---|---|---|---|---|
  | `szabaly` | 80,6% | `elengedes` 0% | ~0,00 s | — |
  | `llm` | 27,8% | `alkudozas` 0% | ~6,04 s | — |
  | **`kaszkad`** (ADR-016, éles) | **86,1%** | `valtozatossag` 40% | ~2,86 s | llm=6, szabaly=30 |
  | `forditott` (ADR-018, elvetve) | 69,4% | `koznyelvi` 40% | ~6,31 s | llm=36 |

  **A fordított kaszkádot megmértük és elvetettük** (ADR-018). Pontosan
  ott javított, ahol az érvelés jósolta — nyelvi változatosság
  20% → 60%, kemény rész elengedése 0% → 66,7% —, de mindent rontott,
  amit a szabályok már jól kezeltek: köznyelvi 100% → 40%, kapuőr
  100% → 50%. Az ADR-016 sorrendje marad hatályban.

  A kísérlet **három maradandó eredményt** hozott, amik az éles úton is
  benne vannak: few-shot példakészlet (`assistant/interpreter/
  peldak.py`), a modell szöveges `datum_kifejezes` mezője a
  hun-date-parser-nek, és a "vitás esetben a parser nyer" szabály.
  Ezek együtt a nyers modellt 27,8%-ról 69,4%-ra vitték — nem eleget a
  fordításhoz, de a jövőbeli modellváltáshoz megmaradó infrastruktúra.

  **A ma ismert leggyengébb pont a `valtozatossag` réteg (40%)**: olyan
  megfogalmazások, amikhez a szabály-alapú rétegnek új mintát kellene
  felvenni (bolt körülírva termékkel vagy megjelenéssel, lemondás a
  "lemond" szó nélkül, vagylagos időpont). Ez a rendszer valódi korlátja,
  nem mérési műtermék.

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

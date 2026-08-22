# Állapot — 2026-08-21 (frissítve: M2 + M4 determinisztikus fele)

Egy oldalas pillanatkép: hol tartunk. A terv és a "miért" a
`docs/blueprint.md`-ben és a `docs/roadmap.md`-ben van, ez itt nem
ismétli meg őket, csak rájuk mutat és számol.

## Mérföldkövek

| Mérföldkő | Állapot | Megjegyzés |
|---|---|---|
| M-1 — Spike | **kész** | Lezárva 2026-08-16. A négy szám megvan, egyik sem hozta a tervezett SLO-t — lásd lent, "Ismert korlátok". |
| M0 — Foglalási mag | **kész** | Séma, migrációk, slotgenerátor, hold, foglalás, áthelyezés, lemondás, mentés+helyreállítás, CLI, konkurencia-tesztek — mind megvan és tesztelt. |
| M1 — Admin beosztásszerkesztő | **részben kész** | Naptárnézet, műszak felvitele, sablon-műszakok, hét másolása, törzsadat-szerkesztés, ütközéslista megvan. A törzsadat-szerkesztés kibővült a "Bolti tudás" mezőkkel (megjelenés/termékleírás/ár, `core/api/adminszolgaltatas.py::shop_description_update`/`service_description_update`) — a `bolt_info` eszköz ezeket olvassa vissza. Ami hiányzik: lásd lent. |
| M2 — Eszközszerződés | **kész** | A hat eszköz (`assistant/tools/`) megvan: JSON-séma v1-gyel, `additionalProperties: false`, egységes hiba-formátummal, LLM nélkül hívható és tesztelt (23 teszt). |
| M3 — Golden set és értékelő | **részben kész** | A nyelvi golden set megvan (22 eset, öt réteg, `tests/golden/nyelvi_alap.yaml`), de a roadmap 150-200 esetet ír elő kilépési feltételként — ez messze nincs meg. A szituációs esetek (naptárállapot → ajánlás) egyáltalán nincsenek felvéve. **A `python feladat.py golden` parancs ma hibával áll le** — a `tests/golden/futtato.py` értékelő script még nincs megírva, csak az esetfájl létezik. A 22 esetet most két másik út futtatja: `spike/golden_futtato.py --ertelmezo szabaly` (eldobható spike-kód, méréshez) és `tests/egyseg/test_rule_based_golden_set.py` (tartós regressziós védőháló, ez fut minden `python feladat.py teszt`-nél). |
| M4 — Asszisztens | **részben kész** | A **determinisztikus fele kész**: `assistant/orchestrator.py` (ADR-007 állapotgép), `assistant/interpreter/` (`Ertelmezo` protokoll + `rule_based.py`, hun-date-parser-rel), `assistant/tools/katalogus.py` (szándékindex is: `core/api/szandekindex.py`). Ez a golden set látható 22 esetén **100%-ot** ad — ez egy erre a fixtúrára épített szabályrendszer eredménye, NEM általánosítási mutató (lásd lent). A koppintós út (M4 terv 7. pontja) is megvan: `ui/vasarlo.py`, két egyenrangú úttal (koppintós + szöveges) egy ablakban, mindkettő ténylegesen végigjátszható (keresés → jelölt-választás → "biztosan lefoglaljam?" → foglalási kód). A blueprint most explicit rögzíti a "Bolti tudás" elvet (10. szakasz): a bolt-szintű tény szerkesztett adat, a modell sosem generálja — a `bolt_info` eszköz `v2` sémát kapott (`megjelenes`/`termek`/`ar`, `migrations/0004_bolt_szolgaltatas_tudas.sql`), az értelmező felismeri ezeket a kérdéseket, és a felület olvashatóan (nem nyers dict-ként) jeleníti meg (`ui/vasarlo.py::tenyvalasz_szoveg`). A "nyugtázó sor" (blueprint 7. szakasz, "Kétlépcsős válasz") is megvan: a keresés elindulásakor a felismert ablakot (bolt + dátum) írja ki, mielőtt a tényleges találatok megjönnének (`ui/vasarlo.py::nyugtazo_szoveg`) — ez a hangcsatorna töltelékmondatának szöveges próbája. **Hiányzik**: tényleges LLM-integráció, kötött dekódolás (GBNF/XGrammar), önkonzisztencia-ellenőrzés, bizalmi jelzés logprobokból, a `valasz` modul (magyar mondatgenerálás — ma egy ideiglenes szótár, `ui/vasarlo.py::_UZENET_KULCS_SZOVEG`). |
| M5 — Dolgozói nézet | **nem kezdődött el** | — |
| M6 — Dev mód és finomhangolás | **nem kezdődött el** | — |

## Konkrét számok

- **Tesztek:** 294 zöld + 1 `xfail` (`tests/egyseg/test_alapsema.py::test_cross_org_reference_ma_not_bukik_el`, `strict=True`).
- **Migrációk:** 4 (`0001_alapsema`, `0002_muszak_slot`, `0003_muszak_sablon`, `0004_bolt_szolgaltatas_tudas` — bolti tudás mezők, lásd lent).
- **ADR-ek:** 14 elfogadva (001–014) + 1 sablon.
- **Golden set — LLM-mel (M-1 mérés):** 22 nyelvi eset, öt rétegben.
  Legjobb mért eredmény — qwen3.5:9b, gondolkodással, javított
  séma-kényszerrel: **47,7%** összesített, legrosszabb réteg a szleng
  (16,7%). **Egyik réteg sem éri el a saját küszöbét** — a kapuőr réteg
  (nem valós foglalási kérés felismerése) az egyetlen, ami 100%-on áll.
  Részletek és módszertan: `spike/EREDMENY.md`.
- **Golden set — determinisztikus alapvonallal:** ugyanaz a 22 eset,
  `assistant/interpreter/rule_based.py`-vel: **100,0%**, minden réteg
  tartja a küszöbét (`spike/eredmeny_szabaly_alapu.json`,
  `tests/egyseg/test_rule_based_golden_set.py`). **Ez nem
  általánosítási mutató** — ezt a szabályrendszert erre a pontos 22
  esetre építettük, kézzel egyeztetve mindegyikkel, szemben az
  LLM-mel, ami sosem látta őket tanításkor. A valódi próba egy jövőbeli,
  bővebb (150-200 eses) golden seten dől el (M3 kilépési feltétel).

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

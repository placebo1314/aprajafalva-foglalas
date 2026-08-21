# Állapot — 2026-08-21

Egy oldalas pillanatkép: hol tartunk. A terv és a "miért" a
`docs/blueprint.md`-ben és a `docs/roadmap.md`-ben van, ez itt nem
ismétli meg őket, csak rájuk mutat és számol.

## Mérföldkövek

| Mérföldkő | Állapot | Megjegyzés |
|---|---|---|
| M-1 — Spike | **kész** | Lezárva 2026-08-16. A négy szám megvan, egyik sem hozta a tervezett SLO-t — lásd lent, "Ismert korlátok". |
| M0 — Foglalási mag | **kész** | Séma, migrációk, slotgenerátor, hold, foglalás, áthelyezés, lemondás, mentés+helyreállítás, CLI, konkurencia-tesztek — mind megvan és tesztelt. |
| M1 — Admin beosztásszerkesztő | **részben kész** | Naptárnézet, műszak felvitele, sablon-műszakok, hét másolása, törzsadat-szerkesztés, ütközéslista megvan. Ami hiányzik: lásd lent. |
| M2 — Eszközszerződés | **nem kezdődött el** | A hat eszköz (`szabad_idopontok`, `foglalas_letrehozas` stb.) JSON-sémája még nincs megírva. |
| M3 — Golden set és értékelő | **részben kész** | A nyelvi golden set megvan (22 eset, öt réteg, `tests/golden/nyelvi_alap.yaml`), de a roadmap 150-200 esetet ír elő kilépési feltételként — ez messze nincs meg. A szituációs esetek (naptárállapot → ajánlás) egyáltalán nincsenek felvéve. **A `python feladat.py golden` parancs ma hibával áll le** — a `tests/golden/futtato.py` értékelő script még nincs megírva, csak az esetfájl létezik. Az M-1 mérésekhez a `spike/golden_futtato.py` (eldobható spike-kód) futott, nem ez. |
| M4 — Asszisztens | **nem kezdődött el** | A modellválasztás méréssel (M-1) megtörtént, de maga az asszisztens-réteg (normalizáló, dátumparser-integráció, orchestrator) nincs megírva. |
| M5 — Dolgozói nézet | **nem kezdődött el** | — |
| M6 — Dev mód és finomhangolás | **nem kezdődött el** | — |

## Konkrét számok

- **Tesztek:** 182 zöld + 1 `xfail` (`tests/egyseg/test_alapsema.py::test_cross_org_reference_ma_not_bukik_el`, `strict=True`).
- **Migrációk:** 3 (`0001_alapsema`, `0002_muszak_slot`, `0003_muszak_sablon`).
- **ADR-ek:** 14 elfogadva (001–014) + 1 sablon.
- **Golden set:** 22 nyelvi eset, öt rétegben. Jelenlegi legjobb mért eredmény —
  qwen3.5:9b, gondolkodással, javított séma-kényszerrel: **47,7%**
  összesített, legrosszabb réteg a szleng (16,7%). **Egyik réteg sem éri el
  a saját küszöbét** — a kapuőr réteg (nem valós foglalási kérés
  felismerése) az egyetlen, ami 100%-on áll. Részletek és módszertan:
  `spike/EREDMENY.md`.

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

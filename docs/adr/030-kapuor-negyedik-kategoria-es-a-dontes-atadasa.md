# ADR-030: A kapuőr negyedik kategóriája, és a döntés átadása

- **Dátum:** 2026-09-05
- **Állapot:** elfogadott
- **Kiváltó ok:** az ELSŐ ÉLES PRÓBA (kézi, `qwen3.5:9b`, 9 forduló)

## Kontextus

Az első valódi próba kilenc fordulója három hibát mutatott meg, és
mindhárom ugyanabból a hiányból jött: **a rendszernek nem volt neve arra,
amit a vásárló csinált.**

| forduló | amit a vásárló mondott | ami történt | ami történnie kellett volna |
|---|---|---|---|
| 7. | „csak a választ beszéled?" | KERESÉS indult, és a `KESZ` állapot `AJANLAT_VAR`-ra romlott | rövid bemutatkozás, az állapot marad |
| 8. | „nekem mind jó. válasz te." | ÚJRA felajánlotta ugyanazt a három időpontot | válasszon a rendszer, és kérjen megerősítést |
| 9. | „a hét tizenötös" | a MÁSODIK jelöltet választotta (07:00–07:15) | a HARMADIKAT (07:15–07:30) |

A 7. és a 8. forduló hibája szerkezeti: a `{eszkoz, parameterek}`
szerződésben nem volt olyan érték, ami ezeket kifejezné, tehát a modell
legjobb tudása szerint is csak keresést tudott adni. A 9. forduló hibája
más fajta — az megmaradt (l. „Amit ez NEM old meg").

## Döntés

**1. A kapuőr negyedik kategóriája: `META_KERDES`.**
A rendszerről szóló kérdés („te egy robot vagy?", „mit tudsz?", „csak a
választ beszéled?") nem foglalási szándék, nem tényválasz, és **nem is
hatókörön kívüli**: erre VAN válaszunk. A válasz sablonból jön
(`valasz.meta_szoveg`), a modell meg sem szólal, és a beszélgetés
állapota NEM mozdul (`allapotgep._ALLAPOTTARTO`).

Miért negyedik kategória, és nem a `HATOKORON_KIVUL` egy oka: a
hatókörön kívüli kérésre azt mondjuk, hogy „ebben nem tudok segíteni" —
ez viszont bemutatkozás. Két különböző mondat, két különböző szándék.

**2. A döntés átadása: `dontsd_el_te`.**
Ha a vásárló ránk bízza a választást („nekem mind jó, válassz te"), a
rendszer **a pontozó első jelöltjét** veszi (a jelöltek már abban a
sorrendben állnak, ADR-006 — az „első" tehát nem önkény, hanem a mi
legjobb ajánlatunk), és megerősítést kér, **kimondott időponttal**: a
jelölt-gombok ilyenkor eltűnnek, tehát a mondatnak meg kell mondania,
miről van szó.

A felismerés a MODELLÉ (nincs kulcsszólista), a végrehajtás az
orchestratoré, két kapuval: csak `AJANLAT_VAR` állapotban, és csak ha
tényleg vannak jelöltek. Enélkül a szokásos visszakérdezés megy — a
„foglalj egyet" önmagában nem mondja meg, mikorra és hova.

**3. Modell-előmelegítés.**
Az első forduló 13,93 s volt, a többi 3,5 s körül — a különbség a modell
betöltése. A felület indításkor, HÁTTÉRSZÁLON, egy egytokenes hívással
betölti a modellt (`llm_based.elomelegit`), és a mód-sorban kiírja,
mikor lett kész. Ugyanezt teszi a golden futtató és a végigjátszás is:
enélkül az ELSŐ eset a betöltés idejét viseli, és a válaszidő-eloszlás
egy olyan számot mutat, ami éles beszélgetés közepén sosem fordul elő.

## Miért így

- **A kapuőr a modell ELŐTT dönt** (ADR-020), tehát a meta-kérdés
  kezelése nulla modellhívás — és a tartalék ágon is működik.
- **A `dontsd_el_te` viszont a modellé**, mert nyelvi felismerés:
  „nekem mind jó", „amelyik neked jó", „mindegy, foglalj egyet" — ezekre
  kulcsszólistát írni pontosan az a ráigazítás lenne, amit a projekt
  kerül. A GARANCIÁT nem a felismerés adja, hanem a két kapu utána.
- **Az előmelegítés nem optimalizálás, hanem a helyzet helyretétele:**
  a betöltés úgyis megtörténik, csak eddig a vásárló első mondata
  fizette meg.

## Amit ez NEM old meg

**A 9. forduló hibája megmaradt.** A „hét tizenötös" a 7:15-kor KEZDŐDŐ
időpontot jelenti (a harmadikat), a rendszer a másodikat választotta
(ami 7:15-kor VÉGZŐDIK). Ez nem visszakérdezéshez vezet, hanem MÁS
IDŐPONT lefoglalásához — a `assistant/sorszam.py` docstringje pontosan
ettől óv.

Ez a bukás mostantól GOLDEN ESET (`elesbol-01-a-het-tizenotos`), és
ehhez a golden futtató is bővült: egy eset megadhatja, MIT ajánlottunk
fel (`felajanlott`), és a futtató ugyanúgy teszi be a beszélgetésbe,
ahogy a felület — enélkül a jelöltre hivatkozó mondatok mérhetetlenek
voltak.

## Amit feladunk

- **Egy negyedik kategóriát** a kapuőrben, ami eddig zárt hármas volt.
  Minden jövőbeli fogyasztónak kezelnie kell — cserébe a rendszerről
  szóló kérdés nem keresés lesz.
- **Egy sablonmondatot, ami magáról a rendszerről állít valamit.** Ez
  karbantartandó: ha a képességek változnak, a mondat hazudni fog.
  Ezért rövid, és csak azt sorolja, ami eszközként létezik.
- **Az előmelegítés VRAM-ot foglal** az indítás pillanatától, akkor is,
  ha a próbálgató végül nem ír be semmit. A `keep_alive` az Ollama
  alapértelmezése (5 perc) — nem kérünk hosszabbat.

## Kiváltó feltétel

- a `META_KERDES` minta valódi foglalási kérést nyel el (a naplóban
  `kapuor` réteg olyan mondatra, ami időpontot kért) — a minta túl tág;
- a `dontsd_el_te` olyan fordulóban szólal meg, ahol a vásárló NEM adta
  át a döntést (mérve a beszédhelyzetek halmaz ellenpróbáin) — ekkor a
  prompt-sor a hibás;
- az előmelegítés után az első forduló továbbra is kiugró (a naplóból:
  az első `valaszido_masodperc` több mint kétszerese a p50-nek).

## Ellenőrzés

```
python -m pytest tests/egyseg/test_kapuor.py tests/egyseg/test_orchestrator.py
python feladat.py golden --halmaz beszedhelyzetek --ertelmezo forditott
python feladat.py vegigjatszas        # az előmelegítés ideje kiírva
```

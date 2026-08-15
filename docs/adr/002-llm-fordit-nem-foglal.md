# ADR-002: Az LLM fordít, nem foglal

- **Dátum:** 2026-08-15
- **Állapot:** elfogadott

## Kontextus

A vásárló magyar mondatokkal foglal, egy LLM értelmezi a kérést. Az LLM-nek
akár közvetlenül is végrehajthatná a foglalási írást (agentic tool-loop,
modell dönt a végleges íráskor), vagy szigorúan elválasztható: a nyelvi réteg
csak fordít, a döntést és az írást egy determinisztikus mag végzi.

## Döntés

Az LLM kizárólag magyar mondat → strukturált eszközhívás → magyar mondat
átalakítást végez; a tényleges foglalási írást és minden döntést a
determinisztikus mag (`mag/`) hajtja végre, LLM-hívás nélkül.

## Miért

- Egy hibás modellválasz legrosszabb esetben kellemetlen (rossz
  visszakérdezés), nem káros (dupla vagy elveszett foglalás) — a hibaosztály
  eleve kizárt, nem csak valószínűtlen.
- A mag LLM nélkül, önállóan tesztelhető és bizonyítható (konkurencia-teszt,
  determinisztikus egységteszt), a nyelvi réteg hibái nem szivárognak át az
  adatintegritásba.
- A modell cserélhető modul marad (`LLMSzolgaltato` interfész) anélkül, hogy
  ez a foglalási logikát érintené.

## Amit feladunk

Azt a rugalmasságot, hogy a modell szabadon, tool-definíciók bővítése nélkül
kezelhessen szokatlan vagy összetett kéréseket — minden új képességhez
explicit új eszközt és sémát kell írni.

## Kiváltó feltétel

Ez **invariáns ADR** — a projekt sérthetetlen alapelvét rögzíti
(`CLAUDE.md`), ezért szándékosan nincs hozzá numerikus küszöb. A
felülvizsgálatot kizárólag az alábbi két esemény valamelyike indíthatja:

- formálisan (nem csak teszteléssel) igazolható, hogy egy adott LLM-alapú
  végrehajtási út semmilyen hibaágban nem eredményezhet dupla vagy elveszett
  foglalást, VAGY
- jogi vagy üzemeltetési kényszer írja elő, hogy a foglalási döntést emberi
  jóváhagyás vagy determinisztikus ellenőrzés nélkül AI hozza meg.

## Váltás mire

Nincs kijelölt következő lépcső — ez a projekt sérthetetlen alapelve
(`CLAUDE.md`). Ha a kiváltó feltétel valaha teljesül, az egy külön,
gondosan indokolt ADR tárgya, nem ennek módosítása.

## Váltás költsége

Nem becsülhető — a teljes architektúra (orchestrator, eszközszerződés,
tesztstratégia) erre az elválasztásra épül.

## Ellenőrzés

A `mag/` egységtesztjei LLM nélkül futnak és zöldek; a hookok kikényszerítik,
hogy a `mag/` ne importáljon az `asszisztens/`-ből (lásd roadmap,
„Fejlesztői környezet").

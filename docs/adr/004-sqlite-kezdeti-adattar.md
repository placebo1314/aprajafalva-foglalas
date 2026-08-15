# ADR-004: SQLite mint kezdeti adattár

- **Dátum:** 2026-08-15
- **Állapot:** elfogadott

## Kontextus

Lokálisan futó rendszer, egyetlen gépen, kis forgalommal. Postgres
üzemeltetése ehhez aránytalan, de a rendszer nőhet.

## Döntés

SQLite WAL módban, egyetlen író folyamattal.

## Miért

- Nulla üzemeltetési teher, a fájl a repóból indul
- A parciális UNIQUE index ugyanúgy véd, mint Postgresben
- A tesztek másodpercek alatt futnak

## Amit feladunk

Egyidejű írók, replikáció, távoli hozzáférés, `EXCLUDE` kényszerek.

## Kiváltó feltétel

- egynél több író folyamat kell
- p95 írási latencia > 50 ms
- egyidejű aktív session > 50
- replikáció vagy távoli hozzáférés igény

## Váltás mire

PostgreSQL 16.

## Váltás költsége

~1 nap, amíg a hordozhatósági szabályok érvényben vannak
(lásd `db-hordozhatosag` skill).

## Ellenőrzés

Ma, amíg nincs Postgres-adapter, a hordozhatóságot **statikusan** tartjuk
fenn: a migrációs linter hook tiltott mintákra (autoincrement, SQLite-
dátumfüggvények, `INSERT OR REPLACE/IGNORE`, `GLOB`, rétegen kívüli SQL)
fut minden migráción, és a `sema-orzo` agent minden új/módosított
migrációt és repo-függvényt átnéz ugyanezen szabályok szerint. Ez nem
bizonyítja, hogy a kód ténylegesen fut Postgresen — csak azt, hogy semmi
nem zár ki egy jövőbeli váltást.

A **tényleges kétmotoros futtatás** (`python feladat.py teszt-mindketto`
valódi Postgres-ágon) csak azután lép életbe, amikor a Postgres-adapter
elkészül — ez a Postgres-váltás **előfeltétele**, nem következménye: nem
azért írjuk meg az adaptert, mert a kiváltó feltétel teljesült, hanem
fordítva — a `teszt-mindketto` csak akkor tud valódi bizonyítékot adni,
ha az adapter már létezik. Amíg ez nem így van, a `python feladat.py
teszt-mindketto` figyelmeztetést ír ki, hogy a "postgres" ág ma ténylegesen
nem Postgres ellen fut, nehogy ez a hiányzó lefedettség észrevétlen
maradjon.

Az írási latenciát a mag méri és naplózza — ez a négy kiváltó feltétel
egyike, és attól függetlenül mérhető/ellenőrizhető, hogy van-e már
Postgres-adapter.

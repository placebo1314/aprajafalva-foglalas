---
name: adr
description: Döntési feljegyzés (ADR) írása kiváltó feltétellel — a menekülőút-doktrína eszköze. Használd, amikor egyszerűsítesz, technológiát választasz, hatókört szűkítesz, invariánst módosítanál, vagy bármikor, amikor a helyes válasz az, hogy „most így csináljuk, de nem örökre". Hívható /adr néven is.
---

# Döntési feljegyzés (ADR)

## Miért

A törpök igényessége nem a lazítást zárja ki, hanem a **dokumentálatlan
egyszerűsítést**. Minden egyszerűsítés rendben van, ha le van írva, hogy mikor
kell visszatérni rá.

A „majd meglátjuk" nem kiváltó feltétel. A kiváltó feltétel konkrét szám vagy
megfigyelhető esemény.

## Sablon

```markdown
# ADR-0XX: <rövid cím>

- **Dátum:** 2026-03-15
- **Állapot:** javasolt | elfogadott | felülírva (ADR-0YY)

## Kontextus

Mi a helyzet, ami döntést igényel. Milyen kényszerek vannak.
2-4 mondat, nem esszé.

## Döntés

Mit választunk. Egy mondatban, kijelentő módban.

## Miért

A legfontosabb 2-3 indok. Ha nincs 2, valószínűleg nem is döntés.

## Amit feladunk

Mit veszítünk ezzel. Ha ide „semmit" kerül, a döntés nincs átgondolva.

## Kiváltó feltétel

Konkrét, mérhető feltételek, amelyek bármelyike esetén újra kell nyitni:

- <mérőszám> meghaladja <konkrét érték>
- <esemény> bekövetkezik
- <igény> felmerül

## Váltás mire

A következő lépcső, névvel. Nem „valami jobbra".

## Váltás költsége

Becslés, és mi tartja alacsonyan.

## Ellenőrzés

Hogyan tudjuk meg, hogy a feltétel teljesült. Ha nincs rá mérés, a
kiváltó feltétel díszlet.
```

## Példa

```markdown
# ADR-004: SQLite mint kezdeti adattár

- **Dátum:** 2026-03-15
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

A CI minden futásnál mindkét motoron végigviszi a teljes tesztkészletet
(`make teszt-mindketto`). Az írási latenciát a mag méri és naplózza.
```

## Számozás és hely

- `docs/adr/004-sqlite-kezdeti-adattar.md`
- Sorszám soha nem használódik újra.
- Felülírásnál a régi ADR **megmarad**, az állapota változik, és hivatkozik az
  újra. A történet része, hogy egyszer másképp gondoltuk.

## Mikor kell ADR

Ha bármelyik igaz:

- egyszerűsítünk valamit, ami később nem lesz elég
- technológiát választunk
- hatókört szűkítünk (v1-ből kihagyunk valamit)
- egy invariánst módosítanánk — ilyenkor az ADR általában arról szól, hogy
  **miért nem** módosítjuk
- egy korábbi ADR kiváltó feltétele teljesült

Ha bizonytalan vagy: az ADR olcsó, a fél év múlva rekonstruált indoklás drága.

## Mikor nem kell

Megvalósítási részlethez, ami holnap átírható következmények nélkül.
Az ADR a nehezen visszafordítható döntésekről szól.

## Az induló készlet

| ADR | Tárgy |
|---|---|
| 001 | Műszak-központú modell |
| 002 | Az LLM fordít, nem foglal |
| 003 | Kapacitás = 1, UNIQUE index |
| 004 | SQLite + váltási feltételek |
| 005 | Redaktálás tárolás előtt |
| 006 | Ajánlatpontozó: képlet, korlát, küszöbök |
| 007 | Orchestrator = determinisztikus állapotgép |

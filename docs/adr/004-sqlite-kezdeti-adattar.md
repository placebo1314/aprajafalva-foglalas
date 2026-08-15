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

A CI minden futásnál mindkét motoron végigviszi a teljes tesztkészletet
(`python feladat.py teszt-mindketto`). Az írási latenciát a mag méri és
naplózza.

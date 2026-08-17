---
name: db-hordozhatosag
description: Adatbázis-hordozhatósági szabályok SQLite és PostgreSQL között — tiltott és kötelező minták, migrációs sablon, repository réteg, tranzakciókezelés, konkurencia. Használd, amikor sémát tervezel, migrációt írsz, SQL-t fogalmazol, a core/repo/ könyvtárban dolgozol, vagy adatbázis-kapcsolatot konfigurálsz.
---

# Adatbázis-hordozhatóság

## Miért

SQLite-tal indulunk (ADR-004), de a váltás Postgresre egy nap legyen, ne egy
hónap. Ezt nem ígéret garantálja, hanem az, hogy **a CI mindkét motoron
futtatja a teljes tesztkészletet**: `make teszt-mindketto`.

Ha egy teszt csak az egyiken megy át, az hiba — akkor is, ha a funkció működik.

## Tilos

| Minta | Helyette |
|---|---|
| `AUTOINCREMENT`, `INTEGER PRIMARY KEY` | UUID, `TEXT` oszlopban |
| `strftime()`, `julianday()`, `datetime('now')` | időszámítás az alkalmazásrétegben |
| `INSERT OR REPLACE`, `INSERT OR IGNORE` | `INSERT ... ON CONFLICT ...` |
| `WITHOUT ROWID` | semmi, felesleges |
| `GLOB` | `LIKE` |
| típusrugalmasságra hagyatkozás | explicit `CHECK` kényszer |
| SQL a repository rétegen kívül | minden lekérdezés a `core/repo/`-ba |

A migrációs linter hook ezeket automatikusan elkapja, de jobb eleve nem
leírni őket.

## Kötelező

**Kapcsolat megnyitásakor:**

```python
conn.execute("PRAGMA foreign_keys = ON")
conn.execute("PRAGMA journal_mode = WAL")
conn.execute("PRAGMA busy_timeout = 5000")
```

**Íráshoz explicit tranzakció:**

```python
conn.execute("BEGIN IMMEDIATE")   # nem a Python implicit módja
```

Az implicit tranzakciókezelés SQLite-ban meglepetéseket okoz, és Postgresen
másképp viselkedik. Legyen mindig kiírva.

**Egyetlen író folyamat.** Ez architekturális megkötés, dokumentálva az
ADR-004-ben. Ha ez megszűnik, az a Postgres-váltás kiváltó feltétele.

## Idő

Minden időpont **UTC-ben, ISO-8601 szövegként** tárolódik:

```
2026-03-29T08:00:00Z
```

Helyi idő csak a megjelenítésnél keletkezik. A DST-átállás így nem az
adatbázis problémája — de a slotgenerátornak tesztje van rá, mert Aprajafalván
márciusban és októberben eltűnik és megjelenik egy óra.

## UUID

```python
import uuid
uuid.uuid4().hex   # TEXT oszlopba
```

Nem azért, mert elosztott rendszert építünk, hanem mert az autoincrement a
migráció legfájóbb pontja: az idegen kulcsok újraszámozása egy egész napot
elvisz.

## Migrációs sablon

`migrations/0007_hold_tabla.sql`:

```sql
-- up
CREATE TABLE hold (
    id            TEXT PRIMARY KEY,
    slot_id       TEXT NOT NULL REFERENCES slot(id),
    session_id    TEXT NOT NULL,
    letrejott     TEXT NOT NULL,
    lejar         TEXT NOT NULL,
    CHECK (length(id) = 32),
    CHECK (lejar > letrejott)
);

CREATE UNIQUE INDEX ix_hold_slot ON hold(slot_id);
CREATE INDEX ix_hold_lejar ON hold(lejar);

-- down
DROP INDEX IF EXISTS ix_hold_lejar;
DROP INDEX IF EXISTS ix_hold_slot;
DROP TABLE IF EXISTS hold;
```

Minden migrációnak van `-- down` szakasza. Nem azért, mert gyakran fogunk
visszagörgetni, hanem mert a visszaút megírása kikényszeríti, hogy átgondold,
mit csinálsz.

## Konkurencia

A slot kapacitása 1, ezért **egyetlen parciális UNIQUE index** elég:

```sql
CREATE UNIQUE INDEX ix_foglalas_slot_aktiv
  ON foglalas(slot_id) WHERE allapot <> 'lemondva';
```

Ez a forma mindkét motorban működik. Ha valaha nevesített erőforrásra
intervallum-átfedést kellene tiltanunk, az Postgres-specifikus `EXCLUDE`
kényszert igényelne — a műszak-központú modell részben ezért is jobb.

```python
cur = conn.execute(
    "INSERT INTO foglalas (...) VALUES (...) ON CONFLICT DO NOTHING",
    parameterek,
)
if cur.rowcount == 0:
    return Eredmeny.MEGELOZTEK   # nem kivétel, hanem normál ág
```

## Repository réteg

Minden SQL a `core/repo/`-ban van, függvények mögé rejtve:

```python
# core/repo/foglalas_repo.py
def booking_create(conn, slot_id, customer_key, idempotency_key) -> Result: ...
def booking_lemond(conn, booking_id, reason) -> Result: ...
def slot_free(conn, slot_id) -> bool: ...
```

A hívó kód sosem lát SQL-t. Ez teszi lehetővé, hogy a Postgres-váltás egyetlen
könyvtár átírása legyen. Egy hook figyeli és blokkolja a rétegen kívüli SQL-t.

## A váltás kiváltó feltételei (ADR-004)

Bármelyik teljesül → Postgres:

- egynél több író folyamat kell
- p95 írási latencia > 50 ms
- egyidejű aktív session > 50
- replikáció vagy távoli hozzáférés igény

Ha ilyet észlelsz, ne kerüld meg — jelezd, és nyiss ADR-t a váltásról.

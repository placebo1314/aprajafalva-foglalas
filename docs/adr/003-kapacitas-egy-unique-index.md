# ADR-003: Kapacitás = 1, UNIQUE index

- **Dátum:** 2026-08-15
- **Állapot:** elfogadott

## Kontextus

A foglalási időszak megnyitásakor sok egyidejű session versenyezhet ugyanazon
slotért. A dupla foglalás elleni védelmet valahogy garantálni kell, és a
garanciának SQLite-on és Postgresen is azonosan kell viselkednie
(lásd ADR-004).

## Döntés

Minden slot kapacitása 1; a védelmet egyetlen parciális UNIQUE index adja
(`ix_foglalas_slot_aktiv ON foglalas(slot_id) WHERE allapot <> 'lemondva'`),
az írás mindig `INSERT ... ON CONFLICT DO NOTHING` formában történik.

## Miért

- Azonosan viselkedik SQLite-ban és Postgresben — nincs motorfüggő
  különbség, amit külön tesztelni vagy dokumentálni kellene.
- Az adatbázis maga a bizonyíték, nem alkalmazásszintű számláló vagy zár —
  konkurencia-teszttel közvetlenül igazolható, nem csak levezethető.
- Nem igényel emelt tranzakciós izolációs szintet, ami pont a legnagyobb
  terhelés (foglalási időszak nyitása) idején rontaná az írási átbocsátást.

## Amit feladunk

A naplózott foglalás-számláló kényelmét (gyors „hány hely van" lekérdezés
index nélkül), és azt a lehetőséget, hogy egy slotra átmenetileg második,
„tartalék" foglalást tegyünk emberi felülbírálat idejére.

## Kiváltó feltétel

- egy slotnak ténylegesen >1 kapacitásúnak kell lennie egyetlen szolgáltatás
  keretében
- egy bevezetendő adatbázismotor (pl. elosztott/multi-master) nem támogat
  azonos szemantikájú parciális UNIQUE indexet

## Váltás mire

Számláló alapú kapacitásmodell (`slot.kapacitas` mező), motorfüggetlen
tranzakciós ellenőrzéssel — a pontos mechanizmus (pl. több, sorszámozott
al-slot rekord saját UNIQUE indexszel) a döntés idején tervezendő, a
hordozhatósági szabályok (ADR-004, `db-hordozhatosag` skill) betartásával.

## Váltás költsége

A teljes `mag/repo/foglalas` réteg és a konkurencia-tesztkészlet
újraírása — becslés napokban, mert minden hívó a jelenlegi
`ON CONFLICT DO NOTHING` szemantikára épít.

## Ellenőrzés

A `konkurencia-teszto` agent tesztkészlete: párhuzamos írási teszt bizonyítja
0 dupla foglalást minden futásnál, `python feladat.py teszt-mindketto` mindkét
motoron.

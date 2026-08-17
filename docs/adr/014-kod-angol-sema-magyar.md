# ADR-014: A kód angolra vált, a séma és a domain szótár magyar marad

- **Dátum:** 2026-08-17
- **Állapot:** elfogadott

## Kontextus

A projekt eddigi konvenciója ("Domain-nevek magyarul, technikai nevek
angolul", CLAUDE.md) a Python-kódban is magyar azonosítókat eredményezett
(`muszak_letrehoz`, `torzsadat_repo`, `szervezet_id`), mert a domain maga
magyar (Aprajafalva, magyar nyelvű vásárlók, magyar szaknyelv: műszak, slot,
hold, szünetblokk). Ez addig működött, amíg a kódot kizárólag magyar
anyanyelvű fejlesztő írta és olvasta.

A tervezett M4/M5 mérföldkövek (asszisztens, dev mód) és a projekt
hosszabb távú életciklusa miatt reális, hogy előbb-utóbb nem magyar
anyanyelvű közreműködő is dolgozik a kódon, vagy a rendszer más nyelvű
piacra is nyílik. A magyar azonosítók ekkor akadállyá válnak — nem a
domainben (az helyesen magyar), hanem magában a kódban.

## Döntés

A **kód** (függvény-, változó-, osztály- és modulnevek) angolra vált. Az
**adatbázis-séma** (tábla- és oszlopnevek) és a **domain szótár**
(`docs/domain.md`) **magyar marad**.

Ez két, egymástól függetlenül kezelt réteget hoz létre:

- A séma a domain nyelve — `docs/domain.md`-re épül, és az átnevezése a
  legvédettebb, legmagasabb kockázatú részt (migrációk, éles adat)
  érintené, kiváltó feltétel nélkül nem indokolt.
- A kód a fejlesztők nyelve — ez szabadon, migráció nélkül átnevezhető,
  mert nincs rá tárolt adat, ami vele együtt öregedne.

A határ konkrétan: SQL-stringekben szereplő tábla-/oszlopnevek és a
`mag/repo/`-függvények (a döntés idején: `core/repo/`) visszaadott
dict-jeinek **string-literál kulcsai** változatlanul magyarok maradnak —
ezek a séma nyelvét követik, nem a kódét. Minden más Python-azonosító
(paraméter, helyi változó, osztály, modul) angolra fordul.

A modulnevek közül csak a top-szintű csomagok mozognak (`git mv`-vel):
`mag→core`, `asszisztens→assistant`, `felulet→ui`, `adatvedelem→privacy`,
`tesztek→tests`, `eszkozok→tools`, `migraciok→migrations`. A `seed/` és a
`spike/` marad (utóbbi eldobható kód, docs/roadmap.md M-1). Az almodulok
(`repo/`, `slot/`, `modell/`, `szabalyok/`, `api/`) és a legtöbb fájlnév
Hungarian maradt ezen a körön — csak ott mozgott fájl is
(`core/modell/muszak.py → core/modell/shift.py`), ahol a bare fájlnév
maga is a lefordítandó domain-szó volt, és a régi néven hagyása vakon
törte volna az importokat.

## Miért

- A séma-váltás sokkal drágább és kockázatosabb (migráció, éles adat,
  visszamenőleges kompatibilitás), mint a kód átnevezése (csak azonosítók,
  nincs tárolt állapot) — külön döntés, külön kiváltó feltétel jár neki.
- A `docs/domain.md` már létező, karbantartott magyar szótár — nem
  duplikáljuk angolul, hanem a kód és a séma közötti hidat egy explicit
  magyar↔angol táblázattal egészítjük ki (lásd `docs/domain.md`).
- A string-literál kivétel (SQL, dict-kulcs) azért szükséges, mert ezek
  ténylegesen a sémát hordozzák — ha ezeket is lefordítanánk, a Python-kód
  és az adatbázis szótára szétválna, és minden lekérdezés egy hallgatólagos
  fordítási táblára szorulna.

## Amit feladunk

- Átmeneti inkonzisztenciát a kód és a séma/CLI felszíne között: egy
  fejlesztő, aki csak a Python-kódot olvassa, angol neveket lát
  (`create_booking`), de az SQL-ben és a CLI-parancsokban (pl.
  `python -m core.api.cli demo-verseny`, `foglal`, `lemond`) továbbra is
  magyar szavakkal találkozik — ez a séma és a felhasználói felület
  (Aprajafalva magyar ajkú működtetői) nyelve, ez a döntés nem érinti.
- Egy kis, de valós kockázati felületet: néhány magyar szó (pl. `datum`,
  `sessziok`/`sessionok`, a `mag` mint "RNG-seed" és mint "modulnév")
  angolra fordítva ütközésbe kerülhet Python-beépítettekkel vagy más,
  szintén lefordított szóval — ezeket kézzel kellett feloldani (lásd a
  commit-történetet), és ez a kockázat minden jövőbeli hasonló átnevezésnél
  visszatér.
- A teljes egyöntetűséget: az almodulok és a legtöbb fájlnév egyelőre
  Hungarian maradt, tehát `torzsadat_repo.create_shop(...)`-szerű,
  vegyes nyelvű hívások keletkeztek. Ez tudatos, szűkített kör ezen a
  körön — teljes fájlnév-egységesítés külön feladat.

## Kiváltó feltétel

A séma (tábla-/oszlopnevek) átnevezéséhez:

- nem magyar anyanyelvű fejlesztő csatlakozik a projekthez, VAGY
- a rendszer ténylegesen többnyelvűvé válik (nem csak a UI-szöveg, a
  domain maga is)

Idáig a séma és a domain szótár marad magyar — ez nem ideiglenes
kompromisszum, hanem a jelenlegi, egynyelvű, magyar falusi kontextusban a
helyes, végleges állapot.

## Váltás mire

Ha a kiváltó feltétel teljesül: új migrációs sorozat, ami a tábla- és
oszlopneveket angolra fordítja, és egy hosszabb accompanying munka, ami a
`docs/domain.md` szótárt kétirányúra bővíti (jelenleg csak magyar→angol
irányban szolgál referenciaként).

## Váltás költsége

Magas: minden migráció, minden SQL-string, minden repo-függvény
újraírása, és egy időszak, amíg a régi és új séma egymás mellett fut
(lásd `db-hordozhatosag` skill, verziózási minta). Ez a magas költség
maga az oka annak, hogy ezt a döntést nem hozzuk meg elővigyázatosságból,
csak akkor, ha a kiváltó feltétel ténylegesen teljesül.

## Ellenőrzés

A kiváltó feltétel teljesülését emberi esemény jelzi (új fejlesztő
csatlakozása, piaci/nyelvi bővítési döntés), nem folyamatos mérés — ez a
tábla-oszloknevek státuszát alapvetően megváltoztató, ritka esemény, nem
küszöbérték-alapú metrika.

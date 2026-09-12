# ADR-035: Tizennyolc forduló — öt szerkezeti hiba egy beszélgetésben

- **Dátum:** 2026-09-21
- **Állapot:** elfogadott
- **Kiváltó ok:** a második IDEGEN próba (18 forduló egy foglalásig, a
  tizedikben frusztráció) — `naplo/probak.jsonl`, session `8292e38a`

## Kontextus

A barátunk lefoglalt egy időpontot. Tizennyolc fordulóból.

| # | amit mondott | ami történt |
|---|---|---|
| 1 | „Örömöt szeretnék. Van nálatok? Mikor?" | melyik boltba szeretnél menni? |
| 3 | „Van késõbbi?" | ugyanaz a keresés, ugyanaz a 8:00 |
| 4 | „10 után kéne." | ugyanaz |
| 5 | „nem jó nekem ilyen korán." | ugyanaz |
| 6 | „ez minden nap van?" | ugyanaz |
| 7 | „akkor a legkésõbbit. De melyik nap?" | ugyanaz |
| 10 | „Így nem haladunk elõre." | **melyik boltba szeretnél menni?** |
| 11 | „de azt már megbeszéltük te láma." | kiút |
| 14 | „igen...ha máshogy nem megy." | új keresés, a választott időpont eldobva |
| 18 | *(gombnyomás)* | foglalás létrejött |

**Egyetlen forduló sem volt önmagában hibás.** Minden válasz védhető:
a keresés lefutott, a visszakérdezés a hiányzó boltra kérdezett, a
kiút a frusztrációra reagált. A beszélgetés EGÉSZE mégis rossz volt —
és a rendszernek nem volt szeme, amivel ezt lássa.

## Döntés

### 1. Az állapotgép nem lép vissza

`AJANLAT_VAR` és `MEGEROSITES_VAR` állapotból a `HIANYZO_ADAT`
**tiltott átmenet** (`allapotgep.ATMENETEK`). Ha már felajánlottunk
időpontokat, egy frusztrált vagy értelmezhetetlen mondat nem törli
őket. A visszakérdezés HELYETT új válaszfajta megy ki:

> Az imént ezeket ajánlottam — Kedden, december huszonkettedikén: 8:00,
> 9:30 vagy 10:20. Melyik jó, vagy nézzek mást?

Az `ajanlat_emlekezteto` állapottartó, nem keres újra, és a holdokhoz
sem nyúl. **A tiltott átmenet ezentúl MARADÁST jelent, nem
`INDULAS`-t**: a beszélgetésben az a legdrágább, ha elfelejtjük, hol
tartunk.

### 2. A hezitáló igen az igen

`MEGEROSITES_VAR` állapotban a kötött dekódolás sémája **háromértékű**:
`igen` / `nem` / `mas_kerdes`. A modell fizikailag nem tud keresésbe
fordulni egy olyan mondatból, mint az „igen...ha máshogy nem megy".

Ez NEM kulcsszólista: a „jó, legyen", „hát ha muszáj", „rendben, csak
végezzünk" végtelen sok alakban létezik, és a felismerés a modell
dolga. Amit mi adunk hozzá, az a SZERKEZET: zárt kérdésre zárt
válaszhalmaz. A hangulat külön mezőbe mehet (`hangulat: kelletlen`),
a naplóba be is kerül — **a döntést nem befolyásolja.**

### 3. A rendszer beszél az ajánlatáról

Új irányítási érték: `ajanlat_kerdes`, négy kérdésfajtával
(`assistant/tools/ajanlat_kerdes.py`):

| `mit` | mikor | mi történik |
|---|---|---|
| `melyik_nap` | „ez minden nap van?", „melyik nap?" | a jelöltekből felel, **keresés nélkül** |
| `mikor_van` + sorszám | „a másodikat mikorra?" | egy konkrét jelöltről felel |
| `van_kesobbi` | „van későbbi?", „nem jó ilyen korán" | **ELTOLJA az ablakot** a legkésőbbi ajánlat mögé |
| `van_korabbi` | „van korábbi?" | eltolja a legkorábbi ajánlat elé |

Az eltolás a lényeg: enélkül ugyanazt találnánk meg megint — és ez
ötször egymás után megtörtént. A `van_kesobbi` a megőrzött NAPSZAKOT is
elengedi: a „nem jó ilyen korán" épp azt mondja, hogy oda ne nézzünk.

### 4. Az ajánlat kimondja a napot

> Kedden, december huszonkettedikén: 8:00, 9:30 vagy 10:20. Melyik jó?

Naponként csoportosítva, mindkét módban. Hangon a napnév a
legkorábbi időpont mellett hangzik el („A legkorábbi **kedden**,
december huszonkettedikén nyolc órakor…") — ott továbbra is két
időpont megy ki, mert három felolvasott időpont megjegyezhetetlen
(ADR-023).

A 7. forduló ezt kérdezte: *„De melyik nap?"* A dátum ott volt a
gombokon — a MONDATBAN nem, és hangon gomb sincs.

### 5. A szolgáltatások köznyelvi neve a törzsadatban van

Új oszlop (`szolgaltatas.koznyelvi_nevek`, 0005. migráció): ahogy a
VÁSÁRLÓ hívja, nem ahogy a bolt nevezi. „öröm, nagy öröm, beszélgetés,
vigasz" → boldogság → Törpilla.

Két helyen használjuk, és a kettő nem ugyanaz:

- **a modellnek**: a rendszerprompt statikus boltsora HELYÉRE a
  törzsadatból épített kínálat kerül (`kinalat.prompt_sor`);
- **a determinisztikus kapunak**: köznyelvi alak → bolt slug szótár
  (`kinalat.koznyelvi_szotar`), ami akkor tölti ki a boltot, ha a
  modell üresen hagyta. Ugyanaz az elv, mint a dátumnál (ADR-011): a
  modell ÉRT, a determinisztikus réteg FELOLD.

**Miért kellett mindkettő.** Mérve (2026-09-21): a kínálat-sor a
BESZÉLGETÉS elején nem segített — ott a modell adatnak látta, nem
szótárnak. A rendszerpromptban már igen. De az „Örömöt szeretnék. Van
nálatok?" mondatra a modell így is `MINDEGY` boltot adott (a „nálatok"
az egész falut jelenti neki) — a determinisztikus kapu az, ami
eljut a Törpilláig.

### 6. Mérőszám: hány forduló az első kéréstől a foglalásig

`python feladat.py naplo` és a riport fejléce is számolja,
beszélgetésenként (`ut_hosszak`). **Cél: 5 alatt.** A köszönés és a
katalógus-kérdés nem számít bele — az a bevezetés (ADR-032), nem a
foglalás útja.

Ez a kör legfontosabb száma: a réteg-megoszlás és a válaszidő azt
mondja meg, hogy a rendszer jól dolgozik-e, ez azt, hogy a VÁSÁRLÓ
eljut-e valahova.

## Miért így

- **A szerkezet erősebb, mint a prompt-fegyelem.** Mind az öt javítás
  olyan helyre került, ahol a hiba strukturálisan nem születhet meg:
  tiltott átmenet, szűkített séma, zárt kérdésfajta-halmaz,
  törzsadat-oszlop. A prompt egyikben sem a fő eszköz.
- **A köznyelvi név ADAT.** Ha egy bolt holnap „vidámságot" is árul,
  azt az admin írja be, nem mi írjuk át a promptot (blueprint 10.).
- **Az út hossza a beszélgetésé, nem a fordulóé.** Az idegen próba
  minden fordulója külön-külön rendben volt; csak az összeg volt rossz.
  Ha nincs olyan szám, ami a beszélgetésre néz, ez a hiba láthatatlan.

## Amit feladunk

- **Egy séma helyett kettő.** A `MEGEROSITES_VAR` külön sémát kap; ha
  egy harmadik állapot is kap majd, a `format_sema()` elágazása nő. Ma
  két ág, kimondott feltétellel.
- **A köznyelvi szótár SZÓALAKOKAT illeszt, nem tőket.** A
  „beszélgetés" bejegyzés nem fogja meg a „beszélgetni"-t. Ez a
  törzsadat dolga (vegye fel az admin), nem morfológiai elemzőé — de
  korlát, és mérhető: ha sok ilyen jön a naplóban, a döntést újra kell
  gondolni.
- **Az ajánlat-emlékeztető ismételhet.** Ha a vásárló háromszor mond
  értelmezhetetlent, háromszor kapja ugyanazt a listát. A
  frusztráció-figyelő ilyenkor is dolgozik, tehát a kiút megszólal —
  de az emlékeztetőnek magának nincs saját fokozata.

## Kiváltó feltétel

- **az `ajanlat_emlekezteto` elnyel egy valódi új kérést** (a naplóban
  emlékeztető olyan mondatra, ami boltot vagy dátumot mondott) — ekkor
  a kapu túl széles, és nem az állapotot, hanem a mondatot kell nézni;
- **a szűkített séma elnyel egy valódi kérdést** (`mas_kerdes` aránya
  tartósan magas MEGEROSITES_VAR-ban) — ekkor a megerősítés-kérdés
  maga a rossz, nem a séma;
- **az út hossza nem megy 5 alá** három egymást követő idegen próbán —
  ekkor nem ezek a hibák a szűk keresztmetszet, és új mérés kell arról,
  hol telik el a hat-nyolc forduló.

## Ellenőrzés

```
python -m pytest tests/egyseg/test_ajanlat_kerdes.py tests/egyseg/test_allapotgep.py
python feladat.py golden --halmaz beszedhelyzetek --ertelmezo forditott
python feladat.py naplo          # „AZ ÚT HOSSZA" szakasz
```

A `tizennyolc` golden réteg (12 eset) a próba mondatait SZÓ SZERINT
tartalmazza — a várt válasszal, nem azzal, ami történt.

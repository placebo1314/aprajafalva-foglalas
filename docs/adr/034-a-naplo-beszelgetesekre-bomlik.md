# ADR-034: A napló beszélgetésekre bomlik — és a koppintás is nyomot hagy

- **Dátum:** 2026-09-21
- **Állapot:** elfogadott
- **Kiváltó ok:** kézi próba után nem lehetett megválaszolni azt a
  kérdést, ami először merül fel: *hogyan jutott el a beszélgetés oda,
  ahova?*

## Kontextus

Három eszközünk olvasta a próba-naplót, és egyik sem a beszélgetésről
szólt:

| eszköz | egysége | mire jó |
|---|---|---|
| `naplo` | a teljes napló | összesítés: rétegek, válaszidők, hibaminták |
| `riport` | EGY forduló | teljes mélység: prompt, nyers válasz, mezőforrás |
| — | **a beszélgetés** | **nem volt** |

A napló FORDULÓK listája volt. Ebből három dolog hiányzott:

1. **Nem volt session-azonosító.** Az „új beszélgetés" gomb nem hagyott
   nyomot, tehát utólag csak az időbélyegek szünetéből lehetett sejteni,
   hol ér véget az egyik menet és hol kezdődik a másik.
2. **A koppintás nem került a naplóba.** Csak a beírt mondatok. Az
   útvonal tehát az AJÁNLATNÁL megszakadt: nem derült ki, választott-e a
   vásárló időpontot, megerősítette-e, létrejött-e a foglalás. Épp az a
   rész hiányzott, amiért az egész van.
3. **Két mező elavultan öröklődött.** Rövidzárnál (`orchestrator:sorszam`)
   a mondat el sem jut a normalizálóig, a gombos utak pedig nem
   frissítették az állapot-megfigyelést — így egy koppintással lefoglalt
   időpont három naplósorában ugyanaz az átmenet állt
   (`INDULAS -> AJANLAT_VAR`), a normalizált alak mezőjében pedig a KÉT
   FORDULÓVAL korábbi mondat.

## Döntés

**1. `session_id` minden naplósorba.** UUID, minden indításnál és minden
„új beszélgetés"-nél új. Nem vásárlói adat, tehát nem redaktáljuk — de
személyhez sem köthető.

**2. A koppintással kiváltott fordulók is naplóznak**
(`ui/vasarlo.py::_gomb_naplo`): jelöltválasztás, megerősítés, elvetés,
alternatíva-keresés. A `reteg` itt `felulet:<akcio>`, nem `szabaly` vagy
`llm` — **egy gombnyomás nem ugyanaz a bizonyíték, mint egy helyesen
értelmezett mondat**, és a mérésben sem szabad annak látszania.

**3. Elavult mező helyett SEMMI.** A normalizált alak csak akkor kerül a
naplóba, ha az értelmező tényleg futott; az állapot-megfigyelés
(`utolso_allapot`) pedig minden állapotváltásnál frissül, nem csak a
szöveges forduló végén. Egy elavult mező rosszabb, mint a hiányzó: úgy
néz ki, mint egy tény.

**4. Új nézet: `python feladat.py utvonal`** (`tools/utvonal.py`).
Session-választó + lépegető (Előző/Következő, nyílbillentyűk), és
fordulónként három blokk:

- **Mi történt** — bemenet, normalizált alak, eszköz, paraméterek,
  válasz, és amit a vásárló LÁTOTT;
- **Miért így döntött** — kapuőr, réteg, rövidzár, mezőforrások, a
  dátumverseny (modell vs. parser, ki nyert), bizonyosság;
- **Hova tovább** — állapot és átmenet, mit kínáltunk fel, és mit
  mondott rá a vásárló.

**5. A magyarázatot nem találjuk ki.** Minden mondata a naplóban álló
mezőre mutat vissza. Ahol a napló hallgat, ott a nézet is rövidebb.
Két konkrét eset, ahol ez számít:

- a `None` bizonyosság NEM bizonytalanság, hanem azt jelenti, hogy a
  mezőt nem a modell adta (pl. a dátumot a parser oldotta fel);
- rövidzárnál a beírt 1.0 nem modell-pontszám — a nézet ezt ki is
  mondja, mert „a modell magabiztos volt" ott hazugság lenne.

**6. Ugyanaz a szöveg megy az ablakba és a `--szoveg` kimenetbe.** Egy
forrás, két megjelenés — különben a hibajelentésben más állna, mint a
képernyőn. A `--szoveg` egyben a képernyő nélküli út is: ha a Tk nem
nyílik meg, a nézet erre esik vissza, nem tracebackre.

## Miért így

- **A beszélgetés az elemzés természetes egysége.** Az állapot, a
  megőrzött paraméterek és az előzmény mind a session-höz tartoznak
  (ADR-019, ADR-028) — egy fordulót ezek nélkül nézni annyi, mint egy
  mondatot a szövegkörnyezete nélkül.
- **Tkinter, mert már van.** Nincs új függőség, és Windowson, macOS-en,
  Linuxon egyaránt elindul — mint a vásárlói felület.
- **A nézet SOSEM ír.** Naplót olvas, semmi mást. Egy elemző eszköznek
  nem lehet mellékhatása arra, amit elemez.

## Amit feladunk

- **A régi naplósorokban nincs azonosító.** Ott az időköz csoportosít
  (`_IDOKOZ_PERC = 10`), és a nézet ezt KIÍRJA (`becsült`). Egy sejtett
  határ nem ugyanaz a bizonyíték.
- **A napló hízik.** A koppintások miatt fordulónként több sor — cserébe
  a foglalás végre benne van.
- **A magyarázat SZÖVEGES sablonokból áll.** Ha egy réteg új okot kezd
  visszaadni, a nézet azt csak nyersen írja ki, amíg mondatot nem
  kap hozzá. Ez tudatos: inkább nyers, mint kitalált.

## Kiváltó feltétel

- **a magyarázat félrevisz** egy valódi hibakeresésnél (a nézet mást
  állít, mint ami a kódban történik) — ekkor a sablon és a forrás
  szétcsúszott, és a mondatokat a kód mellé kell kötni (pl. az
  orchestrator adja a magyarázat-kulcsot, ne a nézet találgassa);
- **a session-lista kezelhetetlenné nő** (több száz beszélgetés) —
  ekkor szűrés kell dátumra és végkimenetelre;
- **valaki a nézetből akar javítani** (pl. golden esetet felvenni egy
  fordulóból) — ez ma szándékosan nincs benne; ha kell, az már nem
  nézet, hanem szerkesztő, és külön döntés.

## Ellenőrzés

```
python -m pytest tests/egyseg/test_utvonal.py
python feladat.py utvonal --szoveg --utolso 1
python feladat.py utvonal                      # ablak, nyílbillentyűkkel
```

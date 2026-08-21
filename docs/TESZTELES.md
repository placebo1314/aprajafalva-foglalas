# Tesztelés

Ez a dokumentum azt írja le, hogyan ellenőrizd, hogy a rendszer működik —
automata teszttel és kézzel is. Az alapfogalmakhoz lásd `docs/KISOKOS.md`,
a projekt egészéhez `docs/ALLAPOT.md`.

## Automata tesztek

| Parancs | Mit futtat | Kb. mennyi ideig tart | Ha elbukik |
|---|---|---|---|
| `python feladat.py teszt` | A teljes `tests/` alatti tesztkészletet SQLite-on. | ~13 másodperc | A pytest kiírja, melyik teszt és melyik `assert` bukott, oszlopszámmal. `182 passed, 1 xfailed` a várt kimenet — az `1 xfailed` szándékos (lásd `docs/ALLAPOT.md`, "Ismert korlátok"). Ha ennél kevesebb `passed` vagy bármi `failed` van, az valódi hiba. |
| `python feladat.py teszt-mindketto` | Ugyanaz a tesztkészlet, előbb `sqlite`, utána `postgres` "motorral". | ~26 másodperc | **Figyelem:** a `postgres` ág ma ténylegesen ugyanazt a SQLite-ot futtatja újra (nincs Postgres-adapter, ADR-004) — ez a parancs ma nem bizonyít semmit Postgresen, csak kétszer futtatja le ugyanazt. |
| `python feladat.py lint` | `ruff format --check .`, utána `ruff check .`. | néhány másodperc | Kiírja a formázási/lint hibás fájlokat és sorokat. `ruff format .` (a `--check` nélküli) automatikusan javítja a formázást; a `ruff check .` hibáit kézzel kell megnézni. |
| `python feladat.py golden` | **Ma hibával leáll**: `No module named tests.golden.futtato`. Az M3 értékelő script még nincs megírva, csak az esetfájl (`tests/golden/nyelvi_alap.yaml`, 22 eset). Az M-1 mérésekhez az eldobható `spike/golden_futtato.py` futott, nem ez. | — | — |

## Kézi próbák sorban

Mindegyik előtt fusson le: `python feladat.py seed` (friss `aprajafalva.db`
a projekt gyökerében).

### Admin felület

```
python -m ui.admin
```

1. **Törzsadat felvitele.** *Törzsadat* fül → a "Hozzáadás" gombbal vegyél
   fel egy új boltot, majd (a bolt kiválasztása után) egy pultot, egy
   alkalmazottat, egy szolgáltatást. **Mit kell látnod:** mindegyik
   megjelenik a saját listájában közvetlenül a hozzáadás után, kiválasztva
   marad. **A hiba jele:** a lista üres marad, vagy hibaüzenet jelenik meg
   pirossal a fül alján.
2. **Műszak.** *Naptár és műszakok* fül → válaszd ki az imént létrehozott
   boltot → jobb oldali űrlapon add meg a műszak adatait (pult,
   alkalmazott, szolgáltatás, kezdet, vég) → "Létrehozás". **Mit kell
   látnod:** a műszak megjelenik a naptárrácsban a megfelelő napon és
   pultoszlopban. **A hiba jele:** piros hibaszöveg az űrlap alatt (pl.
   átfedés vagy érvénytelen időablak esetén ez helyes viselkedés, nem
   hiba).
3. **Sablon.** Kattints az imént felvitt műszakra a naptárban, majd
   *Sablonok és hét-másolás* fül → adj nevet → "Mentés a kiválasztott
   műszakból". **Mit kell látnod:** a sablon megjelenik a bal oldali
   listában.
4. **Hét alkalmazása.** Ugyanezen a fülön → válaszd ki a sablont → adj meg
   egy dátumot → "Erre a hétre (7 nap)". **Mit kell látnod:** az
   "Eredmény" mezőben egy összegzés (hány nap, hány műszak jött létre),
   és a naptár fülön az érintett héten megjelennek az új műszakok.
5. **Hét másolása.** Ugyanezen a fülön → add meg a forrás és a cél hét
   kezdetét → "Másolás". **Mit kell látnod:** a cél héten megjelenik a
   forrás hét TÉNYLEGES beosztása (nem csak a sablon) — kivételnapok
   mindkét oldalon kihagyva.
6. **Kivételnap.** *Törzsadat* fül → add meg a dátumot és az indokot →
   "Kivételnap felvétele". **Mit kell látnod:** az adott napra eső
   műszakok generálása kimarad (a naptáron a nap üresen jelenik meg
   azoknál a pultoknál, ahol a kivételnap érvényes).
7. **Ütközéslista.** *Ütközéslista* fül → "Frissítés". **Mit kell
   látnod:** egy lista a kemény kényszert sértő, átfedő vagy nulla slotot
   generáló műszakokról. A friss demóadaton ez nem üres — ez elvárt, nem
   hiba.

### CLI

Mindegyik parancshoz kell egy adatbázis-fájl útvonal; az alábbi sor egy
üres, ideiglenes fájlon mutatja be az egész folyamatot.

```
python -m core.api.cli migral proba.db
```
**Mit kell látnod:** `Lefuttatva: ['0001', '0002', '0003']`.

```
python -m core.api.cli seed proba.db
```
**Mit kell látnod:** `Betöltve: proba.db (szervezet: <azonosító>)`.

```
python -m core.api.cli keres proba.db <szervezet_azonosito>
```
**Mit kell látnod:** egy sorlistát `<slot_id>  <kezdet> – <vég>` formában.
Másold ki az első sor `slot_id`-jét a következő lépéshez.

```
python -m core.api.cli foglal proba.db <slot_id> aaaa...(64 karakter) idem-1 session-1
```
**Mit kell látnod:** `Eredmény: sikeres` és egy `Foglalási kód: XXXXXXXX`
sor. A `vasarlo_kulcs_hash` helyén 64 hex karakter kell (a valódi
azonosító hash-elt formája — a nyers azonosító sosem kerül ide,
CLAUDE.md 2. invariáns).

```
python -m core.api.cli lemond proba.db <foglalasi_kod>
```
**Mit kell látnod:** `Eredmény: sikeres`.

```
python -m core.api.cli holdok-takaritas proba.db
```
**Mit kell látnod:** `Törölve: N lejárt hold.` (N általában 0 egy friss
adatbázison).

**A hiba jele bármelyiknél:** `Eredmény: ` egy másik szó, mint `sikeres`
(pl. `foglalt` vagy `nem_talalhato`), vagy egy Python-hibakiírás
(traceback).

### Verseny-demó

```
python -m core.api.cli demo-verseny --sessziok 3 --mag 42
```

**Mit bizonyít:** hogy egyidejű foglalási kísérletek közül egy adott
slotra pontosan egy nyer — a parciális UNIQUE index a garancia, nem
alkalmazáslogika (ADR-003).

**Mire figyelj:** a kimenetben egy "MEGELOZTEK" sornak kell megjelennie
(a vesztes session), utána annak a session-nek újra kell próbálkoznia egy
másik időponton. A végén a "Végeredmény" szakasz `Szabad időpont a
végén: X/6` és `Nyert: ...` sorokat ír. Azonos `--mag` értékkel a
lefutásnak **mindig ugyanazt** kell adnia — ha nem, az önmagában hiba
(a determinizmus a `random.Random(mag)`-ra épül).

### Mentés és helyreállítás

Ehhez ma nincs önálló CLI-parancs, csak Python-függvény
(`core.repo.mentes.snapshot_create` és `.restore`). A legegyszerűbb
kézi próba a hozzá tartozó teszt lefuttatása, kilépőkóddal:

```
python -m pytest tests/egyseg/test_mentes.py -v
```

**Mit kell látnod:** `test_mentes_delete_restore_booking_exists PASSED`
és `test_snapshot_not_writes_felul_existing_target PASSED`. Az első teszt
maga a helyreállítási próba: ment, "elveszíti" (törli) az eredeti
fájlt, visszaállít egy pillanatképből, és ellenőrzi, hogy a foglalás és a
parciális UNIQUE kényszer is túlélte.

## Elfogadási feltételek

**Az M1 akkor kész, ha egy hónapnyi beosztás felvitele percekben mérhető,
nem órákban** (roadmap, M1 kilépési feltétel). Ezt így mérd:

1. Indítsd el az admin felületet friss demóadattal.
2. Indíts időzítőt, és vidd fel egy teljes hónapra a beosztást **a
   ténylegesen elérhető eszközökkel** (sablon mentése egy mintaműszakból,
   alkalmazás hétre, hét másolása a többi hétre, kivételnapok felvétele).
3. Állítsd meg az időzítőt, amikor a hónap minden pultjára, minden napjára
   megvan a műszak (kivéve a szándékos kivételnapokat).
4. Ha ez **10 percen belül** megvan — az elfogadási küszöb —, az M1 kritikus
   útja teljesült. Ha órákig tart, vagy menet közben olyan műveletet
   hiányolsz, ami miatt kézzel, műszakonként kell dolgozni, az azt jelzi,
   hogy a "mi hiányzik" lista (`docs/ALLAPOT.md`) még nem zárható le.

Ez a mérés ma **nem végezhető el hiánytalanul**, mert a húzható műszakok
és a kényszerkapcsolók még nincsenek megépítve (lásd `docs/ALLAPOT.md`,
"Mi hiányzik az M1 lezárásához") — a sablon+hét-másolás út már ma is
sokat gyorsít, de a mérést csak ezek megépülése után érdemes véglegesnek
tekinteni.

## Mit NE várj még

- **Nincs asszisztens.** Az M4 mérföldkő nem kezdődött el — nincs olyan
  felület, ahol egy törp magyarul ír egy mondatot, és a rendszer
  válaszol.
- **Nincs magyar nyelvi értelmezés.** A dátumparser-integráció, a
  normalizáló réteg (tájszólás, szleng, elgépelés) és az orchestrator
  állapotgép mind M4-hez tartozik, egyik sincs megírva.
- **Nincs értesítésküldés.** Az M5 mérföldkő (értesítés-**előállítás**,
  küldés nélkül, ADR-012) nem kezdődött el. Ma semmilyen csatornán nem
  megy ki üzenet.

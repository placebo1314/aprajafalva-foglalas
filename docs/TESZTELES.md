# Tesztelés

Ez a dokumentum azt írja le, hogyan ellenőrizd, hogy a rendszer működik —
automata teszttel és kézzel is. Az alapfogalmakhoz lásd `docs/KISOKOS.md`,
a projekt egészéhez `docs/ALLAPOT.md`.

## Automata tesztek

| Parancs | Mit futtat | Kb. mennyi ideig tart | Ha elbukik |
|---|---|---|---|
| `python feladat.py teszt` | A teljes `tests/` alatti tesztkészletet SQLite-on. | ~20 másodperc | A pytest kiírja, melyik teszt és melyik `assert` bukott, oszlopszámmal. `294 passed, 1 xfailed` a várt kimenet — az `1 xfailed` szándékos (lásd `docs/ALLAPOT.md`, "Ismert korlátok"). Ha ennél kevesebb `passed` vagy bármi `failed` van, az valódi hiba. |
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
8. **Bolti tudás szerkesztése** (docs/blueprint.md 10. szakasz). *Törzsadat*
   fül → válassz ki egy boltot a listában — a "Megjelenés" mező alatta
   automatikusan megtelik a meglévő szöveggel (ha a demóadatot töltötted
   be, ott már van szöveg). Írj bele valami mást, "Megjelenés mentése".
   **Mit kell látnod:** "Megjelenés mentve." üzenet; ha újra kiválasztod a
   boltot (kattints máshova, majd vissza), az új szöveg jön vissza, nem a
   régi. Ugyanígy próbáld ki egy szolgáltatás "Termékleírás" és "Ár"
   mezőjét — ezeket a "Kiválasztott szerkesztése" gomb menti el a
   névvel/időtartammal együtt, egy kattintással.

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

### Vásárlói felület

```
python -m ui.vasarlo
```

Két fül nyílik, **Koppintós út** és **Írjon nekünk** — mindkettő
ugyanazt az `assistant/orchestrator.py`-t hívja, LLM nélkül (a
determinisztikus értelmezőt, `assistant/interpreter/rule_based.py`).

**Fontos dátum-figyelmeztetés, mielőtt elkezded:** a koppintós út "Nap"
legördülője a valódi mai naptól számított 7 napot kínálja fel, de a
demóadat (`python feladat.py seed`) egy fix, **2026-12-21-gyel kezdődő
hétre** generál beosztást. Koppintós keresésnél emiatt kézzel írd be a
"Nap" mezőbe (vagy válaszd ki, ha a legördülő engedi) egy ebbe a hétbe
eső dátumot (pl. `2026-12-22`), különben "Sajnos nincs szabad időpont
ebben az ablakban" választ kapsz — ez ilyenkor NEM hiba.

1. **Koppintós keresés.** *Koppintós út* fül → válassz boltot (pl.
   "Törpilla") → írd be a napot (`2026-12-22`) → napszak "bármikor" →
   "Időpontok keresése". **Mit kell látnod:** egy szürke nyugtázó sor
   ("Nézem, mi van a(z) Törpilla boltban, 2026-12-22…") azonnal, utána
   gombokként a talált időpontok. **A hiba jele:** piros hibaszöveg,
   vagy egyik sem jelenik meg.
2. **Választás és megerősítés.** Kattints az egyik időpont-gombra.
   **Mit kell látnod:** "Biztosan lefoglaljam ezt az időpontot?" kérdés,
   egy azonosító-beviteli mező, "Igen, foglalom" és "Mégse" gomb. Írj be
   bármilyen szöveget azonosítóként (ez a demóban csak egy ideiglenes
   hash bemenete, nem valódi azonosító-ellenőrzés), "Igen, foglalom".
   **Mit kell látnod:** "Foglalás létrejött! Foglalási kód: XXXXXXXX" —
   a kód a foglalási kód alfabet szerint (nincs benne O/0/I/1).
3. **Mégse-ág.** Ismételd meg az 1-2. lépést, de a végén "Mégse"-t
   nyomj. **Mit kell látnod:** "Rendben, nem foglaltuk le. Kereshetsz
   újra." — és ha újra rákeresel ugyanarra az ablakra, a korábban
   elutasított időpontnak is szerepelnie kell a jelöltek közt (a hold
   felszabadult).
4. **Szöveges keresés, zárt kérdés gombokkal.** *Írjon nekünk* fül →
   írd be: `szeretnék petárdázni` → Küldés. **Mit kell látnod:** a
   rendszer visszakérdez, és mivel a bolt nem derül ki a mondatból, **három
   gomb** jelenik meg (Szundi / Ügyifogyi / Törpilla) — nem kell
   begépelni a választ. Kattints "Ügyifogyi"-ra. **Mit kell látnod:** a
   nyugtázó sor ("Nézem, mi van a(z) Ügyifogyi boltban…"), majd a
   találatok gombként (vagy "Sajnos nincs szabad időpont", ha a mai
   dátum nem esik a demóhétbe — lásd a fenti figyelmeztetést).
5. **Tényválasz-ág.** *Írjon nekünk* fül → írd be: `Hogy néz ki a
   Törpilla bolt?`. **Mit kell látnod:** a szerkesztett "megjelenés"
   szöveg jelenik meg válaszként (amit a `seed/betolt.py` töltött be,
   vagy amit az admin felületen szerkesztettél). Próbáld ki ugyanígy:
   `Meddig van nyitva a Szundi?`, `Mit árulnak a Törpillánál?` — mindegyik
   a megfelelő szerkesztett mezőt olvassa fel, **nem a modell generálja**
   (docs/blueprint.md 10. szakasz).
6. **Ár — a kapuőr elutasítja.** *Írjon nekünk* fül → írd be:
   `Mennyibe kerül a nagy petárda?`. **Mit kell látnod:** "Ez a kérdés
   nem foglalással kapcsolatos, ebben nem tudok segíteni." — **ez a
   helyes válasz**, nem hiba. Az ár a `bolt_info` sémájában lekérdezhető
   adat, de a kapuőr ma is elutasítja, mielőtt odáig eljutna (golden set
   `kapuor-02`).

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

- **Nincs LLM.** A `ui/vasarlo.py` szöveges útja magyarul ír mondatot
  ÉS válaszol, de az értelmező determinisztikus szabályrendszer
  (`assistant/interpreter/rule_based.py`), nem nyelvi modell — ez az M4
  mérföldkő **alapvonala**, amit egy jövőbeli LLM-integrációnak felül
  kell múlnia (`docs/ALLAPOT.md`). Kötött dekódolás, önkonzisztencia-
  ellenőrzés, bizalmi jelzés logprobokból — egyik sincs, mert nincs
  modellhívás, aminek szüksége lenne rájuk.
- **A magyar nyelvi értelmezés korlátozott.** A determinisztikus
  értelmező a golden set látható 22 esetén jól teljesít (lásd
  `docs/ALLAPOT.md`), de kulcsszó-/regex-alapú — szokatlan
  megfogalmazásra, amit nem láttunk előre, könnyen visszakérdezéssel
  vagy hibás felismeréssel reagál. Ez elvárt, nem hiba.
- **A `valasz` modul (M5) nincs megírva.** A rendszer válaszai (`ui/
  vasarlo.py::_UZENET_KULCS_SZOVEG`, `tenyvalasz_szoveg()`) egy
  ideiglenes, kódba írt szótárból jönnek, nem egy önálló
  mondatgeneráló rétegből.
- **Nincs értesítésküldés.** Az M5 mérföldkő (értesítés-**előállítás**,
  küldés nélkül, ADR-012) nem kezdődött el. Ma semmilyen csatornán nem
  megy ki üzenet.
- **A vásárlóazonosítás ideiglenes.** A `ui/vasarlo.py` bármilyen
  szöveget elfogad "azonosítóként", és egy sima SHA-256-tal hasheli
  (`privacy/hash_ideiglenes.py`) — ez NEM a végleges HMAC+pepper
  megoldás (CLAUDE.md 2. invariáns), és nem is ellenőrzi, hogy az
  azonosító valódi-e.

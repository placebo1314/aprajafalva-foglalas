# Tesztelés

Ez a dokumentum azt írja le, hogyan ellenőrizd, hogy a rendszer működik —
automata teszttel és kézzel is. Az alapfogalmakhoz lásd `docs/KISOKOS.md`,
a projekt egészéhez `docs/ALLAPOT.md`.

## Automata tesztek

| Parancs | Mit futtat | Kb. mennyi ideig tart | Ha elbukik |
|---|---|---|---|
| `python feladat.py teszt` | A teljes `tests/` alatti tesztkészletet SQLite-on. | ~20 másodperc | A pytest kiírja, melyik teszt és melyik `assert` bukott, oszlopszámmal. `467 passed, 1 xfailed` a várt kimenet — az `1 xfailed` szándékos (lásd `docs/ALLAPOT.md`, "Ismert korlátok"). Ha ennél kevesebb `passed` vagy bármi `failed` van, az valódi hiba. |
| `python feladat.py teszt-mindketto` | Ugyanaz a tesztkészlet, előbb `sqlite`, utána `postgres` "motorral". | ~26 másodperc | **Figyelem:** a `postgres` ág ma ténylegesen ugyanazt a SQLite-ot futtatja újra (nincs Postgres-adapter, ADR-004) — ez a parancs ma nem bizonyít semmit Postgresen, csak kétszer futtatja le ugyanazt. |
| `python feladat.py lint` | `ruff format --check .`, utána `ruff check .`. | néhány másodperc | Kiírja a formázási/lint hibás fájlokat és sorokat. `ruff format .` (a `--check` nélküli) automatikusan javítja a formázást; a `ruff check .` hibáit kézzel kell megnézni. |
| `python feladat.py golden` | A golden set (`tests/golden/nyelvi_alap.yaml`, 45 eset) kiértékelése a **determinisztikus** értelmezővel — nem indít Ollamát. Rétegenkénti bontást ír. | néhány másodperc | Kilépőkód 1, ha egy réteg a küszöbe alatt van; a kimenet megnevezi, melyik. Ma három réteg van küszöb alatt (`elengedes`, `valtozatossag`, `mintan_tul`) — ezek `igenyel_llm` esetek, a determinisztikus úton szándékosan buknak, nem hiba. |
| `python feladat.py golden --ertelmezo forditott --modell qwen3.5:9b` | Ugyanaz az **éles** értelmezővel (ADR-018: fordított kaszkád). Ollamát hív. `llm` és `kaszkad` értékkel a másik két felállás mérhető. | ~7-10 perc | Ha az Ollama nem fut, a mérés végigmegy, de minden fordulót a szabály-alapú tartalék old meg — a "Réteg-megoszlás" sorban `szabaly=45` látszik. Ez a jele. |
| `python feladat.py vegigjatszas` | A vásárlói felület szöveges útját játssza végig Tkinter-eseményhurok nélkül, 13 beszélgetéssel (`tools/vegigjatszas.py`). | ~1-3 perc | Traceback, vagy egy olyan forduló, ahol az `eszköz` sor `None`. A `naplo/probak.jsonl` közben ugyanúgy telik, mint kézi próbánál. |

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
ugyanazt az `assistant/orchestrator.py`-t hívja. A szöveges út a
fordított kaszkádot használja (ADR-018): ha fut a háttérszolgáltatás
(Ollama, `APRAJAFALVA_LLM_MODELL`), a modell értelmez; ha nem, **néma
visszaesés** a determinisztikus rétegre — a felület ugyanúgy működik,
csak a próba-naplóban lesz `"reteg": "szabaly"` mindenhol.

**Dátumot nem kell fejben tartanod.** Az ablak tetején egy sor kiírja,
melyik hétre és melyik boltba van beosztás, és mit jelent ezen a
felületen a "ma" — a felület a beosztáshoz igazodik, nem a
rendszerórához (részletesen lent, "Beszélgetés-próba").

1. **Koppintós keresés.** *Koppintós út* fül → válassz boltot
   (**Törpilla** — a demóadat csak ide generál beosztást) → a "Nap"
   legördülő már a beosztás hetét kínálja, hagyd az alapértéken →
   napszak "bármikor" → "Időpontok keresése". **Mit kell látnod:** egy
   szürke nyugtázó sor ("Nézem, mi van a(z) Törpilla boltban…") azonnal,
   utána gombokként a talált időpontok. **A hiba jele:** piros
   hibaszöveg, vagy egyik sem jelenik meg. (Szundi vagy Ügyifogyi
   választásakor a "Sajnos nincs szabad időpont" helyes válasz — oda a
   demóadat nem generál műszakot.)
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
   írd be: `szeretnék menni valamikor` → Küldés. **Mit kell látnod:** a
   rendszer visszakérdez, és mivel a bolt nem derül ki a mondatból,
   **három gomb** jelenik meg (Szundi / Ügyifogyi / Törpilla) — nem kell
   begépelni a választ. Kattints "Törpilla"-ra. **Mit kell látnod:** a
   nyugtázó sor ("Nézem, mi van a(z) Törpilla boltban…"), majd a
   találatok gombként.
5. **Tényválasz-ág.** *Írjon nekünk* fül → írd be: `Hogy néz ki a
   Törpilla bolt?`. **Mit kell látnod:** a szerkesztett "megjelenés"
   szöveg jelenik meg válaszként (amit a `seed/betolt.py` töltött be,
   vagy amit az admin felületen szerkesztettél). Próbáld ki ugyanígy:
   `Meddig van nyitva a Szundi?`, `Mit árulnak a Törpillánál?` — mindegyik
   a megfelelő szerkesztett mezőt olvassa fel, **nem a modell generálja**
   (docs/blueprint.md 10. szakasz).
6. **Ár — a kapuőr elutasítja.** *Írjon nekünk* fül → írd be:
   `Mennyibe kerül a nagy petárda?`. **Amit látni SZERETNÉNK:** "Ez a
   kérdés nem foglalással kapcsolatos, ebben nem tudok segíteni." — ez a
   helyes válasz, nem hiba. **Amit modellel ma gyakran látsz helyette:**
   a rendszer visszakérdez a boltra. Ez a fordított kaszkád ismert
   gyengéje (kapuőr-réteg 50%, ADR-018) — **nem** kritikus, mert a
   rendszer nem talál ki árat, csak feleslegesen kérdez. Modell nélkül
   (determinisztikus kapuőr) a helyes elutasítás megy. **Ami valódi hiba
   lenne:** bármilyen konkrét ár a válaszban.

### Beszélgetés-próba

Ez a szakasz a szöveges út (`Írjon nekünk` fül) kézi próbája: **pontosan
mit írj be, mit kell látnod, mi a hiba jele.**

#### Előkészület

```
python feladat.py seed
python -m ui.vasarlo
```

Modellel is, modell nélkül is végigjátszható. Modellel:

```
set APRAJAFALVA_LLM_MODELL=qwen3.5:9b     # Windows, cmd
$env:APRAJAFALVA_LLM_MODELL="qwen3.5:9b"  # Windows, PowerShell
```

és fusson az Ollama (`ollama serve`). Ha bármelyik hiányzik, a felület
**nem hibázik**, csak csendben a determinisztikus értelmezőre esik
vissza — az ablak tetején álló sor megmondja, melyik eset áll fenn.

#### Dátumot NEM kell fejben tartanod

Az ablak tetején egy sor áll, ilyesmi:

> A demóadat 2026-12-21 – 2026-12-27 hetére szól, beosztás ezekben a
> boltokban van: Törpilla. A mai nap (…) kívül esik ezen, ezért a „ma”
> ezen a felületen 2026-12-21-t jelent — nem kell dátumot fejben
> tartanod. Értelmező: qwen3.5:9b (ha nem fut, csendben szabály-alapú).

Ez azt jelenti: **nyugodtan írj „ma”-t, „holnap”-ot, „kedden”-t** — a
felület ezeket a demóhéthez képest oldja fel. Amit tudni érdemes:

| Amit beírsz | Mire oldódik fel | Van rá beosztás? |
|---|---|---|
| `ma` | 2026-12-21 (hétfő) | igen |
| `holnap` | 2026-12-22 (kedd) | igen |
| `szerdán` | 2026-12-23 | igen |
| `a héten` | 2026-12-21 – 27 | igen |
| `jövő héten` | 2026-12-28 – 2027-01-03 | **nincs** — az üres válasz itt helyes |

És **boltot** a **Törpillát** válaszd: a demóadat csak oda generál
műszakot. Szundi/Ügyifogyi keresésre a "Sajnos nincs szabad időpont"
válasz helyes, nem hiba.

#### A tíz próba

**Mindegyik próba előtt nyomj "Új beszélgetés"-t** (a szöveges fül
alján). A szándék kemény része (bolt, szolgáltatás) szándékosan túléli a
fordulókat — ez kell az alkudozáshoz —, de próbálgatás közben ez azt
jelentené, hogy az előző próba boltja beleszól a következőbe. A 6., 7.
és 9. próba viszont TÖBB egymást követő fordulóból áll: azok közben ne
nyomd meg.

| # | Amit beírsz | Mit kell látnod | A hiba jele |
|---|---|---|---|
| 1 | `Törpillához mennék holnap` | Nyugtázó sor a felismert ablakkal, majd időpontok gombként. | Visszakérdezés a boltra (a mondat kimondta), vagy üres találat. |
| 2 | `szeretnék menni valamikor` | Zárt kérdés + **három bolt-gomb**. Kattints a Törpillára → nyugtázó sor, majd időpontok. | Kitalált bolt vagy kitalált dátum: a helyes válasz itt a kérdés, nem a találgatás. |
| 3 | `Mennyibe kerül a nagy petárda?` | "Ez a kérdés nem foglalással kapcsolatos…" — **de modellel ma gyakran visszakérdez a boltra helyette** (ismert gyengeség, ADR-018, kapuőr 50%). | **Bármilyen ár** a válaszban. Az fordulna elő valódi hibaként; a felesleges visszakérdezés ma dokumentált korlát. |
| 4 | `Hogy néz ki a Törpilla bolt?` | A szerkesztett megjelenés-szöveg (`seed/betolt.py`, vagy amit adminban átírtál). | Kitalált leírás — ezt a mezőt a modell sosem generálja. |
| 5 | `Meddig van nyitva a Szundi szombaton?` | Nyitvatartás-mondat. | Foglalási ág, vagy találgatott nyitvatartás. |
| 6 | Előbb `Törpillához mennék`, aztán **külön fordulóban** `inkább délután` | A második fordulóban a boltot **nem** kérdezi újra — délutáni időpontok jönnek. | Újra rákérdez a boltra: a szándék kemény része elveszett. |
| 7 | Előbb `Törpillához mennék holnap`, aztán `és bármelyik másik boltban?` | Zárt kérdés a boltra, a három gombbal. | Makacsul marad a Törpillánál: a mondat elvetette, mégsem engedte el. |
| 8 | `Le szeretném mondani a foglalásomat.` | Kérdés a foglalási kódra. | Bármi más — kód nélkül lemondani nem szabad. |
| 9 | Írd be háromszor egymás után ugyanazt a semmitmondó mondatot (`mennék`) | A harmadikra **más mondat**, és koppintható kiút-gombok (Másik bolt / Másik hét / Másik napszak). | Harmadszor is ugyanaz a válasz. |
| 10 | Egy időpont-gomb → azonosítónak írj bármit → "Igen, foglalom" | "Foglalás létrejött! Foglalási kód: XXXXXXXX" | Hibaüzenet, vagy nincs kód. |

#### Ha valami furcsa: nyisd meg a naplót

A szöveges fül alján a **"Napló megnyitása"** gomb kiírja az eddigi
fordulókat (`naplo/probak.jsonl`), fordulónként nyolc mezővel:

```
3. [2026-08-23T00:41:07Z]          <- a VALÓDI óra (mikor próbáltad)
   bemenet:      'Törpillához mennék holnap'
   normalizált:  'Törpillához mennék holnap'
   réteg:        llm
   eszköz:       szabad_idopontok
   paraméterek:  {'bolt_id': 'torpilla', 'datum_tol': '2026-12-22T00:00:00Z', ...}
   bizonyosság:  {'eszkoz': 0.99, 'bolt_id': 0.98, ...}
   válasz:       ajanlat
```

Amit ebből leolvashatsz:

- **`réteg`** — `llm`, ha a modell értelmezett; `szabaly`, ha a
  determinisztikus tartalék. Ha mindenhol `szabaly`, akkor nem fut az
  Ollama, vagy nincs beállítva a modellnév. **Egy kivétel:** a bolt-gomb
  megnyomása után szándékosan `szabaly` áll ott — a zárt kérdésre adott
  válasz zárt halmazbeli érték, azt nem értelmezteti a rendszer.
- **`normalizált`** — mit LÁTOTT a rendszer abból, amit beírtál (a
  tájszólási alakok itt már köznyelviek).
- **`bizonyosság`** — a modell tényleges dekódolási valószínűségei. Ha
  egy kritikus mező 0,6 alatt van, az orchestrator zárt kérdéssel
  tisztáz (`BizonyossagKuszobok`) — ilyenkor a `válasz` mező
  `visszakerdezes` lesz, pedig a mondat egyértelműnek tűnt.
- **`válasz`** — `ajanlat`, `visszakerdezes`, `elutasitas`, `kiut`,
  `eszkoz_hiba` vagy `sikeres`.

#### Ugyanez fej nélkül, egyben

```
python feladat.py vegigjatszas
```

Végigjátssza a fenti (és a golden set `mintan_tul` rétegének)
mondatait Tkinter-eseményhurok nélkül, és fordulónként kiírja ugyanezt,
plusz a teljes foglalási menetet a foglalási kódig. Hasznos, ha csak azt
akarod látni, változott-e valami az előző futás óta.

**Figyelem:** VALÓDI foglalást hoz létre a megadott adatbázisban (ez a
lényege — épp azt ellenőrzi, hogy a felület elvezet-e a kódig).
`python feladat.py seed --ujra` visszaállítja, vagy adj meg külön
fájlt: `python feladat.py vegigjatszas --db proba.db` (előtte
`python -m core.api.cli seed proba.db`).

Ez a parancs eddig **hat hibát** talált, amit sem az egységtesztek, sem
a golden set nem fogott meg — mind felületi vagy réteghatár-hiba volt
(elavult időpont-gombok a képernyőn, a „ma" horgonya a bolt zárása
utánra esett, a bolt-gomb megnyomása végtelen visszakérdezésbe futott, a
modell árat olvastatott fel egy megjelenés-kérdésre, majd a címet, és
nem volt mód friss beszélgetést kezdeni). Érdemes minden felületi
változtatás után lefuttatni.

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

- **Önkonzisztencia-ellenőrzés nincs**, és a kötött dekódolás ma az
  Ollama JSON-séma-kényszere (`format`), nem GBNF/XGrammar szintű
  nyelvtan — a kettő nem ugyanaz (`docs/ALLAPOT.md`, M4 sor).
- **A magyar nyelvi értelmezés korlátozott.** A modell egy 9B-s, nem
  magyarra hangolt háló; a golden set `valtozatossag` és `mintan_tul`
  rétegein mindkét felállás a küszöb alatt van (`docs/ALLAPOT.md`,
  "Konkrét számok"). Szokatlan megfogalmazásra a rendszer
  visszakérdezéssel vagy hibás felismeréssel reagálhat. Ez ma elvárt,
  nem hiba — de ez a mérendő pont.
- **A modell nélküli futás nem hibaüzenet.** Ha nincs beállítva
  `APRAJAFALVA_LLM_MODELL`, vagy nem fut az Ollama, a felület csendben a
  determinisztikus rétegre esik vissza. Hogy melyik történt, a
  próba-napló `reteg` mezőjéből derül ki ("Napló megnyitása" gomb).
- **Nincs értesítésküldés.** Az M5 mérföldkő (értesítés-**előállítás**,
  küldés nélkül, ADR-012) nem kezdődött el. Ma semmilyen csatornán nem
  megy ki üzenet.
- **A vásárlóazonosítás ideiglenes.** A `ui/vasarlo.py` bármilyen
  szöveget elfogad "azonosítóként", és egy sima SHA-256-tal hasheli
  (`privacy/hash_ideiglenes.py`) — ez NEM a végleges HMAC+pepper
  megoldás (CLAUDE.md 2. invariáns), és nem is ellenőrzi, hogy az
  azonosító valódi-e.

# Próba-jegyzet — öt perc, kézzel

Nem dokumentáció: **használati sorrend**. Mit írj be, mit nézz, mi a
hiba jele. A teljes kézi próbasor a `docs/TESZTELES.md`-ben van, ez
annak a rövid, mai változata.

## 1. Indítás (30 másodperc)

```
python feladat.py seed                      # demóadat, egyszer elég
set APRAJAFALVA_LLM_MODELL=qwen3.5:9b       # Windows cmd; PowerShell: $env:...
python -m ui.vasarlo
```

**Indításkor a felület ELLENŐRZI, hogy fut-e a modell** (2026-08-31
óta): konfigurálva van-e, válaszol-e az Ollama, és le van-e töltve a
kért modell. Ha bármelyik hiányzik, MODÁLIS ablak jön fel — megmondja,
melyik a három ok közül, mit kell beírni, és két gombot ad:
**„Folytatom tartalékággal"** vagy **„Kilépek"**. A tartalékág érvényes
választás (pl. ha épp a determinisztikus réteget próbálod), csak nem
lehet véletlen.

Miért lett ez modális: háromszor futott végig kézi próba tartalékágon
úgy, hogy csak utólag derült ki — a sárga sávot el lehet olvasni és el
lehet felejteni, főleg ha a beszélgetés egyébként értelmes válaszokat
ad. A sárga sáv MEGMARADT az ablak tetején, a naplóban pedig
fordulónként ott áll, volt-e konfigurált modell és melyik prompt-verzió
futott. A beszélgetés-riport fejlécében piros sáv jelenik meg, ha a
beszélgetésben egyetlen modellhívás sem volt.

A figyelmeztetés alatti sor mondja meg, mit jelent itt a „ma" (a
demóadat egy távoli hétre szól, a felület ahhoz horgonyoz).

Két fül van: **Koppintós út** (gombok) és **Írjon nekünk** (szöveg). A
próba a másodikon zajlik.

## 2. A kimeneti mód-kapcsoló

A szöveges fül tetején: **Kimenet: ( ) szöveges ( ) beszélhető
(felolvasásra)**.

| Mód | Mit látsz | Mire jó |
|---|---|---|
| `szöveges` | a mai viselkedés: több sor fordulónként, időpontok gombokon | ez megy ma a képernyőre |
| `beszélhető` | **egy megszólalás** fordulónként, legfeljebb két mondat, egy kérdés, minden szám kimondva | ez az, amit a TTS kapna — hang nélkül is látható |

Menet közben átkapcsolható; a következő fordulótól érvényes.

## 2b. Amit az ELSŐ ÉLES PRÓBA után érdemes kipróbálni

Három dolog 2026-09-05 óta megy, és mind a három egy valódi próbában
bukott meg először (`docs/ELES_PROBA_20260905.md`):

| írd be | mit kell látnod |
|---|---|
| „te egy robot vagy?", „mit tudsz?" | rövid bemutatkozás — NEM keresés, és a beszélgetés ott folytatódik, ahol abbamaradt |
| „nekem mind jó, válassz te" (felajánlott időpontok után) | a rendszer választ, és KIMONDJA, melyiket: „A legjobb, amit találtam: … Lefoglaljam?" |
| „a hét tizenötös" (felajánlott időpontok után) | a 7:15-kor KEZDŐDŐ időpontra kér megerősítést |

Az első fordulónak már nem kell megvárnia a modell betöltését: az ablak
indításkor előmelegít, és a „Kimenet:" sor mellett kiírja, mikor lett
kész.

## 2c. Amit az első IDEGEN próba után érdemes kipróbálni

Az első próbát olyan ember végezte, aki nem ismerte a rendszert — és
négy forduló alatt jutott el a köszönéstől odáig, hogy menjen be a
boltba élőben (`docs/BEVEZETES_20260919.md`). **Ha valakinek megmutatod
a rendszert, ezzel kezdd**, mert ezen az úton jár egy új ember:

| írd be | mit kell látnod |
|---|---|
| „helló." | köszönés + a három bolt LEÍRÁSSAL: „a Szundiba altatóért, az Ügyifogyiba petárdáért…" — és gombok |
| „milyenek vannak?", „mit lehet itt?" | ugyanaz a felsorolás, modellhívás NÉLKÜL (a naplóban `kapuor` réteg) |
| „Mit lehet kapni a Törpillánál?" | CSAK a Törpilla — aki megnevezi a boltot, annak a három felsorolása zaj |
| „Jó napot! Szeretnék időpontot a Szundiba holnapra" | keresés, NEM bemutatkozás — a kérés viszi a fordulót |

**A gombokon leírás áll, nem azonosító**: „Szundi — altató", nem
„szundi". A zárt bolt-kérdés mellett ott a **„Mit lehet itt?"** gomb is.

**Amit NEM szabad látnod**: „menjen be a boltba élőben" olyan
beszélgetésben, amiben keresés még nem futott. Írd be háromszor, hogy
„mennék" — a válaszoknak MÁSNAK kell lenniük: visszakérdezés →
katalógus → „Kezdjük a legelején: melyik boltba szeretnél menni?". A
negyedikre jön csak az emberhez irányítás.

## 3. Amit érdemes beírni

**Mindhárom boltban van beosztás**, három különböző ritmusban — ez
2026-08-30 óta van így, és érdemes kihasználni:

| Bolt | Ritmus | Nyitva (helyi idő) |
|---|---|---|
| **Szundi** | hosszú, ritka: 30 perc, óránként egy | 14–20 |
| **Ügyifogyi** | rövid, sűrű: 5 perc, 10 percenként | 9–17 |
| **Törpilla** | három pult, három ritmus | 8–16 |

Ugyanaz a mondat háromféle választ ad — ezt érdemes összevetni. Ami
`jövő hétre` szól, ott továbbra is üres a válasz: a demóadat egy hétre
generál, és az üres válasz ilyenkor helyes.

**Ami 2026-08-30-tól NEM fog előjönni:** „Nézzük a … boltban" gomb. A
bolt nem alternatíva, hanem maga a termék (ADR-024) — üres találatnál
a felajánlás bolton BELÜL marad: másik napszak, másik nap, a legkorábbi
szabad időpont, másik változat. A válasz mindig megmondja, melyikben
engedett.

| Beírás | Mit nézz szöveges módban | Mit nézz beszélhető módban |
|---|---|---|
| `Törpillához mennék holnap` | nyugtázó sor, majd időpont-gombok | *„A legkorábbi december huszonkettedikén hét órakor, de van hét tizenötkor is. Melyik jó?"* — **két** időpont, nem három |
| `szeretnék menni valamikor` | „Ehhez még kellene tudnom…" + három bolt-gomb | *„Melyik boltba szeretnél menni?"* — kérdés, nem kijelentés |
| `Mennyibe kerül a nagy petárda?` | ár-elhárítás, **azonnal** (a kapuőr modellhívás nélkül dönt) | ugyanaz, gondolatjel nélkül |
| `Hogy néz ki a Törpilla bolt?` | a szerkesztett megjelenés-szöveg | ugyanaz — ha számot tartalmaz, kimondva |
| egy időpont-gomb → azonosító → „Igen, foglalom" | `Foglalási kód: XXXXXXXX` | *„Megvan a foglalás. A kódod kettő bé ká es…"* — **betűzve** |
| `nem értem, mit kell csinálni` ×4 | 2. fordulóra kiút-gombok, **3.-ra emberhez irányítás** | ugyanaz, egy mondatba építve |
| ajánlat után: `a másodikat` vagy `az utolsó jó lesz` | egyből a megerősítés — **modellhívás nélkül** (a naplóban `orchestrator:sorszam`) | *„December huszonkettedikén kilenc órakor foglalnám le. Rendben?"* |
| `Szeretnék időpontot nyolcvan órára a Törpillába` | keresés óra nélkül, vagy visszakérdezés | **soha nem** nyolc órára szűkített keresés |
| `Bármelyik petárda jó, csak csütörtökön legyen` | keresés indul, és **nem kérdez rá a méretre** — a naplóban `szolgaltatas_id: MINDEGY` | ugyanaz, egy mondatban |
| `Mindegyik boldogság-fajta érdekel, mit lehet kapni?` | a termék-felsorolás, **nem keresés** — ez lista-kérés, nem elengedés | ugyanaz |
| `Mikor tudok legkorábban menni a Szundihoz?` | **EGY** időpont, nem lista, és **nem kérdez vissza időablakot** | *„A legkorábbi …"* |
| koppintós fül: bolt kiválasztása → **„A legkorábbi szabad időpont"** | nap és napszak nélkül fut le | — (a koppintós út mód nélküli) |

**Minden próba előtt nyomj „Új beszélgetés"-t** — a rendszer az előző
fordulókat is átadja az értelmezőnek, tehát az előző próba különben
beleszól a következőbe. Kivétel a többfordulós próbák (a 4×-es panasz, a
foglalási menet): azok közben ne nyomd meg.

## 4. Mire figyelj beszélhető módban

A gépi ellenőrzést a teszt elvégzi (nincs számjegy, kötőjel, zárójel,
felsorolásjel; legfeljebb két mondat és egy kérdés). **Amit csak te tudsz
megnézni:**

1. **Olvasd fel hangosan.** Ha levegőt kell venni a közepén, hosszú.
2. **A megmaradt kérdés a HELYES kérdés-e?** A szabály az utolsót
   tartja meg — azt nem tudja, melyik a fontos.
3. **A betűzött kódot le tudod írni hallás után?** Ha nem, a betűzés
   rossz.

Ami **valódi hiba**: bármilyen számjegy, kötőjel vagy zárójel a rendszer
mondatában; három felsorolt időpont; két kérdés egy megszólalásban.

## 5. A napló olvasása

A szöveges fül alján **„Napló megnyitása (böngészőben)"** — a
beszélgetés-elemzőt nyitja meg: egyetlen HTML fájl
(`naplo/riport.html`), fordulónként **összecsukható blokkal**.
Parancssorból ugyanez:

```
python feladat.py riport --megnyit      # megnyitja a böngészőben
python feladat.py riport --utolso 20    # csak az utolsó 20 forduló
```

Egy fordulót kinyitva ezt látod, ebben a sorrendben:

| Rész | Mire felel |
|---|---|
| bemenet ↔ normalizált alak | mit LÁTOTT a rendszer abból, amit beírtál (ha átírta, „átírva" jelölés) |
| réteg színkóddal | ki döntött — a **piros** (`szabaly:tartalek`) az egyetlen riasztó |
| paraméterek, forrással | minden érték mellett, honnan jött: modell, parser, zárt halmaz |
| dátumfeloldás | mit adott a modell, mit a parser, **melyik nyert** |
| a teljes prompt (csukva) | mit kapott ténylegesen a modell — a „miért ezt csinálta" válasza |
| nyers modellválasz | a modell szava, mielőtt a kapuk hozzányúltak |
| lépésenkénti idő | hol telt el a válaszidő |
| a kimenő válasz mindkét módban | ugyanaz a döntés, szövegesen és felolvasva |

A fejlécben: fordulószám, réteg-megoszlás, p50/p95 válaszidő és
tendencia, visszakérdezések, kiút/ismétlés száma.

### A nyers napló, ha az kell

A `naplo/probak.jsonl` fordulónként egy JSON-sor. A fontos mezők:

- **`réteg`** — `llm` (a modell értelmezett), `kapuor` (elhárítás
  modellhívás nélkül), `szabaly:tartalek` (**az Ollama nem válaszolt**),
  `szabaly:zart_valasz` / `szabaly:tenyvalasz` (szándékos gyors út).
- **`normalizált`** — mit látott abból, amit beírtál.
- **`bizonyosság`** — ha egy kritikus mező 0,6 alatt van, a rendszer
  visszakérdez, pedig a mondat egyértelműnek tűnt.
- **`válaszidő`** — fordulónként.

Összesítve, parancssorból:

```
python feladat.py naplo              # a teljes napló
python feladat.py naplo --utolso 20  # csak az utolsó 20 forduló
```

Amit ebből olvass ki, ebben a sorrendben:

| Sor | Mikor rossz |
|---|---|
| **Válaszidő-eloszlás** | ha a `p50` 10 s vagy a `p95` 25 s fölé megy (ADR-022) |
| **tendencia** | ha `ROMLIK` — nem bukás, hanem kérdés: mi lassult |
| **`csendes_tartalek`** hibaminta | ha megszólal: futott modell, de egyes fordulók mégis a tartalékra estek |
| **`lassu_fordulo`** | egy forduló a p95-elvárás felett |
| **réteg-megoszlás** | ha `szabaly:tartalek` dominál, nem fut az Ollama |

Egy naplósorból golden teszteset-váz is írható:
`python feladat.py naplo --golden 17` — a `varhato` mezőt **üresen
hagyja**, azt neked kell kitöltened, mielőtt mérnél.

## 6. Ha nem akarsz kattintgatni

```
python feladat.py vegigjatszas --mod beszelheto     # 14 beszélgetés + foglalási menet
python feladat.py vegigjatszas --mod mindketto      # ugyanaz kétszer, összevethetően
python feladat.py vegigjatszas --robusztus          # + a teljes robusztussági halmaz (68 eset)
```

Ugyanaz a felület fut, csak eseményhurok és kattintás nélkül, és a
napló ugyanúgy telik. **Valódi foglalást hoz létre** — vagy adj meg
külön fájlt (`--db proba.db`, előtte `python -m seed.betolt proba.db`),
vagy állítsd vissza: `python feladat.py seed --ujra`.

Utána a jelentés ugyanúgy megnyitható: `python feladat.py riport
--megnyit`.

## 7. Amit érdemes szemmel tartani

Ez a három a leggyakoribb, és mind a három CSAK élőben derül ki:

1. **A kiút nem nyelheti-e el a tényt.** Ha két keresés is üresen tér
   vissza, a második válaszban ott kell lennie annak is, hogy *hol*
   nincs időpont — nem csak a „próbáljunk mást?" kérdésnek.
2. **A sorszámos hivatkozás a JÓ időpontot választja-e.** A megerősítés
   beszélhető módban visszaolvassa; szöveges módban a kiválasztott gomb
   mondja meg. Ha eltér, az a legdrágább hiba a rendszerben.
3. **Egy szuszra kimondható-e a beszélhető válasz.** Olvasd fel
   hangosan. Ha levegőt kell venni a közepén, hosszú — a szabály két
   mondat, de két hosszú mondat is barge-int szül.

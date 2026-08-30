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

Modell nélkül is elindul — akkor csendben a szabály-alapú értelmező
dolgozik. **Ilyenkor sárga figyelmeztetés áll az ablak tetején**, és
megmondja, mit kell beírni a bekapcsoláshoz; a fej nélküli végigjátszás
ugyanezt kiírja. A figyelmeztetés alatti sor mondja meg, mit jelent itt
a „ma" (a demóadat egy távoli hétre szól, a felület ahhoz horgonyoz).

**A figyelmeztetés a konfiguráció hiányát jelzi, nem azt, hogy fut-e az
Ollama.** Ha be van állítva a modell, de a szolgáltatás nem fut, azt a
napló `szabaly:tartalek` rétegéből látod (l. lent, 5. pont).

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

## 3. Amit érdemes beírni

**Bolt: a Törpilla.** A demóadat csak oda generál beosztást — a Szundi
és az Ügyifogyi keresésre az üres válasz helyes, nem hiba.

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

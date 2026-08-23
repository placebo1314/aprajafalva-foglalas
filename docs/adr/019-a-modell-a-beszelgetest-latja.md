# ADR-019: A modell a beszélgetést látja — az „elengedés" fogalma megszűnik

- **Dátum:** 2026-08-23
- **Állapot:** elfogadott
- **Viszonya az ADR-018-hoz:** **kiegészíti, nem írja felül.** A sorrend
  marad (modell értelmez, determinisztikus réteg kapuz és tartalék); ami
  megváltozik, az a modell BEMENETE és a megőrzött kontextus szerepe.

## Kontextus

Az ADR-018 után az értelmező így működött:

1. A megőrzött paraméterek **adatként** mentek a promptba: *"A
   beszélgetés eddig ezt tudta: bolt_id=szundi."*
2. Ettől a modell megtartásra hajlott — akkor is, amikor a vásárló
   éppen elvetette a boltot (*„és bármelyik másik boltban?"*).
3. Ezért egy **külön, zárt modellhívás** próbálta utólag korrigálni:
   *„a fenti adatok közül melyik esik ki?"* — mezőneveket kért vissza,
   értéket soha (`valtozas_elemzes`), és egy determinisztikus védőháló
   (`kemeny_reszt_vedd`) szűrte a modell túl-elengedését.

Ez működött, de **sebtapasz volt**, és a mérésen is meglátszott: a
kontextus-sor bevezetése az összesített eredményt 12 ponttal javította,
az `elengedes` réteget viszont 66,7%-ról 0%-ra rontotta — a javítás és a
rontás UGYANANNAK az okból következett. A gyökérok nem az volt, hogy a
modell rosszul dönt az elengedésről, hanem hogy **nem látta a
beszélgetést**: adatokat kapott róla, kontextus nélkül.

Egy ember ezt a kérdést sosem tenné fel magának úgy, hogy „melyik
korábbi mező esik ki". Elolvassa a párbeszédet, és megérti, mit kér a
másik.

## Döntés

**A modell a beszélgetést kapja, párbeszédként.**

```
Vásárló: szeretnék petárdát venni kedden
Rendszer: nincs szabad időpont kedden
Vásárló: és bármelyik másik boltban?
```

Az `ErtelmezesKontextus` új mezője `elozmenyek: list[tuple[str, str]]` —
`(ki, mit)` párok az utolsó néhány fordulóból. A modell **egy hívásban**
adja vissza a teljes kérést; ha egy adat a beszélgetés szerint már nem
érvényes, egyszerűen nem tölti ki a mezőt.

**Törölve** (a fogalommal együtt): `LLMErtelmezo.valtozas_elemzes`,
`kaszkad.kemeny_reszt_vedd`, `ForditottKaszkadErtelmezo.
_elenged_e_boltot`, az ADR-016 kaszkád elengedés-ága,
`rule_based.idobeli_jelzes`, és a hozzájuk tartozó tesztek. A
megtart/elenged szókincs sehol nem marad a kódban.

**A megőrzött kontextus szerepe szűkül**: már nem az értelmezés bemenete,
hanem TARTALÉK (`_tartalek`). Akkor tölt ki egy mezőt, ha a modell nem
látta a beszélgetést — determinisztikus út, gombnyomás, első forduló. Ha
LÁTTA és mégis üresen hagyta, az a döntése: **a `None` erősebb, mint a
megőrzött érték.**

**Az előzményeket a felület vezeti** (`ui/vasarlo.py::szo_elozmenyek`),
nem az orchestrator — a ténylegesen kimondott magyar mondatokat csak ő
ismeri (az orchestrator strukturált választ ad, amit az
`assistant/valasz/` fogalmaz mondattá).

**A biztonsági rétegek változatlanok**: enum a zárt halmazokra,
`hun-date-parser` a dátumra (a modell szöveges `datum_kifejezes`-t ad),
bizonyosság-küszöb alatt zárt kérdés, és a foglalásról a mag dönt.

## Amit a mérés mutatott — két lépésben

A számok a 45 eses golden seten, `qwen3.5:9b`, `temperature 0`.

### Első lépés: a beszélgetés bemenet, elengedés-gépezet nélkül

| Réteg | ADR-018 (elengedés-hívással) | ADR-019 első mérés |
|---|---|---|
| összesített | 88,9% | **73,3%** |
| `alkudozas` | 100,0% | 33,3% |
| `elengedes` | 100,0% | 33,3% |

**Rosszabb lett.** De a bukások MÁS FAJTÁJÚAK voltak, és ez a lényeg: a
boltot a modell mostantól MINDEN alkudozó menetben helyesen hozta a
beszélgetésből (ugyifogyi, szundi, torpilla — mind jó). Ami elromlott, az
az IDŐPONT: a modell a korábbi fordulók napját is továbbvitte, és a
determinisztikus ablak-összevonás ebből egy 12 napos, délelőttre
szűkített ablakot csinált a *„kedden délelőtt" → „bármikor a jövő héten"*
menetben.

Ez a **szándék-rétegzés** doktrínájának megsértése
(`orchestrator.kovetkezo_kontextus`): a puha rész (dátum, napszak) minden
fordulóban frissen dől el, az utolsó mondat felülírja a korábbit, nem
kiegészíti. A modell ezt nem tudhatta — sehol nem mondtuk meg neki.

### Második lépés: a kemény/puha aszimmetria kimondva ÉS kikényszerítve

- A rendszerprompt kimondja: a bolt és a szolgáltatás továbbvihető, az
  időpontot viszont mindig csak az UTOLSÓ mondatból veheti.
- A `_mondatbeli_kifejezes` kapu ezt **kikényszeríti**: a modell
  dátum-idézetét csak akkor fogadjuk el, ha annak minden érdemi szava
  előfordul az aktuális mondatban. A magyar toldalékolás itt a kedvünkre
  dolgozik — a rövidebb idézet („péntek") részszövege az inflektáltnak
  („pénteken").

PLACEHOLDER_VEGSO_TABLA

## Miért

- **A gyökérok szűnt meg, nem a tünet.** Az elengedés-gépezet egy
  hiányzó bemenetet pótolt egy külön kérdéssel. A hiányzó bemenetet
  pótolni olcsóbb és érthetőbb.
- **Egy hívás kettő helyett.** Az elengedés-ág minden olyan fordulóban
  külön modellhívást indított, ahol a bolt a kontextusból jött és a
  mondat nem nevezett meg boltot — épp az alkudozó fordulókban, tehát a
  gyakori esetben. Ez megszűnt.
- **Kevesebb fogalom.** A „megtart/elenged", a „kemény rész védőhálója"
  és a hozzájuk tartozó két modul-szintű függvény eltűnt. Ami marad, az
  egy mondat: *a modell a beszélgetést látja*.
- **A determinisztikus garanciák nem gyengültek.** Sőt, egy ÚJ kapu
  került be (`_mondatbeli_kifejezes`), ami egy eddig nem védett elvet
  (puha rész nem szivárog) kényszerít ki.

## Amit feladunk

- **A megőrzött kontextus mint biztonsági háló** — szándékosan. Ha a
  modell látta a beszélgetést és mégsem tölti ki a boltot, az
  visszakérdezéshez vezet, nem a korábbi bolt csendes újrahasználatához.
  Ez egy fordulóval hosszabb beszélgetés a rossz esetben, cserébe soha
  nem foglal olyan boltba, amit a vásárló épp elvetett.
- **Az ADR-016 kaszkád (`--ertelmezo kaszkad`) elvesztette az
  elengedés-ágát**, mert az a törölt hívásra épült. Az `elengedes`
  rétege emiatt 0% — ez a törlés következménye, nem a fordított
  kaszkádé. Az összehasonlító ág ezzel gyengébb lett; ha valaha
  visszatérnénk hozzá, ezt a képességet a beszélgetés-bemenettel kellene
  újraépíteni benne is.
- **A mérés kevesebbet lát, mint az éles út.** A golden futtató csak a
  VÁSÁRLÓI sorokat adja át előzményként: a mérés nem hívja az
  eszközöket, tehát nincsenek valódi rendszer-válaszok, és kitalálni
  őket hamisítás lenne. Az éles úton a rendszer sorai is átmennek — a
  mért érték tehát **alsó becslés**.

## Kiváltó feltétel (a visszafordulásra)

Bármelyik önmagában újranyitja a döntést:

- egy jövőbeli, bővebb halmazon az `alkudozas` vagy az `elengedes` réteg
  tartósan **< 60%**, ÉS egy kontrollmérés kimutatja, hogy a megőrzött
  kontextus tartalékként való visszaengedése ezen érdemben javít;
- a beszélgetés-előzmény miatt megnőtt prompt a válaszidőt a
  determinisztikus-előbb kaszkád **kétszerese fölé** viszi, amikor a
  hangcsatorna SLO-ja élesedik (ma az előzmény ~4 sor, a hatás mérhető,
  de kicsi);
- a modell egy KORÁBBI fordulóból vett értéket ad meg úgy, hogy azt a
  determinisztikus kapuk nem fogják meg, és ebből rossz foglalás
  születik. (A dátumra ez ma nem lehetséges — `_mondatbeli_kifejezes` —,
  a boltra igen: ott a zárt halmaz véd, de az „melyik boltból" kérdésre
  nem.)

## Ellenőrzés

```
python feladat.py golden --ertelmezo szabaly
python feladat.py golden --ertelmezo forditott --modell qwen3.5:9b
python feladat.py golden --ertelmezo kaszkad   --modell qwen3.5:9b
python feladat.py vegigjatszas
```

Az `alkudozas` és az `elengedes` réteg a mérőszám: ezek mérik, hogy a
modell érti-e a beszélgetést. A `vegigjatszas` a felületi oldalt méri,
amit a golden set szerkezetileg nem tud (l. ADR-018, 4. szakasz).

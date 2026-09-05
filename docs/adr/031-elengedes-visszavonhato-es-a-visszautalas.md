# ADR-031: Az elengedés visszavonható, és a visszautalás áthozza a kemény részt

- **Dátum:** 2026-09-12
- **Állapot:** elfogadott
- **Viszonya az ADR-019-hez:** **szűk kivételt nyit rajta.** A szabály
  marad („a modell `None`-ja erősebb, mint a megőrzött érték"); a
  kivétel egyetlen, nyelvtanilag zárt esetre szól: a NÉVMÁSI
  VISSZAUTALÁSRA.
- **Viszonya az ADR-024-hez:** kiegészíti — a MINDEGY szentinel három
  állapota (nem tudjuk / elengedve / tudjuk) mostantól ODA-VISSZA
  járható.

## Kontextus

Két bukás maradt nyitva a 2026-09-05-i körből, mindkettő MÉRT, és
mindkettő mind a négy megmért modellen egyformán:

**1. A MINDEGY ragadós volt.** Aki elengedett egy mezőt („Bármelyik
petárda jó"), nem tudta visszavonni („mégis inkább a nagyot kérem") — a
rendszer maradt a `MINDEGY`-nél. Ez rosszabb, mint ha meg sem kérdeztük
volna: a vásárló kimondott döntését hagytuk figyelmen kívül.

**2. A szolgáltatás nem élte túl a fordulót.** Az „és csütörtökön
ugyanez?" mondatnál a bolt átjött, a MÉRET nem — a keresés csendben
kitágult minden petárdára.

A promptos javítás **megbukott a mérésen** (2026-09-05, két futás): a
célzott eset továbbra is bukott, az összesített szám nem javult.

## Döntés

**Két determinisztikus kapu, a modell kimenete UTÁN**
(`assistant/interpreter/forditott_kaszkad.py`) — ugyanabban a családban,
mint a `_mondatbeli_kifejezes` és a `_mondatbeli_napszak`.

**1. `_mindegy_visszavonva`** — ha a modell `MINDEGY`-et ad egy mezőre,
DE az aktuális mondat determinisztikusan kimond egy konkrét értéket, a
konkrét érték nyer. A boltra és a szolgáltatásra egyaránt.

**2. `_visszautalasos_tartalek`** — ha a mondat NÉVMÁSSAL utal vissza az
előző fordulóra („ugyanez", „ugyanaz", „ugyanoda", „ugyanolyan"), a
megőrzött kemény rész kitölti azt, amit a modell üresen hagyott.

Mellé egy **morfológiai bővítés** a szabály-alapú rétegben: a
méret-melléknév toldalékolt alakjai (`nagyot`, `nagyra`, `kicsit`) —
zárt toldalékkészlettel, és HÁROM hamis baráttal szándékosan kizárva:
`nagyon` (fokhatározó), `nagyobb` (középfok) és a fokhatározói `kicsit`
(„kicsit később mennék" — az idő, nem méret). A harmadikat a saját
tesztünk fogta meg, miután az első változat még beszippantotta.

## Miért kapu, és miért nem prompt

- **Prompttal megpróbáltuk, és mérve nem javított.** A modell a
  beszélgetésben látott „mindegy"-et viszi tovább; a mondatban
  kimondott konkrét érték viszont determinisztikusan kinyerhető, tehát
  nincs mit találgatni.
- **A visszautalás nyelvtanilag ZÁRT osztály.** A névmási visszautalás
  nem bővülő szókincs, hanem véges lista — épp ezért lehet
  determinisztikusan felismerni anélkül, hogy kulcsszó-toldozás lenne.
- **A kivétel iránya biztonságos.** Az ADR-019 azért adta a `None`-nak
  az elsőbbséget, hogy a rendszer soha ne foglaljon olyan boltba, amit a
  vásárló épp elvetett. A visszautalás ennek az ELLENKEZŐJE: a vásárló
  kimondottan a korábbi tartalomra mutat. Nem elhagyta az adatot,
  hanem hivatkozott rá.

## Amit feladunk

- **Az ADR-019 egyszerűségét.** Eddig egy mondatban el lehetett mondani
  („a `None` erősebb"); mostantól van egy kivétel, és a kivételt is
  tudni kell. Cserébe a névmási visszautalás nem vész el.
- **A morfológiai lista karbantartását.** A toldalékkészlet zárt, de
  nyelv szerint bővíthető — és minden bővítésnél újra el kell dönteni,
  nem szippant-e be hamis barátot.
- **Azt, hogy a szolgáltatás MINDEN esetben átjöjjön.** Visszautalás
  nélkül továbbra sem jön át: „és csütörtökön?" (névmás nélkül) tágabb
  keresést ad. Ez tudatos: ott tényleg nem tudjuk, hogy a méret még
  érdekli-e.

## Ellenpróbák (mind golden esetben rögzítve)

| eset | mit őriz |
|---|---|
| `elengedes-09` | a mondat NEM mond konkrétat → a MINDEGY marad MINDEGY |
| `elengedes-14` | új boltot NEVEZ meg → csere, nem elengedés |
| `elengedes-15` | a „mindegy" a NAPRA vonatkozik → a bolt marad |
| `elengedes-05` | visszautalás NÉLKÜL a megőrzött érték nem jön át |
| `mindegy-05`, `mindegy-06` | a „mindegyik" lista-kérés, nem elengedés |

## Kiváltó feltétel

- a `_mindegy_visszavonva` olyan fordulóban szólal meg, ahol a vásárló
  NEM vonta vissza az elengedést (a mondatban szereplő méret-szó egy
  másik tárgyra vonatkozott) — ekkor a morfológiai lista túl tág;
- a visszautalás-minta olyan mondatra illeszkedik, ahol a névmás NEM az
  előző fordulóra mutat („ugyanakkor viszont…" — ellentétes kötőszóként);
- a mérés szerint a két kapu együtt nem javít a `elengedes` rétegen
  legalább a zajküszöbnyit (`SZORAS_KUSZOB_SZAZALEKPONT`) két egymást
  követő mérésen.

## Ellenőrzés

```
python -m pytest tests/egyseg/test_forditott_kaszkad.py -k "mindegy or visszautalas"
python feladat.py golden --ertelmezo forditott --ismetles 2
```

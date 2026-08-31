# ADR-025: Csúszó előzmény-ablak — az utolsó négy forduló szó szerint, a többi egy sorban

- **Dátum:** 2026-08-31
- **Állapot:** elfogadott
- **Viszonya az ADR-019-hez:** **kiegészíti.** A modell továbbra is a
  BESZÉLGETÉST látja, nem a megőrzött paramétereket adatként. Ami
  változik: mennyi beszélgetést lát, és mi lép a levágott rész helyébe.

## Kontextus

Az ADR-019 óta az értelmező bemenete a beszélgetés, párbeszédként. Ez
helyes, de a beszélgetés nő, a prompt hossza pedig latencia
(`docs/PLATFORM_TANULSAGOK.md`, 2. szakasz). A felület eddig egyszerűen
VÁGOTT: az utolsó 12 naplósor ment át (`ui/vasarlo.py::_ELOZMENY_SOROK`).

A vágásnak két baja van, és a második a súlyosabb:

1. **A prompt így is nő** a hasznos tartalomhoz képest: húsz forduló
   után a beszélgetés-rész hosszabb, mint amennyi az aktuális mondat
   megértéséhez kell.
2. **A levágott rész NYOMTALANUL eltűnik.** A legelső mondatban
   kimondott bolttal együtt — pont azzal a KEMÉNY adattal, aminek az
   ADR-019 szerint végig érvényben kellene maradnia. Húsz forduló után
   a rendszer újra megkérdezi, melyik boltról van szó.

## Döntés

**Két rétegű előzmény**: az utolsó **négy forduló szó szerint**, a
régebbiek helyett **egyetlen, determinisztikusan előállított
összefoglaló sor** (`assistant/interpreter/ablak.py`).

```
Összefoglaló (16 korábbi forduló): bolt=ugyifogyi;
szolgaltatas_id=ELENGEDVE (a vásárló azt mondta: mindegy);
eddig keresett napok: 2026-08-19, 2026-08-20; üresen tért vissza 2 keresés
Vásárló: Na jó.
Rendszer: Melyiket foglaljam?
Vásárló: akkor a másodikat kérem
```

- **Négy forduló szó szerint**, mert a sorszámos („a másodikat") és a
  visszavonó („mégsem, inkább a keddet") hivatkozások az elhangzott
  mondatokra és a felajánlott listákra mutatnak. Ezeket összefoglalni
  annyi, mint eldobni.
- **Az összefoglaló determinisztikus**: a levágott vásárlói mondatokat
  ugyanaz a szabály-alapú értelmező olvassa el, ami a kaszkád tartalék
  rétege. Nincs második modellhívás — egy összefoglalóért fizetni egy
  hívást pont azt a latenciát adná vissza, amit az ablak megspórol.
- **A MINDEGY külön jelöléssel** megy át (`ELENGEDVE`), nem értékként:
  a három állapot (nem tudjuk / elengedve / tudjuk, ADR-024) a levágott
  részen sem eshet kettőre.
- **A felület TÖBBET ad át, mint eddig** (12 → 60 sor): a vágás átkerült
  az értelmezőbe, tehát a puffernek az összefoglaló nyersanyagát kell
  tartania, nem az ablakot.
- Az ablakméret környezetből állítható (`APRAJAFALVA_ABLAK_FORDULO`,
  `0` = nincs ablak) — **a mérés kedvéért**, nem üzemmódként.

## Miért

- **Az összefoglaló nem ugyanaz, mint az ADR-019 előtti kontextus-adat.**
  Akkor a megőrzött paraméterek a TELJES beszélgetésre vonatkoztak, és
  versenyeztek azzal, amit a vásárló épp mondott — ettől lett a modell
  ragadós. Itt az összefoglaló csak azokról a fordulókról szól, amik már
  NEM férnek a szó szerinti ablakba; ami friss, az szó szerint ott van,
  és felülírja.
- **Az időpont-szivárgás szerkezetileg kizárt.** Az összefoglaló
  napokat sorol, de azok MÁR LEFUTOTT keresések — és ha a modell mégis
  onnan idézne dátumot, a kapu eldobja
  (`forditott_kaszkad._mondatbeli_kifejezes`: az idézet minden érdemi
  szavának az AKTUÁLIS mondatban kell szerepelnie). Nem prompt-fegyelem
  kérdése.
- **A rövidülés a beszélgetés-részen érdemi, és pont ott van, ahol nő.**

## A mérés

### 1. Mennyivel rövidül a prompt (`python -m tools.ablak_meres`)

Húsz fordulós fixture, a huszonegyedik mondat egy sorszámos hivatkozás.
Karakterben, `v1` rendszerprompttal:

| ablak | beszélgetés-rész | ebből − | teljes prompt | ebből − |
|---|---|---|---|---|
| nincs (alapvonal) | 1872 | 0,0% | 6649 | 0,0% |
| 8 forduló | 850 | 54,6% | 6047 | 9,1% |
| **4 forduló (éles)** | **477** | **74,5%** | **5674** | **14,7%** |
| 2 forduló | 366 | 80,4% | 5563 | 16,3% |
| 1 forduló | 261 | 86,1% | 5458 | 17,9% |

**Két számot írunk ki, mert két külön kérdésre felelnek.** A
beszélgetés-részre hat az ablak (−74,5%); a teljes promptban a
rendszerprompt állandó tag, ami hígítja az arányt (−14,7%). Csak az
egyiket kiírni mindkét irányban félrevezetne. (A `v2` rendszerprompttal
— ADR-026 — a teljes prompt rövidülése ugyanezen a fixture-ön 22,4%,
mert az állandó tag maga is kisebb lett.)

### 2. Romlik-e a pontosság (`python feladat.py golden`)

51 eset, `qwen3.5:9b`, `forditott` értelmező, `v1` prompt:

| ablak | összesített | leggyengébb réteg | p50 |
|---|---|---|---|
| nincs (alapvonal) | 90,2% | `elengedes` 33,3% | 3,67 s |
| **4 (éles)** | **90,2%** | `elengedes` 33,3% | 3,68 s |
| 1 (agresszív) | 90,2% | `elengedes` 33,3% | 3,64 s |

**Rétegenként is azonos, mind a tizenegy rétegen** — a bukott esetek is
ugyanazok.

**Az ablak=4 sor önmagában nem bizonyít semmit**, mert az ablak be sem
kapcsol: a nyelvi halmaz leghosszabb esete három fordulós. Az `ablak=1`
sor viszont igen — ott a tömörítés a kétfordulós eseteken IS bekapcsol
(ellenőrizve), és a pontosság nem mozdul; még a
`mintan_tul-06-visszavonas` sem, ami épp az összefoglalóba került első
fordulóra hivatkozik vissza („mégsem, inkább maradjunk a keddnél").

Amit egyik sem mér: a húsz fordulós beszélgetést. Olyan golden esetünk
nincs, és kitalálni hamisítás lenne — a húsz fordulós fixture-ön csak
promptot mérünk, pontosságot nem. **A négyes ablak tehát nem azért
marad, mert jobbnak mértük az egyesnél, hanem mert a mai halmazon a
kettő között nincs kimutatható különbség, és a szélesebb ablak viszi
szó szerint a kockázatosabb hivatkozásokat is (sorszám, visszavonás).**

A részletes számok és a bukott esetek: `docs/ABLAK_MERES.md`.

## Amit feladunk

- **A régebbi fordulók szó szerinti szövegét.** Egy negyedik forduló
  előtti, finom megfogalmazásbeli utalás („ahogy az előbb mondtam, a
  feleségem miatt") elveszik: az összefoglaló mezőket őriz, nem
  árnyalatot.
- **Az összefoglaló pontossága a determinisztikus rétegé.** Amit a
  szabály-alapú olvasat nem lát (irónia, körülírt bolt, ritka
  szóhasználat), az nem kerül bele. Ez tudatos csere: egy modellhívás
  pontosabb összefoglalót adna, de akkor az ablak nem spórolna időt,
  csak áthelyezné.
- **Egy új kapcsolót** (`APRAJAFALVA_ABLAK_FORDULO`), amit karban kell
  tartani. Cserébe az ablakméret mérhető, nem hiedelem.

## Kiváltó feltétel

Bármelyik önmagában újranyitja a döntést:

- egy hosszú beszélgetéseket is tartalmazó halmazon az `ablak=4` mérés
  **több mint 3 százalékponttal** rosszabb, mint az `ablak=0` alapvonal;
- a naplóban megjelenik olyan forduló, ahol a rendszer olyan mezőre
  kérdez rá, ami az összefoglalóban ott állt (tehát az összefoglalót a
  modell nem használja);
- a hangcsatorna SLO-ja élesedik, és a mérés szerint a
  beszélgetés-rész rövidítése már nem elég: ekkor a rendszerprompt
  tömörítése a következő lépés (ADR-026), nem az ablak szűkítése.

## Váltás mire

**Kisebb ablak (2 forduló) + gazdagabb összefoglaló** — az összefoglaló
kapjon mezőt a felajánlott, de elutasított időpontokra is. Ez akkor
indokolt, ha a hosszú beszélgetések latenciája lesz a szűk keresztmetszet.

## Váltás költsége

Alacsony: egy szám (`ALAP_FORDULO`) és az `Osszefoglalo` mezői. A
kockázat nem a kódban van, hanem abban, hogy a szűkebb ablak a
sorszámos hivatkozásokat elvágja — ezt a `mindegy`/`alkudozas` rétegek
és a `vegigjatszas` foglalási menete mutatná meg.

## Ellenőrzés

```
python -m tools.ablak_meres --modell qwen3.5:9b     # hossz és tokenszám
APRAJAFALVA_ABLAK_FORDULO=0 python feladat.py golden --ertelmezo forditott
APRAJAFALVA_ABLAK_FORDULO=4 python feladat.py golden --ertelmezo forditott
python -m pytest tests/egyseg/test_ablak.py
```

Az `ablak.py` egységtesztjei három állítást őriznek: az ablak rövidít,
az ablak NEM felejt (a levágott bolt és az elengedett mező túléli), és
az összefoglaló nem szivárogtat időpontot.

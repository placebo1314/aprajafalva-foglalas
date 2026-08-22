# ADR-017: Nincs sürgősség- vagy kapkodás-becslés a szóhasználatból

- **Dátum:** 2026-08-22
- **Állapot:** elfogadott

## Kontextus

A szándékfelismerés bővítésekor (bizonyosság, szándék-rétegzés)
kézenfekvőnek tűnik egy további jelzést is kinyerni a mondatból: mennyire
**sürgős** vagy **kapkodó** a vásárló ("gyorsan", "sürgősen", "mindegy,
csak minél előbb", rövid, tagolatlan mondatok). Ebből elvileg lehetne
rangsorolni, terelni, vagy a felajánlott időpontokat súlyozni.

Két dolog szól ellene. Egyrészt **szövegből ez nem mérhető
megbízhatóan**: a rövid, elharapott fogalmazás nálunk kifejezetten
gyakori és NEM sürgősséget jelez — a blueprint 1. szakasza szerint a
töredékes beszéd, a tájszólás és a kognitívan egyszerűsített
megfogalmazás a mindennapi bemenet. Aki így ír, azt egy
sürgősség-osztályozó rendszeresen félreértené, méghozzá pont a
legkiszolgáltatottabb rétegen (idős törpök, akadálymentesség).

Másrészt **ha mérnénk, a rá épülő terelés sötét mintázat lenne**. A
blueprint 7. szakasza a szűkösségjelzésnél már kimondja: csak akkor
jelzünk szűkösséget, ha IGAZ, konkrét küszöbszámból, homályosan, nem
sürgetve — "ha ez lazul, sötét mintázattá válik". Egy kapkodásra
hangolt válasz pontosan ezt a korlátot kerülné meg: nem a naptár
állapotára reagálna, hanem a vásárló idegállapotára, és épp akkor
sürgetne, amikor a vásárló amúgy is nyomás alatt van.

## Döntés

A rendszer nem becsül sürgősséget vagy kapkodást a szóhasználatból, és
nem épít rá viselkedést. A sürgősség abból derül ki, **mikorra kér
időpontot** — ez tényadat, a dátumparserből jön.

## Miért

- **Nem mérhető megbízhatóan szövegből**, és a hibája rendszeres, nem
  véletlen: a nyelvi rétegek (töredékes, egyszerűsített) épp azok, amiket
  félreértene.
- **A rá épülő terelés sötét mintázat lenne** (blueprint 7. szakasz) —
  az idegállapotra reagáló sürgetés akkor is manipuláció, ha jó
  szándékú.
- **Van helyette valódi, tényalapú jelzés**: a kért dátumablak. Aki
  holnapra kér időpontot, sürgősebb helyzetben van, mint aki jövő
  hónapra — ezt nem kell kitalálni a szavakból, benne van a kérésben.

## Amit feladunk

Egy potenciálisan hasznos jelzést a pultos nézetéhez ("ez a vásárló
sietett"), és a felajánlott jelöltek finomabb, hangulat-alapú
rangsorolását. Ezt tudatosan feladjuk: a blueprint 8. szakasza a
foglaláshoz fűzött megjegyzésnél amúgy is kimondja, hogy a gépi kivonat
**sosem befolyásolhatja az ütemezést**, tehát ez a jelzés ott sem
lehetne több, mint dísz.

## Kiváltó feltétel

Mindkettő együtt:

- a **hangcsatornán a beszédtempó mérhetővé válik** (szó/perc, szünetek
  hossza) — ez a szövegtől független, fizikai jel, nem a szóhasználat
  értelmezése, ÉS
- van rá konkrét használati eset, ami **nem terelés**: pl. a
  turn-detection türelmi idejének igazítása (`docs/PLATFORM_TANULSAGOK.md`,
  M6: "a turn-detection türelmi ideje idős beszédre hangolva"), vagy a
  válasz hosszának rövidítése — tehát a rendszer a SAJÁT viselkedését
  igazítja, nem a vásárló döntését befolyásolja.

## Váltás mire

Beszédtempó-alapú jelzés a hangcsatornán, kizárólag a rendszer saját
válaszviselkedésének hangolására (turn-detection türelmi idő,
válaszhossz) — **nem** a felajánlott időpontok rangsorolására és nem a
pultos nézetébe.

## Váltás költsége

Alacsony technikailag: a jelzés a hangkeretrendszerből (LiveKit/Pipecat)
jönne, nem a mi értelmezőnkből, és a `bizonyossag`-hoz hasonlóan egy
opcionális mezőként utazna. A tényleges munka a hangcsatorna maga (M6),
nem ez a jelzés.

## Ellenőrzés

Ha valaha bekerül: a golden set nyelvi rétegein külön mérni kell, hogy a
jelzés NEM korrelál a réteggel (töredékes/egyszerűsített ≠ sürgős). Ha
korrelál, a jelzés a nyelvi stílust méri, nem a sürgősséget — és akkor
ki kell venni. Enélkül a kiváltó feltétel díszlet.

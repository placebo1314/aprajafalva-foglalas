# ADR-009: Blokkstratégia — v1 fix, áthelyezés kiváltó feltétellel

- **Dátum:** 2026-08-15
- **Állapot:** elfogadott

## Kontextus

A szünet ütközhet egy foglalási kéréssel. A rendszer megpróbálhatná
arrébb tolni a szünetet (mozgatható stratégia), vagy egyszerűen elutasíthatja
a foglalást, ha az ütközés fennáll (fix stratégia). A `BlokkStrategia`
interfész mindkettőt lehetővé teszi.

## Döntés

v1-ben kizárólag a `FixBlokk` stratégia fut (generál, nem mozgat, ütközésnél
elutasít); a `MohoAthelyezo` stratégia interfész szinten tervezett, de nem
aktív alapértelmezésben.

## Miért

- Az áthelyezés sorrendfüggővé teszi a rendszert: ugyanaz a három foglalás
  más sorrendben más beosztást ad — ezt nehéz tesztelni és nehéz
  elmagyarázni a dolgozónak.
- A `FixBlokk` viselkedése egyszerűen naplózható és megmagyarázható: az
  elutasítás oka mindig „a szünet nem mozdítható".
- A stratégia-interfész (`Protocol`) már úgy készül, hogy a váltás ne
  igényeljen sémamódosítást, csak a kapcsoló átállítását.

## Amit feladunk

Magasabb kihasználtságot azokban az esetekben, amikor egy mozgatható szünet
megoldaná az ütközést — v1-ben ezek elutasításra kerülnek, nem kompromisszumos
ajánlatra.

## Kiváltó feltétel

- a dev mód elutasítás-mutatójában a szünetütközés miatti elutasítások
  aránya meghalad egy küszöböt (irányszám: az összes elutasítás >15%-a
  `szunet_utkozes` okú)
- konkrét bolt vagy dolgozó jelzi, hogy a fix szünet rendszeresen
  kihasználatlan időt hagy a naptárban

## Váltás mire

A `MohoAthelyezo` stratégia bekapcsolása `blokk_szabaly.strategia` mezőn,
boltonként vagy dolgozónként választhatóan.

## Váltás költsége

Alacsony a bekapcsoláskor (a kód már létezik), de előfeltétel, hogy minden
mozgást naplózzon a rendszer (audit-igény) — ez volt a v1-ből kihagyás fő
oka, ezt kell előbb bizonyítottan megoldani.

## Ellenőrzés

A dev mód napi összesítője méri az elutasítási okokat típusonként; a
`szunetblokk` mozgatási napló megléte és teljessége a `konkurencia-teszto`
tesztkészletében ellenőrzött.

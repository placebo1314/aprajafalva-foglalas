# ADR-005: Redaktálás tárolás előtt

- **Dátum:** 2026-08-15
- **Állapot:** elfogadott

## Kontextus

Aprajafalván minden lakosnak egyedi, névvel egyértelműen azonosító számsora
van — nemzeti azonosító jellegű adat. A trace-eket dev módban annotátorok
nézik, akik szerepkörüknél fogva nem láthatnak azonosítható adatot.

## Döntés

A trace-ek redaktálása (`<NEV>`, `<AZONOSITO>`, `<TELEFON>`) tárolás ELŐTT
történik; nyers vásárlóazonosító soha nem kerül lemezre, logba vagy
trace-be, csak HMAC-SHA256 hash, pepper külön kulcstárolóban.

## Miért

- Utólagos redaktálás nem garantálható: mire a redaktáló lefutna, a nyers
  adat már bekerülhetett logaggregátorba, mentésbe, cache-be.
- Az annotátor szerepkör kifejezetten nem láthat azonosítható adatot — ha a
  redaktálás utólagos, ez a határ minden hibás futtatásnál sérül.

## Amit feladunk

A teljes nyers trace megőrzésének kényelmét hibakereséshez — egy rosszul
redaktált mintát nem lehet visszamenőleg helyrehozni, mert nincs nyers
forrás, csak új szabállyal újrafuttatható eset.

## Kiváltó feltétel

- a redaktálási lefedettség szintetikus PII-mintákon (golden seten mérve)
  99% alá esik, VAGY a negyedéves mintavételes audit során akár egyetlen
  azonosítható adat átcsúszik a tárolt trace-be
- írásos jogi/megfelelőségi igény merül fel nyers audit trailre (ma nincs
  ilyen igény)

## Váltás mire

Nincs jó váltás az elvre — ha a kiváltó feltétel teljesül, elsőként a
redaktáló szótárt/szabálykészletet kell bővíteni. Csak végső esetben egy
elkülönített, szigorúan korlátozott hozzáférésű nyers-trace tároló, saját
megőrzési idővel és külön adatvédelmi felülvizsgálattal.

## Váltás költsége

A szabálykészlet bővítése alacsony (szótár/regex frissítés); egy különálló
nyers tár bevezetése magas (új adatvédelmi felülvizsgálat szükséges).

## Ellenőrzés

Az `adatvedelem` skill tesztkészlete méri a redaktálási lefedettséget
szintetikus PII-mintákon; az annotátor felület mintavételezett audittal
ellenőrzi, hogy nem szivárgott át azonosítható adat.

# ADR-001: Műszak-központú modell

- **Dátum:** 2026-08-15
- **Állapot:** elfogadott

## Kontextus

A beosztást és a slotgenerálást valamilyen entitáshoz kell kötni. A kézenfekvő
megoldás egy „ki hol dolgozik" mátrix (pult × nap × dolgozó) lenne, de a
boltok napi ritmusa eltérő: ugyanaz a pult más nap más szolgáltatással, más
időtartammal és más szünetszabállyal működhet.

## Döntés

A `műszak` a rendszer központi entitása (pult + alkalmazott + szolgáltatás +
időablak + időtartam + szünetszabály), és a `slot` a műszakhoz tartozik, nem a
pulthoz és nem a dolgozóhoz.

## Miért

- „Ma Törpilla, holnap GipszJakab ugyanazon a pulton" enélkül két külön
  rekordot igényelne szétszórva; a műszak ezt egy entitásba zárja.
- A paraméter-befagyasztás (snapshot) egy konkrét entitást igényel, amire az
  öröklődési lánc (szolgáltatás → bolt → pult → alkalmazott) ráfagyasztható.
- A műszak visszavonása (Törpilla lebetegszik) egy jól körülhatárolt,
  egyetlen művelettel kezelhető egységet igényel.

## Amit feladunk

Az egyszerűbb „ki hol dolgozik" mátrix könnyebb admin-felületét és kevesebb
táblát — cserébe minden nap explicit műszakot igényel, ami kezdetben több
adminmunkát jelent, amíg a sablon-műszakok (M1) nincsenek kész.

## Kiváltó feltétel

- a seed és valós beosztási adatokban bebizonyosodik, hogy egy adott pulton
  belül a szolgáltatás és a dolgozó napon belül soha nem változik (mérve:
  legalább 3 hónapnyi beosztásban 0 ilyen eset)
- az M1 kilépési feltétele („egy hónapnyi beosztás percekben mérhető") a
  műszak-granularitás miatt két egymást követő hónapban nem teljesül

## Váltás mire

Egyszerűsített „pult-nap" modell, ahol a slot közvetlenül pulthoz és naphoz
kötődik, műszak-köztes réteg nélkül.

## Váltás költsége

Séma-migráció, a slotgenerátor és a snapshot-logika átírása — becslés napokban,
mert a legtöbb magasabb szintű modul (hold, foglalás) a slotra épül, nem
közvetlenül a műszakra.

## Ellenőrzés

Az admin beosztásszerkesztő használati adatai (M1 után) és a seed adatból
számolt napon belüli váltási arány.

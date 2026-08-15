# ADR-006: Ajánlatpontozó — képlet, korlát, küszöbök

- **Dátum:** 2026-08-15
- **Állapot:** elfogadott

## Kontextus

A keresés nem adhatja vissza egyszerűen az első szabad slotokat, mert két
egyidejű session könnyen ugyanazt az időpontot kapná (ajánlatszórás), és a
kért ablaktól távoli, csak véletlenül üres időpont ajánlása megzavarja a
vásárlót.

## Döntés

A keresés ritkaság-alapú képlettel pontoz —
`pontszám = w1*(1 - tényleges_lefedettség) + w2*(1 - várható_lefedettség)` —,
szigorúan a kért ablakon belül; az illeszkedés kemény korlát, nem súly. A
szabad sáv és a blokkolt idő kemény kizárás: a pontozó ezeket soha nem
ajánlhatja, és soha nem eheti meg optimalizálással (lásd ADR-011).

## Miért

- Megoldja az ajánlatszórást explicit forgatási logika nélkül: a második
  egyidejű session már látja az első session holdját, tehát más pontszámot
  kap ugyanarra a slotra.
- Az illeszkedés korlátként kezelése kizárja azt a hibát, hogy „péntek
  délelőtt" kérésre csütörtök délutánt ajánlunk csak azért, mert ott üres a
  naptár.
- v1-ben nincs történeti adat; a szándékindex és a kézzel jelölt „népszerű
  sáv" mező elég kiindulásnak a várható lefedettség becsléséhez.

## Amit feladunk

A globálisan legjobb kihasználtságú ajánlás lehetőségét — előfordulhat, hogy
egy ablakon kívüli, valójában jobban illeszkedő időpontot nem ajánlunk fel,
mert szigorúan a kért ablakon belül maradunk.

## Kiváltó feltétel

- a golden set szituációs eseteiben mért ajánlás-helyesség egy küszöb
  (kezdeti cél: 80%) alá esik
- történeti adat elérhetővé válik (M6 finomhangolási hurok után), ami
  pontosabb `várható_lefedettség` becslést tenne lehetővé
- a kézzel karbantartott „népszerű sáv" mező 8 hétnél régebben nincs
  frissítve az admin felületen

## Váltás mire

Történeti adatból tanult lefedettség-modell (napszaki/heti mintázat
becslés), a kézi „népszerű sáv" mező fokozatos kivezetésével.

## Váltás költsége

Alacsony — a pontozó interfész (`w1`, `w2`, `varhato_lefedettseg()`) már
cserélhető implementációra készül, csak a becslő függvény cserélődik.

## Ellenőrzés

A `golden-set` skill szituációs esetei mérik az ajánlás helyességét; a dev
mód kiút-arány mutatója jelzi, ha a pontozás rendszeresen rossz ajánlatot ad.

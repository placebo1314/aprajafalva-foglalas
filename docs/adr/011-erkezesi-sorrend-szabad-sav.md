# ADR-011: Érkezési sorrend + szabad sáv

- **Dátum:** 2026-08-15
- **Állapot:** elfogadott

## Kontextus

Szűkösségben (havonta egy-két órás nyitás) el kell dönteni, ki kapja meg az
időpontot. Emellett van vásárló, aki nem tud vagy nem akar előre foglalni,
és helyben, sorban várva szeretne sorra kerülni.

## Döntés

A foglalás elbírálása szigorúan érkezési sorrendben történik (nincs
prioritási sor, nincs kiemelt út), és minden műszakban marad ki nem osztott
szabad sáv (`muszak.foglalhato_arany`) a be nem foglaló, helyben érkező
vásárlóknak.

## Miért

- Egyszerű és megmagyarázható: amíg bőven van hely, mindegy, de
  szűkösségben ez az egyetlen szabály, ami nem válik panasszá — az „aki
  legközelebb keres, megtalálja" elv kimondva elfogadott, kimondatlanul
  panasz forrása.
- A szabad sáv kemény kényszer, nem a pontozó eheti meg — így a helyben
  érkező vásárló mindig kap utat, ami a „kiút" egyik formája, nem kudarc.
- Elnyeli a csúszást és puffert ad a hibás foglalásnak, tehát a naptár
  realisztikus marad.

## Amit feladunk

Azt a lehetőséget, hogy méltányossági vagy üzleti szempontból (törzsvásárló,
sürgős eset) valaki előre kerülhessen a sorban — ma erre nincs mechanizmus,
mindenki egyenlő eséllyel indul a keresés pillanatában.

## Kiváltó feltétel

- konkrét, dokumentált üzleti igény merül fel prioritási sorra (pl. egy bolt
  kéri törzsvásárlói előny bevezetését)
- a szabad sáv kihasználatlansága (a be nem foglalt, helyben kiszolgált idő
  aránya a szabad sávon belül) három egymást követő hónapban 30% alatt
  marad, ami tartós kapacitáspazarlásra utal

## Váltás mire

Prioritási réteg bevezetése a pontozóba (külön súlyként, nem a korlát
felülírásával), vagy dinamikusan számított `foglalhato_arany` bolt/nap
szerint.

## Váltás költsége

Közepes — a pontozó és a slotgenerátor mindkettőt érinti, a golden set
szituációs eseteit is bővíteni kell.

## Ellenőrzés

A dev mód méri a kiút arányát és a no-show/kihasználtsági mutatókat
(blueprint 9. szakasz); a szűkösséggel kapcsolatos elégedetlenség jelzésére
a beszélgetés végi opcionális értékelés szolgál (rossz értékelést kapott
beszélgetések aránya) — a dolgozói nézet foglaláshoz fűzött megjegyzése
kizárólag a dolgozó tájékoztatására való, nem panaszmérésre.

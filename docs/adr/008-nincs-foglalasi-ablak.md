# ADR-008: Nincs foglalási ablak; felszabaduló slot azonnal elérhető

- **Dátum:** 2026-08-15
- **Állapot:** elfogadott

## Kontextus

A foglalás jellemzően időszakosan nyílik meg (pl. havonta egy-két óra a
következő hónapra). Kérdés, hogy ezt egy külön „foglalási ablak" entitás
vezérelje-e, vagy elég-e, hogy a slot léte maga a szabály.

## Döntés

Nincs külön „foglalási ablak" entitás; ha van generált és szabad slot,
foglalható — akkor is, ha a korábbi foglalási időszak már lezárult (pl.
lemondás miatt felszabaduló slot azonnal újra foglalható).

## Miért

- Egyszerűbb modell: egy táblát (slot) kell karbantartani, nem két
  állapotgépet (ablak + slot) szinkronban.
- Konzisztens vásárlói élmény: amit a keresés mutat, az foglalható — nincs
  rejtett „az ablak már zárva, bár látszik szabad idő" eset.
- A lemondás → azonnali felszabadulás szabály enélkül minden ablak-lezárás
  után külön kivételkezelést igényelne.

## Amit feladunk

Azt a lehetőséget, hogy a bolt explicit jelezze: „a foglalási időszak
lezárult, még ha marad is szabad hely" (pl. adminisztratív okból korlátozná
az utólagos foglalást) — erre ma nincs mechanizmus.

## Kiváltó feltétel

- konkrét, dokumentált admin-igény merül fel arra, hogy egy lezárt
  időszakban felszabaduló slotot ne ajánljunk fel
- negyedévente több mint 3 panasz vagy hibajegy származik abból, hogy
  lemondott slot újra elérhetővé vált

## Váltás mire

Explicit `foglalasi_ablak` tábla bolt/szervezet szinten, amely felülbírálja
a slot elérhetőségét.

## Váltás költsége

Alacsony-közepes — egy új tábla és egy szűrési feltétel a keresésben; a
slotgenerátort nem érinti.

## Ellenőrzés

Admin visszajelzés naplózása: hány alkalommal kérnek „zárjuk le, de ne
engedjünk több foglalást" jellegű műveletet. Ennek hiánya a döntés
helyességét igazolja.

# ADR-010: Nincs roham-üzemmód; a kiszolgálási szint csökkenhet, a képesség nem

- **Dátum:** 2026-08-15
- **Állapot:** elfogadott

## Kontextus

A foglalás előfordulhat, hogy havonta egy-két órára nyílik meg a következő
egész hónapra — ez a rendszer normál üzemmódja, nem peremeset. Kérdés, hogy
ilyenkor a vásárló egy leegyszerűsített, gyorsabb felületet kapjon-e, vagy
ugyanazt a teljes nyelvi élményt.

## Döntés

Nincs külön „roham-üzemmód" felület vagy útvonal; szűkösségben kizárólag
belső, a vásárló számára láthatatlan paraméterek csökkennek (önkonzisztencia
futásszám, sablonarány, hold TTL) — az LLM-es beszélgetés lehetősége, a
visszaigazolás pontossága és a nyelvi rétegek kiszolgálása nem csökken.

## Miért

- A vásárlónak sosem kell másik felületet megtanulnia pont akkor, amikor a
  legkevésbé képes rá (torlódás, stressz, idős törpök aránya magas).
- A degradálható paraméterek explicit fel vannak sorolva (blueprint 5.
  szakasz) — nincs kísértés menet közben rögtönözni, mit kapcsoljunk ki.
- Összhangban van a „csak olyan időpontot mutatunk, amit tartani is tudunk"
  elvvel: a sor és az őszinte várakozás-üzenet a válasz szűkösségre, nem egy
  leegyszerűsített felület.

## Amit feladunk

Azt az egyszerűsítést, hogy csúcsidőben egy statikus, gyorsabb, de kevésbé
kifejező felületre válthatnánk — ez explicit tiltott, tehát a rendszernek
minden terhelésen bírnia kell a teljes nyelvi felületet, ami több mérnöki
munkát igényel korán (párhuzamos slotok, sor).

## Kiváltó feltétel

- a spike (M-1) méréseiben 5 egyidejű beszélgetésnél a válaszidő SLO
  (p95 < 2,5 s szöveg) nem tartható semmilyen belső paraméter-csökkentéssel
- élesben mért egyidejű aktív session két egymást követő foglalási nyitáson
  meghaladja a skálázási cél felső sávját (100+ szál) egyetlen gépen

## Váltás mire

Explicit degradált útvonal (pl. kizárólag a koppintós út elérhető torlódás
idején) — ez felülírná a jelen döntést, saját ADR-t igényelne.

## Váltás költsége

Magas — a koppintós út ma is párhuzamos felület, de „csak ez legyen
elérhető torlódásnál" új állapotot, új kommunikációt és új tesztfedettséget
igényel.

## Ellenőrzés

A spike méri az 1/3/5 párhuzamos beszélgetés válaszidejét (roadmap M-1,
2. pont); élesben a dev mód p95 latencia mutatója folyamatosan ellenőrzi.

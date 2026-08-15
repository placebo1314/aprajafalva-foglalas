# ADR-013: Elsődleges modell Apache-2.0; Racka ellenőrzőként

- **Dátum:** 2026-08-15
- **Állapot:** elfogadott

## Kontextus

Két nyelvi modell-jelölt van: egy Apache-2.0 licencű alapmodell (Qwen3-alap)
és a Racka-4B, ami Qwen3-4B alapon magyar tokenizer-cserével készült
(subword fertility 3,13 → 1,66, közel fele latencia), de CC-BY-NC-SA-4.0
licenccel, kapuzva, kutatási célra.

## Döntés

Az elsődleges, finomhangolt és éles modell egy Apache-2.0 licencű
alapmodell a nulladik naptól; a Racka-4B csak ellenőrző jelölt, méréshez,
nem éles útvonalon.

## Miért

- A Racka licence (CC-BY-NC-SA-4.0, kutatási célra) nem kompatibilis egy
  élesen, esetlegesen kereskedelmi körülmények között futó rendszerrel
  engedély nélkül.
- Az Apache-2.0 modell a nulladik naptól rendelkezésre áll finomhangolásra,
  nincs licenc-blokkoló a fejlesztés elején.
- A modell mögötte cserélhető modul (`LLMSzolgaltato` interfész), tehát a
  döntés nem zárja ki, hogy később mérés alapján váltsunk.

## Amit feladunk

A Racka lényegesen jobb magyar tokenizálásából fakadó teljesítményelőnyt
(feleannyi token, közel fele latencia) az éles útvonalon — ha ez a mérésen
igazolódik, engedély nélkül nem élvezhetjük.

## Kiváltó feltétel

- a golden seten a Racka lényegesen jobb eredményt ad — konkrét küszöb: a
  leggyengébb nyelvi rétegen mért pontosság-különbség > 5 százalékpont —, ÉS
- a projekt olyan szintet lép (pl. kereskedelmi vagy többtelepüléses
  üzemeltetés), ahol a licenc engedélyezése vagy megvásárlása indokolt és
  ténylegesen megtörténik

## Váltás mire

Racka-4B mint elsődleges modell, írásos licenc-engedéllyel.

## Váltás költsége

Alacsony technikailag (`LLMSzolgaltato` interfész mögött), a licenc-
egyeztetés időigénye ismeretlen — ez a fő korlátozó tényező, nem a kód.

## Ellenőrzés

A `golden-set` skill szerinti modellösszehasonlítás (`eval-futtato` agent,
`python feladat.py golden`), `docs/LICENCEK.md` frissítése minden
modellváltáskor.

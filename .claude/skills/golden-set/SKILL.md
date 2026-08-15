---
name: golden-set
description: A kiértékelő halmaz formátuma és használata — nyelvi és szituációs tesztesetek, mérőszámok, modellösszehasonlítás, regressziófigyelés. Használd, amikor tesztesetet írsz vagy bővítesz, modellt választasz vagy hasonlítasz össze, kiértékelőt futtatsz, finomhangolás eredményét méred, vagy el kell dönteni, hogy egy változtatás javított-e.
---

# Golden set

## Miért a modell előtt készül

A golden set **dönti el, melyik modellt választjuk**. Ha utólag írnánk, a
tesztesetek észrevétlenül a már kiválasztott modell erősségeihez igazodnának.

Ez az M2 mérföldkő, és szándékosan megelőzi az M3-at.

## Kétféle teszteset

### Nyelvi: mondat → eszközhívás

```yaml
- id: nyelvi-041
  bemenet: "jövő hét kedden délelőtt szeretnék nagy petárdát"
  most: "2026-03-10T09:00:00Z"        # a relatív dátum feloldásához
  varhato:
    eszkoz: szabad_idopontok
    parameterek:
      bolt_id: ugyifogyi
      szolgaltatas_id: nagy_petarda
      datum_tol: "2026-03-17T00:00:00Z"
      datum_ig: "2026-03-17T23:59:59Z"
      napszak: delelott
  cimkek: [relativ_datum, szolgaltatas_azonositas]
```

A `most` mező kötelező minden relatív dátumot tartalmazó esetnél — enélkül a
teszt egy hét múlva megbukik, és senki nem érti, miért.

### Szituációs: naptárállapot + kérés → mit ajánljon

Ez az ajánlatpontozó tesztje, és legalább olyan fontos, mint a nyelvi.

```yaml
- id: szituacio-012
  naptar:
    muszak: torpilla-pult-1-2026-03-20
    foglalt: ["08:00", "08:30", "09:00"]
    holdok:  ["09:30"]
  keres:
    napszak: delelott
  varhato:
    elso_jelolt_nem: "09:30"          # holdolt slotot nem ajánlunk
    jeloltek_szama: 2
    figyelmeztetes_szukosseg: true    # itt jogos
  cimkek: [pontozo, hold, szukosseg]
```

## Mérőszámok

| Mit mérünk | Küszöb |
|---|---|
| Szolgáltatás-azonosítás | > 98% |
| Dátumértelmezés | > 99% |
| Séma-érvényesség (`valid@1`) | 100% (kötött dekódolás mellett elvárt) |
| Eszközválasztás | > 98% |
| Pontozó: helyes első jelölt | > 90% |
| Téves szűkösség-figyelmeztetés | **0** |

Az utolsó sor nem teljesítménymutató, hanem becsületbeli kérdés. Ha a rendszer
akkor is siettet, amikor nincs miért, a figyelmeztetés két hét alatt elveszti
az értékét.

## A kiértékelő

```
make golden                      # az aktuális modell
make golden MODELL=racka-4b      # konkrét jelölt
make golden --osszehasonlit a,b  # két modell egymás mellett
```

A kimenet mindig tartalmazza:

- összesített pontszám címkénként (nem csak globálisan)
- **minden bukott eset felsorolva**, bemenettel és a kapott kimenettel
- tokenszám és latencia percentilisek
- az előző futáshoz képesti eltérés

A címkénkénti bontás a fontos. Egy 96%-os globális szám elrejtheti, hogy a
relatív dátumok 70%-on állnak.

## Modellválasztás

Legalább **egy nem-kereskedelmi és egy megengedő licencű** jelöltet mérünk
(lásd `docs/LICENCEK.md`). A döntés szempontjai sorrendben:

1. Pontosság a kritikus címkéken (dátum, szolgáltatás)
2. Latencia — a tokenizer-hatékonyság itt sokat számít magyarul
3. Licenc — **kis különbségnél mindig a szabadabbat választjuk**
4. Méret és erőforrásigény

A licenc nem utólagos szempont. Egy NC-licencű modellre épített rendszer nem
tud fizetőssé válni anélkül, hogy a modellréteget kicserélnénk.

## Bővítés

Minden hibából teszteset lesz. Ez a szabály:

```
valós beszélgetésben hiba → redaktált trace → annotálás → golden set
```

A dev mód (M5) pont ezt a hurkot építi meg. Egy hiba, amiből nem lett teszteset,
újra elő fog fordulni.

**Az eseteket nem töröljük**, csak jelöljük elavultnak, ha a viselkedés
szándékosan változott — az ADR számával együtt.

## Amire figyelni kell

- **Ne a modell kimenetéből írj tesztesetet.** Előbb döntsd el, mi a helyes,
  aztán mérj. Fordítva a teszt a modell tükre lesz.
- **A szituációs esetek determinisztikusak** — nincs bennük LLM, tehát 100%-ot
  kell hozniuk. Ha nem, az kódhiba, nem modellhiba.
- **Az idő fagyasztva.** Minden eset saját `most` értékkel fut.
- Legalább 150-200 eset kell, mielőtt bármit kijelentünk egy modellről.

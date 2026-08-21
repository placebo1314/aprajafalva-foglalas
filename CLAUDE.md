# Aprajafalvi időpontfoglaló

Magyar nyelvű, lokálisan futó időpontfoglaló Aprajafalva három boltjához.
Részletes terv: `docs/blueprint.md`. Ütemterv: `docs/roadmap.md`.

## Alapelv

**Az LLM nem foglal, hanem fordít.**

A foglalási logika a `core/`-ban van, determinisztikusan. Az `assistant/`
dolga kizárólag: magyar mondat → strukturált eszközhívás → magyar mondat.
Az orchestrator állapotgép, nem LLM.

Következmény: egy hibás modellválasz legrosszabb esetben kellemetlen
(rossz visszakérdezés), nem káros (dupla vagy elveszett foglalás).

## Sérthetetlen invariánsok

Ezek nem irányelvek. Ha egy változtatás sértené valamelyiket, a változtatás
rossz — akkor is, ha működik.

1. **Egy slotra pontosan egy aktív foglalás lehet.** Bizonyíték: parciális
   UNIQUE index + konkurencia-teszt. Nem számláló, nem alkalmazásszintű zár.
2. **Nyers vásárlóazonosító soha nem kerül lemezre, logba vagy trace-be.**
   Csak HMAC-hash. A pepper nem az adatbázisban van.
3. **A `core/` nem importál az `assistant/`-ből.** Egyirányú függés.
4. **Minden idő UTC-ben tárolódik**, ISO-8601 szövegként. Helyi idő csak a
   megjelenítésnél keletkezik.
5. **Minden SQL a `core/repo/`-ban van.** Máshol nincs nyers lekérdezés.
6. **Csak olyan időpontot mutatunk, amit tartani is tudunk.** Ajánlott
   jelölt = van rá hold.

## Parancsok

```
python feladat.py teszt              # teljes tesztkészlet (SQLite)
python feladat.py teszt-mindketto    # ugyanaz SQLite-on ÉS Postgresen
python feladat.py golden             # golden set kiértékelés
python feladat.py migracio "<nev>"   # új migráció váza
python feladat.py seed               # demóadat betöltése
python feladat.py lint               # ruff
```

A projekt Windowson, macOS-en és Linuxon egyaránt fut. Nincs `make`, nincs
bash-függőség: minden eszköz Python.

## Konvenciók

- **A kód angolul, a séma és a domain szótár magyarul** (ADR-014).
  Python-azonosítók (függvény, változó, osztály, top-szintű modulnév)
  angolul (`create_booking`, `org_id`, `Shift`, `core/`). A séma
  (tábla-/oszlopnevek SQL-stringekben) és a repo-függvények visszaadott
  dict-jeinek **string-literál kulcsai** magyarul maradnak — ez a séma
  nyelve, nem a kódé, lásd `docs/domain.md` a magyar↔angol szótárért.
  A CLI-parancsok (`python feladat.py teszt`, `foglal`, `lemond`) és a
  konzol-/UI-szövegek is magyarok maradnak — ez a felhasználói felület
  nyelve, nem a kódé.
- **Minden elsődleges kulcs UUID**, szövegként tárolva. Soha nem
  autoincrement.
- **Migrációk sorszámozva**, up és down iránnyal. Kézi sémamódosítás soha.
- **Egyszerűsítés csak ADR-rel**, konkrét kiváltó feltétellel. Lásd
  `docs/adr/` és a `adr` skillt.
- **Többlépéses, egyértelmű feladatnál ne kérj checkpointot lépések
  között** — csak akkor állj meg, ha valódi, eldöntendő kérdés merül fel.
  A commitok és a tesztek adják a biztonságot, nem a közbenső jóváhagyás.

## Modulhatárok

```
core/         önálló, LLM nélkül működik      → nem importál semmi mást
assistant/    importálhat core/-ból            → csak eszközhívásokat állít elő
privacy/      önálló                          → mindkettő használhatja
ui/           importálhat core/-ból            → nem hív LLM-et közvetlenül
```

Az almodulok (`core/repo/`, `core/slot/`, `core/modell/`, `core/szabalyok/`,
`core/api/`) és a legtöbb fájlnév (pl. `torzsadat_repo.py`, `migracio.py`)
egyelőre magyar maradt — csak a fenti top-szintű csomagnevek mozogtak
(ADR-014, "Amit feladunk" szakasz).

## Ha elakadsz

- Domain-kérdés (műszak, szünet, hold, snapshot) → `foglalasi-mag` skill
- Adatbázis, migráció, hordozhatóság → `db-hordozhatosag` skill
- Személyes adat, redaktálás, megőrzés → `adatvedelem` skill
- Eszközök JSON-sémája → `eszkoz-szerzodes` skill
- Teszteset, kiértékelés, modellválasztás → `golden-set` skill
- Döntés rögzítése → `adr` skill vagy `/adr`

Ha egy kérés ütközik egy invariánssal, ne oldd meg kreatívan — jelezd, és
javasolj ADR-t.

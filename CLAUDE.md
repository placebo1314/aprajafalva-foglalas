# Aprajafalvi időpontfoglaló

Magyar nyelvű, lokálisan futó időpontfoglaló Aprajafalva három boltjához.
Részletes terv: `docs/blueprint.md`. Ütemterv: `docs/roadmap.md`.

## Alapelv

**Az LLM nem foglal, hanem fordít.**

A foglalási logika a `mag/`-ban van, determinisztikusan. Az `asszisztens/`
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
3. **A `mag/` nem importál az `asszisztens/`-ből.** Egyirányú függés.
4. **Minden idő UTC-ben tárolódik**, ISO-8601 szövegként. Helyi idő csak a
   megjelenítésnél keletkezik.
5. **Minden SQL a `mag/repo/`-ban van.** Máshol nincs nyers lekérdezés.
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

- **Domain-nevek magyarul** (`muszak`, `slot`, `foglalas`, `szunetblokk`),
  technikai nevek angolul (`repository`, `session`, `handler`).
- **Minden elsődleges kulcs UUID**, szövegként tárolva. Soha nem
  autoincrement.
- **Migrációk sorszámozva**, up és down iránnyal. Kézi sémamódosítás soha.
- **Egyszerűsítés csak ADR-rel**, konkrét kiváltó feltétellel. Lásd
  `docs/adr/` és a `adr` skillt.

## Modulhatárok

```
mag/          önálló, LLM nélkül működik      → nem importál semmi mást
asszisztens/  importálhat mag/-ból             → csak eszközhívásokat állít elő
adatvedelem/  önálló                          → mindkettő használhatja
felulet/      importálhat mag/-ból             → nem hív LLM-et közvetlenül
```

## Ha elakadsz

- Domain-kérdés (műszak, szünet, hold, snapshot) → `foglalasi-mag` skill
- Adatbázis, migráció, hordozhatóság → `db-hordozhatosag` skill
- Személyes adat, redaktálás, megőrzés → `adatvedelem` skill
- Eszközök JSON-sémája → `eszkoz-szerzodes` skill
- Teszteset, kiértékelés, modellválasztás → `golden-set` skill
- Döntés rögzítése → `adr` skill vagy `/adr`

Ha egy kérés ütközik egy invariánssal, ne oldd meg kreatívan — jelezd, és
javasolj ADR-t.

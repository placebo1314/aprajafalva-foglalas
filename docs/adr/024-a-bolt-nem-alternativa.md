# ADR-024: A bolt nem alternatíva — a bolt-ajánlás visszavonva

- **Dátum:** 2026-08-30
- **Állapot:** elfogadott
- **Viszonya a többihez:** **visszavonja** a 2026-08-30-i „itt nincs, de
  a szomszédban van" funkciót (`masik_bolt`), ami ugyanaznap készült el.
  Az ADR-006 (ajánlatpontozó) és a blueprint 1. szakaszának 5. igénye
  („ha nincs hely, alternatíva jöjjön") érvényben marad — csak az derül
  ki, hogy a BOLT nem tartozik az alternatívák közé.

## Kontextus

A `nincs_meghirdetett_idopont` üzenet igaz volt, de nem mondta meg, hol
VAN időpont. Erre került be egy `masik_bolt` mező: ha ebben a boltban
nincs, de egy másikban van, a rendszer felajánlotta a másikat, gombbal.

Működött, tesztelt volt, és a mérésen sem rontott. **Mégis rossz.**

## A hiba a modellünkben, nem a kódban

Aprajafalva három boltja **nem ugyanannak a szolgáltatásnak három
telephelye**, hanem három különböző termék:

| Bolt | Termék |
|---|---|
| Szundi | altató |
| Ügyifogyi | petárda |
| Törpilla | boldogság |

Ebből két dolog következik, és mindkettőt figyelmen kívül hagytuk:

1. **Aki petárdát kér, annak a boldogság-bolt nem alternatíva.** Az
   ajánlás nem „kevésbé jó találat", hanem MÁS KÉRÉSRE adott válasz. A
   vesztes ág attól még nem lesz kellemes, hogy tesz valamit — attól
   lesz kellemes, hogy hasznosat tesz.
2. **A bolt-azonosítás ezért triviális.** A profilok szándékosan
   különbözőek (`assistant/tools/katalogus.py`: a szolgáltatás
   egyértelműen meghatározza a boltot). Ahol a bolt kiderül a kérésből,
   ott nincs mit „ajánlani"; ahol nem derül ki, ott a helyes válasz a
   kérdés — vagy a minden boltra kiterjedő keresés (l. lent).

**A funkció tehát egy nem létező problémát oldott meg**, és közben egy
valódit takart el: a bolton BELÜLI lazítási sorrendet (ADR nélkül, l.
„Váltás mire").

## Döntés

**A `masik_bolt` mező, a hozzá tartozó mondat és gomb megszűnik.** Nem
kikapcsolva marad (mint az önkonzisztencia, ADR-021), hanem törölve:
ott a kikapcsolt kód egy MÉRT, de nem javító képesség volt; itt a
képesség maga téves.

**Egy dolog marad, és az nem ajánlás:** ha a vásárló **nem adott meg
boltot**, a keresés minden boltra megy. Ez alapértelmezés, nem
javaslat — a különbség az, hogy nem írjuk felül a vásárló választását,
hanem a hiányzó választás helyére lépünk. Ennek az explicit alakja a
`MINDEGY` érték (l. `assistant/tools/semak.py`): a `null` azt jelenti,
hogy nem tudjuk (kérdezzünk), a `MINDEGY` azt, hogy a vásárló
elengedte (ne kérdezzünk többet).

## Amit feladunk

- **A „hol van egyáltalán időpont" kérdés megválaszolatlan marad**, ha
  a vásárló boltja üres. A válasz ilyenkor annyi, hogy ITT nincs — és
  ez helyes, mert a másik bolt más terméket árul.
- **Egy valós, de más eset elveszik vele:** ha egyszer lesz két bolt
  UGYANAZZAL a termékkel (két „petárda-bolt" a falu két végén), a
  kereszt-bolt ajánlás értelmes lesz. Ma nincs ilyen, és a mai
  katalógusban nem is lehet (`SZOLGALTATAS_NEVEK`: minden szolgáltatás
  pontosan egy bolthoz tartozik).

## Miért nem hagyjuk bent „arra az esetre"

A halott kód kockázata (ADR-021, „Amit feladunk") itt nagyobb, mint az
előnye: a `masik_bolt` ág minden üres keresésnél lefutott, tehát nem
volt ingyen, és minden jövőbeli olvasónak azt sugallta volna, hogy a
bolt cserélhető dimenzió. **Egy rossz fogalom a kódban rosszabb, mint
egy hiányzó funkció**, mert a következő döntés már rá épül.

## Kiváltó feltétel

Bármelyik újranyitja:

- **Két bolt ugyanazzal a szolgáltatással.** Ha a katalógusban egy
  szolgáltatás-slug két bolthoz tartozik, a kereszt-bolt ajánlás
  értelmet nyer — akkor viszont NEM „másik bolt" néven, hanem
  ugyanannak a terméknek a másik helyszíneként.
- **Több telephely egy boltnak.** Ugyanez, más szóval.

## Váltás mire

A bolt helyett a bolton BELÜLI lazítási sorrend a helyes válasz arra,
hogy „nincs hely" (blueprint 1., 5. igény):

1. **más időpont a kért ablakban** (a preferált óra / napszak elengedése),
2. **tágabb ablak** — a következő szabad időpont, akár hetekkel később
   (`legkozelebbi_idopont`, holddal, tehát kimondható időponttal),
3. **más pult ugyanabban a boltban** — ma nem szűkítünk pultra, tehát
   ez nem is szólal meg; ha valaha szűkítenénk, itt a helye,
4. **más variáns a bolton belül** (kis/nagy petárda), de csak ha a
   vásárló elengedte a terméket (`szolgaltatas_id: MINDEGY`).

Ez a sorrend a `szabad_idopontok._alternativ_dimenzio` kimenete, és a
válasz megmondja, melyik dimenzióban engedett.

## Váltás költsége

A visszavonás egy commit: a mező, a mondat, a gomb és a hozzá tartozó
tesztek törlése. A helyére lépő lazítási sorrend külön munka, ugyanabban
a körben.

## Ellenőrzés

```
python -m pytest tests/egyseg/test_tools.py
python feladat.py vegigjatszas --robusztus
```

A naplóban a `masik_bolt` mező nem jelenhet meg, és a felületen nem
állhat elő „Nézzük a … boltban" gomb.

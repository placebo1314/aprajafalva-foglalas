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

1. **más időpont a kért ablakban** — a napszak-kötöttséget engedjük el,
   a nap marad (`napszak`),
2. **tágabb ablak** — előbb ugyanazon a héten másik nap (`nap`), aztán
   a kért ablak vége utáni legkorábbi szabad időpont, akár hetekkel
   később (`kesobb`, a `legkozelebbi_idopont` eszközzel, tehát holddal,
   tehát kimondható időponttal: „a legkorábbi szabad időpont december
   huszonharmadikán van"),
3. **más pult ugyanabban a boltban** — l. lent, nincs mit lazítani,
4. **más variáns a bolton belül** — a szolgáltatás-szűrés elengedése
   (`varians`).

Ez a sorrend a `szabad_idopontok.LAZITAS_DIMENZIOK`, a lépés tartalma a
`lazitas_terve()`, a döntés az `_alternativ_dimenzio()`. **Mindegyik
mondat kimondja, melyik dimenzióban engedtünk** — az „van egy másik
időpont" önmagában nem válasz, mert a vásárló nem tudja, mit adott fel
érte (`assistant/valasz/sablonok.py`, `alternativa`).

### Két dimenzió ma nem tud megszólalni — és a kettő nem ugyanúgy

Ezt a mérés mondta ki, nem a terv:

- **`pult`: nincs mit lazítani.** A keresés ma sem szűkít pultra —
  sem az ajánlatpontozó, sem a repo (`free_slots_search`: a szűrés
  bolt és szolgáltatás szerint megy, a pult csak a slot
  GENERÁLÁSÁBAN szerepel). Ezért nem került be a listába: egy mindig
  üresen visszatérő ág hazugság lenne. Bizonyíték rá teszt van
  (`test_a_kereses_nem_szukit_pultra`), nem ígéret. Ha valaha
  szűkítenénk pultra, a helye a `nap` és a `kesobb` közé kerül.
- **`varians`: van mit lazítani, csak a mai KATALÓGUSBAN nincs.** A
  dimenzió megvalósult, és valódi lekérdezéssel próbálkozik; hogy ma
  mégsem szólal meg, az az adaton múlik: a `kis_petarda` és a
  `nagy_petarda` slug UGYANARRA a „petárda" szolgáltatás-sorra mutat
  (`katalogus.py`, `docs/domain.md`: „Szolgáltatás ≠ variáns"), tehát
  a szűrés elhagyása ugyanazokat a slotokat adja. Amint egy boltnak
  két, ütemezésileg különböző szolgáltatása lesz, magától megszólal —
  a teszt (`test_szabad_idopontok_alternativ_dimenzio_varians`) épp
  ilyen adaton méri.

**A „ha a vásárló elengedte a terméket" feltételt úgy értjük, hogy a
felajánlás MAGA a kérés az elengedésre.** A gomb megnyomása állítja
`MINDEGY`-re a `szolgaltatas_id`-t; ha már eleve `MINDEGY` volt, a
dimenzió értelmetlen (nincs mit elengedni, mert minden változatot
nézünk), és a `lazitas_terve` ilyenkor `None`-t ad. A fordított
olvasat — csak akkor ajánljuk, ha már elengedte — halott ággá tenné,
és épp azt a mondatot venné el, amiért a dimenzió van.

### A kiút-gombok is átálltak

A beszélgetés-zsákutca kiútja (`orchestrator._KIUT_DIMENZIOK`) eddig
„másik boltot" ajánlott elsőként. Ugyanaz a hiba, kisebb helyen: ott is
a bolt volt a cserélhető dimenzió. A három gomb mostantól **másik nap /
másik napszak / a legkorábbi szabad időpont** — az utolsó a
`legkozelebbi_idopont` eszközre megy, tehát valódi választ ad, nem újabb
kérdést.

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

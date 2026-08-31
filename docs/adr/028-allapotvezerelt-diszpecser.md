# ADR-028: Állapotvezérelt diszpécser — a modell megtudja, hol tart a beszélgetés

- **Dátum:** 2026-09-01
- **Állapot:** elfogadott
- **Viszonya az ADR-007-hez:** **kiegészíti.** Az orchestrator eddig is
  állapotgép volt; ami változik, az az, hogy az állapot KIMONDOTT — a
  promptban, a naplóban és a kódban rögzített átmenetekben.

## Kontextus

Az orchestrator állapota eddig belső ügy volt: a `_SessionAllapot.allapot`
mező négy szöveges értéket vett fel (`kezdet`, `valasztasra_var`,
`megerositesre_var`, `lezarva`), az átmeneteket pedig szétszórt
értékadások végezték. A modell ebből semmit nem látott.

Ennek mért következménye volt (2026-08-31, `vegigjatszas`,
`qwen3.5:9b`): az „igen, foglald le" mondatból ÚJ KERESÉS lett, mert a
modell a mondatot önmagában olvasta. Egy csupasz „a második" vagy
„igen" **önmagában kétértelmű** — csak a helyzet teszi egyértelművé.

Az akkori javítás determinisztikus rövidzár volt
(`assistant/megerosites.py`): ha megerősítésre várunk, az igen/nem
választ nem értelmeztetjük. Ez megoldotta a KONKRÉT esetet, de nem a
fajtáját: az „az a fél kilences jó lesz" vagy „a középső" ugyanúgy a
felajánlott listára hivatkozik, és arra nincs zárt minta.

## Döntés

**Hat explicit állapot, kódban rögzített átmenetekkel, és az aktuális
állapot egy sorban a promptban** (`assistant/allapotgep.py`).

| állapot | mit várunk |
|---|---|
| `INDULAS` | bármilyen kérést |
| `HIANYZO_ADAT` | a hiányzó mezőt (zárt kérdést tettünk fel) |
| `AJANLAT_VAR` | sorszámot vagy időpontot a felajánlott N-ből |
| `MEGEROSITES_VAR` | igent vagy nemet |
| `KESZ` | új kérést (a foglalás létrejött) |
| `KIUT` | választást a felkínált irányok közül |

Három következmény, mindhárom külön ér valamit:

1. **A promptba egy sor kerül** (`prompt_sor`), pl.: *„Állapot:
   AJANLAT_VAR — 3 időpontot ajánlottunk fel, és most ezek közül várunk
   választást: sorszám, időpont, vagy visszalépés."* Ez HELYZETLEÍRÁS,
   nem utasítás — nem azt mondja meg, mit adjon vissza a modell, hanem
   azt, hogy mire válaszol a vásárló.
2. **Az átmenetek zártak** (`ATMENETEK`), és minden váltás egy helyen
   megy át (`Orchestrator._allapotba`) — a gombos és a szöveges út
   állapota így nem csúszhat szét. Nem engedélyezett átmenetnél nincs
   kivétel (a vásárló nem eshet ki egy fejlesztői tévedéstől): naplózunk
   és a biztonságos `INDULAS`-ba térünk.
3. **A napló minden fordulónál rögzíti az állapotot és az átmenetet**
   (`allapot`, `atmenet` mező) — a `python feladat.py naplo` külön
   blokkban összesíti, a riport fordulónként mutatja.

**Az állapot NEM a válasz mezője**, hanem megfigyelhetőség
(`Orchestrator.utolso_allapot`) — ugyanaz a minta, mint az
`utolso_ertelmezes`-nél. A válasz dict a felület szerződése; egy
megfigyelési mező odatétele csendben megváltoztatná azt.

## Ami ebből NEM következik

**A determinisztikus rövidzárak maradnak** (`sorszam.py`,
`megerosites.py`). Azok a GARANCIA: ha a felajánlott háromból a
másodikat kérik, azt nem a modell dönti el — egy elrontott sorszám nem
visszakérdezést okoz, hanem MÁS IDŐPONTOT foglal le. Az állapotsor
akkor segít, amikor a rövidzár nem illeszkedik. A kettő egymás mellett
áll, nem egymás helyett.

## A mérés — és a mérés HATÁRA

**A golden set ezt nem tudja megmérni.** A mérési út
(`tests/golden/futtato.py::ertelmezo_hivo`) az értelmezőt hívja, nem az
orchestratort: nincs session, nincsenek felajánlott jelöltek, tehát
állapot sincs. Egy kitalált állapotsor a mérésben pontosan az a fajta
hamisítás lenne, amit az ADR-019 óta kerülünk (ott a rendszer-válaszokat
nem találjuk ki).

Ezért az állapotsor hatását ott mérjük, ahol valódi:
`python feladat.py vegigjatszas` MODELLEL, `APRAJAFALVA_ALLAPOT_SOR`
be/ki kapcsolóval. Négy olyan mondattal, amit a determinisztikus
rövidzár szándékosan nem ismer fel:

| | találat |
|---|---|
| determinisztikus alapvonal (modell nélkül) | 0/4 |
| modell, állapotsor KI | 2/4 |
| modell, állapotsor BE | **3/4** |

**A nagyobb hatás nem az állapotsoré, hanem a hiányzó ESZKÖZÉ**: a
modellnek eddig nem volt mivel kifejeznie, hogy a vásárló a listából
választott (`jelolt_valasztas` — l. lent). Az állapotsor ehhez képest
egy esetet fordított meg („a legkorábbi megfelel": állapotsor nélkül
`legkozelebbi_idopont` keresés lett belőle). **Négy próbából egy
különbség nem bizonyíték** — irányt mutat, ezért marad a kapcsoló.

A végigjátszás többi menete mindkét felállásban azonosan futott
(35 forduló, két sikeres foglalás, kivétel nélkül): az állapotsor nem
zavarja meg azokat a fordulókat, ahol nincs mire hivatkozni — ez volt a
legfőbb kockázata.

A golden seten mért 90-91% ettől függetlenül változatlan marad — ott az
állapotsor nem is jelenik meg.

## Ami az állapotsorral EGYÜTT kellett: `jelolt_valasztas`

A mérés első köre egy szerkezeti hiányt tárt fel: a modell akkor sem
tudta volna kifejezni a listából választást, ha érti a helyzetet — a
`{eszkoz, parameterek}` szerződésben nem volt rá érték. A legjobb, amit
tehetett, egy újabb keresés volt.

Ezért az `Ertelmezo` protokoll új irányítási értéket kapott (nem
`assistant/tools/` eszközt, hanem a `visszakerdez`-hez hasonló
vezérlést): **`jelolt_valasztas` + `sorszam`**. Két determinisztikus
kapu védi, mert egy elrontott választás nem visszakérdezést okoz, hanem
MÁS IDŐPONTOT foglal le:

1. csak `AJANLAT_VAR` állapotban fogadjuk el;
2. csak a tényleges tartományban — a negyedikre nem kerekítünk.

## Amit feladunk

- **Egy sornyi promptot fordulónként.** A leghosszabb állapotsor ~150
  karakter; a mérés szerint (ADR-026) a prompt hossza ezen a méreten
  nem latencia-tényező, de ingyen nincs.
- **Egy új fogalmat**, amit karban kell tartani: minden új válasz-típus
  kap majd egy állapot-leképezést, és aki elfelejti, annál az állapot
  némán megáll (ismeretlen típusnál nem mozdul). Ezt a
  `test_allapotgep.py` teszteli, de csak az ISMERT típusokra.
- **Azt a lehetőséget, hogy az állapotot a felület vezesse.** Az
  állapot az orchestratoré; a felület (ami a beszélgetést vezeti,
  ADR-019) nem írhatja felül. Ez helyes, de azt jelenti, hogy egy
  jövőbeli másik felületnek is az orchestratortól kell kérnie
  (`allapot_sor()`).

## Kiváltó feltétel

- az állapotsorral mért végigjátszás **nem jobb** a nélküle mértnél két
  egymást követő mérésen — ekkor a sor csak tokent visz, és ki kell
  venni (a kapcsoló ezért marad a kódban);
- megjelenik olyan forduló, ahol a modell az állapotsort UTASÍTÁSNAK
  veszi (pl. `AJANLAT_VAR`-ban mindenáron sorszámot ad vissza egy
  témaváltó mondatra) — ekkor a sor megfogalmazása a hibás, nem a
  létezése;
- a naplóban tartósan megjelennek nem engedélyezett átmenetek — ekkor
  az `ATMENETEK` tábla hiányos, és a valóságot kell követnie, nem
  fordítva.

## Váltás mire

**Állapotfüggő eszközkészlet**: `MEGEROSITES_VAR`-ban a modell csak egy
szűkített eszközhalmazt kapna (igen/nem/visszakerdez), a kötött
dekódolás szintjén. Ez erősebb garancia, mint a promptsor — de
elveszítené azt, hogy a vásárló bármikor témát válthat.

## Váltás költsége

Közepes: a `FORMAT_SEMA` ma egy konstans; állapotfüggővé tenni azt
jelenti, hogy a séma hívásonként épül, és a séma-verziózás
(`eszkoz-szerzodes` skill) bonyolultabb lesz.

## Ellenőrzés

```
python -m pytest tests/egyseg/test_allapotgep.py
python feladat.py naplo            # az "Állapotok és átmenetek" blokk
APRAJAFALVA_ALLAPOT_SOR=ki python feladat.py vegigjatszas
```

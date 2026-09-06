# ADR-033: Helyi idő a megjelenítésben — és a felolvasó három hibája

- **Dátum:** 2026-09-20
- **Állapot:** elfogadott
- **Kiváltó ok:** kézi próba — „az időpontokat gombként jeleníti meg", és
  a felolvasó nem használható

## Kontextus

### 1. A rendszer ROSSZ IDŐPONTOT mondott

A CLAUDE.md 4. invariánsa két mondat, és eddig csak az elsőt tartottuk
be:

> Minden idő UTC-ben tárolódik, ISO-8601 szövegként. **Helyi idő csak a
> megjelenítésnél keletkezik.**

A megjelenítés nem csinálta meg. A demóadat boltjai 8 órakor nyitnak
helyi idő szerint, a slot `2026-12-21T07:00:00Z` alakban áll az
adatbázisban — és a vásárló ezt látta a gombon:

```
2026-12-21 07:00–07:10 (UTC)
```

...a felolvasó pedig azt mondta neki, hogy „hét órakor". Télen egy,
nyáron két óra tévedés, MINDEN időponton, mindkét csatornán, a
megerősítés-kérdésben is — abban a mondatban, amire a vásárló igent
mond.

**Ez nem formázási hiba volt.** A rendszer minden más ponton helyesen
számolt: az ajánlatpontozó a napszakot (délelőtt/délután) már eddig is
helyi órára váltotta (`core/api/ajanlatpontozo.py`). Egyedül a
KIMONDÁS maradt UTC-ben — az a pont, ahol a szám elhagyja a rendszert.

### 2. A gombfelirat nem része a beszélgetésnek

A szöveges mondat csak BEVEZETTE a jelölteket („Ezeket az időpontokat
találtam — melyik jó?"), és az időpont kizárólag gombfeliratként
létezett. Egy gombfelirat viszont nem olvasható vissza, nem kerül a
beszélgetés menetébe, és aki felolvastatja a képernyőt, annak
egyszerűen nincs ott.

### 3. A felolvasó három hibája

MÉRVE (`python feladat.py hangproba --meres`):

| | előtte | most |
|---|---|---|
| késleltetés mondatonként | **2,07 s** | **0,14–0,23 s** |
| hangmodell betöltése | mondatonként újra | egyszer, indításkor (1,5 s) |

A Piper külön PROGRAMKÉNT hívva mondatonként ~2 másodperc — a mondat
hosszától FÜGGETLENÜL, tehát nem a szintézis lassú, hanem az indulás:
minden megszólalásnál új Python-folyamat, és újra betöltött 60 MB-os
hangmodell. A modell 3,5 s alatt válaszol; ha a hang még kettőt tesz
rá, a beszélgetés ritmusa elvész.

A másik kettő ennél is egyszerűbb: minden szintézis UGYANARRA a fájlra
írt (arra, amit a lejátszó épp olvasott), és a régi mondatot semmi nem
hallgattatta el, tehát két forduló hangja egymásra csúszott.

## Döntés

**1. Egyetlen konverziós pont: `assistant/valasz/helyi_ido.py`.**
`helyi_iso(iso, zona)` ugyanolyan ALAKÚ ISO-szöveget ad vissza, csak a
zóna szerinti falióra-idővel és `Z` nélkül. A formázók
(`assistant/valasz/szamok.py`) karakterpozíció szerint vágnak, tehát a
konverzió után változatlanul működnek — egy ponton váltunk, nem tíz
formázóban. **A `Z` eltűnése a jelzés, hogy ez már nem UTC.**

**2. A zóna a TÖRZSADATBÓL jön, és a hívó adja át.** A felület
induláskor betölti (`org_load(...)["idozona"]`), és minden
időpont-tartalmú mondatnak átadja (`ajanlat_mondat`,
`megerosites_ker_szoveg`, `nyugtazo_szoveg`, a gombfeliratok). A
`zona=None` nem elnézés: az az eset, amikor nincs szervezet.

**3. Az „(UTC)" nem hagyja el a rendszert.** A vásárlónak nincs dolga
az időzónákkal — az ő ideje a falióra.

**4. A mondat KIMONDJA az időpontokat, nem csak bevezeti őket.**
Szöveges módban minden jelölt kezdete elhangzik („Ezeket az időpontokat
találtam: 9:20, 9:40 vagy 10:00. Melyik jó?"); a gombok megmaradnak — a
kettő nem egymás helyett van. Hangon marad a legkorábbi + egy
alternatíva (három felolvasott időpont megjegyezhetetlen).

**5. A hangmodell betöltve marad, és előre betöltjük.** Ha a Piper
Python-csomagként elérhető, a `PiperVoice` egyszer töltődik be és
megmarad; a felület indításkor, háttérszálon melegíti — ugyanaz a minta,
mint a modell-előmelegítésnél (ADR-030).

**6. A lejátszás megszakítható, és minden mondat SAJÁT fájlba megy.**
Új megszólalás elhallgattatja a régit (`hang.leallit()`): a vásárló
kérdése fontosabb, mint az előző válasz vége. Windowson a szinkron
`PlaySound`-ot MÉRVE nem szakítja meg egy másik szálból küldött
`SND_PURGE`, ezért aszinkron lejátszás + megszakítható várakozás a WAV
hosszáig.

**7. A végigjátszás beszélhető módban ELLENŐRIZ, nem csak kiír.**
Fordulónként két dolgot: átment-e a megszólalás a formai kapun
(`beszelheto.tiltott_jelek`), és ha a forduló gombot rajzolt, KÉRDEZ-e
a kimondott szöveg. Gomb önmagában néma. A kifogások a végén egyben is
megjelennek, és a kilépőkód is jelzi őket.

## Miért így

- **A konverzió a megjelenítésben, nem a tárolásban.** A 4. invariáns
  nem változott: a slot, a hold és a foglalás UTC marad. Ami változott,
  az az, hogy a második mondatát is betartjuk.
- **A zónát a hívó adja, nem a sablon kéri le.** Az `assistant/valasz/`
  nem nyúl adatbázishoz — ez a modulhatár (CLAUDE.md), és egy kényelmi
  lekérdezés kedvéért nem sértjük meg.
- **A felolvasó gyorsítása nem optimalizálás, hanem javítás.** Két
  másodperc csend minden mondat előtt nem „lassú", hanem használhatatlan:
  a vásárló azt hiszi, nem történt semmi, és újra beszél.

## Amit feladunk

- **A szöveges ajánlat-mondat hosszabb lett.** Három időpont felsorolása
  a gombok fölött redundáns annak, aki látja a képernyőt. Cserébe a
  beszélgetés ÖNMAGÁBAN teljes: visszaolvasható, naplózható,
  felolvastatható.
- **A hangmodell memóriában marad** (~60 MB) az egész munkamenet alatt.
  Egy 8 GB-os kártyán a nyelvi modell mellett ez elhanyagolható, de nem
  nulla.
- **A megszakítás elveszi a mondat végét.** Ha a vásárló az utolsó
  szótag előtt ír, azt már nem hallja. Ez tudatos: a két hang egyszerre
  rosszabb.
- **A koppintós út NAP-VÁLASZTÓJA még UTC-dátumokból épül**
  (`muszak_repo.slot_range`). A mai demóadaton (8-17 óra közti
  műszakok) a két naptár egybeesik, tehát nem látszik — de ha egy bolt
  este tíz után is nyitva lenne, a lista egy nappal elcsúszna. Ez nem
  javítás nélkül maradt hiba, hanem tudatos határ: a nap-választó a
  BEOSZTÁS időszakát mutatja, nem egy konkrét időpontot, és a
  szerződését (`helyi_datum`) csak azzal együtt érdemes átgondolni,
  hogy a beosztás maga is helyi napokban gondolkodik-e.

## Kiváltó feltétel

- **egy időpont MÉGIS UTC-ben jelenik meg** — akkor a konverzió nem
  egyetlen ponton történik, és a `helyi_ido.py` szerződését kell
  szigorítani (pl. típussal, nem stringgel);
- **több szervezet, több időzóna egy adatbázisban** — a felület ma EGY
  zónát tölt be induláskor; ekkor a zónának a válaszdicttel kell
  utaznia, nem a felület állapotában ülnie;
- **a felolvasó késleltetése tartósan 0,5 s fölé megy** (`hangproba
  --meres`) — akkor a betöltve tartás nem elég, és streamelő szintézis
  kell (mondatonként darabolva, az első darab azonnal szól).

## Ellenőrzés

```
python -m pytest tests/egyseg/test_helyi_ido.py tests/egyseg/test_hang.py
python feladat.py hangproba --meres
python feladat.py vegigjatszas --mod mindketto     # HANG-KIFOGÁS sorok
```

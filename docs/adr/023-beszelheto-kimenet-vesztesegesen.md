# ADR-023: A beszélhető kimenet veszteséges — két mondat, egy kérdés

- **Dátum:** 2026-08-26
- **Állapot:** elfogadott
- **Viszonya a többihez:** a blueprint 7. szakaszának („Négy technika",
  „Kétlépcsős válasz") kimondott alakra vonatkozó kiegészítése. Az
  ADR-022 (válaszidő-eloszlás) a másik fele ugyanennek az
  előkészületnek: az egyik azt mondja meg, MIT mondunk, a másik azt,
  MENNYI IDŐ alatt.

## Kontextus

Az M6 hangcsatornához négy komponens kell (ASR, TTS, turn-detection,
barge-in), és mind a négy **konfiguráció, nem építés**
(`docs/PLATFORM_TANULSAGOK.md`). Van viszont két darab, ami a mi
dolgunk, és amit hang NÉLKÜL is meg lehet csinálni — sőt, csak addig
lehet olcsón:

1. **a TTS bemenete**: felolvasható magyar mondat;
2. **az ASR kimenetének elviselése**: mi történik, ha a gép rosszul
   hallja (ez a robusztussági halmaz 13. kategóriája, külön kérdés).

Ez az ADR az elsőről szól.

**Miért nem elég a mai szöveges kimenet.** Egyetlen valódi mondatunk a
felületről:

> Ezeket az időpontokat találtam — melyik jó?
> `2026-12-22 08:00–08:15 (UTC)` `2026-12-22 08:15–08:30 (UTC)` …

Felolvasva ebből ez lesz: egy gondolatjel (szünet), majd három
azonosíthatatlan időbélyeg, „kettőspont" és „UTC" szavakkal. A vásárló
nem tud választani, mert nem tudja megjegyezni, mi közül választ.

## Döntés

A `valasz` modulnak **két kimeneti módja** van: `szoveges` (a mai
viselkedés, változatlanul) és `beszelheto`. A beszélhető mód öt
szabálya:

| Szabály | Mögötte álló hiba |
|---|---|
| Nincs felsorolás, markdown, zárójel — egész mondatok | a TTS a jelölést vagy felolvassa, vagy elnyeli |
| A számok kimondva (`szamok.py`) | a magyar TTS a `08:15`-öt NÉMÁN rontja el |
| Egy kérdés fordulónként | két kérdésre a vásárló az egyikre felel, és nem tudjuk, melyikre |
| Legfeljebb két mondat válaszonként | a hosszú válasz barge-int szül |
| Időpont-felsorolás helyett a legkorábbi + EGY alternatíva | három felolvasott időpont megjegyezhetetlen |

**Két rétegben érvényesül.** Ahol a megfogalmazás hangon másképp helyes
(két kérdés helyett egy, „a másik fülön" helyett a bolt), ott a
`sablonok.py` `beszelheto` szótára írja felül a mondatot — ez az
elsődleges út, mert jó megfogalmazást nem lehet automatikusan
előállítani. Ahol csak a formázás zavarna (számjegy, zárójel,
gondolatjel), ott a **kimeneti kapu** (`beszelhetove()`) intézi el; ez a
háló, ami egy jövőbeli, elfelejtett sablont is elkap.

## Amit feladunk

**A mód VESZTESÉGES, és ez a döntés lényege, nem a mellékhatása.**

- **A harmadik és további időpont.** Marad a legkorábbi és egy
  alternatíva.
- **A szolgáltatás leírása és időtartama.** Marad a név.
- **Minden zárójeles megjegyzés** — a kapu eldobja, nem kibontja.
- **A korábbi kérdések.** Ha egy fordulóban több kérdés keletkezne, az
  UTOLSÓ marad. Ez heurisztika: azt feltételezi, hogy a beszélgetés a
  legfrissebb kérdésnél tart. Lehet olyan eset, ahol a korábbi kérdés
  volt a fontosabb — ezt nem tudjuk megkülönböztetni.
- **Az évszám a dátumban.** „December huszonkettedikén" — egy foglalási
  beszélgetésben az év sosem kérdés (a keresési ablak hetes
  nagyságrendű), kimondva viszont hosszú.
- **Az időzóna.** A kimondott időpont nem tartalmazza; a helyi időre
  váltás a megjelenítő rétegé (CLAUDE.md 4. invariáns).

Szöveges csatornán mindez a képernyőn marad. Hangon elveszik, és a
vásárlónak rá kell kérdeznie.

**Miért nem a „mondjuk el mindent, csak tömörebben" út.** Az pontosan
az a hiba, amit a barge-in mér: a vásárló belevág, az ASR a saját
hangunkat is hallja, és a forduló összeomlik. A hosszú válasz nem
lassabb — hanem törékenyebb.

## Miért így, és nem utófeldolgozással

Kézenfekvő lett volna egyetlen „szöveg → beszélhető szöveg" függvény, a
meglévő mondatokra ráeresztve. Ezt **nem** tettük, mert:

- egy két kérdést tartalmazó mondatból nem lehet automatikusan egy
  kérdést csinálni — a MEGFOGALMAZÁS emberi döntés;
- a felületre hivatkozó mondat („a másik fülön") hangon nem javítható,
  csak újraírható;
- az időpont-felsorolás nem formázási kérdés: azt kell eldönteni, MELYIK
  kettő hangzik el.

A kapu ettől még kell — de hálónak, nem fő útnak.

## Mérés

A formai szabályokat teszt őrzi, a TELJES sablonkészletre
(`tests/egyseg/test_beszelheto.py`): egyetlen beszélhető mondat sem
tartalmazhat számjegyet, kötőjelet, zárójelet vagy felsorolásjelet, és
fordulónként legfeljebb két mondat, egy kérdés mehet ki.

A fej nélküli végigjátszás mindkét módban végigmegy
(`python feladat.py vegigjatszas --mod mindketto`). A 2026-08-26-i
futáson: **141 rendszer-mondat, 0 formai sértés**, és a két mód a
92-92 fordulóból **egyetlen** eseten döntött másképp — azon, ahol a
modell amúgy is ingadozik (`docs/ALLAPOT.md`, D szakasz).

## Kiváltó feltétel

Bármelyik újranyitja:

- **A TTS bekötése.** Ha a kiválasztott hangmotor maga is helyesen
  mondja ki a számokat és a dátumokat, a `szamok.py` egy része
  fölöslegessé válhat — de csak MÉRÉS után szabad kivenni, mert a hiba
  némán történik.
- **Mért barge-in arány** (M5 dev-mód metrika): ha a két mondat is sok,
  a korlát szigorodik; ha kevés, tágulhat. Ma nincs mérésünk, a két
  mondat tapasztalati szám.
- **Egy olyan eset, ahol az „utolsó kérdés marad" szabály rossz
  kérdést tart meg** valós beszélgetésben. Akkor a szabály helyett
  az orchestrator-nak kell megmondania, melyik kérdés a fontos.

## Váltás költsége

A mód kapcsolóból jön (`ui/vasarlo.py`, `--mod`), a szabályok egy
modulban vannak (`assistant/valasz/beszelheto.py`), a felülíró
mondatok egy szótárban (`sablonok.py::beszelheto`). A szöveges út
viselkedése egyetlen karakterrel sem változott — ezt regressziós teszt
rögzíti.

## Ellenőrzés

```
python -m pytest tests/egyseg/test_beszelheto.py
python feladat.py vegigjatszas --mod mindketto
python -m ui.vasarlo            # a szöveges fülön: Kimenet → beszélhető
```

Az utolsó a legfontosabb: **olvasd fel hangosan**. Amit a teszt nem tud
megmondani — hogy egy szuszra kimondható-e, hogy a megmaradt kérdés a
helyes kérdés-e, és hogy a betűzött kód leírható-e hallás után — az
emberi próba (`docs/TESZTELES.md`).

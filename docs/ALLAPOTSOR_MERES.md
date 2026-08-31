# Az állapotsor mérése — és miért nem a golden seten

**Dátum:** 2026-09-01 · **Modell:** `qwen3.5:9b`, `num_ctx=8192`, v1
prompt, 4 fordulós ablak · **Út:** `python feladat.py vegigjatszas` (a
VALÓDI felület, fej nélkül)

## Miért nem a golden set méri ezt

A golden mérési út (`tests/golden/futtato.py::ertelmezo_hivo`) az
ÉRTELMEZŐT hívja, nem az orchestratort: nincs session, nincsenek
felajánlott jelöltek, tehát **állapot sincs**. Egy kitalált állapotsor a
mérésben pontosan az a fajta hamisítás lenne, amit az ADR-019 óta
kerülünk (ott a rendszer-válaszokat nem találjuk ki).

Ezért az állapotsor hatását ott mérjük, ahol valódi: a fej nélküli
végigjátszásban, `APRAJAFALVA_ALLAPOT_SOR=be|ki` kapcsolóval.

## A próba: hivatkozás a felajánlott listára, minta NÉLKÜL

Négy mondat, amit a determinisztikus rövidzár (`assistant/sorszam.py`)
SZÁNDÉKOSAN nem ismer fel — nincs bennük sorszó, vagy nem a kötött
szerkezetben. Mindegyik előtt ugyanaz a keresés fut le, tehát mindegyik
három felajánlott időpontra hivatkozik.

A siker mércéje: a forduló **megerősítés-kérésbe** fut-e (a rendszer
értette, hogy a listából választottak), vagy új keresést indít.

| mondat | állapotsor BE | állapotsor KI |
|---|---|---|
| „az a fél kilences jó lesz" | `jelolt_valasztas` ✔ | `jelolt_valasztas` ✔ |
| „a középső legyen" | `jelolt_valasztas` ✔ | `jelolt_valasztas` ✔ |
| „a legkorábbi megfelel" | `jelolt_valasztas` ✔ | `legkozelebbi_idopont` ✘ |
| „inkább a késeibb" | `szabad_idopontok` ✘ | `szabad_idopontok` ✘ |
| **összesen** | **3/4** | **2/4** |

**A determinisztikus alapvonal (modell nélkül): 0/4.** A szabály-alapú
réteg egyiket sem ismeri fel — nem is tudja: ezek a mondatok nem
tartalmaznak sorszót.

## Amit ez mond, és amit nem

**1. A nagyobb hatás nem az állapotsoré, hanem a hiányzó ESZKÖZÉ.**
A mérés első köre azt mutatta meg, hogy a modellnek **nem volt mivel**
kifejezni, hogy a vásárló a listából választott: a `jelolt_valasztas`
irányítási érték nem létezett, tehát a legjobb, amit tehetett, egy újabb
keresés volt. Az eszköz bevezetése után (ADR-028) 2/4 már állapotsor
nélkül is megvan.

**2. Az állapotsor egy esetet fordított meg** — „a legkorábbi
megfelel". Állapotsor nélkül a modell ezt a `legkozelebbi_idopont`
kérdésnek olvasta („mikor tudok legkorábban?"), ami önmagában véve
védhető olvasat; az állapotsorral viszont tudta, hogy három konkrét
időpont áll a képernyőn, és azok közül a legkorábbit kérik.

**3. Négy próbából egy különbség nem bizonyíték.** Ez a mérés
irányt mutat, nem tényt állít. Az ADR-028 kiváltó feltétele ezért
kimondja: ha két egymást követő mérésen nem jobb az állapotsorral, ki
kell venni — a kapcsoló emiatt marad a kódban.

**4. A negyedik mondat mindkét felállásban elbukik.** Az „inkább a
késeibb" összehasonlító hivatkozás („a felajánlottak közül a későbbi"),
amihez a rendszernek a jelöltek IDŐRENDJÉT is értenie kellene — az
állapotsor ma csak a darabszámot mondja meg. Ez a következő lépés
természetes helye: a felajánlott időpontok bekerülhetnének az
állapotsorba is (ma csak a beszélgetés-előzményben szerepelnek,
sorszámozva).

## A többi menetre nincs hatása

A végigjátszás többi része (14 beszélgetés, gombos és írásbeli foglalási
menet) mindkét felállásban azonosan futott le: 35 forduló, 28 modell-réteg,
két sikeres foglalás, kivétel nélkül. Az állapotsor tehát **nem zavarja
meg** azokat a fordulókat, ahol nincs mire hivatkozni — ez volt a
legfőbb kockázata (hogy a modell utasításnak veszi, és mindenáron
választani akar).

## Reprodukció

```
APRAJAFALVA_LLM_MODELL=qwen3.5:9b APRAJAFALVA_ALLAPOT_SOR=be \
  python feladat.py vegigjatszas
APRAJAFALVA_LLM_MODELL=qwen3.5:9b APRAJAFALVA_ALLAPOT_SOR=ki \
  python feladat.py vegigjatszas
```

Nyers kimenetek: `spike/meres_20260901/vegigjatszas_allapotsor_{be,ki}.log`.

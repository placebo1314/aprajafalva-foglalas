# ADR-029: Hangkimenet Piperrel — és a néma elmaradás megszüntetése

- **Dátum:** 2026-09-01
- **Állapot:** elfogadott
- **Viszonya az ADR-023-hoz:** **kiegészíti.** A beszélhető kimeneti mód
  (mit mondjunk) marad; ez a döntés arról szól, hogy elhangzik-e.

## Kontextus

A beszélhető mód 2026-08-26 óta létezik: egész mondatok, kimondott
számok, fordulónként két mondat és egy kérdés. Csakhogy **TTS soha nem
volt bekötve** — a mód a SZÖVEGET formázta felolvasásra, hangot senki
nem adott ki. A `docs/roadmap.md` M6 szakasza ezt le is írja („az ASR, a
TTS … konfiguráció, nem építés"), a FELÜLETEN viszont ez sehol nem
látszott: aki átkapcsolt beszélhető módra, csendet kapott.

**A csend és a „nincs telepítve" ugyanúgy néz ki.** Ez ugyanaz a
hibaosztály, mint a tartalékágon futó kézi próba (ADR-027 köre): a
rendszer működik, csak nem azt csinálja, amit a használója hisz.

## Döntés

**Van hangkimenet, és ha nincs, azt a rendszer KIMONDJA.**

- `assistant/hang.py` — Piper TTS mögé egy vékony réteg: megkeresi a
  Pipert (önálló program VAGY `piper-tts` Python-csomag), a magyar
  hangmodellt (`hu_HU-anna-medium` és társai) és a lejátszót
  (Windowson `winsound`, máshol `aplay`/`afplay`/`paplay`).
- **Három hiány, három teendő** (`HangAllapot.hianyok`): nincs Piper /
  nincs magyar hang / nincs lejátszó. Egy összevont „nem működik"
  üzenet abban a pillanatban lenne udvarias, amikor haszontalan.
- `python feladat.py hangproba` — egyetlen mondatot szintetizál és
  lejátszik; ha nem megy, kiírja, mi hiányzik és mit kell beírni.
- **A felület a kapcsoló mellett kiírja a hang állapotát** — akkor is,
  ha minden megvan („Felolvasás: hu_HU-anna-medium"), mert akkor a
  csendnek MÁS oka van.
- Beszélhető módban a válasz **külön szálon** hangzik el; a lejátszás
  blokkol, az eseményhurkon a felület a mondat végéig megfagyna.

**A Piper NEM függősége a projektnek.** Nincs a `pyproject.toml`-ban, és
ez a modul semmit nem tölt le magától: a hangmodell 60-100 MB, azt a
felhasználó tölti le, tudatosan.

## A mérés

Ezen a gépen (Windows 11, Python 3.14) végigmérve:

| lépés | eredmény |
|---|---|
| diagnózis Piper NÉLKÜL | `nincs_piper`, `nincs_hang` — a lejátszó megvan |
| `pip install piper-tts` után | „Piper: python -m piper", `nincs_hang` marad |
| a hang letöltése után (`python -m piper.download_voices hu_HU-anna-medium`) | „Minden megvan" |
| szintézis | 204 kB WAV, 4,73 s, 22050 Hz, mono |
| a WAV nem néma | csúcsamplitúdó 32767 |
| lejátszás | lefutott (`winsound`) |

A diagnózis mindhárom állapotban helyesen mondta meg, mi hiányzik — ez
a fontosabbik fele: a hang megléte a gépé, a megmondás a rendszeré.

## Miért Piper

- **Lokálisan fut**, hálózat nélkül — ugyanaz az elv, mint az
  Ollamánál (a projekt egésze offline működik).
- **Van magyar hangja**, MIT licenc alatt, letölthető modellként.
- **Cserélhető**: az `assistant/hang.py` egy szintetizál+lejátszik
  párost ad, a hívók (`ui/vasarlo.py`, `tools/hangproba.py`) nem tudják,
  mi van mögötte.

## Amit feladunk

- **A telepítés egyszerűségét.** Két külön lépés kell (csomag + hang),
  és ez a `hangproba` kimenetében is látszik. Cserébe nem viszünk be egy
  100 MB-os bináris függőséget a repóba.
- **A hang minőségének megválasztását.** A `hu_HU-anna-medium` az első a
  preferencia-sorrendben; nem hasonlítottuk össze a másik két magyar
  hanggal. Erre ma nincs mérési módszerünk (a hangminőség nem
  golden-set-elhető), és a találgatás rosszabb lenne, mint a
  dokumentált önkény.
- **A streaming felolvasást.** Ma a teljes mondat szintetizálódik,
  aztán szólal meg — egy valódi hangcsatornán ez a késleltetés sok
  lenne. A barge-in és a turn-detection továbbra sincs meg.

## Kiváltó feltétel

- a szintézis+lejátszás késleltetése a fordulónkénti válaszidő
  **20%-a fölé** kerül (ma a modellhívás 3,7 s, a szintézis ~1 s alatti
  volt egy 4,7 s-os mondatra) — ekkor streaming kell, nem fájlba írás;
- megjelenik olyan magyar hang, ami MÉRHETŐEN érthetőbb (pl.
  felolvasott foglalási kódok visszahallgatásos tesztjén), és a licence
  megengedő;
- a hangcsatorna élesedik: ekkor a Piper-fájl-alapú út nem elég,
  mert a barge-inhez darabolható folyam kell.

## Váltás mire

**Streaming TTS** (Piper `--output-raw` folyammal vagy más motor), a
lejátszást a felülettől független hangszálra bízva.

## Váltás költsége

Közepes: a felület oldalán a szál-kezelés megmarad, de a
`szintetizal()`/`lejatszik()` pár helyére folyam-kezelés kerül, és a
megszakíthatóság (barge-in) új fogalom a rendszerben.

## Ellenőrzés

```
python feladat.py hangproba                 # egy mondat, végig
python feladat.py hangproba --csak-diagnozis
python -m pytest tests/egyseg/test_hang.py  # a diagnózis, hang nélkül
```

A tesztek SOSEM szólalnak meg és nem telepítenek semmit: a diagnózist
mérik, nem a hangot.

# Újrahasznosítható komponensek

*Ne írjuk meg azt, ami már létezik — de tudjuk, milyen licenc alatt.*

Minden sor mellett szerepel a licenc. A licenc nem utólagos szempont: ha a
projekt valaha fizetőssé válna, a nem-kereskedelmi komponensek mind cserére
szorulnak. Ezért van modul mögé rejtve mindegyik.

---

## Magyar nyelvi réteg

### hun-date-parser — **a legfontosabb találat**

`pip install hun-date-parser` · MIT licenc · szegedai

Ez pontosan a dátumértelmező modulunk, készen. <cite index="20-1">Magyar mondatokból nyer ki dátumintervallumokat, és datetime objektumokat alakít vissza magyar szöveggé.</cite>

```python
from hun_date_parser import text2datetime
from datetime import datetime

text2datetime('találkozzunk jövő kedd délután!', now=datetime(2020, 12, 27))
# [{'start_date': datetime(2020, 12, 29, 12, 0),
#   'end_date':   datetime(2020, 12, 29, 17, 59, 59)}]
```

Két dolog teszi kifejezetten a mi feladatunkra szabottá:

- **Intervallumot ad vissza, nem pontot.** A „délután" nálunk is ablak, nem
  időpont — pont ez kell a keresésnek.
- <cite index="24-1">A `now` paraméterrel tetszőleges időponthoz képest oldja fel a relatív dátumokat</cite>, ami a golden set fagyasztott idejéhez elengedhetetlen.

<cite index="20-1">Az ellenkező irány is megvan: datetime → magyar szöveg</cite>, több változatban („múlt héten vasárnap", „2020 december 20", „este fél 7 után 4 perccel"). Ez a **válaszsablonoknak** ajándék: a rendszer természetesen tud időpontot mondani, LLM nélkül.

Korlát, amit ismerni kell: <cite index="19-1">egy összehasonlító elemzés szerint a könyvtár a magyar dátumkifejezéseknek viszonylag szűk körét kezeli</cite> — de a mi tartományunk („holnap", „jövő kedd", „péntek délelőtt") pont a jól lefedett rész. A golden set fogja megmutatni, hol szorul kiegészítésre.

**Döntés:** ez a `asszisztens/datum/` alapja. Köré vékony saját réteg kerül a
hiányzó esetekre és a validálásra.

### HuSpaCy

`pip install huspacy` · <cite index="21-1">Apache 2.0 a könyvtárra, a betanított modellek CC BY-SA 4.0 alatt</cite> · SzegedAI

Ipari erősségű magyar NLP eszköztár. Nálunk **nem az értelmezéshez** kell,
hanem:

- **redaktáláshoz** — névfelismerés (NER) a trace-ekben
- **szinonimakezeléshez** — lemmatizálás a szolgáltatásnevekhez („petárdát",
  „petárdához" → „petárda")

A modellek eltérő licence miatt a `LICENCEK.md`-ben külön sorban szerepelnek.

### hundate-core

MIT · COREtxt

Alternatív magyar dátumértelmező, szélesebb kifejezéskörre törekszik. Ha a
hun-date-parser a golden seten hiányosnak bizonyul, ez a második jelölt.
Egyelőre nem építünk rá.

---

## Kötött dekódolás

Ez teszi lehetetlenné a hibás JSON-t — nem valószínűtlenné, hanem
lehetetlenné. <cite index="26-1">A kényszer generálás közben érvényesül, így a kimenet garantáltan érvényes: nincs parse-hiba, nincs újrapróbálkozás, nincs tartalék parser.</cite>

| Eszköz | Mikor | Licenc |
|---|---|---|
| **llama.cpp GBNF** | lokális GGUF modellel — a mi esetünk | MIT |
| **XGrammar** | ha később vLLM-re váltunk | Apache 2.0 |
| Outlines / Guidance | Transformers-alapú kísérletezéshez | Apache 2.0 |

<cite index="31-1">llama.cpp-nél a GBNF nyelvtan JSON Schema → GBNF automatikus konverzióval használható, és ez a helyes választás lokális futtatásnál.</cite> Vagyis az eszközsémáinkból közvetlenül lesz nyelvtan, kézi munka nélkül.

Ha valaha vLLM-re váltanánk: <cite index="25-1">az XGrammar a vLLM, SGLang és TensorRT-LLM alapértelmezett háttere, tokenenként 40 mikroszekundum alatti késleltetéssel</cite> — a séma változatlan marad, csak a háttér cserélődik.

**Fontos figyelmeztetés a tervezéshez:** <cite index="31-1">a formai és a tartalmi helyesség független probléma. A kötött dekódolás az elsőt oldja meg; a másodikat prompt-tervezés és kimenet-szintű validálás.</cite> Vagyis a séma garantálja, hogy JSON jön — azt nem, hogy jó dátummal. Ezért van bizalmi küszöb és visszakérdezés.

---

## Modellek

Részletesen a `docs/LICENCEK.md`-ben. Röviden:

| Modell | Licenc | Megjegyzés |
|---|---|---|
| Racka-4B (ELTE) | **CC-BY-NC-SA-4.0, kapuzott** | magyar tokenizer, fele annyi token — de csak kutatásra |
| Qwen3-4B / 8B | Apache 2.0 | a Racka alapja, szabadon használható |
| OpenEuroLLM-Hungarian | Gemma-alapú, saját feltételek | ellenőrizni kell |
| EuroLLM, Salamandra | megengedő | gyengébb magyarul |

**Kötelező tudni:** a Whisper magyar finomhangolatai a leggyakoribb
licenccsapda — több közülük nem-kereskedelmi vagy külön engedélyhez kötött.
Hangcsatorna előtt mindegyiket egyesével kell ellenőrizni.

---

## Infrastruktúra

| Komponens | Mire | Licenc |
|---|---|---|
| SQLite | kezdeti adattár (ADR-004) | közkincs |
| PostgreSQL | a következő lépcső | PostgreSQL licenc |
| ruff | formázás, lintelés | MIT |
| pytest | tesztek | MIT |
| fastText | kapuőr intent-osztályozó | MIT |
| llama-cpp-python | modell futtatás | MIT |

**Migrációkhoz:** szándékosan nem használunk keretrendszert. Sorszámozott
`.sql` fájlok up/down szakasszal, saját futtatóval — kb. 100 sor. Egy ORM
migrációs rétege itt több kockázatot hozna (rejtett SQLite-specifikus
viselkedés), mint amennyi munkát megspórol.

**ORM sincs.** A repository réteg kézzel írt SQL-t tartalmaz. Ez így
átlátható, és a Postgres-váltás egyetlen könyvtár átolvasása.

---

## Hangcsatorna (M6)

| Komponens | Mire | Licenc |
|---|---|---|
| LiveKit Agents | WebRTC + SIP, böngésző és telefon egy ügynökkel | Apache 2.0 |
| Pipecat | hang-első pipeline, jobb turn-detection | BSD |
| Whisper finomhangolatok | magyar ASR | **egyesével ellenőrizni** |
| F5-TTS magyar | beszédszintézis | ellenőrizni |
| Profivox (BME SmartLab) | szűk tématerületen kiváló minőség | ellenőrizni |

**A négyből egyik sincs bekötve — és ez szándékos** (`docs/roadmap.md`,
M6: „configure, do not build"). Ami 2026-08-26-ig elkészült, az a hang
két SZÖVEGOLDALI fele, mert az kész van akkor is, ha a hangkeretrendszer
választása még odébb van:

- **beszélhető kimeneti mód** (`assistant/valasz/beszelheto.py`) — a TTS
  BEMENETE, felolvasható alakban;
- **ASR-hibatűrés mérése** (`tests/golden/robusztus.yaml` 13. szakasz) —
  a Whisper ismert magyar hibaosztályai szövegként előállítva.

A sorrend nem véletlen: mindkettő megmondja, MIT várunk majd a
komponensektől, mielőtt választanánk közülük.

---

## Amit szándékosan magunk írunk

- **A foglalási mag.** Nincs olyan kész ütemező, ami a mi
  műszak-modellünkkel és a mozgatható szünettel dolgozna. A meglévő
  foglaltrendszerek (Cal.com és társai) más domainre gondolkodnak.
- **Az ajánlatpontozó.** Ez a mi üzleti logikánk.
- **Az orchestrator állapotgép.** Egy általános agent-keretrendszer itt
  többet ártana: a lényeg, hogy determinisztikus és átlátható legyen.
- **A redaktáló réteg.** A magyar sajátosságok és a helyi azonosítóformátum
  miatt saját szabályok kellenek — HuSpaCy NER-rel kiegészítve.
- **A számok, dátumok és órák KIMONDOTT alakja**
  (`assistant/valasz/szamok.py`). Elvben ez a TTS dolga volna, és van rá
  kész könyvtár is — csakhogy a magyar TTS-ek pontosan ezen a ponton
  szoktak elesni („nulla nyolc kettőspont tizenöt"), és a hiba NÉMÁN
  történik, mert a szöveg helyesnek látszik. Ha mi mondjuk ki a
  számokat, a hiba szövegben látszik, tehát tesztelhető — hang nélkül,
  ma (`tests/egyseg/test_beszelheto.py`). A tábla kicsi és zárt: a
  0-3999 tartomány, 31 nap, 12 hónap, 26 betűnév.

---

## Karbantartás

Ez a lista a `docs/LICENCEK.md`-del együtt él. Új függőség felvételekor
mindkettőbe kerüljön be, a **letöltés dátumával és linkkel** — a licencek
változnak, és utólag nehéz rekonstruálni, mi volt érvényben.

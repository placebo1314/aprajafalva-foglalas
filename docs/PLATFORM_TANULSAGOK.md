# Tanulságok: Cal.com és Vapi

*Mit tanulhatunk a fizetős platformoktól — a saját terveink szemüvegén át.*

A cél nem másolás, hanem annak igazolása, hol állunk jól, és mely konkrét
technikák emelhetők át lokálisan. Két rendszert néztünk: a Cal.com nyílt
forrású ütemezőt (a foglalási oldal) és a Vapi hang-agent platformot (a
beszélgetés oldal).

---

## 1. Amit a Cal.com visszaigazol

**A slot-zárolás megerősítés előtt — ez a mi hold-fogalmunk.** A Cal.com API-ja
külön `reserve` / `release` műveletet ad a slotokra, amit a foglalási felület
használ, hogy lezárja a slotot a megerősítés előtt. Pontosan a `hold`
entitásunk, TTL-lel. Nem melléktermék tehát, hanem iparági alapminta.

**A dupla foglalás valódi, visszatérő veszély.** A Cal.com 6.4-es változata
külön javította azt a hibát, amikor két ember egyszerre erősítette meg ugyanazt
a függő foglalást, és dupla foglalás lett belőle. Egy évek óta fejlesztett,
éles rendszernél is előfordult — ez igazolja, miért tettük a parciális UNIQUE
indexet a mag legvédettebb pontjává, és miért van rá szálas konkurencia-teszt.

**Buffer, minimum notice, napi limit — a mi snapshot-paramétereink.** A Cal.com
availability-modellje pontosan azokat a mezőket kezeli, amiket a műszakba
befagyasztunk: puffer a foglalás után, minimális előjegyzési idő, napi/heti
darabszám-korlát. A modellünk tehát nem hiányos — ugyanazokat a fogalmakat
fedi, csak műszak-központú elrendezésben.

**Webhookok = a mi eseménykibocsátásunk.** A Cal.com `BOOKING_CREATED`,
`BOOKING_RESCHEDULED`, `BOOKING_CANCELLED` eseményeket publikál, amikre külső
rendszerek iratkoznak fel. Ez az `esemenyek` táblánk és a rá épülő értesítés,
statisztika, várólista — ugyanaz az architektúra, más néven. Megerősíti, hogy
jó helyre tettük (M0-ba).

**A reschedule elsőrendű művelet, nem lemondás + új.** A Cal.com külön
`reschedule` végpontot ad. Ez az `foglalas_athelyezes` atomi műveletünk —
és a tény, hogy egy érett rendszer sem oldja meg lemondás+újrafoglalással,
igazolja, hogy jól döntöttünk.

### Amit a Cal.com-tól átveszünk

**Prefetch + helyi szűrés (a foglalási felületre, M5+).** Egy közösségi
Cal.com-komponens a hónap slotjait előre betölti, amikor a naptár a képernyőre
kerül, és a napváltáskor a gyorsítótárból szűr, nem hív újra. A mi
tablet-felületünkre pont illik: a bolt egy heti slotja elfér a memóriában, a
böngészés nulla hálózati kérés. Ott, ahol a hálózat lassú lehet, ez sokat ér.

**A `szabad sáv` melletti napi limit.** A Cal.com „max N booking per day"
funkciója egyszerű és a törpöknél is hasznos lehet — de nálunk ez már részben
megvan a műszak kapacitásában. Nem sürgős, de érdemes jelölni: a
`muszak.napi_limit` egy jövőbeli, olcsó mező.

### Amit tudatosan NEM veszünk át

A Cal.com Next.js + Prisma + PostgreSQL + Redis stacken fut, naptár-szinkronnal
(Google, Outlook). Ez a mi kontextusunkban túlméretezett: nincs külső naptár,
nincs OAuth, nincs több ezer szervezet. A `docs/blueprint.md` menekülőút-
doktrínája szerint ezek a mi ADR-jeink kiváltó feltételei mögött vannak.

---

## 2. Amit a Vapi tanít a hangcsatornáról (M6)

A Vapi kutatása a legértékesebb, mert **három korábbi döntésünket számszerűen
igazolja**, és ad pár konkrét beállítást.

**A töltelékmondat bevett technika, és sablonból jön.** A Vapi „filler phrase"
mintája: amikor egy eszközhívás lassú, a rendszer azonnal mond egy rövid
sablonmondatot („hadd nézzem meg"), és közben fut a háttérművelet. Pontosan az,
amiben megállapodtunk. Megerősíti azt is, hogy **a töltelék sablon, nem
modell** — a generálás maga késleltetne.

**A két-modelles „gyors + okos" mintának ára van.** A kutatási irodalom
(ConvFill, VoiceAgentRAG) leírja a mintát, ahol egy gyors modell tölteléket
mond, egy lassabb, okosabb pedig javítja — de kimondják a veszélyt is: ha a
gyors modell rosszat mond, és a lassú javítja, az **ismételt korrekció rombolja
a felhasználó bizalmát**. Ez pontosan az az érv, amiért elvetettük a prompt-
javító modellt a válaszútvonalon. A helyes minta: a töltelék soha ne mondjon
tényt, csak folyamatot jelezzen — így nincs mit javítani.

**A barge-in a keretrendszer dolga, nem a miénk.** Egy éles gyakorlati útmutató
egyértelmű: a legtöbb csapatnak a helyes döntés a VAD és a turn-detection
*konfigurálása*, nem az újraírása — „configure, do not build". A közbevágás-
kezelés a LiveKit/Pipecat rétegben van, milliónyi valós híváson tanított
modellel. A mi felelősségünk csak annyi: félbeszakításkor a szándékindexben
összegyűlt adat ne vesszen el. Ez megerősíti, amit a blueprint 16. kockázati
sorába írtunk.

**A visszakérdezés vs. háttércsatorna megkülönböztetése.** A Vapi külön kezeli,
amikor a felhasználó tényleg félbeszakít, és amikor csak „ühüm", „igen"
hangokkal jelzi, hogy figyel. Idős törpöknél ez fontos lesz: a csend nem jelenti
a mondat végét, és az „ühüm" nem közbevágás. A turn-detection türelmi ideje
(`waitSeconds`) beállítható — nálunk ez inkább hosszabb legyen, mint a Vapi
sales-alapértelmezései.

### Konkrét számok, amiket referenciának veszünk

| Mérőszám | Vapi/iparági érték | A mi vonatkozásunk |
|---|---|---|
| Voice-to-voice cél | 500–700 ms | a mi felfüggesztett hang-SLO-nk sávja |
| Barge-in arány (beszélgetős) | 5–15% | e fölött a válaszunk túl hosszú |
| Barge-in arány (sablonos) | 1–3% | a sablonos nyugtázás előnye számokban |
| Turn-detection késés | 300–500 ms | idős beszédnél inkább feljebb |

**A barge-in arány mint diagnosztika.** Ez új és hasznos: ha a rendszert sokan
szakítják félbe, az azt jelzi, hogy **túl hosszan beszél**. Ezt érdemes majd a
dev mód metrikái közé venni — olcsó jelzés arról, hogy a válaszok túl bőbeszédűek.

**A prompt hossza latencia.** A Vapi útmutató szerint minden szó a rendszer-
promptban időbe kerül, és a ritkán használt instrukciókat érdemes feltételes
ágakba tenni. Ez a mi „szűk értelmező" elvünket erősíti: minél kisebb a modell
feladata, annál gyorsabb.

---

## 3. Kaszkád vs. speech-to-speech — architekturális megerősítés

Egy 2026-os elemzés szerint a **kaszkád architektúra** (külön STT → LLM → TTS)
marad az uralkodó 2026-ban, a rugalmasság, a megfigyelhetőség és a költség
miatt — a beszéd-a-beszédhez (egyetlen multimodális modell) pedig „provider
lock-in" és nulla köztes szöveg jár, amit nem lehet naplózni és pontozni.

Ez fontos nekünk: a mi tervünk (külön ASR, LLM-értelmező, TTS, mind cserélhető)
**a kaszkád minta**, és pont a megfigyelhetőség miatt választottuk — a redaktált
trace-ek a köztes szövegből élnek. A tanulság: „tartsd a modult annyira
cserélhetőnek, hogy a váltás konfiguráció legyen, ne újraírás". Ez szó szerint
a menekülőút-doktrínánk.

---

## 4. Összefoglaló: hol állunk a fizetős szinthez képest

**Amiben egyenrangúak vagyunk (vagy jobbak lokálisan):**
- konkurencia-biztos foglalás (a mi UNIQUE indexünk + tesztek)
- hold, reschedule, események — mind megvan
- adatvédelem: a mi lokális, redaktált, hash-elt modellünk *erősebb*, mint egy
  felhős szolgáltatóé, mert az adat el sem hagyja a gépet

**Amiben a fizetős platformok előrébb tartanak:**
- a hangpipeline érettsége (barge-in, turn-detection) — de ezt *konfiguráljuk*,
  nem építjük
- a nyelvi modell nyersereje — de nálunk a szűk feladat + finomhangolás a válasz
- a kész integrációk (naptár, fizetés) — amikre nincs is szükségünk

**A stratégiai tanulság:** a fizetős platformok nagy része olyan problémákat old
meg, amelyek nekünk nincsenek (több ezer bérlő, külső naptárak, globális
skálázás). Amire tényleg szükségünk van — megbízható foglalás, természetes
magyar párbeszéd, adatvédelem —, azt lokálisan is elérhetjük. A különbség nem
a képességben van, hanem az érettségben, és azt a dev mód hurka hozza be
hónapról hónapra.

---

## 5. Konkrét teendők, amiket ez a kutatás a roadmapre tesz

Egyik sem sürgős, mind jelölésre kerül a megfelelő mérföldkőnél:

- **M4 (asszisztens):** a rendszerprompt legyen a lehető legrövidebb; a ritka
  instrukciók feltételes ágba. A töltelékmondat sablonkészlete a válaszmodul
  része.
- **M5 (dev mód):** a barge-in arány és a válaszhossz kerüljön a metrikák közé.
- **M5 (felület):** prefetch + helyi szűrés a tablet-böngészéshez.
- **M6 (hang):** a turn-detection türelmi ideje idős beszédre hangolva;
  „configure, do not build" a barge-inra; háttércsatorna („ühüm") elkülönítése a
  valódi közbevágástól.
- **Jövőbeli olcsó mező:** `muszak.napi_limit`, ha a boltok kérik.

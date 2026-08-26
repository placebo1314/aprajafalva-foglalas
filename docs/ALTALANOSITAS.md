# Általánosítás — mi javul elvileg, és mi marad ismert korlát

Ez a dokumentum a robusztussági kör (2026-08-23) melléktermékéből lett
önálló: minden mérés, ami bukást talál, két javítás közül választ.

- **Strukturális javítás** — a HIBAOSZTÁLYT szünteti meg. Attól
  ismerhető fel, hogy a javítás után egy olyan bemenet is helyesen
  fut, amit soha nem láttunk.
- **Ráigazítás** — az EGYETLEN mondatot javítja meg, ami éppen
  megbukott. A mérés zöld lesz tőle, a rendszer nem lesz jobb.

**A projekt szabálya: ráigazítást nem csinálunk.** Ha egy bukás
javítása egyetlen mondatra igazítás lenne, a bukás ide kerül, ismert
korlátként — kimondva, hogy mi nem működik, és miért nem javítjuk
most. Ez a `docs/AKADALYOK.md`-től abban különbözik, hogy az a
FEJLESZTÉS akadályait gyűjti; ez a RENDSZER képességének határait.

---

## 1. Amit ez a kör strukturálisan javított

Három javítás, mindhárom hibaosztályt szüntetett meg, nem esetet. **A
2026-08-26-i kör kettővel bővítette a listát** (1.4 és 1.5) — mindkettő
a MÉRÉST javította, nem a rendszert, és épp ezért tanulságos: egy vak
mérőszám rosszabb, mint a hiányzó mérőszám, mert biztonságérzetet ad.

### 1.1 Múltbeli időkifejezésből nem lesz keresési ablak

**A bukás:** a robusztussági halmaz `hosszu-01` esete tartalmazza, hogy
*„a szomszédom … így csinálta a múlt héten"*. Ebből a rendszer keresési
ablakot csinált a folyó hétre. A vásárló egy szót sem mondott arról,
hogy mikor akar menni.

**Miért nem ráigazítás a javítás:** nem a „múlt héten" kifejezést
tiltottuk le, hanem a MÚLTRA MUTATÓ időkifejezéseket vesszük ki a
szövegből a dátumfeloldás előtt
(`rule_based._mult_ido_kifejezesek_nelkul`). Ugyanez a javítás fogja a
„múlt kedden", „előző héten", „tavalyi alkalommal" alakokat is, amiket
soha nem mértünk. És a vegyes mondat is helyesen fut: *„múlt kedden
voltam, de szerdán mennék"* → a szerda feloldódik.

**Amit ez NEM old meg:** a `nyelvi_alap.yaml::egyszerusitett-03`
(„Múltkor is voltam") esetet a rendszer korábban is helyesen kezelte,
de VÉLETLENÜL — ott nem volt hét- vagy napnév, amibe a parser
belekapaszkodhatott volna. A védelem tehát ott sem elvi volt; most
lett azzá.

### 1.2 A hatókör-döntés determinisztikus (ADR-020)

**A bukás:** a `forditott` alapmérésen HÁROM hatókörön kívüli válasz.
A „Mennyibe kerül a nagy petárda?" kérdésre — és mindkét prompt
injection kísérletre — a rendszer `bolt_info`-t hívott, vagyis
termékleírást olvasott volna fel egy ár-kérdésre.

**Miért nem ráigazítás:** nem az ár-kérdést tiltottuk le a promptban,
hanem a hatókör-döntés kikerült a modell alól egy zárt, három elemű
osztályozásba, ami a modell ELŐTT fut. Kívül eső kérésnél a modell meg
sem szólal. Az ár csak egy eset ebből; ugyanez a réteg hárítja el a
politikát, a matematikát, a személyes tanácsot és a kreatív kérést is.

### 1.3 Redaktálás tárolás előtt

**A bukás:** a próba-napló a vásárló mondatát NYERSEN írta lemezre. Egy
kéretlenül bediktált telefonszám azonnal invariánssértés (CLAUDE.md 2.).

**Miért nem ráigazítás:** nem a naplóból tiltottuk ki a
telefonszám-szerű sztringeket, hanem a `privacy/redakcio` a
zárt alakú személyes adatok (telefon, TAJ, adóazonosító, igazolvány,
e-mail, bankkártya) osztályát ismeri fel, és minden lemezre írt mezőn
lefut.

### 1.4 A mérés fordulónkénti adatai nem veszhetnek el (2026-08-26)

**A bukás:** a golden futtató modell-útjain (`kaszkad`, `forditott`) a
hívó egy closure volt, ami a fordulónkénti kimeneteket nem emelte át
magára. Az ismétlés-stabilitás vizsgálata ezért **némán kimaradt**: a
jelentésben 0 állt, nem azért, mert stabil volt, hanem mert nem mértük.

**Miért nem ráigazítás:** a hiányzó két sor pótlása ráigazítás lett
volna — a következő burkoló ugyanígy felejtene. Helyette a closure-ből
`BurkoltHivo` osztály lett, ami az átvezetést MAGA végzi, és amit
egységteszt fog (`test_robusztus_halmaz.py`). A hibaosztály: „a mérés
egy köztes rétegen csendben elveszíti az adatot".

### 1.5 A stabilitás definíciója egy helyen él (2026-08-26)

**A bukás:** a stabilitás-vizsgálat a TELJES kimenet-dictet
hasonlította össze, a `bizonyossag` mezővel együtt — az pedig logprob,
tehát a negyedik tizedesjegyen ingadozik. Öt AZONOS eszközhívás
„négyféle kimenetnek" számított.

**Miért nem ráigazítás:** nem a `bizonyossag` mezőt zártuk ki egy
listával, hanem a futtató mostantól ugyanazt a KANONIKUS alakot
használja, amin az önkonzisztencia szavaztat
(`onkonzisztencia.eszkozhivas_kulcsa`, ADR-021: `{eszkoz,
parameterek}`). A hibaosztály: „ugyanannak a fogalomnak két
definíciója van a kódban".

---

## 2. Ismert korlátok

### 2.1 A hosszú bemenet farka — és amit a szórásról meg kellett tanulni

**Mérve** (2026-08-23, `qwen3.5:9b`, `forditott`): a robusztussági
halmaz fordulónkénti átlaga 3,62 s volt, EGYETLEN kilógó esettel — a
`hosszu-01-tobb-tema` (632 karakter, öt téma) **15,18 s**, épp az akkori
15 s-os keret felett.

**Újramérve** (2026-08-26, ugyanaz a modell, ugyanaz a mondat, közben
az értelmezőhöz nem nyúltunk): a leglassabb egyfordulós eset **5,50 s**,
a `hosszu-01` ennél is kevesebb. A p50 4,62 s, a p95 5,08 s.

**A különbség nem a kód, hanem az Ollama futásonkénti szórása.** Ebből
két dolog következik, és mindkettő fontosabb, mint maga az eset:

1. **Egyetlen futás egyetlen száma nem állítás, csak adat.** A 15,18 s
   nem volt hamis mérés — de nem is volt a rendszer tulajdonsága.
2. **Ezért lett a válaszidő-elvárás ELOSZLÁS és TENDENCIA** (ADR-022):
   p50 < 10 s, p95 < 25 s, és a két félidő mediánjának összevetése. Egy
   szám (átlag) ezt a helyzetet nem tudta kezelni: hol „tartja", hol
   „nem tartja", ugyanattól a kódtól.

**A korlát ettől korlát marad:** a hosszú, többtémájú bemenet a
leglassabb eset, és a hangcsatornán (ahol a türelem szűkebb) érezhető
lesz. **Miért nem javítjuk most:** a bemenet rövidítése (csonkolás,
összefoglalás) vagy egy kisebb modell külön architekturális döntés,
ADR-rel. A csonkolás ráadásul KOCKÁZATOS: a `hosszu-02` eset épp azt
mutatja, hogy a valódi kérés a mondat VÉGÉN is lehet, tehát a
„vágjuk le a végét" megoldás pont a lényeget dobná el.

### 2.2 A kapuőr mintalistája új témára új mintát igényel

A kapuőr (`assistant/kapuor/`) pozitív mintaillesztés — pontosan az a
technika, amit az ADR-018 a determinisztikus ÉRTELMEZŐRŐL elmarasztalt
(„minden új megfogalmazás új mintát igényel"). Ez itt tudatos, és két
okból elfogadható:

1. **Más a hibázás iránya.** Az értelmezőnél a minta hiánya rossz
   ÉRTÉST okoz; itt a minta hiánya ÁTENGEDÉST okoz, és az átengedett
   kérést a mögötte álló rétegek (zárt halmazok, kötött dekódolás, az
   ár kimeneti tiltása) még fogják.
2. **A hatókör zárt fogalom, a nyelv nem.** Új bolt vagy szolgáltatás
   ritkán születik; új megfogalmazás minden nap.

**A korlát ettől korlát marad:** egy új hatókörön kívüli TÉMA (mondjuk
jogi tanácsadás) mintát igényel, és addig átcsúszik. Ilyenkor a
mögöttes rétegek miatt a legrosszabb kimenetel egy fölösleges
visszakérdezés, nem kitalált tény — de az sem jó élmény.

### 2.3 Egy mondaton belüli ellentmondást nem oldunk fel

*„Kedden szeretnék, de nem kedden."* A robusztussági halmaz mindkét
viselkedést elfogadja (visszakérdezés vagy tág keresés), mert
egyikre sincs objektíven helyes kinyert érték.

**Miért nem javítjuk:** az ellentmondás felismerése mondattani elemzés
lenne (a tagadás hatóköre), nem mintaillesztés. Egy „ha ugyanaz a nap
kétszer szerepel, egyszer tagadva" szabály pontosan ráigazítás lenne
— a következő megfogalmazás („kedden, illetve mégse") már nem esne
bele.

**Ami MŰKÖDIK:** a feloldható ellentmondás (`ellentmondas-02`:
„délelőtt jó lenne, de csak délután érek rá") — ott a második
tagmondat erősebb, és a mérés mindkét napszakot elfogadja.

### 2.4 Egy fordulóban egy szándék

*„Foglalj le keddre és mondd le a pénteki foglalásomat."* Egy fordulóban
egy eszköz hívható (`assistant/orchestrator.py`), tehát a második
szándék némán elveszik.

**Miért nem javítjuk:** a szándék-sor (több művelet egy fordulóból,
sorban végrehajtva) az orchestrator állapotgépének bővítése —
ADR-igényes, és a foglalási invariánsokat is érinti (mi történik, ha a
sor közepén hiba van?). Egy „csak az elsőt hajtsuk végre" szabály
viszont pont attól rossz, hogy CSENDBEN veszíti el a másikat.

**Amit a mérés bizonyít:** a veszélyes fele nem történik meg — a
lemondás foglalási kód nélkül soha nem indul el (`tilos:
kitalalt_kod`), tehát a rendszer nem töröl semmit egy félreértésből.

### 2.5 Idegen nyelvű bemenetre magyar válasz megy

A `assistant/valasz/sablonok.py` egyetlen nyelvkulcsot ismer (`hu`). Egy
angol vagy német kérésre a rendszer magyarul kérdez vissza.

**Miért nem javítjuk:** a második nyelv egy új `SABLONOK["en"]`
bejegyzés — a kód nem nyelvspecifikus, tehát a MUNKA a fordítás, nem a
programozás. Amíg nincs döntés arról, hogy kiszolgálunk-e idegen
nyelvű vásárlót, a fordítás elvégzése korai.

**Ami MŰKÖDIK:** ha a kritikus adatok magyarul vannak a kevert
mondatban (`nyelv-03`: „Szeretnék egy appointmentet holnapra a
Törpillához"), a keresés elindul.

### 2.6 A névredaktálás csak a bemutatkozó szerkezetet fogja

A `privacy/redakcio` a számformátumokat (telefon, TAJ, e-mail…)
megbízhatóan felismeri, a SZEMÉLYNEVET viszont csak bemutatkozó
szerkezetben („a Marika vagyok", „a nevem Kovács János").

**Miért nem javítjuk:** nincs olyan minta, ami a „Marika" szót
megkülönböztetné bármelyik másik szótól névlista nélkül. Egy csendben
bővülő névlista a legrosszabb megoldás: soha nem lesz teljes, és
elhiteti, hogy megoldott a kérdés.

**A helyes irány (nem ebben a körben):** a névfelismerés vagy
nyelvi modellel megy (offline, a dev-naplóra, blueprint 10. „Bíró"),
vagy sehogy — és akkor a napló megőrzési ideje a védelem, nem a
redaktálás.

### 2.7 Múltbeli időpontra a keresés üres eredményt ad, magyarázat nélkül

*„Tegnapra kérnék időpontot"* → a „tegnap" tökéletesen feloldható
kifejezés, csak épp a múltba mutat. A keresés lefut, és üres listát
ad — ami nem hazugság, de nem magyarázza el, miért.

**Miért nem javítjuk itt:** a múltbeli ablak szűrése az ESZKÖZ dolga
(`assistant/tools/szabad_idopontok.py`), nem az értelmezőé — az
értelmező helyesen ismerte fel, mit mondott a vásárló. Az eszközbe
tett szűrő viszont a `most` paraméter szemantikáját érinti, amit a
felület horgonya (`ui/vasarlo.py::horgony_most`) is használ, tehát
nem egysoros változás.

### 2.8 Csoportos foglalás fogalma nincs

*„Ezer főnek foglalnék."* Egy slot = egy foglalás (CLAUDE.md 1.
invariáns). A létszám némán elvész.

**Miért nem javítjuk:** a csoportos foglalás a foglalási MAG
kiterjesztése (több slot atomi lefoglalása), nem nyelvi kérdés. Az 1.
invariánst nem sérti, de új fogalmat vezet be — ADR-igényes.

**Amit a mérés bizonyít:** nem keletkezik `letszam` paraméter — a
kötött dekódolás kizárja, tehát a rendszer nem tesz úgy, mintha
értené.

### 2.9 A determinisztikus réteg az `elengedes` rétegen 0%

Változatlan korlát az ADR-018 óta (`docs/ALLAPOT.md`). A szándék
kemény részének elvetése („és bármelyik másik boltban?") a modell
képessége; mintával reménytelen, mert a mondatban nincs olyan szó,
amit keresni lehetne.

### 2.10 A „hét eleje" szűkítés nincs modellezve

`nyelvi_alap.yaml::mintan_tul-08`. A „jövő hét eleje" a teljes jövő
hétre old fel. Tudatos v1 döntés: a szűkebb ablak megépítése külön
lépés, és amíg nincs meg, nem mérünk rá.

### 2.11 A beszélhető mód VESZTESÉGES — és ez nem hiba

A fordulónkénti két mondat és az egy kérdés (blueprint 7.,
`assistant/valasz/beszelheto.py`) **korlát, nem cél**. Ami nem fér
bele, az eldobódik:

- a harmadik és további **időpont** (marad a legkorábbi + egy
  alternatíva);
- a szolgáltatás **leírása és időtartama** (marad a név);
- minden **zárójeles megjegyzés**.

Szöveges csatornán ez az információ ott marad a képernyőn — hangon
elveszik, és a vásárlónak rá kell kérdeznie.

**Miért nem javítjuk:** a „mondjunk el mindent, csak gyorsabban"
megoldás pontosan az a hiba, amit a barge-in mér (a vásárló belevág,
és onnantól az ASR a saját hangunkat is hallja). Amit a hang nem bír
el, azt nem mondjuk ki — nem pedig sűrítve mondjuk el.

### 2.12 A beszélhető mód FORMAI szabályt őriz, nem érthetőséget

A teszt (`tests/egyseg/test_beszelheto.py`) azt méri, hogy nincs
számjegy, kötőjel, zárójel és felsorolásjel, hogy legfeljebb két mondat
és egy kérdés megy ki. Azt **nem** méri, hogy

- a megmaradt kérdés a HELYES kérdés-e (a szabály az UTOLSÓ kérdést
  tartja meg — ez heurisztika, nem tudás);
- a mondat kimondva természetes-e;
- a betűzött foglalási kód hallás után LEÍRHATÓ-e.

Ez a három emberi próba (`docs/TESZTELES.md`, „Beszélhető mód: mit néz
az ember"), és amíg nincs TTS, csak felolvasva ellenőrizhető.

### 2.13 Az admin által szerkesztett tény nem lesz mondhatóbb

A `bolt_info` értékei szerkesztett adatok (nyitvatartás, cím,
megjelenés). Beszélhető módban ezek is átmennek a kimeneti kapun, tehát
a számok kimondottá válnak — de a MONDATSZERKEZET marad, ami az
adminban van. Egy „H-P 8:00-16:00" alakból „hétfő péntek nyolc órától
tizenhat óráig" lesz: számokban helyes, magyarul csonka.

**Miért nem javítjuk:** a rövidítés-feloldás (H → hétfő, P → péntek)
egy újabb mintalista lenne, ami minden új rövidítéssel bővülne — és
közben a helyes megoldás egyszerű: az adminban kimondható szöveget kell
írni. Ez a szerkesztő felület dolga (M1), nem a válaszrétegé.

---

## 3. Amit a robusztussági mérés NEM tud megmutatni

A halmaz az ÉRTELMEZŐT méri (mondat → eszközhívás). Ezért nem látszik
benne:

- az **orchestrator** rétegei: ismétlésfigyelés, frusztráció-kiút,
  bizonyosság-kapu, rate limiting — ezeket a
  `tests/egyseg/test_orchestrator.py` és a fej nélküli végigjátszás
  hajtja meg;
- a **felület** viselkedése: gombok, jelöltek, megerősítés;
- a **valódi adatbázis** állapota: a mérés nem hív eszközt, tehát a
  „van-e szabad hely" kérdésre nem kap választ.

Egy eset, ami emiatt ALÁbecsli a rendszert: a mérés az értelmező
bizonyosság-értékét nem kapuzza, pedig élesben az orchestrator
küszöb alatt zárt kérdéssé alakítaná — ugyanaz a mérési korlát, amit a
`docs/ALLAPOT.md` a nyelvi halmazra már rögzített.

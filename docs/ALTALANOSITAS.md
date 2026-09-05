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

### 1.6 A „mindegy" ÉRTÉK lett, nem hiány (2026-08-30, ADR-024)

**A bukás:** a `null` és a „mindegy melyik" ugyanaz volt a rendszernek
— mindkettő hiányzó mező, tehát mindkettőre visszakérdezés járt. Aki
kimondta, hogy elengedi a boltot vagy a terméket, ugyanazt a kérdést
kapta vissza még egyszer.

**Miért strukturális javítás, nem eseti:** nem egy visszakérdezést
tiltottunk le, hanem HÁROM állapotot vezettünk be kettő helyett
(`katalogus.MINDEGY`): hiányzik → kérdezünk; `MINDEGY` → a vásárló
elengedte, nem kérdezünk többé, mindenben keresünk; konkrét slug →
szűkítünk. A szentinel a séma enumjának is része, tehát a modell
használhatja — a felismerése nyelvi feladat, nem kulcsszólista.

**A hibaosztály neve:** „két különböző dolog ugyanazzal az üres
értékkel". Ugyanez a minta másutt is keresendő: mindenhol, ahol egy
`None` egyszerre jelenti azt, hogy „nem tudjuk", és azt, hogy „nincs
megkötés".

**És a fordítottja is hibaosztály — ezt a végigjátszás fogta meg.** A
szentinel bevezetése után a modell a `napszak` mezőn olyan mondatokra
is `MINDEGY`-et adott, amikben egy szó sem esett időpontról (54
fordulóból 6: „Petárdázni szeretnék.", „Szundihoz mennék."). Vagyis
„nincs megadva" értelemben használta, nem „elengedtem" értelemben.

A javítás nem a prompt szigorítása lett, hanem a HATÁR kimondása: **a
szentinel ott ér valamit, ahol egy KÉRDÉST némít el.** A boltra és a
szolgáltatásra rákérdeznénk, a napszakra soha — ott tehát a három
állapot kettőre esik össze, és a kapu `barmikor`-ra normalizál. Egy
elengedés, aminek nincs elnémítandó kérdése, csak egy második név
ugyanarra az értékre — ami megint az 1.6 hibaosztálya, csak a másik
irányból.

### 1.7 A lazítás dimenziói bolton belülre kerültek (2026-08-30, ADR-024)

**A bukás:** a „nincs hely" válaszra a rendszer másik BOLTOT ajánlott.
Működött, tesztelt volt — és rossz: Aprajafalva három boltja három
különböző terméket árul, tehát aki petárdát kér, annak a boldogság-bolt
nem gyengébb találat, hanem MÁS KÉRDÉSRE adott válasz.

**A tanulság általánosítható:** egy alternatíva akkor alternatíva, ha
ugyanarra a kérésre válasz. A vesztes ág nem attól lesz kellemes, hogy
tesz valamit, hanem attól, hogy hasznosat tesz. A helyére a bolton
BELÜLI sorrend lépett (napszak → nap → később → variáns), és minden
válasz kimondja, melyik dimenzióban engedett.

### 1.8 A régi fordulók összefoglalva élnek tovább (2026-08-31, ADR-025)

**A bukás:** az előzményt a felület egyszerűen VÁGTA (utolsó 12 sor).
Ami kicsúszott, az nyomtalanul eltűnt — a legelső mondatban kimondott
bolttal együtt, pedig annak az ADR-019 szerint végig érvényben kellene
maradnia. Húsz forduló után a rendszer újra megkérdezte, melyik boltról
van szó.

**A tanulság általánosítható:** a vágás nem tömörítés. Ha egy
kontextusból ki kell dobni, akkor azt kell eldönteni, MI MARAD BELŐLE —
és a maradéknak megkülönböztethetőnek kell lennie a hiánytól (az
elengedett mező `ELENGEDVE`-ként megy át, nem konkrét értékként, nem is
üresen). Ugyanaz a három állapot, mint a MINDEGY-nél (1.6): nem tudjuk /
elengedve / tudjuk.

### 1.9 A zárt kérdésre adott választ nem a modell értelmezi (2026-08-31)

**A bukás:** a rendszer feltette a saját, zárt kérdését („biztosan
lefoglaljam ezt az időpontot?"), az „igen, foglald le" választ viszont a
szokásos értelmezési úton engedte — a modell új keresésnek olvasta, és a
folyamatban lévő megerősítés a kiválasztott időponttal együtt eltűnt. A
foglalás írásban emiatt nem volt befejezhető.

**A tanulság általánosítható, és már másodszor jön elő** (első: a
sorszámos hivatkozás, `assistant/sorszam.py`): **ha MI tettünk fel egy
zárt kérdést, a válasz zárt halmaz — azt nem értelmeztetjük.** Nem a
modell képességén múlik, hanem a szerkezeten: a rossz válasz itt nem
visszakérdezés, hanem rossz foglalás vagy elveszett állapot. Amiből
következik egy visszatérő ellenőrzési pont: **minden új, zárt kérdésnél
meg kell nézni, hogy az ÍRÁSBELI válaszát ki dolgozza fel.**

### 1.10 A prompt-változtatás mérés nélkül feltevés (2026-08-31, ADR-026)

**A bukás:** a „mért prompt-gyakorlatok" szerint átépített
rendszerprompt (megkötések elöl, kevesebb de sokfélébb példa) 14,7
ponttal ROSSZABB lett — és pontosan azokon a rétegeken, amiknek a
példáját kivettük.

**A tanulság általánosítható:** a few-shot példák nem stilisztikai
díszek, hanem az egyetlen hely, ahol egy RITKA nyelvi alak egyáltalán
megjelenik a modell előtt. Egy tájszólásos példa nem levezethető egy
köznyelviből — ezért a „kevesebb, de sokfélébb példa" elv csak ott
működik, ahol a példák TÉNYLEG ugyanazt tanítják. Ehhez tartozik egy
módszertani tanulság is: a v2 két dolgot változtatott egyszerre, és
csak egy harmadik verzió (v3 = új szerkezet + régi példák) tudta
szétválasztani, melyik ártott.

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

### 1.11 A rendszerről szóló kérdés nem foglalási kérés (2026-09-05, ADR-030)

**A bukás** (első éles próba, 7. forduló): a „csak a választ beszéled?"
mondatból KERESÉS lett — a rendszer újra felajánlotta ugyanazokat az
időpontokat egy olyan kérdésre, aminek semmi köze a foglaláshoz. Ráadásul
a már LEZÁRT foglalás állapotát (`KESZ`) is visszarántotta
`AJANLAT_VAR`-ba.

**A tanulság általánosítható:** a kapuőr eddig azt kérdezte, „a miénk-e
ez a kérés?" — és a rendszerről szóló kérdésre a válasz IGEN, csak épp
nem foglalási értelemben. Egy zárt osztályozásból hiányzó kategória nem
semlegesen viselkedik: a mondat a legközelebbi meglévő kategóriába esik,
és ott kárt okoz. **Ha egy rendszer nem tud magáról beszélni, akkor
foglalni fog helyette.**

### 1.12 Amit a vásárló ÁTAD, azt el kell venni (2026-09-05, ADR-030)

**A bukás** (első éles próba, 8. forduló): a „nekem mind jó. válasz te."
mondatra a rendszer ÚJRA felajánlotta ugyanazt a három időpontot —
visszaadta a döntést annak, aki épp lemondott róla.

**A tanulság általánosítható:** a `{eszkoz, parameterek}` szerződésben
nem volt olyan érték, ami ezt kifejezné, tehát a modell legjobb tudása
szerint sem tudott mást tenni. Ugyanaz a fajta hiány, mint a
`jelolt_valasztas`-nál (ADR-028): **a modell nem tud olyat mondani,
amire nincs szava** — és ilyenkor nem hibázik, hanem a legközelebbi
meglévő szót használja. A javítás ezért sosem prompt-fegyelem: új szó
kell a szerződésbe.

### 1.13 Aki nem ismeri a rendszert, azt a rendszer FAGGATJA (2026-09-19, ADR-032)

**A bukás** (első IDEGEN próba, négy forduló): a „helló." mondatra a
rendszer azt kérdezte, MELYIK boltba szeretne menni. A „milyenek
vannak?" kérdésre — mert az sem tartalmazott boltnevet — az
ismétlés-figyelő kiutat ajánlott, a harmadikra pedig elküldte a
vásárlót a boltba, élőben. Keresés egyetlenegyszer sem futott.

**A tanulság általánosítható:** minden rétegünk (visszakérdezés,
ismétlés-figyelő, frusztráció-figyelő) EGY közös feltevésre épült — hogy
a vásárló tudja, mit lehet nálunk kérni. A feltevés sehol nem volt
kimondva, ezért sehol nem is lehetett megcáfolni; a rétegek nem
egymástól függetlenül hibáztak, hanem együtt, ugyanazon a ponton.

Ebből két külön dolog következik:

1. **A ki nem mondott feltevés nem téveszthető el, csak öröklődik.** Aki
   megnevezte a boltot, annak minden réteg jól működött — a mérés tehát
   nem is mutathatta a hibát, mert a golden set minden esete olyan
   emberé volt, aki már tudta, mit akar. **Egy halmaz nem tudja mérni
   azt a beszédhelyzetet, amit nem tartalmaz.** Ezért lett az
   `elso_talalkozas` külön réteg, és ezért a próba SZÓ SZERINTI
   mondataiból.
2. **A kudarcot jelző mechanizmusnak tudnia kell, honnan indultunk.** Az
   ismétlés- és a frusztráció-figyelő „nem jutunk előre"-t mért, és
   igaza is volt — csak épp az „előre" nem ugyanaz annak, aki elakadt,
   és annak, aki még el sem indult. A kiút kapuja ezért állapotkérdés
   (`utolso_kereses`), nem szövegkérdés: **a feladás csak próbálkozás
   után értelmes.**

Rokon 1.11-gyel: ott a rendszerről szóló kérdésnek nem volt kategóriája,
itt a kínálatról szólónak. Mindkét esetben a hiányzó kategória nem
semlegesen viselkedett, hanem a legközelebbi meglévőbe esett — ott
keresés lett belőle, itt kiút.

### 2.9d A MINDEGY ragadóssága — MEGOLDVA (2026-09-12, ADR-031)

**A bukás** (`mindegy-07`, `elengedes-10/11`): aki elengedett egy mezőt
(„Bármelyik petárda jó"), nem tudta visszavonni („mégis inkább a nagyot
kérem").

**Két javítási kísérlet, egy megbukott.** A prompt-szabály nem
segített (2026-09-05, két futáson mérve). Ami megoldotta: egy
DETERMINISZTIKUS KAPU — ha a mondat kimond egy konkrét értéket, az
felülírja a MINDEGY-et —, plusz a méret-melléknév toldalékolt alakjai a
szabály-alapú rétegben. A megkülönböztetés fontos: az első kísérlet a
modelltől kért valamit, a második a modell UTÁN dönt.

### 2.9e A szolgáltatás átmentése — MEGOLDVA a visszautalásra (2026-09-12, ADR-031)

**A bukás** (`elengedes-05/12`): az „és csütörtökön ugyanez?" mondatnál
a bolt átjött, a szolgáltatás nem.

**Megoldva, de SZŰKEN**: csak akkor, ha a mondat NÉVMÁSSAL utal vissza
(„ugyanez", „ugyanoda"). Névmás nélkül („és csütörtökön?") továbbra sem
jön át — és ez tudatos: ott tényleg nem tudjuk, hogy a méret még
érdekli-e a vásárlót. A `elengedes-05` eset épp ezt az ellenpróbát
őrzi.

### 2.9b A MINDEGY átszivárog a szomszéd mezőre

`nyelvi_alap.yaml::mindegy-03-pult`. Mérve (2026-08-30, `qwen3.5:9b`,
három futásból három): a „mindegy, melyik pultnál, csak legyen hely
holnap a petárdásnál" mondatra a modell a `szolgaltatas_id`-t is
`MINDEGY`-re állítja, pedig a mondat a pultról beszél.

**Miért nem javítjuk determinisztikusan:** ahhoz tudni kellene, melyik
mezőre vonatkozik a „mindegy" — azaz kulcsszó-alapú mezőhozzárendelést
építenénk, pontosan azt, amit a szentinel bevezetésekor elkerültünk. A
kár korlátos (egy elmaradó pontosító kérdés), a mérés viszont látja,
tehát nem néma.

### 2.9c Két lazítási dimenzió ma nem tud megszólalni

- **`pult`**: nincs mit lazítani — a keresés ma sem szűkít pultra
  (tesztelt tény: `test_a_kereses_nem_szukit_pultra`). Ezért nem is
  szerepel a dimenziók között: egy mindig üresen visszatérő ág
  hazugság lenne.
- **`varians`**: a dimenzió megvalósult és valódi lekérdezéssel
  próbálkozik, de a mai KATALÓGUSBAN a `kis_petarda` és a
  `nagy_petarda` ugyanarra a szolgáltatás-sorra mutat, tehát a szűrés
  elhagyása ugyanazokat a slotokat adja. Amint egy boltnak két,
  ütemezésileg különböző szolgáltatása lesz, magától megszólal.

A kettő nem ugyanaz a fajta korlát, és ezt érdemes szétválasztva
tartani: az első a KÓD tulajdonsága, a második az ADATÉ.

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

## 3. A KIUTAK ANATÓMIÁJA (2026-08-30 mérés)

A kiút a rendszer beismerése, hogy nem jut előre. Ezért a SZÁMA
mérőszám — de csak akkor mond bármit, ha tudjuk, MI vezetett oda. Ez a
szakasz azt írja le, amit a fej nélküli végigjátszás naplója mutat.
Nem esetenkénti javítás: a MINTÁKAT rögzíti, a javítás máshol dől el.

### 3.1 A mérés: ugyanaz a kód, ugyanaz a 204 forduló, más ADAT

A demóadat korábban csak a Törpillába adott beosztást, tehát a másik
két boltra irányuló minden kérés üres eredményre futott. A kérdés az
volt: **a kiutak hány százaléka jött ebből?**

Az A/B ugyanazon a kódon, ugyanazzal a 15 beszélgetéssel és a teljes
robusztussági halmazzal, mindkét kimeneti módban futott — csak az
adatbázis különbözött:

| | régi adat (csak Törpilla) | új adat (mindhárom bolt) |
|---|---|---|
| ajánlat | 70 (34,3%) | **95 (46,6%)** |
| eszközhiba | 30 (14,7%) | **13 (6,4%)** |
| **kiút** | **26 (12,7%)** | **18 (8,8%)** |
| ebből emberhez irányítás | 14 | 12 |
| ismételt visszakérdezés | 7 | 6 |

**A hipotézis RÉSZBEN igazolódott.** A kiutak harmada (8 / 26) tűnt el
az adat pótlásától — nem a „nagy része". A maradék 18 nem adathiány.

**Ami eltűnt, névvel** (mind a nyolc ugyanabba a mintába esik):

| Bemenet, ami kiúthoz vezetett | régi | új |
|---|---|---|
| „talán jövő héten, még nem tudom biztosan" | 2 | 0 |
| „jövő héten, vagy 28-án tudok menni?" | 2 | 0 |
| „mégsem, inkább maradjunk a keddnél" | 2 | 0 |
| „és jövő héten péntek?" | 2 | 0 |

**A mechanizmus fontosabb, mint a szám.** Ezek a fordulók az ÚJ adaton
is üres eredményt adnak (a „jövő hét" a demóhéten kívül esik) — mégsem
lesz belőlük kiút. Azért, mert a kiutat nem az egyedi üres keresés
váltotta ki, hanem a MÁSODIK EGYFORMA üres válasz: a beszélgetés első
fordulója most már ajánlattal indul, tehát a számláló nem gyűlik fel.
Ebből következik, amit a szám önmagában nem árul el: **egy üres válasz
nem baj; kettő egymás után az.**

### 3.2 A maradék 18 kiút: mind INFORMÁCIÓ NÉLKÜLI forduló

Mind a 18 három bemenet-mintából jön (fordulónként két mód, ezért
párosak a számok):

| Minta | db | Mi történik |
|---|---|---|
| **Üres szándék ismételve** — „Mennék valamikor." ötször; „mennék" / „szeretnék menni" / „menni szeretnék" | 12 | A rendszer zárt kérdést tesz fel (melyik bolt), a vásárló nem válaszol rá, hanem újrafogalmazza ugyanazt a semmit |
| **Kimondott elakadás** — „nem értem, mit kell csinálni" négyszer | 6 | A frusztráció-figyelő tervezett útja: kiút, majd ember |

**Egyik sem párbeszédhiba.** Mindkét mintában a forduló NEM TARTALMAZ
foglalható információt: nincs benne bolt, nincs benne nap. A rendszer
egyetlen alternatívája a találgatás lenne — pontosan az, amit a
robusztussági halmaz `ismetles-01` esete TILT.

**A kiút itt nem a beszélgetés hibája, hanem a vége.** A 18-ból 12 már
emberhez irányít, ami a vásárló 8. igénye szerinti helyes kimenetel.

**A mérőszám ezért félrevezető önmagában.** A próbakorpusz
SZÁNDÉKOSAN tartalmaz ilyen eseteket (a robusztussági halmaz egész
kategóriája erről szól), tehát a kiút-arány nem csökkenthető nullára
anélkül, hogy a rendszer elkezdene tippelni. Amit érdemes figyelni: a
kiutak közül hány jött ADATHIÁNYBÓL (ma 0) és hány EGYFORMA VÁLASZ
ISMÉTLŐDÉSÉBŐL (ma 6, a többi eszkaláció).

### 3.3 Az ismételt visszakérdezés két mintája

A hat ismételt visszakérdezés (ugyanarra a mezőre kétszer) két
csoportba esik, és egyik sem hiba:

- **Idegen nyelvű bemenet** („Ich möchte einen Termin für morgen früh
  vereinbaren.") — a rendszer magyarul kérdez vissza a boltra, mert a
  mondatból a boltot nem tudja kiolvasni. Ismert korlát (2.5).
- **Sorszámos hivatkozás kontextus nélkül** („az utolsó jó lesz", „Az
  elsőt kérem.") — nincs felajánlott lista, tehát nincs mire
  hivatkozni; a visszakérdezés a helyes válasz (a robusztussági halmaz
  14. kategóriája pontosan ezt írja elő).

**Amit ez a kettő közösen mutat:** az ismételt visszakérdezés akkor
keletkezik, amikor a vásárló mondata ÉRTELMES, de a rendszer számára
használhatatlan. Ez más, mint az üres forduló — és ma ugyanoda vezet.
Ha valaha javítani akarjuk, a különbséget kell megfognunk, nem a
számot csökkenteni.

---

## 4. Amit a robusztussági mérés NEM tud megmutatni

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

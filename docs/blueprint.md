# Aprajafalvi időpontfoglaló — Műszaki terv

*Állapot: tervezés lezárva. Implementáció következik.*

---

## 1. Mit építünk

Magyar nyelvű, lokálisan futó időpontfoglaló Aprajafalva három boltjához.
A vásárló hétköznapi magyar mondatokkal foglal — szövegesen, boltban elhelyezett
tableten, később telefonon.

**A metafora:** Dulifuli feladatait vesszük át. Nem tanácsadót építünk, hanem
azt a munkát vesszük le valakiről, amit nem szeret csinálni.

**Kettős olvasat, tudatosan:** ma Aprajafalva három boltja fut rajta, de a
rendszer platformnak épül. Ahol a platform-olvasat ma olcsó (egy oszlop, egy
interfész), ott most építjük be. Ahol drága lenne, ott ADR rögzíti a váltást.

### Célok

| Szint | Cél |
|---|---|
| Elsődleges | A vásárló magyarul foglaljon, és a foglalás megbízhatóan létezzen. |
| Boltok | Nagyobb kihasználtság úgy, hogy a dolgozói szünet sérthetetlen marad. |
| Beosztás | Ne legyen napi robotmunka. Egy hónapnyi beosztás percek alatt felvihető. |
| Mérnöki | Lokális, moduláris, kicsiben indul, dokumentált úton nő. Modell cserélhető. |
| Tanulási | A dev mód visszacsatolási hurka hónapról hónapra jobbá teszi a rendszert. |

### A vásárló igényei (fontossági sorrendben)

1. Bízhasson a foglalásában — visszaigazolás, kód, később visszanézhető.
2. Értsék meg elsőre.
3. Gyorsan végezzen — a gyakori eset két fordulóból.
4. Ne faggassák feleslegesen.
5. Kapjon őszinte választ — ha nincs hely, alternatíva jöjjön.
6. Tudjon hibázni — javítás, ne újrakezdés.
7. Ne sürgessék.
8. Legyen kiút emberhez vagy sorbanálláshoz.

**Nyelvi sokféleség.** A falu lakossága nyelvileg erősen tagolt: idős törpök
régies fordulatokkal, tájszólás, elharapott és töredékes mondatok, fiatalok
szlengje, és kognitívan egyszerűsített beszéd. Ez nem peremeset, hanem a
mindennapi bemenet. Külön szakasz szól róla (7.).

---

## 2. A sérthetetlen alapelv

> **Az LLM nem foglal, hanem fordít.**

A foglalást determinisztikus mag végzi. Az asszisztens dolga kizárólag a magyar
mondat → strukturált eszközhívás → magyar mondat átalakítás. Az orchestrator
állapotgép, nem LLM.

Következmény: egy hibás modellválasz legrosszabb esetben *kellemetlen*
(rossz visszakérdezés), nem *káros* (dupla vagy elveszett foglalás).

---

## 3. Domain-modell

### A műszak a központi entitás

```
műszak = pult + alkalmazott + szolgáltatás + időablak + időtartam + blokkszabály
```

A slot a **műszakhoz** tartozik. „Ma Törpilla, holnap GipszJakab ugyanazon a
pulton" = két külön műszak.

### Kulcsdöntések

**Slot kapacitása mindig 1** → a konkurencia egyetlen parciális UNIQUE index:

```sql
CREATE UNIQUE INDEX ix_foglalas_slot_aktiv
  ON foglalas(slot_id) WHERE allapot <> 'lemondva';
-- írás: INSERT ... ON CONFLICT DO NOTHING
```

SQLite-ban és Postgresben azonosan viselkedik.

**Paraméter-befagyasztás (snapshot).** A műszak létrehozásakor az öröklődési
lánc (szolgáltatás → bolt → pult → alkalmazott) feloldódik, a konkrét érték a
műszakba íródik. Törzsadat módosítása nem hat visszamenőleg; külön
`muszak_ujraszamol()` van rá. A felületen ki kell írni.

A befagyasztás a **paraméterekre** vonatkozik, nem a műszak létezésére — a
műszak visszavonható (lásd 9.).

**Szolgáltatás ≠ variáns.** A szolgáltatás ütemezési egység (időtartammal), a
variáns kereskedelmi attribútum, nulla ütemezési hatással. A variáns nem
szerepel a magban; `varians.idotartam_felulíras` alapból NULL.

**Egy pult egy műszakban egyféle szolgáltatást ad** → egy foglalás = egy slot.

**Egy szolgáltatás egy bolthoz tartozik.** A három bolt profilja különböző, így
a bolt-azonosítás triviális.

**Nincs foglalási ablak mint entitás.** A szabad slot léte maga a szabály: ha
van generált slot, foglalható. Amikor nem lehet foglalni, a rendszer nem
elérhető. Következmény: lemondáskor a slot magától újra szabad lesz, akkor is,
ha a „foglalási időszak" már lezárult. Ez tudatos (ADR-008).

### Táblák

`szervezet`, `bolt`, `pult`, `alkalmazott`, `beosztas`, `szolgaltatas`,
`varians`, `csomag`, `csomag_szolgaltatas`, `muszak`, `muszak_blokk`, `slot`,
`foglalas`, `hold`, `vasarlo`, `elerhetoseg`, `kivetel_nap`, `esemenyek`,
`ertekeles`

Kulcsmezők: `foglalas.idempotencia_kulcs`,
`vasarlo.kulcs_verzio`, `puffer_utana_perc`, `min_racs_perc`.
**Minden elsődleges kulcs UUID.**

---

## 4. Műszakblokkok: szünet és szabad sáv

A műszakon belüli nem-foglalható idő **egyetlen entitás**, típussal:

```
muszak_blokk.tipus ∈ {szunet, ebed, szabad_sav}
```

Ugyanaz a generálás, ugyanazok a kényszerek, ugyanaz a stratégia-interfész.

### Szünet mint stratégia

```python
class BlokkStrategia(Protocol):
    def general(self, muszak) -> list[MuszakBlokk]: ...
    def utkozes(self, muszak, blokkok, kert_slot) -> BlokkEredmeny: ...
```

| Stratégia | Viselkedés | Mikor |
|---|---|---|
| `FixBlokk` | generál, nem mozgat, ütközésnél elutasít | **v1** |
| `MohoAthelyezo` | legközelebbi érvényes helyre tol | ha az elutasítások indokolják |
| `KoltsegAlapu` | preferenciákkal optimalizál | később |

A választás a műszakon (`blokk_szabaly.strategia`), boltonként és dolgozónként
eltérhet. **A kemény kényszerek ellenőrzése a stratégián kívül van** — a
munkajogi minimumot nem az implementáció dönti el.

Az áthelyezés azért nincs v1-ben, mert **sorrendfüggővé** teszi a rendszert:
ugyanaz a három foglalás más sorrendben más beosztást ad. Ezt nehéz tesztelni
és nehéz elmagyarázni a dolgozónak. Minden mozgást naplózni kell (ADR-009).

Kemény kényszerek: minimum összes szünet, maximum folyamatos munka, **munkajogi
minimum** (védett kategória), a blokk nem lóghat ki a műszakból.

Puha preferenciák (költségfüggvénybe): időzítés, egyenletes vs. összevont
elosztás, ne aprózódjon.

### Szabad sáv — érkezési sorrend

Az óra nem osztható ki 100%-ban:

```
muszak.foglalhato_arany   # pl. 0.8 → az óra 20%-a marad nyitva
```

Négy dolgot old meg egyszerre:

- **kiszolgálja azt, aki nem foglal** — az idős törp bemegy és sorra kerül;
  ez a „kiút" legjobb formája, nem kudarc, hanem külön út
- **elnyeli a csúszást** — ha egy vásárlás hosszabb lett, nem tolódik az egész nap
- **puffer a hibás foglalásnak**
- **realisztikus naptár**

**A pontozó soha nem eheti meg a szabad sávot.** Kemény kényszer, nem
preferencia — különben az optimalizálás pont azt tömi be, amit védeni akarunk.

A dolgozói nézetnek kell sorbanállás-panel: ki várakozik, mióta, mikor a
következő foglalt időpont.

---

## 5. Konkurencia és kapacitás

### Hold — puha zár

Keresés és ajánlás után 1-3 időpontra puha zár (TTL 2-5 perc, session-höz
kötve). A hold ugyanabban a slotban ül, mint a foglalás.

**Két szabály:**
1. *Csak olyan időpontot mutatunk, amit tartani is tudunk.* Ajánlott jelölt =
   van rá hold.
2. *Széles kívánságra nem adunk széles zárat.* A „péntek délelőtt" nem zárolja
   a délelőttöt.

Közös eszközön (tablet) a hold csendben megújul, amíg a session él — a
gondolkodás nem hiba.

### Szándékindex

Session-szintű rekord, memóriában, csúszó TTL-lel (5-10 perc):

```
{bolt?, szolgaltatas?, het?, nap?, jelolt_slotok[], bizonyossag, utolso_frissites}
```

Soha nem blokkol, a vásárló sosem látja, **nem tartalmaz vásárlóazonosítót**.
Interfész: `szandek_frissites()`, `szandek_lekerdezes()` — mögé később Redis
kerül változatlan hívásokkal.

### Kapacitástervezés — ez elsőrendű követelmény

Előfordulhat, hogy a foglalás havonta **egy-két órára** nyílik meg a következő
egész hónapra. Ilyenkor a terhelés nem peremeset, hanem a rendszer normál
üzemmódja.

**Nincs külön roham-üzemmód.** A rendszer nem viselkedik másképp, amikor sokan
vannak — a vásárlónak sosem kell másik felületet megtanulnia.

Amit szűkösségben csökkentünk, az kizárólag belső luxus:

| Csökkenthető | Nem csökkenthető |
|---|---|
| önkonzisztencia 3-5 futásról 1-re | az LLM-es beszélgetés lehetősége |
| sablonarány feljebb | a visszaigazolás pontossága |
| hold TTL rövidebb | a nyelvi rétegek kiszolgálása |

**A kiszolgálási szint csökkenhet, a képesség nem** (ADR-010).

Ha nincs szabad kapacitás, **sor keletkezik, nem másik rendszer**. A várakozó
őszinte üzenetet lát, a beszélgetése ugyanaz marad.

### Skálázási cél

| Fázis | Cél |
|---|---|
| Fejlesztés | 3 egyidejű szál |
| v1 | 3-5 egyidejű beszélgetés elfogadható minőséggel |
| Később | több gép, több instance, 100+ egyidejű szál |

Egy modellpéldány, több párhuzamos slot (llama.cpp szerver). Nagyobb terhelésre
vLLM folyamatos kötegeléssel — a séma változatlan, csak a háttér cserélődik.

**Két varrat, ami a többgépes jövőt eldönti:** a szándékindex memóriában van
(→ Redis, kész interfész mögött), és az SQLite egyetlen írót enged (→ ADR-004
kiváltó feltétele, a repository réteg miatt egy könyvtár átírása).

### Igazságosság

Érkezési sorrend, kimondva. Amíg bőven van hely, mindegy; szűkösségben látható
lesz, ki kapott és ki nem. Az „aki legközelebb keres, megtalálja" elv panasszá
válik. Egyszerű és megmagyarázható (ADR-011).

---

## 6. Ajánlatpontozó

```
pontszám = w1 * (1 - tényleges_lefedettség)
         + w2 * (1 - várható_lefedettség)
         korlátozva: csak a kért ablakon belül
         kizárva:    szabad sáv, blokkolt idő
```

Az illeszkedés **korlát, nem súly**. Ha valaki péntek délelőttöt kért, nem
ajánlunk csütörtök délutánt csak azért, mert ott üres a naptár.

Mellékhaszon: ez megoldja az ajánlatszórást is — két egyidejű session közül a
második már látja az első holdját.

v1-ben történeti adat nincs: a várható lefedettség az aktív szándékindexre és
kézzel jelölt „népszerű sáv" mezőre támaszkodik.

---

## 7. Kommunikációs szabályok

Ugyanolyan kötelezőek, mint a technikai invariánsok.

### Nyelvi rétegek

A golden set **rétegzett**, és minden réteg külön küszöböt kap:

| Réteg | Példa |
|---|---|
| Köznyelvi | „szeretnék időpontot kedden" |
| Tájszólás, régies | helyi alakok, elavult szórend |
| Elharapott, töredékes | „kedden… petárda… lehet?" |
| Szleng | fiatalok rövidítései |
| Kognitívan egyszerűsített | ismétlés, körülírás, témaugrás |

**A leggyengébb réteg a mérőszám, nem az átlag.** Egy 98%-os átlag mögött
állhat 70% az idős törpökön — és pont ők nem tudnak mást választani.

### Négy technika

1. **Normalizáló réteg az értelmező előtt** — tájszólási alakok, szleng,
   gyakori elgépelések köznyelvi formára; adminból szerkeszthető táblázat,
   nem modellmunka.
2. **Zárt kérdésre váltás bizonytalanságnál** — két sikertelen értelmezés után
   ne nyitottan kérdezzen újra, hanem: „Kedden vagy szerdán?"
3. **Visszaolvasásos megerősítés mindig**, egyszerű mondattal.
4. **Egy kérdés egy fordulóban.** Összetett kérdés tilos. Akadálymentességi
   szabály, nem stílus.

### Szűkösség jelzése

- Csak ha a beszélgetésből **már ismert a preferencia** vagy konkrét igény.
- Csak ha **igaz**, konkrét küszöbszámból — a napló utólag auditálható.
- **Homályosan, darabszám nélkül.** ✅ „kevés hely maradt péntek délelőttre" ·
  ❌ „már csak két időpont maradt"
- Tényszerű hangnem, nem sürgető.

Ha ez lazul, sötét mintázattá válik: két hét után senki nem hiszi el, pont
amikor számít.

### Megerősítés és lezárás

- A foglalás tényét **mindig konkrétan** vissza kell igazolni.
- **Egy beszélgetésben egy helyre egy slot foglalható.** Nincs csoportos
  vagy többszörös foglalás — minden vásárló saját beszélgetésben, saját
  slotot foglal.
- A végén **opcionális értékelés**, 2-3 koppintás, nem szöveges. **A trace-hez
  kötve, nem a foglaláshoz** — így nem lesz belőle vásárlói profil, és a dev
  módban azonnal látszik, mely beszélgetések mentek rosszul.

### Kétlépcsős válasz (hangcsatorna)

Az M-1 spike méréseiből (`spike/EREDMENY.md`) tudjuk, hogy a tartalmi
válaszhoz szükséges modellhívás ideje messze meghaladja azt, amit egy
hangalapú beszélgetésben csöndként el lehet viselni. Erre a válasz nem a
modell felgyorsítása, hanem a válasz kettéosztása:

1. **Azonnali, sablonos nyugtázás.** Mielőtt a tartalmi válasz elkészülne,
   a rendszer egy előre megírt töltelékmondatot ad ("Egy pillanat, nézem…").
   Ez **sablon, nem modellgenerálás** — a generálás önmagában annyi időt
   venne igénybe, hogy a nyugtázás elkésne, és pont a célját (a csönd
   megtörését) veszítené el.
2. **Tartalmi válasz.** Ez már a ténylegesen lekérdezett/kinyert adatot
   tartalmazza, a szokásos módon (visszaolvasásos megerősítéssel stb.).

A szabály **nem az, hogy „a nyugtázó mondat nem tartalmazhat tényt"** —
hanem hogy csak **igazolt, determinisztikus forrásból származó** tényt
mondhat vissza. Van, amit a rendszer a nyugtázás pillanatában már
ellenőrizhetően tud (a felismert keresési ablak, a beazonosított bolt) —
ezt vissza lehet mondani. Amit még nem tud (mert az még nem futott le,
vagy nem determinisztikus komponensből jön), azt nem.

| Mondható | Forrás | Nem mondható |
|---|---|---|
| A felismert keresési ablak („kedden délelőttre nézem") | dátumparser | Konkrét szabad időpont, **mielőtt** a keresés ténylegesen lefutott és eredményt adott |
| Zárt halmazból biztosan azonosított bolt/szolgáltatás („az Ügyifogyiban nézem") | katalógus-egyezés | Kapacitás-szám (hány hely maradt, hány foglalás van) |
| A folyamat állapota („keresem", „egy pillanat") | orchestrator állapotgép | A modell bármilyen ellenőrizetlen generálása — akkor is, ha valószínűnek tűnik |

A közös vonás: minden **mondható** tétel egy determinisztikus komponensből
jön, amit a nyugtázás pillanatában már lekérdeztünk, nem generáltunk. A
**nem mondható** oszlop nem azért tilos, mert „még nincs kész a válasz" —
azért, mert nincs mögötte ellenőrzött forrás, tehát nem is állítható róla,
hogy igaz.

Szöveges csatornán **nincs** töltelékmondat — ott a natív gépelés-jelzés
("...ír") tölti be ugyanezt a szerepet, plusz üzenet nélkül.

---

## 8. Adatvédelem

Aprajafalván minden lakosnak egyedi számsora van, ami névvel egyértelműen
azonosít → nemzeti azonosító jellegű adat.

- **Nyers azonosító soha nem kerül lemezre, logba, trace-be.** HMAC-SHA256,
  pepper külön kulcstárolóban. `vasarlo.kulcs_verzio` teszi lehetővé a
  rotálást.
- **Az azonosító formátuma validátor-interfész mögött van** — más településen
  más formátum lesz.
- **Név csak amíg van jövőbeli foglalás.** Megőrzés: teljesülés + ~30 nap,
  majd **automatikus** törlés (ütemezett feladat).
- **Trace-ek redaktálása tárolás ELŐTT.** `<NEV>`, `<AZONOSITO>`, `<TELEFON>`.
  Az annotátor nem lát azonosítható adatot.
- **Elérhetőség külön cél.** Nem következik a foglalásból: külön tábla, külön
  hozzájárulás, a foglalás lezárása után törlődik. Hívószámnál is megkérdezzük,
  küldjünk-e üzenetet.
- **Hitelesítés:** a számsor nem titok, tehát nem hitelesítő. Lemondáshoz és
  módosításhoz **foglalási kód**. A „mik a foglalásaim" lekérdezéshez számsor +
  név, erős rate limitinggel és enumeráció-védelemmel (azonos válasz és
  válaszidő létező és nem létező azonosítóra).
- **Névtelen böngészés:** időpontok megnézéséhez semmi nem kell.
- **Közös eszközön a session a vásárlóhoz tartozik**, nem a tablethez. Távozáskor
  törlődik — nem elég a képernyőt visszaugrasztani.

### Dolgozói adatok

A rendszer rögzíti, ki mikor dolgozott, mennyi szünetet kapott, mekkora a
kihasználtsága. A statisztika és a predikció ezt igényli, tehát gyűjtjük — de
**a munkáltatói nézetben alapból aggregált és pult-szintű**. Személyre bontott
nézet külön kapcsoló, dokumentált indokkal.

### Megjegyzés a foglaláshoz

A beszélgetésből kiderülő hasznos információ (preferált variáns, korábbi
vásárlás, sietős-e) megjelenik a pultos nézetében. Ez az **egyetlen pont, ahol
gépi kivonat emberi döntést befolyásol**, ezért három korlát:

1. **Zárt halmaz, ahol lehet** — strukturált mezők, nem próza.
2. **Ami szabad szöveg, az redaktálva megy** — egészségi állapotra, családi
   helyzetre utaló megjegyzés nem kerülhet be.
3. **Soha nem befolyásolja az ütemezést**, és jelölve van, hogy gépi kivonat.

Megőrzés: a foglalással együtt törlődik.

---

## 9. Üzemeltetés

### Értesítések — előállítás igen, küldés még nem

| Esemény | Üzenet |
|---|---|
| Foglalás létrejött | összefoglaló |
| Áthelyezés | új adatok |
| Műszak elmarad | értesítés + alternatíva |
| Pultos változott | tájékoztatás |

**v1-ben az üzenet előáll, de nem megy ki.** Külön modul, szolgáltató-interfész
mögött, kikapcsolható. Ennek oka elvi: a külső SMS- vagy e-mail-szolgáltató
adatfeldolgozó, és a „minden lokálisan fut" elvvel ütközik. A küldés
bekapcsolása külön döntés (ADR-012), az üzenet a minimumot tartalmazza —
időpont, bolt, kód; nevet és terméket nem.

### Műszak visszavonása

Törpilla lebetegszik, pult kiesik, műszak rövidül. Kell egy művelet, ami
felsorolja az érintett foglalásokat, alternatívát javasol és eseményt bocsát ki.
Ez az üzemeltetés leggyakoribb eseménye.

### Foglalás áthelyezése

„Át tudnám tenni szerdára?" — **atomi művelet**, nem lemondás + új foglalás.
Vagy megszerzi az újat és elengedi a régit, vagy semmi nem változik. Egy
hónappal előre foglalt időpontnál ez gyakori lesz.

### Kivételnapok

`kivetel_nap` tábla szervezet és bolt szinten: ünnep, rendkívüli zárás, leltár.
Enélkül a slotgenerátor karácsonyra is generál.

### Mentés és helyreállítás

Egyetlen gép, egyetlen adatbázisfájl. **A „0 elveszett foglalás" invariáns eddig
csak a konkurenciára vonatkozott, a lemezre nem.**

- óránkénti `VACUUM INTO` pillanatkép + WAL-másolat külön eszközre
- **helyreállítási próba a tesztkészletben** — az a mentés, amit sosem
  állítottak vissza, nem mentés
- indítás előtti ellenőrzőlista a foglalási időszak előtt

### Megfigyelhetőség

Minden eszközhívás latenciája és kimenetele naplózva (azonosító nélkül), napi
összesítő. Állandó mutatók a dev módban:

- p50/p95 latencia eszközönként
- félreértési arány **nyelvi rétegenként**
- kiút aránya — **mérni kell, nem megszüntetni**; a nulla általában nem
  tökéletességet jelent, hanem hogy a törpök feladták
- no-show arány, kihasználtság
- rossz értékelést kapott beszélgetések aránya

---

## 10. Architektúra

```
Csatornák (chat, bolti tablet, admin, később hang)
        ↓
Orchestrator  ← determinisztikus állapotgép
        ↓
Alrendszerek ─┬─ LLM runtime
              └─ Foglalási mag
        ↓
{Dev-napló (redaktált) | Adatbázis | Értesítés-előállító}
```

**A tabletek vékony kliensek.** Egy gép szolgálja ki mindet: egy modellpéldány,
egy naptár, egy igazság.

### Alrendszerek

| Alrendszer | Feladat | LLM? |
|---|---|---|
| Kapuőr | témán belül van-e a kérés | **nem**, determinisztikus, a modell előtt fut |
| Normalizáló | tájszólás, szleng → köznyelv | nem, szótár |
| Dátumértelmező | „jövő hét péntek" → dátum | nem, szabályok |
| Szándékértelmező | mondat → eszközhívás JSON | igen, kötött dekódolással |
| Ajánlatpontozó | melyik slotot kínáljuk | nem |
| Hold-kezelő | zárolás, TTL | nem |
| Foglalási mag | a tényleges írás | nem |
| Válaszgeneráló | magyar mondat | ~80% sablon |
| Szándékindex | torlódásfigyelés | nem |
| Bíró | trace-előszűrés | igen, **csak offline** |

Bizalmi jelzés a kötött dekódolás logprobjaiból, kritikus mezőkre (dátum, bolt,
szolgáltatás). **A visszakérdezésről az orchestrator dönt, nem az LLM.**

Önkonzisztencia: az értelmező 3-5×, a JSON eszközhívások pontos
egyenlőségvizsgálatával. Szűkösségben és hangon ez elesik.

**Kerülendő:** szabad szöveg súlyozott keverése, LLM-ek egymással beszélgetése.
Maximum két aktív modell a válaszútvonalon.

### Kapuőr — témán belül tartás, determinisztikus réteg

A témán belül tartás **nem a modell prompt-fegyelmén múlik.** Ez egy
determinisztikus réteg, ami a modell **előtt** fut, nem egy utólagos
javítás vagy rendszerprompt-utasítás ("csak foglalással kapcsolatos
kérdésre válaszolj"). Három zárt kategória, ebben a sorrendben eldöntve:

1. **Foglalási szándék** — időpont keresése, foglalás, áthelyezés,
   lemondás, lekérdezés. Ez megy tovább az értelmezőhöz
   (szándékértelmező, kötött dekódolással).
2. **Engedélyezett tényválasz, zárt listából** — a `bolt_info` mezői
   (lásd lent, "Bolti tudás"). Ez nem hívja az értelmezőt tartalmi
   kérdésben, egyenesen a szerkesztett adathoz megy.
3. **Egyik sem** — a rendszer **visszaterel**, nem improvizál. Nincs
   "megpróbálom kitalálni, mit akarhat" ág; a válasz jelzi, hogy erre
   nem tud segíteni, és felkínálja, mire tud (kiút, blueprint 7. szakasz).

A kapuőr tehát nem *kéri meg* a modellt, hogy maradjon témán belül —
eldönti helyette, mielőtt a modell egyáltalán szóhoz jutna a tartalmi
válaszban. Ha ez a döntés a modellre lenne bízva, a téma-tartás annyira
lenne megbízható, amennyire a modell aznap fegyelmezett — ez a kockázat
technikailag kizárt, nem csak csökkentett.

### Bolti tudás — szerkesztett adat, nem modell-tudás

A bolt-szintű tényadat — nyitvatartás, cím, termékleírás, személyes
megjelenés, árak (ahol az ártájékoztatás egyáltalán engedélyezett) —
**szerkesztett adat a boltnál**, nem a modell paramétereiben él. A
`bolt_info` eszköz ezt kikeresi egy zárt, admin-szerkeszthető mezőkészletből,
a válaszgeneráló felolvassa — **a modell sosem generálja ezt a
tartalmat**, csak egy mondatba fogalmazza a már kikeresett tényt.

Következmény:

- A tudás frissítése **admin-szerkesztés**, nem újratanítás és nem
  prompt-módosítás. Ha megváltozik a nyitvatartás, az admin felületen
  írják át — a modell változatlan marad, nem kell újra mérni a golden
  seten.
- A modell **sosem hallucinálhat tényt** erről a rétegről — nincs is
  honnan: a tény nem az ő súlyaiban van, csak megfogalmazza, amit a
  `bolt_info` visszaadott.
- Amire nincs szerkesztett adat, arra a válasz "ezt nem tudom" —
  **nem kitalálás** (lásd fent, a kapuőr harmadik kategóriája, és a
  golden set `kapuor-02` esete: az ár kitalálása kifejezetten tiltott
  minta).
- Ez a döntés közvetlenül kizárja a **tudás-finomhangolást** mint utat
  (lásd 14. szakasz, "Modellstratégia") — a tárgyi tudás sosem kerül a
  modellbe sütve, tehát nincs is mit finomhangolással frissíteni rajta.

### Koppintós út

Nem tartalék, hanem **párhuzamos felület**: van, aki nem akar beszélgetni, csak
gombot nyomni. Akadálymentességi kérdés, ugyanolyan rangú, mint a chat.

---

## 11. Szerepkörök

**Vásárló** — chat, tablet, később hang. Koppintós út egyenrangúan.

**Dolgozó** (mobil) — mai műszak, élő „most", saját blokkok, szünetkérés most,
**sorbanállás-panel**, no-show és „hosszabb lett" jelölés, csúszásjelzés,
foglaláshoz fűzött megjegyzés. Írás csak saját műszakra.

**Admin** (asztali) — **beosztásszerkesztő sablon-műszakokkal** (ez a kritikus
út, lásd ütemterv), törzsadat, szabálykapcsolók és profilok, foglaláskezelés,
ütközéslista, műszak-visszavonás, statisztika.

**Sablon-műszakok (M1, elkezdve).** Egy sablon egy elmentett, dátumtól
független műszak-recept: pult, alkalmazott, szolgáltatás, napi
óra-időablak, snapshot-mezők és blokkszabály
(`migraciok/0003_muszak_sablon.sql`). Meglévő műszakból menthető, majd
egy napra vagy egy teljes hétre alkalmazható. Ettől külön áll a **hét
másolása**: nem egy sablont ismétel, hanem egy már létező hét TÉNYLEGES,
akár pultonként eltérő beosztását helyezi át egy másik hétre — mindkét
út tiszteletben tartja a kivételnapokat (a generátor a szokásos módon
hagyja ki azokat).

**Ütközéslista (M1, elkezdve).** Három ok miatt kerülhet rá egy műszak:
kemény kényszert sért (`mag/szabalyok/kenyszerek.py::ellenoriz()` — a
logika onnan jön, a lista nem duplikálja), két műszak időben átfedi
egymást ugyanazon a pulton, vagy nulla slotot generált anélkül, hogy
kivétel napra esne (kivétel napon a nulla slot szándékos, nem hiba). A
kényszerek.py két bolt-/profilfüggő paramétere (`min_osszes_szunet_perc`,
`max_folyamatos_munka_perc`) egyelőre a lista saját, felülírható
alapértéket kap — a profilrendszer (lásd "Kényszerkapcsolók" lent) még
nem épült meg.

**Dev / annotátor** — külön szerepkör, trace-böngésző, „mi lett volna a helyes
válasz". Nem lát azonosítható adatot. Elsőként a rosszra értékelt
beszélgetéseket nézi.

### Kényszerkapcsolók

Hármas állapotúak (Örökölt / Be / Ki), négy szinten (rendszer → bolt → dolgozó
→ műszak), látható forrásjelöléssel. A védett kategória nem kapcsolható
szabadon.

A kombinatorikus tesztelhetetlenség ellen: **profilok** („laza", „szoros",
„ünnepi") és **magyarázó motor** (elutasításkor melyik szabály, honnan
öröklődött).

---

## 12. Szolgáltatási szintek

**A válaszidő-SLO-k (az alábbi tábla mind a négy p95 sora) ideiglenesen
FELFÜGGESZTVE.** A fejlesztés jelen szakaszában (M0/M1) mérjük és
naplózzuk őket, de nem blokkolók — egyetlen teszt vagy build sem bukhat
emiatt. A feloldás feltétele **M4 lezárása**. Ez a jelenlegi fejlesztési
sorrendből következik (`docs/roadmap.md`: "a beosztásszerkesztő előbb, mint
az asszisztens" — amíg nincs LLM-réteg, a válaszidő-SLO-nak nincs mit
mérnie). **Ez nem vonatkozik a lenti invariánsokra** (dupla/elveszett
foglalás) — azok soha nem függnek fel, teszttel bizonyítottak maradnak.

| Mit | Cél | Státusz |
|---|---|---|
| Foglalás megerősítése (mag) | p95 < 100 ms | felfüggesztve |
| Szabad időpont keresés | p95 < 200 ms | felfüggesztve |
| Első reakció (sablon, hang) | p95 < 500 ms | felfüggesztve |
| **Tartalmi válasz (modell)** | **p50 < 10 s ÉS p95 < 25 s**, a tendencia figyelve (a korábbi „átlag < 15 s" helyett) | **aktív keretként, l. lent** |
| Szolgáltatás-azonosítás | > 98% **a leggyengébb nyelvi rétegen is > 90%** | aktív |
| Dátumértelmezés | > 99% | aktív |

### A válaszidő-keret: ELOSZLÁS, nem egy szám (2026-08-26, ADR-022)

A tartalmi válasz korábbi célja (p95 < 8 s) először **átlag 15
másodpercre** tágult (2026-08-23), majd **kétpontos eloszlás-elvárássá**
alakult (2026-08-26, ADR-022):

| Pont | Elvárás | Mit véd |
|---|---|---|
| **p50** | **< 10 s** | a TIPIKUS forduló — a beszélgetés ritmusa |
| **p95** | **< 25 s** | a FAROK — a türelem felső határa |
| **tendencia** | figyelve, nem küszöb | a lassú elsodródás |

Miért nem az átlag: **az átlag pont azt a két hibát mossa össze, amit
külön kell látni.** Egy 15 s-os átlag állhat abból, hogy minden forduló
15 s (a rendszer egyenletesen lassú — modellt vagy promptot kell
cserélni), és abból is, hogy 40 forduló 3 s és kettő 250 s (a rendszer
gyors, de van egy patológiás ága — azt az EGY ágat kell megkeresni). A
két eset ugyanazt az átlagot adja, és teljesen más javítást kíván.

A **tendencia** azért van a képen, mert a két küszöb pillanatfelvétel: a
p50 hónapokon át maradhat 9,8 s-on úgy, hogy közben minden hétben
romlik. A napló-elemző (`python feladat.py naplo`) ezért a napló első és
második felének p50-jét külön is kiírja, és megmondja az irányt. **Ez
nem küszöb** — ha romlik, az nem bukás, hanem kérdés, amit fel kell
tenni.

Ez nem az SLO-k feloldása és nem is a felfüggesztés visszavonása — a
felfüggesztett p95-sorok (mag, keresés, első reakció) továbbra is
felfüggesztve maradnak M4 lezárásáig. Ez egy **fejlesztési keret**: az a
tartomány, amin belül egy fordulónak maradnia kell, hogy a válaszidő ne
váljon önmagában kizáró tényezővé, amíg a pontosságon dolgozunk.

**Amit a keret megenged:** egy fordulóban **több modellhívás is**, ha
mérhető pontosságjavulást hoz. Ilyen a 10. szakasz önkonzisztencia-
ellenőrzése (az értelmező 3×, a JSON eszközhívások pontos
egyenlőségvizsgálatával). Az engedély **feltételes**: a hívásszám
növelése csak MÉRÉSSEL indokolható — mennyit javít, és mennyivel lassít
—, és a mérésnek a golden seten kell megtörténnie, nem egyedi
példákon. Ha egy plusz hívás nem javít mérhetően, kikapcsolva marad,
akkor is, ha elméletileg indokolt.

**Amit a keret NEM enged:** a **két elvárás EGYÜTT** áll — egy 4 s-os
p50 nem vásárolja meg a 40 s-os p95-öt, és fordítva. Egy
determinisztikusan eldönthető kérdésre (kapuőr, gombnyomás, zárt
halmazbeli válasz) továbbra sem szabad modellt hívni — ott a helyes
válaszidő nulla nagyságrendű, és a keret tágulása ezen nem változtat.

**Hangcsatornán a p95 szigorúbb lesz.** A 25 s szöveges csatornára szól,
ahol a várakozást a gépelés-jelző kitölti. Hangon a kétlépcsős válasz (7.
szakasz) első lépcsője (< 500 ms sablon) a türelem valódi mérőszáma, és
a tartalmi válaszra a mai 25 s nem tartható — ezt a hangcsatorna
bekötésekor újra kell tárgyalni, l. ADR-022 „Kiváltó feltétel".

A fenti "Első reakció" / "Tartalmi válasz" sor a korábbi "Asszisztens
válasz (szöveg)" / "Asszisztens válasz (hang)" bontást váltja fel — ez az
M-1 spike méréseiből (`spike/EREDMENY.md`) származó **javasolt módosítás**,
nem véglegesített döntés. A mért válaszidők (1 párhuzamos kéréssel is
percek nagyságrendűek) mellett a korábbi 2,5 s / 800 ms cél irreális
volt; a kétlépcsős válasz (7. szakasz) miatt a hangcsatornán a felhasználó
szempontjából releváns szám az azonnali sablon-reakció, nem a teljes
modellválasz. **A véglegesítéshez ADR kell** — ez a felfüggesztéstől
független, önálló döntés.

**Ezek a számok ma feltételezések.** A spike méri be őket; utána válnak
követelménnyé, ha a felfüggesztés feloldódik.

**Invariánsok** — teszttel bizonyítva, a fenti felfüggesztéstől
FÜGGETLENÜL mindig kötelezők:
- dupla foglalás: **0**
- elveszett foglalás: **0** (konkurenciából *és* lemezhibából)

---

## 13. Menekülőút-doktrína

Minden egyszerűsítés írásos döntés, **konkrét kiváltó feltétellel**.

```
ADR-004: SQLite mint kezdeti adattár
V�ltás, ha:  >1 író folyamat VAGY p95 írás > 50 ms VAGY
             egyidejű aktív session > 50 VAGY replikáció-igény
V�ltás mire: PostgreSQL 16
Ellenőrzés:  a CI mindkét motoron futtatja a teljes tesztkészletet
```

### Hordozhatósági szabályok

**Tilos:** `AUTOINCREMENT` és egész kulcs (→ UUID), SQLite dátumfüggvények
(→ időszámítás az appban, ISO-8601 UTC), típusrugalmasság (→ explicit `CHECK`),
`INSERT OR REPLACE` (→ `ON CONFLICT`), szétszórt SQL (→ `mag/repo/`).

**Kötelező:** `foreign_keys=ON`, `journal_mode=WAL`, `busy_timeout=5000`,
explicit `IMMEDIATE` tranzakciók, egyetlen író folyamat, sorszámozott up/down
migrációk.

### Platform-varratok (ma olcsó, később drága)

| Varrat | Ma | Nélküle később |
|---|---|---|
| `szervezet_id` + repo-szintű szűrés | egy oszlop, egy sor | minden tábla és lekérdezés |
| `vasarlo.kulcs_verzio` | egy oszlop | kulcsrotáció lehetetlen |
| Azonosító-validátor interfész | egy protokoll | bedrótozott formátum |
| `kivetel_nap` tábla | egy tábla | ünnepnapra generált slotok |
| Sablonok fájlban, nyelvkulccsal | egy könyvtár | szétszórt szövegek |
| `session.csatorna` | egy mező | nem tudni, hol romlik a megértés |
| `szervezet.idozona` | egy oszlop | megjelenítési hibák |

---

## 14. Modellstratégia

**Elsődleges modell: Apache-2.0 licencű** (Qwen3-alap) a nulladik naptól.
Ez az, amire finomhangolunk, és amitől függünk.

**A Racka-4B ellenőrző jelölt.** Qwen3-4B alap magyar tokenizer-cserével, a
subword fertility 3,13 → 1,66 (feleannyi token, közel fele latencia). Licence
CC-BY-NC-SA-4.0, kapuzott, kutatási célra. Ha a golden seten lényegesen jobb,
és a projekt szintet lép, engedélyt kérünk vagy veszünk.

Ezért a modell **cserélhető modul**: `LLMSzolgaltato` interfész, a modell
konfigból jön.

A tájszólás és a helyi nyelvhasználat egyik alapmodell tanítóanyagában sincs —
**ezt csak saját adatból lehet megtanulni**. A „mi lett volna a helyes válasz"
hurok tehát nem kényelmi funkció, hanem az egyetlen út a falu nyelvéhez.

**A finomhangolás célja kizárólag a nyelvi megértés** — tájszólás,
töredékes beszéd, szleng, elgépelés —, **nem a tárgyi tudás.** A bolti
tényadat (nyitvatartás, cím, termék, ár) az adatbázisban van, a
`bolt_info` eszközön keresztül kikeresve (10. szakasz, "Bolti tudás") —
ezt sosem tanítjuk bele a modell súlyaiba. Ez tudatosan kizárja a
legdrágább és legtörékenyebb utat, a **tudás-finomhangolást**: egy
modellbe sütött tényanyag minden admin-szerkesztésnél újratanítást
igényelne, és bármikor hallucinálhat, amit rosszul tanult meg. A „mi
lett volna a helyes válasz" hurok emiatt kizárólag ÉRTELMEZÉSI hibákat
gyűjt (rossz eszközválasztás, rossz paraméter-kinyerés, elveszett
kontextus) — egy téves nyitvatartás-válasz adatbázis- vagy
eszközhiba, nem finomhangolási feladat, és nem is javítható
finomhangolással.

`docs/LICENCEK.md`: komponensenként licenc, letöltés dátuma, link.
A Whisper magyar finomhangolatai a leggyakoribb licenccsapda.

### M-1 spike (2026-08-16) — mért tények

A `spike/` alatti eldobható kóddal (`docs/roadmap.md`, M-1) mért adatok.
Ez nem döntés, csak tény — a részletes bontás `spike/EREDMENY.md`-ban van,
és egyik ADR-t sem módosította.

- Helyi Ollama, `qwen3.5:4b` és `qwen3.5:9b` (mindkettő Apache-2.0). A
  Racka-4B ellenőrző jelölt nem volt elérhető lokálisan, nem mérhető.
- A golden seten mért három konfiguráció közül (4B gondolkodás nélkül,
  9B gondolkodással, 9B gondolkodás nélkül) **egyik sem éri el** egyetlen
  rétegküszöböt sem (12. szakasz / golden-set skill). A 4B modell
  gondolkodással golden-futtatása nem lett artifactként elmentve.
- A 4B modell gondolkodással ~25×-ösen több tokent termel mondatonként,
  mint a 9B (1441 vs. 57 token/mondat, 1 párhuzamos kéréssel mérve) — a
  mért adatok szerint jelenleg egyik konfigurációban sem éri meg a 9B-nél
  kisebb modell mellett dönteni.
- A szöveges asszisztens-válasz SLO-jához (12. szakasz, p95 < 2,5 s)
  képest minden mért válaszidő 1 és 3 párhuzamos kéréssel is 6–73×-os
  túllépés.
- SQLite írási p95 10 egyidejű session mellett 207 ms, ami meghaladja a
  13. szakasz ADR-004 kiváltó feltételét (p95 > 50 ms); 3 session mellett
  (35 ms) nem.
- A hun-date-parser könyvtár közvetlen pontosságát a spike nem
  perzisztálta artifactként — ez a mérés megismétlendő.

A modellválasztás, az adattár-váltás és a roham-üzemmód kérdése ezek után
is nyitott.

---

## 15. v1 hatókör

**Benne:** három bolt, műszakok, slotgenerálás, kivételnapok · keresés,
pontozás, hold, foglalás, **áthelyezés**, lemondás · fix blokkstratégia
(szünet + szabad sáv) · szöveges asszisztens normalizálóval · admin
beosztásszerkesztő sablonokkal · dolgozói nézet sorbanállással · értesítés
előállítása · dev mód trace-szel és értékeléssel · mentés és helyreállítás

**Kikapcsolva, de a modell helyes:** alkalmazottválasztás · automatikus
ütközés-áthelyezés

**Későbbre, kiterjesztési ponttal:**

| Bővítés | Horog |
|---|---|
| Várólista | eseménykibocsátás |
| Üzenetküldés élesítése | szolgáltató-interfész |
| Blokk-áthelyezés | `BlokkStrategia` |
| Egy pulton több szolgáltatás | `muszak_szolgaltatas` |
| Elosztott futás | szándékindex-interfész, repository réteg |
| Hangcsatorna | ugyanaz az eszközszerződés |

---

## 16. Kockázatok

| # | Kockázat | Kezelés |
|---|---|---|
| 1 | Nyelvi sokféleség (tájszólás, töredékes beszéd) | normalizáló, zárt kérdés, rétegzett golden set |
| 2 | Terheléscsúcs a foglalási időszakban | párhuzamos slotok, sor, degradáció képességvesztés nélkül |
| 3 | Beosztáskészítés napi teher | sablon-műszakok, korai admin felület |
| 4 | Kapcsolókombinációk tesztelhetetlensége | profilok + magyarázó motor |
| 5 | Lemezhiba, elveszett adat | mentés + helyreállítási próba |
| 6 | Modellicenc | Apache-2.0 elsődleges, Racka csak ellenőrző |
| 7 | Szűkösségjelzés sötét mintázattá válik | küszöb konfigból, auditálható napló |
| 8 | Az annotálás gazdátlan marad | heti fél óra, nevesített felelős |
| 9 | Snapshot-elv félreértése | felületen kiírva |
| 10 | Közbevágás, párhuzamos beszéd (barge-in) | a barge-in érzékelése/megszakítása a hangkeretrendszer felelőssége; a mi felelősségünk a szándékindex megőrzése félbeszakításkor |

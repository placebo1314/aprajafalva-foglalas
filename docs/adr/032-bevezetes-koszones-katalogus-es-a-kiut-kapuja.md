# ADR-032: A bevezetési rés — köszönés, katalógus, és a kiút kapuja

- **Dátum:** 2026-09-19
- **Állapot:** elfogadott
- **Kiváltó ok:** az ELSŐ IDEGEN PRÓBA (négy forduló, `qwen3.5:9b`)

## Kontextus

Az első próbát olyan ember végezte, aki NEM ismerte a rendszert. Négy
forduló alatt jutott el a köszönéstől odáig, hogy „menjen be a boltba
élőben" — és közben a rendszer **egyetlen keresést sem futtatott**:

| | a vásárló | a rendszer |
|---|---|---|
| 1. | „helló." | „Ehhez még kellene tudnom: melyik boltba szeretnél menni." |
| 2. | „milyenek vannak?" | „Úgy látom, így nem jutunk előre. Melyiket próbáljuk: másik napot, másik napszakot…" |
| 3. | „másik napszakot." | „Úgy látom, ez így nem vezet sehova — ne kínlódj vele tovább. A boltban élőben is fel tudnak venni időpontot." |
| 4. | „de én mindenképp itt akarom." | *(ugyanaz a mondat még egyszer)* |

**A hiba egyetlen feltevésből következik: hogy a vásárló ismeri a
boltokat.** Az első kérdésünk az volt, hogy MELYIK bolt — és minden
további rétegünk (visszakérdezés, ismétlés-figyelő, frusztráció-figyelő)
erre a feltevésre épült. Aki nem tudta megnevezni a boltot, azt a
rendszer előbb faggatta, aztán elküldte.

Ez nem nyelvi hiba, és nem is modell-hiba: **a rendszernek nem volt
válasza arra a kérdésre, amit egy új ember először tesz fel.**

## Döntés

**1. A kapuőr ötödik kategóriája: `KOSZONES`.**
A csak-köszönés („helló", „jó napot", „szia") nem foglalási szándék,
nem tényválasz, és nem hatókörön kívüli. A válasz: köszönés + rövid
bemutatkozás + **mi van itt** — a boltokkal és a szolgáltatásaikkal.
Szűk minta: a mondat EGÉSZE köszönés; a „Jó napot, szeretnék
időpontot" továbbra is foglalási kérés.

**2. Új eszköz: `kinalat`** (`assistant/tools/kinalat.py`).
„Milyenek vannak?", „mit lehet itt?", „mit árultok?" → a boltok és a
szolgáltatásaik, rövid leírással. **Engedélyezett tényválasz**, tehát a
kapuőr kapja el, modellhívás nélkül. Ha a beszélgetésből már tudjuk a
boltot, csak azt sorolja.

**3. Minden adat az ADATBÁZISBÓL jön, nem a sablonból.**
A bolt neve, a szolgáltatás neve és a leírás egyaránt szerkesztett
törzsadat (blueprint 10.). A sablon csak a keretet adja, a ragozást
pedig egy külön modul (`assistant/valasz/ragozas.py`): „a **Szundiba**
altatóért, az **Ügyifogyiba** petárdáért". Ha az admin átírja a
leírást, a mondat is változik — kódmódosítás nélkül.

**4. A zárt kérdés LEÍRÁST mutat, nem azonosítót.**
„Szundi — altató", nem „szundi". A gombokon és — mert ott nincs gomb —
a beszélhető mondatban is: *„Melyik boltba szeretnél menni: a Szundiba
altatóért, az Ügyifogyiba petárdáért vagy a Törpillába
boldogságért?"*

**5. A kiút csak KERESÉS UTÁN szólal meg.**
Ha a beszélgetés még egyetlen keresésig sem jutott el, a kiút helyett a
katalógus megy ki. A kiút azoké, akik tudják, mit akarnak, és nem
sikerül — nem azoké, akik még nem tudják, mit lehet. A bemutatkozás
NEM számít kiútnak (`Frusztracio.bemutatkozas_kiadva`): a `kiut_ajanlva`
nem nő tőle, tehát ha a vásárló ezután akad el, az ELSŐ kiút jár neki,
nem rögtön az „menjen be a boltba".

**6. A kiút gombjai csak keresés után kínálnak nap/napszak-váltást.**
Enélkül olyat kínálnánk, amiből a vásárló még semmit nem látott. A zárt
bolt-kérdés mellé viszont bekerült egy **„Mit lehet itt?"** gomb — az
első lépés annak, aki most találkozik a rendszerrel.

**5b. A bemutatkozás LEGFELJEBB EGYSZER áll a kiút helyébe.**
A fej nélküli végigjátszás fogta meg: enélkül az „ismétlés → kiút"
beszélgetés második ÉS harmadik fordulójára szó szerint ugyanaz a
felsorolás ment ki. Ha a vásárló a katalógus után SEM választ boltot, a
lista megismétlése nem segítség, hanem pontosan az a körbe-körbe, amit
el akartunk kerülni. A létra így négy fokú, mind a négy más:

| forduló | válasz |
|---|---|
| 1. | visszakérdezés (zárt, bolt-gombok + „Mit lehet itt?") |
| 2. | **katalógus** — mi van itt egyáltalán |
| 3. | **kiút bolt-kérdéssel** — „Kezdjük a legelején: melyik boltba?" |
| 4. | emberhez irányítás |

**6b. A keresés nélküli kiút MONDATA is más, nem csak a gombja.**
A régi bevezető felsorolta a három dimenziót („másik napot, másik
napszakot vagy a legkorábbi szabad időpontot") — keresés nélkül ez
olyat ígért, amiből a vásárló még semmit nem látott, ráadásul gomb sem
jött hozzá. Külön sablon (`bevezetes_bolt`) szól ilyenkor, és a boltok
mennek ki gombként, a katalóguséval azonos leírással. Egy zsákutcát
cseréltünk kérdésre.

## Miért így

- **A kapuőrben, mert a modell előtt kell eldőlnie.** A köszönésre és a
  „milyenek vannak?"-ra adott válasz nem függhet attól, fut-e az
  Ollama: mindkettő nulla modellhívással megy, tartalék ágon is.
- **Eszközként, mert adat.** A katalógus nem sablonszöveg, hanem
  lekérdezés — ugyanaz az elv, mint a `bolt_info`-nál: a bolti tudás
  szerkesztett adat, nem modell-tudás.
- **A kiút kapuja állapotkérdés, nem szövegkérdés.** Nem azt vizsgáljuk,
  MIT mondott a vásárló, hanem hogy jutottunk-e valameddig
  (`utolso_kereses`). Egy szövegfeltétel itt találgatás lenne.

## Amit feladunk

- **Egy ötödik kategóriát a kapuőrben** (a hármas zárt halmaz így már
  öt), és egy hatodik eszközt. Mindkettőt karban kell tartani.
- **Egy morfológiai közelítést** (`ragozas.py`): a `-ba/-be` hangrendi
  illeszkedés a mai három boltnévre helyes, de nem morfológiai elemző.
  Ha a boltok száma vagy a nevek jellege nő, ez az első hely, amit ki
  kell dobni.
- **A kiút gyorsaságát.** Aki tényleg elakadt, de még nem keresett,
  mostantól előbb kap egy felsorolást. Ez egy fordulóval hosszabb út —
  cserébe nem küldjük el olyat, aki még el sem indult.

## Kiváltó feltétel

- a `KOSZONES` minta valódi kérést nyel el (a naplóban `kapuor` réteg
  olyan mondatra, ami időpontot kért);
- a katalógus-válasz után a vásárlók többsége NEM választ boltot (a
  naplóból: `kinalat` után `visszakerdezes` vagy újabb `kinalat`) —
  ekkor a felsorolás nem segít, hanem elnyom;
- a `ragozas.py` hibás alakot ad egy új boltnévre — ekkor vagy
  morfológiai könyvtár kell, vagy vissza a semleges „Szundi (altató)"
  alakhoz.

## Ellenőrzés

```
python -m pytest tests/egyseg/test_kapuor.py tests/egyseg/test_orchestrator.py
python feladat.py golden --halmaz beszedhelyzetek --ertelmezo forditott
python -m ui.vasarlo      # írd be: „helló." — a válasznak fel kell sorolnia a boltokat
```

Az `elso_talalkozas` golden réteg (8 eset) az első négy fordulót SZÓ
SZERINT tartalmazza — a várt válasszal, nem azzal, ami történt.

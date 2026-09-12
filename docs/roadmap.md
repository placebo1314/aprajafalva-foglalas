# Aprajafalvi időpontfoglaló — Ütemterv

*Kísérő dokumentum: `blueprint.md`*

---

## Vezérelv

Minden mérföldkő önmagában szállítható. A sorrend nem véletlen:

- a **mag** előbb, mint bármi, ami rá épül
- a **beosztásszerkesztő** előbb, mint az asszisztens — mert üres naptáron a
  legjobb asszisztens is haszontalan
- a **golden set** előbb, mint a modellválasztás — különben a tesztek a már
  kiválasztott modell erősségeihez igazodnának

---

## M-1 — Spike (egy hét, a többi előtt)

**Állapot: LEZÁRVA (2026-08-16).** A négy szám megvan, részletek:
`spike/EREDMENY.md`. Az SLO-táblázat frissült (blueprint 12. szakasz), de
a válaszidő-SLO-k ideiglenesen FELFÜGGESZTVE maradnak M4 lezárásáig — az
"drámaian rossz" kilépési feltétel valójában bekövetkezett (a mért
válaszidők és a golden-set pontosság is messze a cél alatt), ezért a terv
itt módosult: a fejlesztési sorrend (mag → beosztásszerkesztő →
asszisztens) előbbre veszi a válaszidő-SLO betartását igénylő munkát.

**Nem termék, hanem méréssorozat.** A tervben szereplő SLO-számok ma
feltételezések; ez a hét dönti el, hogy tarthatók-e.

Amit megmérünk:

1. Egy Apache-2.0 licencű modell (Qwen3-4B) hány százalékban ad helyes
   eszközhívást **húsz kézzel írt magyar mondatra**, köztük tájszólásra és
   töredékes beszédre.
2. Mennyi a válaszidő 1, 3 és 5 párhuzamos beszélgetésnél.
3. Mennyi az SQLite írási latenciája 50 egyidejű session szimulálásakor.
4. A `hun-date-parser` a mi dátumkifejezéseink hány százalékát oldja meg.

**Kilépési feltétel:** a négy szám megvan, és az SLO-táblázat frissült valós
értékekre. Ha valamelyik drámaian rossz, a terv módosul — ezért van elöl.

A spike kódja eldobható. Nem lesz belőle alap.

---

## M0 — Foglalási mag

- séma és migrációk (`szervezet_id`, `kulcs_verzio`, `kivetel_nap` már benne)
- slotgenerátor kivételnapokkal
- `muszak_blokk`: `FixBlokk` stratégia (szünet, ebéd, szabad sáv)
- keresés + ajánlatpontozó
- hold-kezelés
- foglalás, **áthelyezés** (atomi), lemondás
- műszak visszavonása
- redakciós réteg
- eseménykibocsátás
- **mentés és helyreállítási próba**
- konkurencia- és DST-tesztek, seed, CLI

**Kilépési feltétel:** a CLI-ből minden művelet elvégezhető, a konkurencia-teszt
zöld, a helyreállítási próba lefut, és a teljes tesztkészlet átmegy SQLite-on és
Postgresen is.

---

## M1 — Admin beosztásszerkesztő

**Állapot: ELKEZDVE (2026-08-16).** `felulet/admin/` — Tkinter, a
legegyszerűbb működő forma. Eddig elkészült:

- naptárnézet (pultok oszlopokban, egyelőre nem húzható, csak
  kattintható), slot/blokk megjelenítés kattintásra
- műszak felvitele (kézzel vagy sablonnal), foglalások listája
  lemondással
- **sablon-műszakok**: mentés egy meglévő műszakból
  (`migraciok/0003_muszak_sablon.sql`), alkalmazás napra/hétre, és hét
  másolása másik hétre (a forrás hét TÉNYLEGES beosztását, nem csak egy
  sablont) — kivételnapok mindkét úton kihagyásra kerülnek
- törzsadat-szerkesztés az UI-ból: bolt/pult/alkalmazott/szolgáltatás
  felvitele és átnevezése, kivételnap felvétele (eddig csak a `seed`-ből
  jöttek)
- **ütközéslista**: kemény kényszert sértő, átfedő és nulla slotot
  generáló (nem kivétel napi) műszakok listázása, a
  `mag/szabalyok/kenyszerek.py`-ra építve

A `mag/api/adminszolgaltatas.py` lett az egyetlen belépési pont a
felület felől — saját SQL-t nem tartalmaz, mindent a `mag/repo/`-n
keresztül végez. Szolgáltatásréteg-tesztekkel lefedve (Tkinter-teszt
nincs). Még nyitva: húzható műszakok, kényszerkapcsolók, profilok,
magyarázó motor.

**Ez a kritikus út.** Ha a foglalás havonta egy-két órára nyílik meg a következő
egész hónapra, akkor addigra ott kell lennie egy hónapnyi beosztásnak.

- naptárnézet, pultok oszlopokban, húzható műszakokkal
- **sablon-műszakok** — enélkül a napi beosztás elviselhetetlen
- törzsadat, kényszerkapcsolók, profilok
- ütközéslista, magyarázó motor

**Kilépési feltétel:** egy hónapnyi beosztás felvitele **percekben mérhető**,
nem órákban.

---

## M2 — Eszközszerződés

**Állapot: KÉSZ (2026-08-21).** `assistant/tools/` — a hat eszköz,
JSON-sémával (v1, `additionalProperties: false`), egységes
hiba-formátummal (`sikeres`/`ok`/`uzenet_kulcs`/`alternativak`), zárt
katalógussal a bolt-/szolgáltatás-azonosításhoz
(`assistant/tools/katalogus.py`). Az ajánlatpontozó (ADR-006,
`core/api/ajanlatpontozo.py`) és a szándékindex
(`core/api/szandekindex.py`) ezzel együtt készült el, mert a
`szabad_idopontok` eszköz nélkülük nem adhatna pontozott jelöltet.
Mind a hat eszköz LLM nélkül hívható és tesztelt (23 teszt,
`tests/egyseg/test_tools.py`).

Hat eszköz JSON-sémával és verziózással:

| Eszköz | Azonosítás |
|---|---|
| `szabad_idopontok` | nem |
| `foglalas_letrehozas` | igen |
| `foglalas_athelyezes` | foglalási kód |
| `foglalas_lekerdezes` | igen, rate limit |
| `foglalas_lemondas` | foglalási kód |
| `bolt_info` | nem |

**Kilépési feltétel:** minden eszköz teszttel lefedve, LLM nélkül hívható.

---

## M3 — Golden set és értékelő

Kétféle eset: **nyelvi** (mondat → eszközhívás) és **szituációs**
(naptárállapot + kérés → mit ajánljon).

A nyelvi esetek **rétegzettek**: köznyelvi, tájszólás, töredékes, szleng,
kognitívan egyszerűsített. Mindegyik külön küszöbbel.

Az induló készlet kézzel készül, és tudottan hiányos. A valós adat a dev mód
hurkából jön — ezért kell a trace-rögzítés az első naptól.

**2026-08-22:** a `python feladat.py golden` fut (`tests/golden/futtato.py`,
tartós modul — a spike korábban ezt nem tudta futtatni, csak
`spike/golden_futtato.py`-val lehetett mérni). A nyelvi készlet 28 esetre nőtt
(22 egyfordulós + 6 többfordulós, alkudozás — szűkítés, tágítás, visszalépés,
napszak-/boltváltás, elutasítás-után-alternatíva). Ez még messze a
kilépési feltétel alatt van; a szituációs esetek egyáltalán nincsenek felvéve.

**2026-08-26:** két halmaz van (`--halmaz nyelvi|robusztus`), együtt
**108 eset**: nyelvi 45, robusztussági 63. A robusztussági halmaz
19 esettel bővült — **ASR-hibaszimuláció** (13. szakasz), hat
hibafajtában, külön mérési bontással. A szituációs esetek továbbra is
hiányoznak, és a kilépési feltétel a NYELVI halmazra vonatkozik: az 45
eset, nem 150-200.

**2026-08-30:** a nyelvi halmaz **51 esetre** nőtt — új réteg a
`mindegy` (6 eset, `igenyel_llm: true`): az ELENGEDETT mező
(`katalogus.MINDEGY`, ADR-024) felismerése, két ellenpróbával („a
mindegyik LISTÁT kér, nem elengedés"). A robusztussági halmaz
változatlanul 68 eset. Együtt **119 eset**.

**2026-08-31:** HARMADIK halmaz — `beszedhelyzetek` (23 eset, 9 réteg,
`--halmaz beszedhelyzetek`). Nem a mondat felszínét méri, hanem a
beszédhelyzetet: nem magának foglal, feltételesen tervez,
összehasonlít, korábbi foglalásra hivatkozik azonosítás nélkül, két
időpontot kér, elköszön, meggondolja magát, közbekérdez, szokatlan igét
használ. Együtt **142 eset** (51 + 68 + 23). A kilépési feltétel MÁSIK
fele viszont ezzel teljesült: **két modell össze van hasonlítva**
(`qwen3.5:9b` vs. `qwen3:8b`, `docs/MODELL_OSSZEHASONLITAS.md`), és a
mérés a prompt-verziókra is kiterjedt (`docs/PROMPT_AB.md`).

**2026-09-05:** mindkét nyelvi halmaz bővült — nyelvi 51 → **55**
(elengedés-ellenpróbák: mikor NEM szabad elengedni; és a MINDEGY
visszavonhatósága), beszédhelyzetek 23 → **28** (sürgetés,
másik csatornára hivatkozás). Együtt **151 eset**. A bővítés azonnal
két hibát talált (`docs/ALTALANOSITAS.md` 2.9c–2.9d) — ez a golden set
tulajdonképpeni haszna: nem a zöld szám, hanem a talált bukás.

**2026-09-12:** a nyelvi halmaz **85 esetre** nőtt — a három
leggyengébb réteg tíz-tíz új esetet kapott, más beszédhelyzetekből
(`docs/HALMAZ_BOVITES_20260912.md`). Együtt **184 eset**. A futtató
mostantól ISMÉTELT mérést is tud (`--ismetles`), és kimondja, ha egy
különbség a szóráson belül van.

**2026-09-19:** a beszédhelyzetek halmaz 31 → **39 eset** — új réteg az
`elso_talalkozas` (8 eset): olyan mondatok, amiket egy a rendszert NEM
ISMERŐ ember mond. A négy alapesete az első IDEGEN próbából való, SZÓ
SZERINT, a helyes válasszal (`docs/BEVEZETES_20260919.md`). Együtt
**192 eset**. A réteg 100% — de a lényeg nem a szám: **a rés azért volt
láthatatlan, mert a halmaz minden esete olyan emberé volt, aki már
tudta, mit akar.** Egy halmaz nem tudja mérni azt a beszédhelyzetet,
amit nem tartalmaz.

**2026-09-20:** a végigjátszás beszélhető módban **ELLENŐRIZ**, nem csak
kiír (`--mod beszelheto`): fordulónként átmegy-e a megszólalás a formai
kapun, és ha a forduló gombot rajzol, kérdez-e a kimondott szöveg —
gomb önmagában néma (ADR-033). A kifogások a végén egyben is
megjelennek, és a kilépőkód is jelzi őket. Ez az első ellenőrzés, ami
nem az ÉRTELMEZÉST méri, hanem azt, hogy **mit kap meg az, aki nem
látja a képernyőt.**

**2026-09-21:** a beszédhelyzetek halmaz 39 → **51 eset** — új réteg a
`tizennyolc` (12 eset): a MÁSODIK idegen próba mondatai, szó szerint.
A barátunk tizennyolc fordulóból foglalt, és a tizedikben azt írta,
hogy „Így nem haladunk előre" (`docs/TIZENNYOLC_FORDULO_20260921.md`).
Együtt **204 eset**.

A halmaz ekkor kapott két új képességet, mindkettőt azért, mert enélkül
a javítás MÉRHETETLEN lett volna: az eset kimondhatja, MELYIK
ÁLLAPOTBAN hangzik el az utolsó fordulója (`allapot:`) — különben a
MEGEROSITES_VAR szűkített sémáját sosem mérnénk —, és a futtató átadja
az értelmezőnek a DEMÓADAT kínálatát (köznyelvi nevekkel), ahogy a
felület is.

**Új mérőszám a golden seten kívül:** az ÚT HOSSZA (első kéréstől a
foglalásig, beszélgetésenként) a `naplo` és a `riport` fejlécében.
Cél: 5 forduló alatt. Ez az első szám, ami nem a fordulót méri, hanem
a beszélgetést.

**Kilépési feltétel:** 150-200 eset — **teljesült** (204, ebből nyelvi
85); futtatható értékelő — **kész**; két modell összehasonlítható —
**kész** (2026-09-05-re öt modell van megmérve ugyanazon a halmazon).
Ami a lezáráshoz még hiányzik: SZITUÁCIÓS esetek (naptárállapot →
ajánlás), azokból ma egy sincs.

---

## M4 — Asszisztens

**Állapot: RÉSZBEN KÉSZ — a determinisztikus fele elkészült
(2026-08-22-ig).** `assistant/orchestrator.py` (ADR-007 állapotgép,
szándék-rétegzéssel: `kovetkezo_kontextus()`), `assistant/interpreter/`
(`Ertelmezo` protokoll + a szabály-alapú `rule_based.py`,
`hun-date-parser`-integrációval), `assistant/valasz/` (magyar
mondatsablonok, nyelvkulcs alatt), `core/api/szandekindex.py`,
`ui/vasarlo.py` (koppintós út). Ez a golden set látható 28 esetén
(22 egyfordulós + 6 többfordulós alkudozás) 100%-ot ad — ez az
**alapvonal**, ami fölé egy tényleges LLM-es értelmezőnek kell
kerülnie, NEM maga a kilépési feltétel teljesülése (lásd lent — ehhez
valódi modell és bővebb golden set kell). **Hiányzik**: maga a
modellválasztás/LLM-integráció, kötött dekódolás, önkonzisztencia-
ellenőrzés, bizalmi jelzés.

- modellválasztás **méréssel** (Apache-2.0 jelölt + Racka ellenőrzőként)
- ~~normalizáló réteg (tájszólás, szleng, elgépelés)~~ — kész, szabály-alapú
- ~~dátumparser (`hun-date-parser` + saját kiegészítés)~~ — kész
- kapuőr (kész, szabály-alapú), kötött dekódolás (LLM-specifikus, hiányzik), ~~válaszsablonok~~ — kész (`assistant/valasz/`)
- ~~szándékindex~~ — kész (`core/api/szandekindex.py`), ~~orchestrator állapotgép~~ — kész (`assistant/orchestrator.py`)
- ~~**zárt kérdésre váltás**~~ — kész; visszaolvasásos megerősítés (részben — "biztosan lefoglaljam?" megvan, teljes visszaolvasás nincs)
- ~~koppintós út párhuzamos felületként~~ — kész (`ui/vasarlo.py`)
- ~~szándék rétegzése (kemény/puha, alkudozás)~~ — kész (`assistant/orchestrator.py::kovetkezo_kontextus`)
- ~~enumeráció-védelem és rate limiting (`foglalas_lekerdezes`)~~ — kész (`assistant/orchestrator.py::_foglalas_lekerdezes`)
- rendszerprompt a lehető legrövidebb legyen, a ritkán használt
  instrukciók feltételes ágba kerüljenek — csak az LLM-integrációval
  együtt dől el, ma még nincs miből (`docs/PLATFORM_TANULSAGOK.md`,
  Vapi-tanulság: "a prompt hossza latencia")

**Kilépési feltétel:** a golden seten a szolgáltatás-azonosítás > 98%, és a
**leggyengébb nyelvi rétegen is > 90%**.

---

## M5 — Dolgozói nézet és értesítés-előállítás

- mai műszak, élő nézet, szünetkérés
- **sorbanállás-panel** (érkezési sorrend)
- foglaláshoz fűzött megjegyzés (redaktált, zárt halmaz)
- értesítések **előállítása** — küldés nélkül
- opcionális értékelés a beszélgetés végén
- **dev mód metrikái közé:** barge-in arány és válaszhossz
  (`docs/PLATFORM_TANULSAGOK.md`, Vapi-tanulság — a magas barge-in arány
  azt jelzi, hogy a rendszer túl hosszan beszél)
- **felület:** prefetch + helyi szűrés a tablet-böngészéshez
  (`docs/PLATFORM_TANULSAGOK.md`, Cal.com-tanulság — a heti slotlista
  elfér a memóriában, a böngészés nulla hálózati kérés)

---

## M6 — Dev mód és finomhangolás

**Állapot: a HANGCSATORNA ELŐKÉSZÍTÉSE elkezdődött (2026-08-26).** Maga
az M6 nem indult el; ami elkészült, az a hang két SZÖVEGOLDALI fele —
az, ami hang nélkül is megépíthető és mérhető.

- ~~**beszélhető kimeneti mód**~~ — kész (`assistant/valasz/beszelheto.py`,
  `szamok.py`): egész mondatok, kimondott számokkal, fordulónként
  legfeljebb két mondattal és egy kérdéssel; a felületen kapcsolható
  (`ui/vasarlo.py`), a végigjátszásban `--mod mindketto`
- ~~**ASR-hibatűrés mérése**~~ — kész (`tests/golden/robusztus.yaml` 13.
  szakasz, 19 eset hat hibafajtában): a Whisper magyar hibái szövegként
  előállítva, külön bontásban mérve
- trace-böngésző, „mi lett volna a helyes válasz"
- rosszra értékelt beszélgetések előre sorolva
- export, LoRA finomhangolás, mérés a golden seten
- állandó mutatók: kiút aránya, félreértés rétegenként, no-show
- **turn-detection idős beszédre hangolva** (`docs/PLATFORM_TANULSAGOK.md`,
  Vapi-tanulság): hosszabb türelmi idő (`waitSeconds`), mint a Vapi
  sales-alapértelmezései; „configure, do not build" elv a barge-inra —
  a VAD/turn-detection a hangkeretrendszer (LiveKit/Pipecat) dolga, nem
  saját fejlesztés; a háttércsatorna („ühüm") elkülönítve a valódi
  közbevágástól, félbeszakításkor a szándékindex adata nem veszhet el

### Mi hiányzik még a hanghoz — és miért nem építjük

Mind a négy **konfiguráció, nem építés** (`docs/PLATFORM_TANULSAGOK.md`,
„configure, do not build"):

| Hiányzik | Mi lesz a dolgunk | Miért nem most |
|---|---|---|
| **ASR** (beszéd → szöveg) | modellválasztás és magyar hangolás mérése, a normalizáló szótár bővítése a tényleges hibákkal | ma szimuláljuk a hibáit; a valódi hibaeloszlást csak éles hangból lehet megismerni |
| **TTS** (szöveg → beszéd) | hangválasztás, sebesség, a kimondott számok ELLENŐRZÉSE (a beszélhető mód épp ezt készíti elő) | a szöveg oldala kész; hang nélkül a hangminőségről nincs mit mondani |
| **Turn-detection** | `waitSeconds` idős beszédre hangolva, háttércsatorna elkülönítve | a keretrendszer (LiveKit/Pipecat) dolga, a paraméter mérés kérdése |
| **Barge-in** | a félbeszakított forduló állapotának megőrzése | a szándékindex (`core/api/szandekindex.py`) már ma is elviseli — de bizonyítani csak hanggal lehet |

Amit a szövegoldali előkészítés **nem old meg**: a válaszidő. A
blueprint 12. szakaszának p95-e (25 s, ADR-022) SZÖVEGES csatornára
szól; hangon 25 másodperc csönd nem türelmi határ, hanem a hívás vége.
Ezt a hangcsatorna bekötésekor újra kell tárgyalni — ADR-022 kiváltó
feltétele.

---

## Az első tíz lépés (M0 első fele)

**1. Csontváz.** Repó, git, `make` célok, `CLAUDE.md`. Még nincs kód.

**2. Döntések rögzítése.**

| ADR | Tárgy |
|---|---|
| 001 | Műszak-központú modell |
| 002 | Az LLM fordít, nem foglal |
| 003 | Kapacitás = 1, UNIQUE index |
| 004 | SQLite + váltási feltételek |
| 005 | Redaktálás tárolás előtt |
| 006 | Ajánlatpontozó: képlet, korlát, küszöbök |
| 007 | Orchestrator = determinisztikus állapotgép |
| 008 | Nincs foglalási ablak; felszabaduló slot azonnal elérhető |
| 009 | Blokkstratégia; v1 fix, áthelyezés kiváltó feltétellel |
| 010 | Nincs roham-üzemmód; a kiszolgálási szint csökkenhet, a képesség nem |
| 011 | Érkezési sorrend + szabad sáv |
| 012 | Értesítés előáll, de nem megy ki |
| 013 | Elsődleges modell Apache-2.0; Racka ellenőrzőként |

**3. Skillek és hookok.** Előbb az eszközök, aztán a munka.

**4. `docs/domain.md` magyarul.** Minden fogalom definíciója, Törpilla-példával.

**5. Séma és migrációk.** A `sema-orzo` átnézi. A platform-varratok már itt
bekerülnek.

**6. Seed adat.** Három bolt, Törpilla három pultja, egy hét beosztás,
kivételnapok.

> GipszJakab: 10 perc vásárlás + 10 perc szünet óránként
> Törpilla: max 2 vásárló óránként + 15 perc szünet
> Hulk Hugan: 4 órás műszak, 15 percenként foglalható, szünet nélkül

**7. Slotgenerátor.** Első teszteset: az egyórás Törpilla-ábra.

**8. Foglalás, hold, áthelyezés, lemondás** — utána **azonnal** konkurencia- és
DST-teszt. Ne haladjunk tovább, amíg nem zöld.

**9. Blokkgenerátor** (`FixBlokk`) — szünet, ebéd, szabad sáv.

**10. Mentés, helyreállítási próba, CLI.** **Ez a mérföldkő:** a mag kész.

---

## Fejlesztői környezet

**Claude Code a fő eszköz.** A `.claude/` alatt hat skill, három agent, hét hook.
A Cowork a `docs/` gondozására opcionális — ugyanazt a konfigurációt olvassa.

**Amit a hookok kikényszerítenek:** modulhatár (a `mag/` nem importál az
`asszisztens/`-ből), SQL csak a `mag/repo/`-ban, migrációk hordozhatósága,
tiltott minták (nyers azonosító, beégetett titok).

---

## Nyitott kérdések

1. **Munkajogi paraméterek** — a 6 óra / 20 perc a végleges érték?
2. **Az annotálás gazdája** — ki csinálja a heti fél órát?

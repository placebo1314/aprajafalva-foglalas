# Aprajafalvi időpontfoglaló — Fogalomtár

*Kísérő dokumentum: `blueprint.md`. Ez a séma és a migrációk alapja — minden
tábla egy itt definiált fogalomra vezethető vissza.*

---

## Hierarchia egy pillantásra

```
szervezet
 └─ bolt
     └─ pult ─── alkalmazott (beosztáson keresztül)
         └─ műszak  (pult + alkalmazott + szolgáltatás + időablak
                      + időtartam + szünetszabály — BEFAGYASZTVA)
             ├─ slot          (kapacitás mindig 1)
             │   ├─ hold      (puha zár, TTL-lel)
             │   └─ foglalás  (végleges, legfeljebb 1 aktív / slot)
             └─ műszakblokk   (szünet | ebéd | szabad sáv)

szolgáltatás ── variáns (kereskedelmi attribútum, nulla ütemezési hatás)
```

---

## Fogalmak

### Szolgáltatás

Ütemezési egység: van saját alapértelmezett **időtartama** (pl. „kis
petárda" — 5 perc). Egy szolgáltatás pontosan egy bolthoz tartozik. A
szolgáltatás jelenik meg a magban (`mag/`) — ez az, amit a slotgenerátor és
az ütemező ténylegesen lát.

### Variáns

**Nem ütemezési egység.** Kereskedelmi attribútum a szolgáltatáson belül
(pl. „piros / sárga / kék" petárda), **nulla hatással** az időtartamra és a
slotra. Nem szerepel a magban, nem jelenhet meg az ütemezőben. Biztonsági
szelep: `varians.idotartam_felulíras` alapból `NULL`, és amíg nincs róla
ADR, az is marad (lásd ADR-003, ahol tisztázódott, hogy a csoportos
foglalás sem ide, sem a slot-kapacitásba nem tartozik — az egy külön,
egyelőre kikapcsolt bővítési pont).

> **Ökölszabály:** ha a döntés megváltoztatja, *mennyi ideig* tart a
> kiszolgálás, az szolgáltatás. Ha csak azt mondja meg, *mit* kap a
> vásárló, az variáns.

### Pult

Fizikai vagy szervezeti kiszolgálóhely egy bolton belül. A pult önmagában
nem hordoz napi ritmust — azt a rajta futó műszakok adják meg egyenként.

### Alkalmazott

A dolgozó, aki egy adott műszakban egy adott pultot kiszolgál. Egy
alkalmazotthoz tartozhat felülbírálás (pl. lassabb/gyorsabb kiszolgálási
idő), ami az öröklődési láncban a szolgáltatás alapértékét módosíthatja,
mielőtt a műszakba fagyna.

### Műszak

**A rendszer központi entitása.** Definíciója:

```
műszak = pult + alkalmazott + szolgáltatás + időablak + időtartam + szünetszabály
```

A slot a **műszakhoz** tartozik, nem a pulthoz és nem a dolgozóhoz — ez a
leggyakoribb modellezési hiba, amit ez a fogalom kizár. „Ma Törpilla, holnap
GipszJakab ugyanazon a pulton" = **két külön műszak**, még akkor is, ha a
pult és a szolgáltatás azonos marad.

A műszak létrehozásakor az öröklődési lánc (lásd **Snapshot** lent)
feloldódik, és a konkrét paraméterek a műszakba íródnak — ettől a
pillanattól a műszak a törzsadattól független, önálló rekord.

### Snapshot (paraméter-befagyasztás)

A műszak létrehozásakor az öröklődési lánc

```
szolgáltatás alapérték → bolt → pult → alkalmazott → MŰSZAK (befagyasztva)
```

feloldódik, és minden paraméter (időtartam, szünetszabály, stb.) konkrét
értékként a műszakba kerül. Ettől kezdve:

- a törzsadat (pl. a szolgáltatás alapértelmezett időtartama) módosítása
  **nem hat visszamenőleg** a már létező műszakra;
- a friss értékek csak egy explicit `muszak_ujraszamol()` hívással
  kerülnek be, sosem automatikusan;
- a befagyasztás a **paraméterekre** vonatkozik, nem a műszak létezésére —
  a műszak önmagában visszavonható (pl. betegség esetén).

Ez a leggyakoribb félreértésforrás a felület felől nézve, ezért ezt ott is
ki kell írni.

### Slot

A műszakon belüli, ténylegesen foglalható időegység. Mérete a műszakba
fagyasztott időtartamtól függ. **Kapacitása mindig 1** — ebből következik a
teljes konkurenciakezelés: egy parciális UNIQUE index szavatolja, hogy egy
slotra legfeljebb egy aktív foglalás létezhessen (lásd ADR-003).

### Műszakblokk (`muszak_blokk`)

A műszakon belüli **nem foglalható** idő — de nem hiány, hanem explicit
rekord, típussal:

```
muszak_blokk.tipus ∈ {szunet, ebed, szabad_sav}
```

Ugyanaz a generálás, ugyanazok a kényszerek, ugyanaz a
stratégia-interfész mindhárom típusra. v1-ben a `FixBlokk` stratégia fut:
generál, nem mozgat, ütközésnél elutasít (lásd ADR-009).

**Szünet:** kemény kényszerek védik — minimum összes szünetidő, maximum
folyamatos munkaidő, munkajogi minimum (6 óra fölött 20 perc, védett
kategória, kapcsolóval nem kikapcsolható), és a szünet nem lóghat ki a
műszakból.

**Ebéd:** a szünet egy típusa (`tipus = 'ebed'`), választható hosszal a
bolt engedélyezett opcióiból, rögzített vagy ablakon belül mozgatható
(`legkorabban` / `legkesobb`).

### Szabad sáv

A műszak azon része, amit **tudatosan nem osztunk ki** foglalásra:

```
muszak.foglalhato_arany   # pl. 0.8 → az óra 20%-a marad nyitva
```

Négy célt szolgál egyszerre: kiszolgálja azt, aki nem foglal (a helyben
érkező, jellemzően idős vásárló „kiútja"), elnyeli a csúszást, puffert ad
hibás foglalásnak, és realisztikus naptárat tart fenn. **A pontozó soha nem
eheti meg a szabad sávot** — ez kemény kényszer, nem preferencia (lásd
ADR-006, ADR-011).

### Hold

**Puha zár**, nem foglalás. A keresés 1-3 jelöltet pontoz, mindegyikre
holdot tesz (TTL alapból 2-5 perc, torlódásnál rövidebb), és csak azokat a
jelölteket ajánlja fel, amelyekre ténylegesen van hold. A hold
session-höz kötött, **nem tartalmaz vásárlóazonosítót**, és ugyanabban a
slotban ül, mint a végleges foglalás — nincs kettős könyvelés.

Két szabály, amit sosem sértünk meg: *csak olyan időpontot mutatunk, amit
tartani is tudunk* (ajánlott jelölt = van rá hold), és *széles kívánságra
nem adunk széles zárat* (a „péntek délelőtt" nem zárolja a délelőttöt,
csak a konkrét jelölteket).

### Foglalás

A hold megerősítéséből született végleges rekord. Egy slotra legfeljebb egy
aktív foglalás létezhet (`allapot <> 'lemondva'`), amit a slot UNIQUE
indexe garantál, nem alkalmazáslogika. Az `idempotencia_kulcs` mező védi az
újraküldött kérés elleni duplázástól.

---

## Végigvezetett példa: Törpilla keddi műszakja

A seed adatból (roadmap, „Az első tíz lépés", 6. pont):

> Törpilla: max 2 vásárló óránként + 15 perc szünet

**1. Szolgáltatás.** Törpilla pultja a „kis petárda" szolgáltatást adja,
aminek a bolti alapértelmezett időtartama 25 perc.

**2. Alkalmazotti felülbírálás.** Törpilla profiljában rögzítve van, hogy ő
óránként legfeljebb 2 vásárlót szolgál ki — ez az öröklődési láncban felül
írja a szolgáltatás alapértékét 30 percre (60 perc / 2 vásárló).

**3. Műszak létrehozása.** Amikor az admin felviszi Törpilla keddi
8:00–16:00 közötti műszakját erre a pultra, az öröklődési lánc feloldódik:

```
szolgáltatás alapérték (25 perc) → alkalmazotti felülbírálás (30 perc)
                                  → MŰSZAK: időtartam = 30 perc (befagyasztva)
```

Ha holnap a „kis petárda" bolti alapértelmezett időtartama 20 percre
változik, a keddi műszak **marad** 30 percen — a snapshot ezt garantálja.

**4. Slotgenerálás.** A 8 órás műszakból, 30 perces slotmérettel, a rendszer
óránként 2 slotot generál — összhangban a „max 2 vásárló óránként"
szabállyal, mert a snapshotolt időtartam már ezt tükrözi.

**5. Szünetblokk.** Minden órára 15 perc szünet kerül beütemezésre
(`muszak_blokk.tipus = 'szunet'`), `FixBlokk` stratégiával: ha egy foglalási
kérés a szünettel ütközne, a rendszer elutasítja, nem tolja el (v1,
ADR-009).

**6. Szabad sáv.** Ha a bolt `foglalhato_arany` értéke 0.8, a műszak
napi kapacitásának 20%-a szándékosan kimarad a foglalható slotok közül —
ezt a helyben, foglalás nélkül érkező vásárlók kapják.

**7. Keresés és hold.** Egy vásárló a chatben azt írja: „kedden délelőtt
szeretnék petárdát venni". A keresés Törpilla keddi műszakjának szabad
slotjait pontozza, 1-3 jelöltet választ ki, és mindegyikre 3 perces holdot
tesz — csak ezeket ajánlja fel.

**8. Foglalás.** A vásárló megerősíti a 9:30-as jelöltet. A hold
foglalássá alakul; a slot UNIQUE indexe garantálja, hogy eközben senki más
nem foglalhatta le ugyanazt a 9:30-as slotot.

**9. Ha Törpilla lebetegszik.** A műszak visszavonásra kerül (nem törlésre)
— az érintett foglalások listázódnak, alternatíva kerül felajánlásra, és
esemény kerül kibocsátásra (`muszak_modosult`). A már befagyasztott
paraméterek (30 perc, szünetszabály) a visszavonásig érvényben maradtak,
tehát a történet visszakereshető.

---

## Kapcsolat a sémához

Ez a fogalomtár közvetlenül leképezhető a `docs/blueprint.md` 3. szakaszában
felsorolt táblákra (`szervezet`, `bolt`, `pult`, `alkalmazott`, `beosztas`,
`szolgaltatas`, `varians`, `csomag`, `csomag_szolgaltatas`, `muszak`,
`muszak_blokk`, `slot`, `foglalas`, `hold`, `vasarlo`, `elerhetoseg`,
`kivetel_nap`, `esemenyek`, `ertekeles`). A séma és a migrációk írásakor ez a
dokumentum a hivatkozási alap — ha egy tábla vagy mező nem vezethető vissza
egy itt definiált fogalomra, az vagy hiányzik innen, vagy nem kellene, hogy
létezzen.

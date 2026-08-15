---
name: foglalasi-mag
description: A foglalási domain szabályai — műszak, slot, hold, szünetblokk, paraméter-öröklődés és snapshot, ajánlatpontozás, konkurenciakezelés. Használd, amikor a mag/ könyvtárban dolgozol, foglalási vagy beosztási logikát írsz vagy módosítasz, ütemezéssel, kapacitással, szünetekkel foglalkozol, vagy el kell dönteni, hogy egy időpont felajánlható-e.
---

# Foglalási mag

## Az alapelv

Ez a modul LLM nélkül, önmagában működik. Minden foglalási döntés itt születik,
determinisztikusan. Az asszisztens csak hívja — sosem dönt helyette.

## A műszak a központi entitás

```
műszak = pult + alkalmazott + szolgáltatás + időablak + időtartam + szünetszabály
```

A **slot a műszakhoz tartozik**, nem a pulthoz és nem a dolgozóhoz. Ez a
leggyakoribb modellezési hiba: „ki hol dolgozik" nem elég, mert ugyanaz a pult
más nap más ritmussal működik.

„Ma Törpilla, holnap GipszJakab ugyanazon a pulton" = **két külön műszak**.

## Slot kapacitása mindig 1

Ebből következik az egész konkurenciakezelés:

```sql
CREATE UNIQUE INDEX ix_foglalas_slot_aktiv
  ON foglalas(slot_id) WHERE allapot <> 'lemondva';
```

Írás mindig:

```sql
INSERT INTO foglalas (...) VALUES (...) ON CONFLICT DO NOTHING;
```

Ha 0 sor keletkezett, valaki megelőzött. **Ne emelj izolációs szintet, ne
számolj, ne zárolj alkalmazásszinten.** Az index a bizonyíték, és SQLite-ban
és Postgresben azonosan viselkedik.

A vesztes ág nem hibaüzenet: azonnal keress alternatívát, tedd rá a holdot,
és azt ajánld fel.

## Paraméter-befagyasztás (snapshot)

A műszak létrehozásakor az öröklődési lánc **feloldódik**, és a konkrét érték
a műszakba íródik:

```
szolgáltatás alapérték → bolt → pult → alkalmazott → MŰSZAK (befagyasztva)
```

Következmények, amiket be kell tartani:

- Törzsadat módosítása **nem hat visszamenőleg** meglévő műszakra.
- Van külön `muszak_ujraszamol()` művelet, ami újra feloldja a láncot. Ez
  explicit, sosem automatikus.
- A felületen ki kell írni, hogy a módosítás csak új műszakokra érvényes.
  Ez a leggyakoribb félreértésforrás.

## Szolgáltatás ≠ variáns

| | Szolgáltatás | Variáns |
|---|---|---|
| Mi | ütemezési egység | kereskedelmi attribútum |
| Példa | „kis petárda" 5 perc | piros / sárga / kék |
| Ütemezési hatás | van (időtartam) | **nulla** |
| Szerepel a magban | igen | nem |

A variáns nem jelenhet meg az ütemezőben. Biztonsági szelep:
`varians.idotartam_felulíras` alapból `NULL`, és amíg nincs ADR róla, az is
marad.

Egy pult egy műszakban **egyféle** szolgáltatást ad → az időtartam műszakon
belül fix → **egy foglalás = egy slot**.

## Hold — puha zár

```
keresés → pontozás → 1-3 jelölt → HOLD mindegyikre → ajánlás
                                                        ↓
                                            megerősítés → foglalás
                                            TTL lejár  → felszabadul
```

- TTL alapból 2-5 perc, torlódásnál rövidebb (akár 90 másodperc).
- A hold a session-höz kötött, **nem tartalmaz vásárlóazonosítót**.
- A hold ugyanabban a slotban ül, mint a végleges foglalás. Nincs kettős
  könyvelés: a keresés a holdolt slotot nem kínálja fel.

**Két szabály, amit sosem sértünk meg:**

1. *Csak olyan időpontot mutatunk, amit tartani is tudunk.* Ajánlott jelölt =
   van rá hold. Ami hold nélkül szerepel listában, arra a szöveg jelzi, hogy
   tájékoztató jellegű.
2. *Széles kívánságra nem adunk széles zárat.* A „péntek délelőtt" nem zárolja
   a délelőttöt, csak a konkrét jelölteket.

## Szünet — mozgatható entitás

A szünet nem hiány, hanem `szunetblokk` rekord. Foglalási ütközéskor a rendszer
megpróbálja **arrébb tolni** a legközelebbi érvényes helyre. Ha nem megy, a
foglalás elutasításra kerül.

**Minden mozgást naplózni kell.** Panaszkezelésnél ez az egyetlen bizonyíték.

Kemény kényszerek — megsértésük elutasítás:

- minimum összes szünetidő
- maximum folyamatos munkaidő
- **munkajogi minimum** (6 óra felett 20 perc) — védett kategória, kapcsolóval
  nem kikapcsolható
- a szünet nem lóghat ki a műszakból

Puha preferenciák — költségfüggvénybe mennek, nem elutasításba:

- dolgozói és bolti időzítési preferencia
- egyenletes vs. összevont elosztás
- ne aprózódjon fel

Az ebédszünet a `szunetblokk` egy típusa (`tipus = 'ebed'`): választható hossz
a bolt engedélyezett opcióiból, rögzített vagy ablakon belül mozgatható
(`legkorabban` / `legkesobb`), `beszamit_kvotaba` jelzővel. Validálni kell a
hossz-jogosultságot: 4 órás műszakba ne kerüljön 2 órás ebéd.

v1: fix generálás + egyszerű mohó áthelyezés. A gördülő kvóta
(`szunet_szabaly.mod = 'rugalmas'`) dokumentált és tesztelt, de **nem generált**.

## Ajánlatpontozó

A keresés nem az első szabad slotokat adja vissza, hanem pontoz:

```
pontszám = w1 * (1 - tényleges_lefedettség)
         + w2 * (1 - várható_lefedettség)
         korlátozva: csak a kért ablakon belül
```

- **tényleges lefedettség**: aktív holdok és foglalások a slot körüli sávban
- **várható lefedettség**: szándékindexből + kézzel jelölt „népszerű sáv"
  (történeti adat majd később)
- **illeszkedés**: ez **korlát, nem súly**

A korlát a lényeg. Ha valaki péntek délelőttöt kért, nem ajánlunk csütörtök
délutánt csak azért, mert ott üres a naptár. A ritkaság a kért ablakon *belül*
rendez.

Mellékhaszon: ez megoldja az ajánlatszórást is. Két egyidejű session közül a
második már látja az első holdját, tehát más pontszámot kap. Nem kell külön
forgatási logika.

## Szándékindex

Session-szintű, **memóriában**, csúszó TTL-lel (5-10 perc). Nem adatbázis.

```python
{bolt?, szolgaltatas?, het?, nap?, jelolt_slotok[], bizonyossag, utolso_frissites}
```

- **Soha nem blokkol.** Csak jelzés, nem kényszer.
- A vásárló sosem látja.
- **Nem tartalmaz vásárlóazonosítót.** Ez nem stílus, hanem adatvédelmi
  követelmény.
- Interfész: `szandek_frissites()`, `szandek_lekerdezes()`. Mögé később Redis
  kerülhet változatlan interfésszel.

## Eseménykibocsátás

Minden állapotváltozás eseményt ír az `esemenyek` táblába:

```
foglalas_letrejott, foglalas_lemondva, hold_lejart,
szunet_athelyezve, muszak_modosult, slot_felszabadult
```

Erre épül majd a dolgozói élő nézet, az értesítés, a várólista és a statisztika
— mind külön modulként, a mag módosítása nélkül. **Ne hagyd ki egyik művelet
végéről sem.**

## Idempotencia

A `foglalas.idempotencia_kulcs` mező miatt egy újraküldött kérés nem duplázhat.
Hálózati hiba, felhasználói dupla kattintás, hangcsatorna ismétlés — mind ide
fut be.

## Amit sosem csinálunk a magban

- LLM-hívás bármilyen formában
- Helyi idő tárolása (minden UTC)
- Autoincrement kulcs
- SQL a `mag/repo/`-n kívül
- Csendes elutasítás — az elutasításnak mindig van gépi olvasható oka, amit a
  magyarázó motor fel tud oldani

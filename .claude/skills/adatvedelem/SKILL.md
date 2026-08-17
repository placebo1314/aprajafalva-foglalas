---
name: adatvedelem
description: Személyes adatok kezelése — HMAC-hashelés, redaktálás tárolás előtt, megőrzési idők, automatikus törlés, hitelesítés foglalási kóddal, enumeráció-védelem. Használd, amikor vásárlói adattal, azonosítóval, névvel, telefonszámmal dolgozol, trace-t vagy naplót írsz, lemondást vagy módosítást hitelesítesz, illetve bármikor, amikor személyes adat kerülhet lemezre.
---

# Adatvédelem

## A kockázat

Aprajafalván minden lakosnak egyedi számsora van, ami névvel együtt
egyértelműen azonosít. Ez **nemzeti azonosító jellegű adat**, kiemelt
kezeléssel. Egy kiszivárgott napló itt nem kellemetlenség, hanem
adatvédelmi incidens.

## Az azonosító sosem kerül lemezre nyersen

```python
# privacy/hash.py
import hmac, hashlib

def hash_azonosito(nyers: str, pepper: bytes) -> str:
    return hmac.new(pepper, nyers.encode("utf-8"), hashlib.sha256).hexdigest()
```

- A **pepper külön kulcstárolóban** van, nem az adatbázisban. Ha egy fájlban
  lenne a hash-ekkel, semmit nem érne.
- A keresés a hash-en történik, tehát a nyers érték soha nem kell lekérdezéshez.
- A `vasarlo` tábla `vasarlo_kulcs` oszlopa ez a hash. Nyers azonosítót tároló
  oszlop nincs, és nem is kerül bele.

Egy hook blokkolja a `nyers_azonosito` szimbólum használatát a
`privacy/` modulon kívül.

## Redaktálás — tárolás ELŐTT

Ez a sorrend nem ízlés kérdése. Ha utólag redaktálunk, a nyers adat egy
pillanatra lemezre került, és a biztonsági mentésben örökre ott marad.

```
beszélgetés → REDAKTÁLÓ → trace tárolás
                  ↓
        <NEV>, <AZONOSITO>, <TELEFON>
```

A tanításhoz ez elég, sőt jobb: a modellnek a mondatszerkezetet kell
megtanulnia, nem konkrét törpök nevét.

Az annotátor szerepkör soha nem lát azonosítható adatot. Ez nem hozzáférési
beállítás kérdése — az adat egyszerűen nincs ott.

## Megőrzés és automatikus törlés

| Adat | Meddig |
|---|---|
| Név | amíg van jövőbeli foglalás |
| Foglalás részletei | teljesülés + ~30 nap panaszablak |
| `vasarlo_kulcs` (hash) | statisztikához megmaradhat |
| Redaktált trace | a finomhangolási cél élettartamáig |

A törlés **ütemezett feladat**, nem kézi művelet. A nem-törlés a leggyakoribb
adatvédelmi hiba, és mindig ugyanúgy keletkezik: valaki majd megcsinálja.

```python
# ütemezve, naponta
def lejart_adatok_torlese(conn, most): ...
```

A törlési kérelemnek el kell érnie a trace-eket is. Ha egy trace nem
kereshető vissza `vasarlo_kulcs` alapján, akkor vagy redaktált (jó), vagy
törölhetetlen (baj).

## Jogalapok szétválasztva

| Cél | Jogalap |
|---|---|
| Foglaláskezelés | szerződés teljesítése |
| Modell-finomhangolás | **külön cél** — jogos érdek vagy hozzájárulás |
| Hangfelvétel | hozzájárulás, tájékoztatással a hívás elején |

A második sor a fontos: a foglaláshoz megadott adat nem használható
automatikusan tanításra. Ezért van külön jelző a trace-en.

## Hitelesítés

**A számsor nem titok.** Kiszámítható, ismerhető, kikövetkeztethető — tehát
nem hitelesítő. Ezt a tervezés elején kell eldönteni, mert utólag fájdalmas.

| Művelet | Mi kell hozzá |
|---|---|
| Időpontok böngészése | **semmi** |
| Foglalás véglegesítése | azonosítás |
| „Mik a foglalásaim" | számsor + név, erős rate limiting mellett |
| Lemondás, módosítás | **foglalási kód** (magas entrópiájú, csak a foglaló kapja) |

Hangcsatornán: DTMF bevitel vagy visszahívott szám.

## Enumeráció-védelem

Létező és nem létező azonosítóra **azonos válasz és azonos válaszidő**.
Különben a rendszer azonosítótesztelő szolgáltatássá válik.

```python
# rossz: "Nincs ilyen vásárló"
# jó:    "Ha van foglalás ezekkel az adatokkal, elküldtük a részleteket"
```

Ehhez járul: erős rate limiting, minden lekérdezés naplózása (hash-elt
kulccsal), és gyanús mintázatra riasztás.

## Névtelen böngészés

Időpontok megnézéséhez semmi nem kell. Azonosítás csak a véglegesítésnél.

Ez adatvédelmileg tiszta és a vásárlónak is kellemesebb — a törpök igényei
között a negyedik helyen szerepel, hogy ne faggassák feleslegesen.

## Amit sosem naplózunk

- nyers azonosító számsor
- teljes név (csak `vasarlo_kulcs`)
- telefonszám
- a beszélgetés nyers szövege redaktálás nélkül
- pepper, kulcs, jelszó bármilyen formában

Ha hibakereséshez mégis kellene, a válasz nem az, hogy „csak fejlesztéskor" —
a fejlesztői gép is gép, a napló is fájl.

## DPIA

Kis léptéknél nem feltétlenül kötelező, de a nemzeti azonosító jellegű adat és
a hangfelvétel együtt közelít a küszöbhöz. Készüljön egy rövid, dokumentált
mérlegelés a `docs/` alatt — ha később kérdés lesz, ez a bizonyíték, hogy
végiggondoltuk.

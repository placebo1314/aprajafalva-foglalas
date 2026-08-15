# ADR-012: Értesítés előáll, de nem megy ki

- **Dátum:** 2026-08-15
- **Állapot:** elfogadott

## Kontextus

A foglaláshoz kapcsolódó eseményekhez (létrejött, áthelyezve, műszak
elmarad, pultos változott) hasznos lenne értesítést küldeni a vásárlónak.
A küldéshez azonban külső SMS- vagy e-mail-szolgáltató kellene, ami
adatfeldolgozó, és ütközik a „minden lokálisan fut" elvvel.

## Döntés

v1-ben az értesítő üzenet előáll, de nem kerül kiküldésre; a küldés
szolgáltató-interfész mögött van, alapból kikapcsolva.

## Miért

- Külső SMS/e-mail-szolgáltató bevonása adatfeldolgozói szerződést és
  adatvédelmi felülvizsgálatot igényelne, ami ma nincs kész.
- Az üzenet-előállítás önmagában is hasznos és tesztelhető (dolgozói/admin
  nézet, dev mód), a küldés bekapcsolása ettől függetlenül dönthető később.
- Az üzenet már ma is a minimumot tartalmazza (időpont, bolt, kód — nevet és
  terméket nem), tehát a jövőbeli bekapcsolás nem igényel újratervezést.

## Amit feladunk

A vásárlói bizalom egy elemét: visszaigazolás nélkül (csak a felületen
látott kód) a vásárló nem kap emlékeztetőt, ami főleg a hosszú
előrefoglalásnál (hónapokkal előre) növelheti az elfelejtett/no-show
foglalások arányát.

## Kiváltó feltétel

- a no-show arány (dev mód mutatója) 15% fölé emelkedik két egymást követő
  hónapban
- az adatfeldolgozói szerződés és adatvédelmi felülvizsgálat egy konkrét
  SMS/e-mail szolgáltatóval lezárul

## Váltás mire

A szolgáltató-interfész mögötti tényleges küldő implementáció bekapcsolása
(pl. SMS-átjáró), konfigurációs kapcsolóval boltonként.

## Váltás költsége

Alacsony a kódban (interfész már kész), magas a jogi/adatvédelmi
előkészítésben (DPA, felülvizsgálat).

## Ellenőrzés

A dev mód no-show mutatójának trendje; az adatvédelmi felülvizsgálat
lezárását dokumentum (DPA) igazolja.

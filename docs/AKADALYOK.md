# Akadályok és döntési pontok — 2026-08-16

Nem volt olyan elakadás, ami miatt egy feladatot ki kellett volna hagyni —
mind a hét pont elkészült, teszttel és lint-tel zölden. Ez a fájl a
menet közben hozott, nem magától értetődő döntéseket rögzíti, hogy
utólag visszakereshetők legyenek.

## 1. Új migráció a "ne módosítsd a mag/repo/ invariánsait" tiltás alatt

A "sablon mentése" (4. feladat) csak akkor ér valamit, ha a sablon
**túléli az alkalmazás újraindítását** — egy csak-memóriabeli sablon nem
oldaná meg az M1 kilépési feltételét ("egy hónapnyi beosztás percekben").
Ehhez perzisztens tárolás kellett: új `muszak_sablon` tábla,
`migraciok/0003_muszak_sablon.sql`-ként.

Értelmezés: a tiltás ("ne módosítsd a mag/repo/ invariánsait") a
**meglévő** invariánsokra vonatkozik (parciális UNIQUE index, HMAC-only
azonosító, UTC-only idő, stb.) — nem arra, hogy új migráció egyáltalán
nem készülhet. A CLAUDE.md maga is a migrációt jelöli ki a séma-bővítés
sanctioned útjaként ("Migrációk sorszámozva... Kézi sémamódosítás soha").
Az új tábla egyetlen meglévő kényszert sem érint, up/down mindkét irányba
tesztelve (lásd `tesztek/egyseg/test_muszak_slot.py`).

Ha ez az értelmezés téves, a migráció egy paranccsal visszagörgethető
(`migracio.visszagorget(conn, sorszamig="0002")`), a rá épülő
`mag/repo/sablon_repo.py` és a hozzá tartozó `mag/api/adminszolgaltatas.py`
függvények pedig önállóan törölhetők — nincs más modul, ami rájuk épül.

## 2. Az ütközéslista két küszöbértéke provizórikus

A `mag/szabalyok/kenyszerek.py::ellenoriz()` két paramétere
(`min_osszes_szunet_perc`, `max_folyamatos_munka_perc`) a modul saját
docstringje szerint bolt-/profilfüggő, "nincs bennük egyetlen helyes
érték". Mivel a profilrendszer (blueprint 11. szakasz, "Kényszerkapcsolók")
még nem épült meg, az `utkozeslista()` egy ÁTMENETI alapértéket használ
(20 perc, 360 perc) — ezt bármikor felül lehet írni híváskor, és nem
tekintendő törzsadatban rögzített, végleges szabálynak.

## 3. Menet közben talált és javított hiba

Az admin UI-ban (`felulet/admin/app.py`) egy bolt hozzáadása vagy
átnevezése után a bolt-legördülő visszaugrott az ábécé szerint első
boltra, elveszítve a felhasználó aktuális kiválasztását — ez nem a
feladat része volt, de kézi végigpróbáláskor kiderült, és mivel közvetlenül
érintette a most épített funkciót, helyben javítottam
(`_bolt_lista_frissitese`, ami megtartja a kiválasztást, ha a bolt még
létezik).

## 4. Korábbi (M-1 spike) nyitott pontok — nem ebben a körben keletkeztek

Ezeket a `spike/EREDMENY.md` már dokumentálja, itt csak jelzem, hogy nem
lettek pótolva: Racka-4B nem futtatható lokálisan (kapuzott licenc, kézi
GGUF + `ollama create` kellene), a hun-date-parser könyvtár közvetlen
pontossága nincs JSON-artifactként rögzítve.

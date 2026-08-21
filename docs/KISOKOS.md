# Kisokos

Ez a dokumentum azoknak szól, akik még sosem látták a projektet. Nem kell
hozzá programozói vagy adatbázis-tudás.

## Mit csinál a rendszer, három mondatban

Aprajafalva három boltjában a törpök időpontot foglalhatnak — ma még nem
maguktól, hanem az admin visz fel egy beosztást, amiből a rendszer
szabad időpontokat generál. A rendszer garantálja, hogy egy időpontot
soha ne foglaljon le két törp egyszerre, még akkor sem, ha egyszerre
próbálkoznak. Később egy magyarul beszélő gép is bekerül, ami a törpök
hétköznapi mondatait fordítja le foglalássá — de ez a rész még nincs
megépítve.

## Hogyan indítsd el

### Előfeltételek

- **Python 3.11 vagy újabb.** Nyiss egy parancssort, és írd be:

  ```
  python --version
  ```

  Ha ez hibát ad, próbáld `python3 --version`-nel — van, ahol így hívják.
- **Git.** Ha a projektet már letöltötted, ez megvan.

Semmi mást nem kell telepíteni. Nincs szükség Node.js-re, Docker-re,
adatbázis-szerverre.

### Telepítés

Nyiss egy parancssort a projekt mappájában, és futtasd:

```
pip install ruff pytest
```

### Első futtatás

```
python feladat.py seed
```

Ez létrehoz egy `aprajafalva.db` nevű fájlt a projekt gyökerében, benne
három bolttal és egy hétnyi beosztással. A kimenet végén ezt kell
látnod:

```
  szervezet: <egy hosszú azonosító>
  boltok: ['szundi', 'ugyifogyi', 'torpilla']
  műszakok: 21 (ebből 3 kihagyva: kivetel_nap)
  generált slotok összesen: 312
```

Utána futtasd le a tesztkészletet, hogy lásd, minden működik:

```
python feladat.py teszt
```

A végén ezt kell látnod: `182 passed, 1 xfailed`. Az `1 xfailed` nem
hiba — egy szándékosan bukó teszt, ami egy még meg nem írt ellenőrzést
dokumentál (részletek: `docs/ALLAPOT.md`).

## Mit próbálj ki

### 1. Az admin felület

Indítsd el:

```
python -m ui.admin
```

Egy ablak nyílik meg öt füllel: **Naptár és műszakok**, **Foglalások**,
**Sablonok és hét-másolás**, **Törzsadat**, **Ütközéslista**.

1. Kattints a **"Demóadat betöltése"** gombra a tetején. Ha nem futtattad
   még a `python feladat.py seed`-et, ez most létrehozza az adatbázist.
2. A **Naptár és műszakok** fülön válassz ki egy boltot a legördülőből
   (pl. "torpilla") — meg kell jelennie egy naptárrácsnak, oszloponként a
   pultokkal, benne a heti műszakokkal.
3. Kattints egy műszakra a rácsban — jobb oldalt meg kell jelennie a
   részleteinek (kezdet, vég, időtartam).
4. Menj a **Törzsadat** fülre, és vegyél fel egy új boltot a "Hozzáadás"
   gombbal — meg kell jelennie a bolt-listában, és a naptár fülön is
   választható lesz.
5. Menj az **Ütközéslista** fülre, és kattints "Frissítés"-re — egy
   listának kell megjelennie azokról a műszakokról, amik ütköznek a kemény
   kényszerekkel (pl. túl kevés szünet). Ha a demóadat betöltve van, néhány
   találatot mutatnia kell — ez elvárt, nem hiba, a demóadat szándékosan
   tartalmaz ilyen eseteket.

### 2. A verseny-demó

Ez azt bizonyítja be, hogy két egyidejű foglalási kísérlet közül pontosan
egy nyer — sosem foglalja le mindkettő ugyanazt az időpontot.

```
python -m core.api.cli demo-verseny --sessziok 3 --mag 42
```

Amit látnod kell: két "session" ugyanarra a legkorábbi időpontra
próbál zárat (hold-ot) szerezni. Az egyik megkapja, a másik
**"MEGELOZTEK"** üzenetet kap, és egy másik időpontra vált. A végén egy
**"FOGLALÁS LÉTREJÖTT"** sor jelenik meg minden sikeres foglaláshoz, egy
kóddal. A `--mag` szám (itt 42) determinisztikussá teszi a lefutást —
ugyanazzal a számmal mindig ugyanaz történik, ez a visszakereshetőség
miatt fontos, nem véletlen.

## Gyakori hibák és megoldásuk

| Hiba | Megoldás |
|---|---|
| `'python' is not recognized...` (Windows) vagy `command not found: python` (macOS/Linux) | A Python nincs telepítve, vagy nincs a PATH-on. Telepítsd a [python.org](https://python.org)-ról, telepítéskor pipáld be az "Add to PATH" opciót. macOS/Linuxon próbáld `python3`-mal. |
| `ModuleNotFoundError: No module named 'pytest'` vagy `'ruff'` | Futtasd: `pip install ruff pytest`. Ha ez sem megy, próbáld `python -m pip install ruff pytest`-tel. |
| `sqlite3.OperationalError: no such table` | Az adatbázis vagy nincs migrálva, vagy üres. Futtasd előbb: `python feladat.py seed` (ez migrál is). |
| Ékezetes betűk (ő, ű, á) kockaként vagy kérdőjelként jelennek meg a Windows konzolon | A `feladat.py`-n keresztül futtatott parancsok ezt automatikusan kezelik. Ha közvetlenül futtatsz egy `python -m ...` parancsot és mégis elromlik, állítsd be előtte: `set PYTHONUTF8=1` (Windows) vagy `export PYTHONUTF8=1` (macOS/Linux). |
| Az admin felület ablaka nem nyílik meg, `TclError` vagy hasonló | A Tkinter hiányzik a Python-telepítésből. Windows/macOS hivatalos telepítőnél ez alapból benne van; Linuxon lehet, hogy külön csomag kell (pl. `sudo apt install python3-tk`). |

## A fájlok térképe

| Könyvtár | Mire való |
|---|---|
| `core/` | A foglalási logika — séma-hozzáférés, slotgenerálás, foglalás, hold, mentés. Ez fut LLM nélkül is. |
| `ui/` | Az admin felület (Tkinter). |
| `assistant/` | A leendő magyar nyelvi asszisztens helye — ma még csak üres vázkönyvtárak, nincs benne kód. |
| `privacy/` | A leendő adatvédelmi réteg (redaktálás) helye — ma még üres vázkönyvtár. |
| `seed/` | A demóadat betöltője. |
| `tests/` | A tesztkészlet, benne a golden set is (`tests/golden/`). |
| `migrations/` | Sorszámozott adatbázis-migrációk. |
| `tools/` | Fejlesztői segédszkriptek (pl. új migráció váza). |
| `spike/` | Az M-1 mérési kód — eldobható, nem lesz belőle alap. |
| `docs/` | Ez a dokumentum, a terv, az ütemterv, a döntési feljegyzések. |

## Szótár

- **Műszak** — egy pult, egy alkalmazott, egy szolgáltatás és egy
  időablak együtt, egy napra. Ebből lesznek a foglalható időpontok.
- **Slot** — egy ténylegesen foglalható időegység a műszakon belül.
  Mindig pontosan egy vásárló férhet bele.
- **Hold** — egy pár perces "foglalva tartás", mielőtt a foglalás
  véglegesedik. Ez akadályozza meg, hogy két vásárló egyszerre
  "csússzon be" ugyanarra az időpontra.
- **Blokk** — a műszak nem foglalható része: szünet, ebéd, vagy
  szándékosan üresen hagyott sáv.
- **Szabad sáv** — a műszaknak az a része, amit szándékosan nem osztunk
  ki foglalásra, hogy maradjon hely a helyben, foglalás nélkül
  érkezőknek is.
- **Snapshot** — amikor egy műszakot felviszünk, a rá vonatkozó
  beállítások (időtartam, szünetszabály) "belefagynak" — ha utána a
  törzsadat megváltozik, a már felvitt műszakot ez nem érinti.

Ez a szótár rövidített, laikus változata a `docs/domain.md`-nek — ott
minden fogalomhoz tartozik egy részletesebb magyarázat és egy
végigvezetett példa.

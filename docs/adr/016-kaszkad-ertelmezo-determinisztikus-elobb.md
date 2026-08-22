# ADR-016: Kaszkád értelmező — determinisztikus előbb, LLM csak kiegészít

- **Dátum:** 2026-08-22
- **Állapot:** elfogadott — **megerősítve 2026-08-22-én** (ADR-018: a
  fordított sorrendet megmértük, rosszabbnak bizonyult, ez a döntés
  marad hatályban)
- **Megjegyzés a számozáshoz:** a 015 szándékosan kimaradt — sem a
  git-történetben, sem a repóban nem szerepelt korábban 015-ös ADR;
  ellenőrizve (2026-08-22), a szám emiatt véglegesen kimarad, nem kerül
  utólag felhasználásra (`adr` skill, "Számozás és hely").

## Kontextus

Az M4 asszisztensnek végül valódi LLM-integrációra van szüksége — a
determinisztikus `SzabalyAlapuErtelmezo` (`rule_based.py`) egy
alapvonal, nem helyettesíti a modellt a nyelvi sokféleségre (blueprint
7. szakasz). A kérdés: milyen SORRENDBEN kombináljuk a két réteget.

Mérés (`python feladat.py golden --ertelmezo szabaly|llm|kaszkad`, a
látható golden seten, `qwen3.5:9b`, rövid rendszerprompttal,
`think: false`):

| Értelmező | Összesített | Leggyengébb réteg | Átlagos válaszidő |
|---|---|---|---|
| `szabaly` | 100,0% | 100,0% (alkudozas) | ~0,00 s |
| `llm` | 26,8% | 0,0% (alkudozas) | ~7,12 s |
| `kaszkad` | 100,0% | 100,0% (alkudozas) | ~1,76 s |

A `kaszkad` réteg-megoszlása (melyik réteg oldotta meg az utolsó
fordulót): **szabaly=28, llm=0** — a látható halmazon a determinisztikus
réteg minden esetet önállóan megold (ez már korábban is így volt, l.
`docs/ALLAPOT.md`), a modell egyetlen esetben sem járult hozzá
ÉRDEMBEN a végeredményhez. Ahol a `KaszkadErtelmezo` mégis meghívta a
modellt (a `visszakerdez`-re jutó, hiányzó `bolt_id`-s esetekben), ott a
modell javaslatát vagy eldobta (érvénytelen bolt), vagy az azzal
újrafuttatott determinisztikus parser is visszakérdezésre jutott — a
`kaszkad` ilyenkor a szabály-alapú válasz mellett maradt, amely már
eleve helyes volt. **Ez a mérés korlátja, nem az elvé**: a látható
halmaz pontosan azokra a mintákra épül, amiken a szabály-alapú réteg
már bizonyítottan jól teljesít — a modell tényleges hozzáadott értéke
(elgépelés, körülírás, szokatlan szórend) ott várható, ahol a
mintaillesztés ténylegesen elakad, ezt a látható halmaz nem méri.

## Döntés

A kaszkád mindig a determinisztikus `SzabalyAlapuErtelmezo`-t futtatja
ELŐSZÖR, és a modellt kizárólag a hiányzó `bolt_id` kiegészítésére hívja
— soha nem fordítva, és soha nem a modell dönt elsőként.

## Miért

- **Mérve gyorsabb és pontosabb önmagában.** A determinisztikus réteg a
  látható halmazon 100%-ot ad, nulla hívási latenciával; a modell
  önmagában (rövid prompttal) 26,8%-ot, ~7 s/hívással. Ha a
  determinisztikus réteg elég, a modellhívás tiszta veszteség
  (költség, latencia, hibalehetőség) hozzáadott érték nélkül.
- **A determinisztikus réteg sosem hallucinál zárt halmazon kívüli
  boltot vagy dátumot** — ezt a kaszkád explicit ki is kényszeríti
  (`assistant/interpreter/kaszkad.py`: a bolt zárt halmazon marad, a
  dátum mindig újrafuttatott determinisztikus parserből jön). Egy
  modell-elsőbbségi sorrendnél ugyanezt utólag kellene ellenőrizni és
  javítani — bonyolultabb, és a hibás első döntés (rossz eszközválasztás
  is) nehezebben javítható utólag, mint egy hiányzó mező kiegészítése.
- **A hangcsatorna válaszidő-SLO-ja** (blueprint §12, ma felfüggesztve
  M4 lezárásáig) a determinisztikus-előbb sorrenddel a leggyorsabb: a
  legtöbb forduló a modellhívást teljesen megúszza.

## Amit feladunk

Egy modell-elsőbbségi felállás rugalmasabb lehetne olyan esetekben,
ahol a teljes mondat együttes (nem csak egy hiányzó mező) értelmezése
segítene — pl. ha a bolt ÉS a dátum egyszerre van körülírva/elgépelve,
a mai kaszkád ezt nem oldja meg (a `_KIEGESZITHETO_MEZOK` csak
`bolt_id`-ra szűkül, `assistant/interpreter/kaszkad.py` dokumentálja).
Ezt tudatosan feladjuk a kiszámíthatóságért és a sebességért.

## Kiváltó feltétel

Bármelyik teljesülése újranyitja a döntést:

- egy jövőbeli, bővebb (150-200 eses, valós beszélgetésekből származó)
  golden seten a determinisztikus réteg önmagában a leggyengébb
  rétegen **< 70%**-ot ad (a mintaillesztés rendszeresen elakad), ÉS
- ugyanazon a réteg-halmazon a modell (megfelelő prompttal) konzisztensen
  **> 90%**-ot ad, ÉS
- a válaszidő-költség (a modell minden fordulóban hívása) belefér a
  hangcsatorna SLO-jába, amint az érvénybe lép (blueprint §12).

## Váltás mire

"Modell-elsőbbségi" kaszkád: a modell dönt elsőként a teljes
eszközválasztásról és minden mezőről, a determinisztikus réteg csak
UTÓLAG validál (zárt halmazok ellenőrzése, dátum felülbírálása a
determinisztikus parserrel) — a három korlát (dátum, zárt halmaz,
réteg-napló) változatlanul megmarad, csak a sorrend és a "ki dönt
elsőként" fordul meg.

## Váltás költsége

Alacsony technikailag — a `KaszkadErtelmezo` az `Ertelmezo` protokoll
mögött van, a hívói felület (`assistant/orchestrator.py`) nem
változna. A tényleges munka a `_KIEGESZITHETO_MEZOK` szűkítés
feloldása és egy validáló-réteg megírása, ami a modell TELJES
válaszát ellenőrzi (nemcsak egy mezőt) — ez a mai kód egyszerű
bővítése, nem újraírás.

## Ellenőrzés

`python feladat.py golden --ertelmezo szabaly|llm|kaszkad`,
rétegenkénti bontással — a `Réteg-megoszlás: szabaly=N llm=M` sor
mutatja, ténylegesen mennyit tesz hozzá a modell. Ha ez a szám egy
bővebb/valós halmazon tartósan nullához közeli marad, az is
információ: azt jelenti, a determinisztikus réteg elég volt, a
modellhívás felesleges.

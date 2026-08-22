# ADR-018: Fordított kaszkád (LLM elöl) — megmérve, elvetve

- **Dátum:** 2026-08-22
- **Állapot:** **elvetve** (a mérés nem igazolta). Az **ADR-016 hatályban
  marad**, a felülírás NEM történt meg.

## Kontextus

Felmerült, hogy az ADR-016 sorrendje (determinisztikus előbb, a modell
csak kiegészít) fordítva helyesebb: a modell értelmezzen, a
determinisztikus réteg legyen a kapu és a tartalék.

Az indok komoly volt, és két részből állt:

1. **Az ADR-016 döntése félrevezető mérésen állt.** A látható golden
   halmaz a szabályokhoz igazodott — a determinisztikus réteg 100%-a
   sosem volt általánosítási mutató (a `docs/ALLAPOT.md` ezt mindig
   jelezte). Az akkori LLM-mérés pedig **few-shot példák nélkül**,
   **normalizálás nélkül** és **determinisztikus dátumfeloldás nélkül**
   futott — vagyis nem a modell képességét mérte, hanem egy hiányos
   promptot.
2. **A determinisztikus réteg mintaillesztéssé nőtt** (bolt-, napszak-,
   lemondás-, áthelyezés-mintalisták), és a nyelvi változatosságot elvi
   okból nem tudja lefedni: minden új megfogalmazás új mintát igényel.

**Az ADR-016 numerikus kiváltó feltétele NEM teljesült** (nincs 150-200
eses, valós beszélgetésekből származó halmaz, és a modell nem adott
>90%-ot). A felülvizsgálatot tehát nem a küszöb indította, hanem az
1. pont: az a gyanú, hogy a korábbi döntés rossz bizonyítékon állt. Ez
önmagában elég ok az újramérésre — de a döntést a mérésnek kellett
eldöntenie, nem az érvelésnek.

## A mérés

A kifogásokat előbb **orvosoltuk**, hogy a fordított felállás a
lehető legjobb formájában induljon:

- **few-shot példák** (`assistant/interpreter/peldak.py`): 8 pár, a
  golden set öt nyelvi rétegéből egy-egy, plusz kapuőr és
  visszakérdezés — szándékosan NEM a golden set mondatai;
- **normalizáló a modell előtt** (tájszólás/szleng/csapdaszó);
- **determinisztikus dátumfeloldás**: a modell szövegesen idézi a
  dátumot (`datum_kifejezes`), a `hun-date-parser` oldja fel; ha a
  modell mégis ISO-dátumot ad, a parser felülbírálja;
- zárt halmazok, foglalási kód a mondatból, bizonyosság-továbbadás.

Mérés a bővített golden seten (36 eset, benne 5 új "nyelvi
változatosság" és 3 "elengedés" eset, amiket szabállyal nem lehet
megoldani), `qwen3.5:9b`:

| Értelmező | Összesített | Leggyengébb réteg | Válaszidő | Réteg-megoszlás |
|---|---|---|---|---|
| `szabaly` | 80,6% | `elengedes` 0% | ~0,00 s | — |
| `llm` | 27,8% | `alkudozas` 0% | ~6,04 s | — |
| **`kaszkad`** (ADR-016) | **86,1%** | `valtozatossag` 40% | ~2,86 s | llm=6, szabaly=30 |
| `forditott` (ez az ADR) | 69,4% | `koznyelvi` 40% | ~6,31 s | llm=36 |

Rétegenként, `szabaly` → `forditott`:

| Réteg | szabaly | forditott | |
|---|---|---|---|
| `valtozatossag` | 20% | **60%** | +40 |
| `elengedes` | 0% | **66,7%** | +66,7 |
| `koznyelvi` | 100% | 40% | −60 |
| `kapuor` | 100% | 50% | −50 |
| `szleng` | 100% | 66,7% | −33 |
| `alkudozas` | 100% | 66,7% | −33 |
| `toredekes` | 100% | 87,5% | −12,5 |
| `egyszerusitett` | 100% | 87,5% | −12,5 |

## Döntés

**Nem fordítjuk meg a sorrendet.** Az ADR-016 (determinisztikus előbb)
hatályban marad, és a `kaszkad.py` marad az éles út. A fordított
felállás `assistant/interpreter/forditott_kaszkad.py`-ként, mért
kísérletként megmarad, `--ertelmezo forditott` kapcsolóval
reprodukálhatóan.

## Miért

- **Összesítetten rosszabb**: 69,4% vs 86,1%. A modell pontosan ott
  javít, ahol az érvelés jósolta (nyelvi változatosság, kemény rész
  elengedése), de **mindent ront, amit a szabályok már jól kezeltek** —
  és a golden set nagyobb része ilyen.
- **A kapuőr romlása különösen súlyos**: 100% → 50%. A témán belül
  tartás a blueprint 10. szakasza szerint kifejezetten NEM a modell
  prompt-fegyelmén múlhat — a mérés ezt megerősítette.
- **Kétszer lassabb** (6,31 s vs 2,86 s), miközben a hangcsatorna
  válaszidő-SLO-ja még csak felfüggesztve van, nem eltörölve.
- A kifogások orvoslása (few-shot, normalizálás, dátum-kapu)
  **érdemben javított a nyers modellen** (27,8% → 69,4%), de nem
  eleget: a determinisztikus kapuk +41,6 pontot mentenek meg, és még
  így is elmarad.

## Amit feladunk

A `valtozatossag` és `elengedes` rétegeken mért nyereséget (+40 és
+66,7 pont). Ez valódi veszteség: ezek épp azok a rétegek, amik az
általánosítást mérik. A mai `kaszkad` ezeken 40%-ot és 100%-ot ad —
az `elengedes`-t a meglévő elengedés-ág megoldja, a `valtozatossag`
marad a leggyengébb pont (40%), és ez a rendszer ma ismert korlátja.

## Kiváltó feltétel

Bármelyik kettő együtt újranyitja:

- egy **erősebb vagy magyarra hangolt modell** (pl. ADR-013 Racka-ága,
  vagy egy finomhangolt változat) a `kaszkad` mai
  réteg-megoszlásában mérve a `koznyelvi` és `kapuor` rétegen **≥ 95%**-ot
  ad — vagyis nem rontja el azt, amit ma a szabályok visznek, ÉS
- a `valtozatossag` réteg a `kaszkad`-dal tartósan **< 60%** marad,
  tehát a mintaillesztés bővítése bizonyítottan nem hoz be többet.

## Váltás mire

A `forditott_kaszkad.py` alapértelmezetté tétele (a modul készen áll,
tesztelve van) — vagy egy köztes felállás: eszközválasztás
(kapuőr + eszköz) determinisztikusan, paraméterkitöltés a modellel.

## Váltás költsége

Alacsony: a modul megvan, `--ertelmezo forditott`-tal bármikor
újramérhető. A tényleges költség a mérés ideje, nem a kód.

## Ellenőrzés

`python feladat.py golden --ertelmezo szabaly|llm|kaszkad|forditott`,
rétegenkénti bontással és réteg-megoszlással. A kiváltó feltétel
mindkét fele közvetlenül leolvasható ebből a kimenetből.

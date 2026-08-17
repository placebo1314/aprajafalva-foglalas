---
name: eszkoz-szerzodes
description: Az asszisztens és a foglalási mag közti eszközfelület — JSON-sémák, kötött dekódolás, verziózás, hibaágak, bizalmi jelzés. Használd, amikor eszközt adsz hozzá vagy módosítasz, JSON-sémát írsz, az assistant/ertelmezo modulon dolgozol, constrained decodingot konfigurálsz, vagy azt tervezed, hogyan kérdezzen vissza az asszisztens.
---

# Eszközszerződés

## Mit jelent

Ez az a felület, amin keresztül az asszisztens a maghoz beszél. **Minden, amit
az LLM tehet, egy eszközhívás.** Nincs más út: nem ír adatbázisba, nem hív
függvényt közvetlenül, nem dönt kapacitásról.

Ha egy új képesség nem fér bele egy eszközbe, az nem az LLM feladata.

## Az eszközök

| Eszköz | Mit csinál | Kell hozzá azonosítás |
|---|---|---|
| `szabad_idopontok` | keresés, pontozott jelöltek + hold | nem |
| `foglalas_letrehozas` | hold véglegesítése | igen |
| `foglalas_lekerdezes` | „mik a foglalásaim" | igen, rate limit |
| `foglalas_lemondas` | foglalási kóddal | foglalási kód |
| `bolt_info` | nyitvatartás, cím, időtartam | nem |

Ennyi. Ha egy hatodik eszköz kerülne be, az ADR-t érdemel — a felület szűkössége
védelem, nem korlát.

## Séma-alapelvek

**Zárt halmazok mindenhol, ahol lehet.** A szolgáltatás nem szabad szöveg,
hanem enum. Így az azonosítás osztályozás, nem generálás.

```json
{
  "name": "szabad_idopontok",
  "input_schema": {
    "type": "object",
    "properties": {
      "bolt_id":        {"type": "string", "enum": ["szundi", "ugyifogyi", "torpilla"]},
      "szolgaltatas_id":{"type": "string", "enum": ["kis_petarda", "nagy_petarda", "nagy_orom", "..."]},
      "datum_tol":      {"type": "string", "format": "date-time"},
      "datum_ig":       {"type": "string", "format": "date-time"},
      "napszak":        {"type": "string", "enum": ["delelott", "delutan", "este", "barmikor"]},
      "session_id":     {"type": "string"}
    },
    "required": ["bolt_id", "szolgaltatas_id", "datum_tol", "datum_ig", "session_id"],
    "additionalProperties": false
  }
}
```

- `additionalProperties: false` mindenhol. Ha a modell kitalál egy mezőt, az
  hiba legyen, ne csendes elnyelés.
- **Dátum sosem szabad szöveg.** A magyar dátumkifejezést a `datum` modul
  fordítja le, nem az LLM. Az eszköz már ISO-8601-et kap.
- `session_id` minden hívásban kötelező — ebből él a hold és a szándékindex.

## Kötött dekódolás

Az értelmező kimenete **mindig** séma-kényszerített. Nem „kérjük meg a modellt,
hogy JSON-t adjon", hanem a dekódolás szintjén tesszük lehetetlenné a
hibás formátumot.

- llama.cpp esetén GBNF nyelvtan, JSON-sémából automatikusan generálva.
- Ha később vLLM-re váltunk, XGrammar a beépített háttér, ugyanezzel a sémával.

A séma tehát nem dokumentáció, hanem futásidejű kényszer. Ezért kell egy
helyen tartani: `assistant/ertelmezo/semak/`.

## Bizalmi jelzés

A kötött dekódolás logprobjaiból mezőnkénti bizalom számolható. A **kritikus
mezőkre** küszöb van:

| Mező | Alacsony bizalom esetén |
|---|---|
| `datum_tol` / `datum_ig` | visszakérdez |
| `bolt_id` | visszakérdez |
| `szolgaltatas_id` | visszakérdez |
| `napszak` | mehet tovább, tág értelmezéssel |

A visszakérdezésről **az orchestrator dönt**, nem az LLM. A modell csak
számot ad, a szabály kívül van.

## Önkonzisztencia

Az értelmező 3-5 futása, majd a JSON eszközhívások **pontos
egyenlőségvizsgálata**. Szabad szövegnél ez nem működne — strukturált
kimenetnél viszont olcsó és megbízható.

Ha a futások nem egyeznek, az önmagában bizonytalansági jelzés → visszakérdezés.

**Hangcsatornán ez kiesik**, mert nincs rá időbudget. Ott a sablonos válasz és
a visszaolvasásos megerősítés veszi át a szerepét.

## Hibaágak

Minden eszköz ugyanazt a hibaformátumot adja vissza:

```json
{
  "sikeres": false,
  "ok": "megeloztek",
  "uzenet_kulcs": "slot_elfogyott",
  "alternativak": [ { "slot_id": "...", "kezdet": "..." } ]
}
```

- `ok` gépi olvasható, zárt halmazból: `megeloztek`, `nincs_szabad_hely`,
  `szabaly_tiltja`, `hitelesites_szukseges`, `ervenytelen_kod`
- `uzenet_kulcs` a válaszsablonra mutat — **az LLM nem fogalmazza meg a
  hibaüzenetet**
- `alternativak` majdnem mindig van. A vesztes ág is legyen kellemes.

## Verziózás

Az eszközök sémái verziózva vannak (`v1`, `v2`). Ha egy séma változik:

1. Új verzió jön létre, a régi marad.
2. A golden set mindkét verzión lefut.
3. A régi verzió eltávolítása külön lépés, ADR-rel.

Ez azért kell, mert a finomhangolt modell egy konkrét sémára tanult. A séma
csendes módosítása a modellt rontja el, és ezt nehéz észrevenni.

## Amit az eszközök nem csinálnak

- nem fogalmaznak magyar mondatot (az a `valasz` modul dolga)
- nem döntenek kapacitásról (az a mag dolga)
- nem tárolnak azonosítót a session-ben
- nem adnak vissza konkrét darabszámot a szabad helyekről — a szűkösség
  jelzése homályos marad, lásd a kommunikációs szabályokat

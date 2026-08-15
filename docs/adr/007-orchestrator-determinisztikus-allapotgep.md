# ADR-007: Orchestrator = determinisztikus állapotgép

- **Dátum:** 2026-08-15
- **Állapot:** elfogadott

## Kontextus

Az LLM nem foglal, csak fordít (ADR-002), de valakinek el kell döntenie,
mikor kérdezzen vissza, mikor váltson zárt kérdésre, és milyen sorrendben
hívja az eszközöket. Ez a döntés rábízható a modellre (agent-loop) vagy egy
explicit, kódolt vezérlőre.

## Döntés

Az orchestrator explicit, kódolt állapotgép — nem prompt-vezérelt
agent-loop —, ami dönt a visszakérdezésről, a zárt kérdésre váltásról és az
eszközhívások sorrendjéről.

## Miért

- A visszakérdezésről az orchestrator dönt, nem az LLM — így a „két
  sikertelen értelmezés után zárt kérdés" szabály (blueprint 7.) garantáltan
  érvényesül, nem a modell aznapi viselkedésén múlik.
- Az állapotátmenetek LLM nélkül, egységteszttel lefedhetők és
  determinisztikusan reprodukálhatók.
- Kiszámítható latencia és hibaág: nincs „a modell úgy döntött, hogy még
  egyszer megkérdez" jellegű nemdeterminizmus.

## Amit feladunk

Azt a rugalmasságot, hogy a modell szabadon alakíthassa a beszélgetés
dramaturgiáját (pl. váratlanul jó kontextusban rövidebb utat találjon);
minden új konverzációs mintához explicit állapotgép-bővítés kell.

## Kiváltó feltétel

- az állapotgép állapotainak száma egy karbantarthatósági küszöb (irányszám:
  30 állapot) fölé nő, és két egymást követő golden futásban legalább 3
  korábban zöld eset bukik
- bizonyítottá válik, hogy egy korlátozott, mérhetően validált LLM-alapú
  tervező a kommunikációs szabályokat (blueprint 7.) legalább ugyanolyan
  arányban tartja be, mint az állapotgép

## Váltás mire

Réteges állapotgép (al-állapotgépek modulonként), vagy explicit
policy-tábla, amit az LLM javasol, de determinisztikus validátor ellenőriz
végrehajtás előtt.

## Váltás költsége

Közepes — az orchestrator már ma is interfész mögött van (eszközszerződés),
az átírás hatása a golden seten mérhető, éles kockázat nélkül bevezethető.

## Ellenőrzés

A `golden-set` skill szituációs esetei és az orchestrator állapotátmenet-
lefedettségi tesztjei.

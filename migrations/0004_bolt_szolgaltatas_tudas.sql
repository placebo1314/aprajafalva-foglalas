-- up

-- Bolti tudás mezők — a `bolt_info` eszköz kikeresi, a modell sosem
-- generálja (docs/blueprint.md 10. szakasz, "Bolti tudás — szerkesztett
-- adat, nem modell-tudás"). Üres alapértékkel indulnak: a "nincs
-- megadva" állapot NEM hiányzó oszlop, hanem üres string — a `bolt_info`
-- eszköznek ez alapján kell eldöntenie, hogy van-e tényleges válasza
-- (üres string = "ezt nem tudjuk", nem NULL-ellenőrzés).
--
-- `megjelenes` a bolton van (hogyan ismerhető fel/néz ki a hely), a
-- `termekleiras`/`ar` a szolgáltatáson (bolt-szinten nem értelmezhető,
-- egy bolton belül szolgáltatásonként más lehet). Az `ar` MA szöveges
-- mező, nem numerikus: az ártájékoztatás egyáltalán nem biztos, hogy
-- engedélyezett (lásd a golden set `kapuor-02` esetét, "tilos:
-- kitalalt_ar") — ez a migráció csak a tárolási helyet teremti meg, a
-- kapuőr-döntést (kiadható-e) nem változtatja meg.
ALTER TABLE bolt ADD COLUMN megjelenes TEXT NOT NULL DEFAULT '';

ALTER TABLE szolgaltatas ADD COLUMN termekleiras TEXT NOT NULL DEFAULT '';
ALTER TABLE szolgaltatas ADD COLUMN ar TEXT NOT NULL DEFAULT '';

-- down

-- SQLite 3.35+ és Postgres is támogatja a DROP COLUMN-t egyszerű,
-- CHECK/index nélküli oszlopokra — itt egyik új oszlopon sincs külön
-- CHECK vagy index, ami ezt megakadályozná.
ALTER TABLE szolgaltatas DROP COLUMN ar;
ALTER TABLE szolgaltatas DROP COLUMN termekleiras;
ALTER TABLE bolt DROP COLUMN megjelenes;

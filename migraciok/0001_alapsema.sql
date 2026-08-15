-- up

-- Törzsadat-táblák: szervezet, bolt, pult, alkalmazott, szolgaltatas,
-- varians, kivetel_nap. Lásd docs/domain.md és docs/blueprint.md 3. szakasz.
--
-- Minden elsődleges kulcs UUID, TEXT oszlopban (uuid.uuid4().hex, 32 karakter).
-- Minden időbélyeg UTC, ISO-8601 szövegként ('____-__-__T__:__:__Z' minta).
-- A `szervezet_id` minden táblán szerepel — platform-varrat: ma egy oszlop,
-- egy sor, később a repo-szintű szűrés alapja (blueprint 13. szakasz). A
-- konzisztenciáját (hogy a bolt_id/szolgaltatas_id tényleg ugyanahhoz a
-- szervezethez tartozik-e) a mag/repo/ réteg tartja fenn íráskor.

CREATE TABLE szervezet (
    id          TEXT PRIMARY KEY,
    nev         TEXT NOT NULL,
    idozona     TEXT NOT NULL,
    letrehozva  TEXT NOT NULL,
    CHECK (length(id) = 32),
    CHECK (length(nev) > 0),
    CHECK (length(idozona) > 0),
    CHECK (letrehozva LIKE '____-__-__T__:__:__Z')
);

CREATE TABLE bolt (
    id            TEXT PRIMARY KEY,
    szervezet_id  TEXT NOT NULL REFERENCES szervezet(id),
    nev           TEXT NOT NULL,
    letrehozva    TEXT NOT NULL,
    CHECK (length(id) = 32),
    CHECK (length(nev) > 0),
    CHECK (letrehozva LIKE '____-__-__T__:__:__Z')
);

CREATE INDEX ix_bolt_szervezet ON bolt(szervezet_id);

CREATE TABLE pult (
    id            TEXT PRIMARY KEY,
    szervezet_id  TEXT NOT NULL REFERENCES szervezet(id),
    bolt_id       TEXT NOT NULL REFERENCES bolt(id),
    nev           TEXT NOT NULL,
    letrehozva    TEXT NOT NULL,
    CHECK (length(id) = 32),
    CHECK (length(nev) > 0),
    CHECK (letrehozva LIKE '____-__-__T__:__:__Z')
);

CREATE INDEX ix_pult_szervezet ON pult(szervezet_id);
CREATE INDEX ix_pult_bolt ON pult(bolt_id);

CREATE TABLE alkalmazott (
    id            TEXT PRIMARY KEY,
    szervezet_id  TEXT NOT NULL REFERENCES szervezet(id),
    bolt_id       TEXT NOT NULL REFERENCES bolt(id),
    nev           TEXT NOT NULL,
    letrehozva    TEXT NOT NULL,
    CHECK (length(id) = 32),
    CHECK (length(nev) > 0),
    CHECK (letrehozva LIKE '____-__-__T__:__:__Z')
);

CREATE INDEX ix_alkalmazott_szervezet ON alkalmazott(szervezet_id);
CREATE INDEX ix_alkalmazott_bolt ON alkalmazott(bolt_id);

-- Szolgáltatás: ütemezési egység, saját időtartammal. Egy szolgáltatás
-- egy bolthoz tartozik (blueprint 3. szakasz).
CREATE TABLE szolgaltatas (
    id                    TEXT PRIMARY KEY,
    szervezet_id          TEXT NOT NULL REFERENCES szervezet(id),
    bolt_id               TEXT NOT NULL REFERENCES bolt(id),
    nev                   TEXT NOT NULL,
    alap_idotartam_perc   INTEGER NOT NULL,
    letrehozva            TEXT NOT NULL,
    CHECK (length(id) = 32),
    CHECK (length(nev) > 0),
    CHECK (alap_idotartam_perc > 0),
    CHECK (letrehozva LIKE '____-__-__T__:__:__Z')
);

CREATE INDEX ix_szolgaltatas_szervezet ON szolgaltatas(szervezet_id);
CREATE INDEX ix_szolgaltatas_bolt ON szolgaltatas(bolt_id);

-- Variáns: kereskedelmi attribútum, nulla ütemezési hatással. Az
-- idotartam_feluliras biztonsági szelep — alapból NULL, és amíg nincs róla
-- ADR, az is marad (blueprint 3. szakasz, docs/domain.md). A CHECK
-- kényszer ezt adatbázis-szinten kikényszeríti: a mező kitöltéséhez a
-- CHECK feloldása kell, ami migrációt és ADR-t igényel.
CREATE TABLE varians (
    id                    TEXT PRIMARY KEY,
    szervezet_id          TEXT NOT NULL REFERENCES szervezet(id),
    szolgaltatas_id       TEXT NOT NULL REFERENCES szolgaltatas(id),
    nev                   TEXT NOT NULL,
    idotartam_feluliras   INTEGER,
    letrehozva            TEXT NOT NULL,
    CHECK (length(id) = 32),
    CHECK (length(nev) > 0),
    CHECK (idotartam_feluliras IS NULL),
    CHECK (letrehozva LIKE '____-__-__T__:__:__Z')
);

CREATE INDEX ix_varians_szervezet ON varians(szervezet_id);
CREATE INDEX ix_varians_szolgaltatas ON varians(szolgaltatas_id);

-- Kivételnap: szervezet vagy bolt szinten (bolt_id NULL = az egész
-- szervezetre vonatkozik). Enélkül a slotgenerátor karácsonyra is generál
-- (blueprint 9. szakasz).
CREATE TABLE kivetel_nap (
    id            TEXT PRIMARY KEY,
    szervezet_id  TEXT NOT NULL REFERENCES szervezet(id),
    bolt_id       TEXT REFERENCES bolt(id),
    datum         TEXT NOT NULL,
    indok         TEXT NOT NULL,
    letrehozva    TEXT NOT NULL,
    CHECK (length(id) = 32),
    CHECK (datum LIKE '____-__-__'),
    CHECK (length(indok) > 0),
    CHECK (letrehozva LIKE '____-__-__T__:__:__Z')
);

CREATE INDEX ix_kivetel_nap_szervezet ON kivetel_nap(szervezet_id);
CREATE INDEX ix_kivetel_nap_bolt ON kivetel_nap(bolt_id);

-- Két külön parciális UNIQUE index, mert NULL-t a UNIQUE nem egyenlít ki:
-- bolt-szintű kivétel egyedi bolt+dátum szerint, szervezet-szintű kivétel
-- (bolt_id NULL) egyedi szervezet+dátum szerint.
CREATE UNIQUE INDEX ix_kivetel_nap_bolt_datum
  ON kivetel_nap(bolt_id, datum) WHERE bolt_id IS NOT NULL;
CREATE UNIQUE INDEX ix_kivetel_nap_szervezet_datum
  ON kivetel_nap(szervezet_id, datum) WHERE bolt_id IS NULL;

-- down

DROP INDEX IF EXISTS ix_kivetel_nap_szervezet_datum;
DROP INDEX IF EXISTS ix_kivetel_nap_bolt_datum;
DROP INDEX IF EXISTS ix_kivetel_nap_bolt;
DROP INDEX IF EXISTS ix_kivetel_nap_szervezet;
DROP TABLE IF EXISTS kivetel_nap;

DROP INDEX IF EXISTS ix_varians_szolgaltatas;
DROP INDEX IF EXISTS ix_varians_szervezet;
DROP TABLE IF EXISTS varians;

DROP INDEX IF EXISTS ix_szolgaltatas_bolt;
DROP INDEX IF EXISTS ix_szolgaltatas_szervezet;
DROP TABLE IF EXISTS szolgaltatas;

DROP INDEX IF EXISTS ix_alkalmazott_bolt;
DROP INDEX IF EXISTS ix_alkalmazott_szervezet;
DROP TABLE IF EXISTS alkalmazott;

DROP INDEX IF EXISTS ix_pult_bolt;
DROP INDEX IF EXISTS ix_pult_szervezet;
DROP TABLE IF EXISTS pult;

DROP INDEX IF EXISTS ix_bolt_szervezet;
DROP TABLE IF EXISTS bolt;

DROP TABLE IF EXISTS szervezet;

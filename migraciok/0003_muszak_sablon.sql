-- up

-- Műszak-sablon: egy elmentett, újra felhasználható műszak-recept (pult,
-- alkalmazott, szolgáltatás, napi időablak órára kerekítve, snapshot-mezők,
-- blokkszabály) — az M1 kilépési feltétele ("egy hónapnyi beosztás felvitele
-- percekben mérhető") ennek ismételt alkalmazásán múlik. Lásd
-- docs/roadmap.md M1 és docs/blueprint.md "Sablon-műszakok" szakasz.
--
-- Ugyanazok a szabályok, mint a 0001/0002-ben: UUID TEXT kulcsok
-- (length = 32), ISO-8601 UTC szöveges idő a `letrehozva`-n, szervezet_id
-- minden táblán. A `kezdet_ora`/`veg_ora` SZÁNDÉKOSAN óra-granularitású
-- egész szám (nem időbélyeg): a sablon dátumtól független — ugyanaz a
-- sablon bármelyik napra/hétre alkalmazható, a konkrét dátumot az
-- alkalmazás pillanatában kapja meg (mag/api/adminszolgaltatas.py). Ez a
-- v1 admin űrlap (felulet/admin/app.py) óra-választóival egyezik; napon
-- átnyúló (éjfél utáni) sablon nem támogatott — ha ez kiváltó feltétellé
-- válik, új migráció kell.
CREATE TABLE muszak_sablon (
    id                    TEXT PRIMARY KEY,
    szervezet_id          TEXT NOT NULL REFERENCES szervezet(id),
    nev                   TEXT NOT NULL,
    bolt_id               TEXT NOT NULL REFERENCES bolt(id),
    pult_id               TEXT NOT NULL REFERENCES pult(id),
    alkalmazott_id        TEXT NOT NULL REFERENCES alkalmazott(id),
    szolgaltatas_id       TEXT NOT NULL REFERENCES szolgaltatas(id),
    kezdet_ora            INTEGER NOT NULL,
    veg_ora               INTEGER NOT NULL,
    idotartam_perc        INTEGER NOT NULL,
    puffer_utana_perc     INTEGER NOT NULL,
    min_racs_perc         INTEGER NOT NULL,
    foglalhato_arany      REAL NOT NULL,
    blokk_szabaly         TEXT NOT NULL,
    letrehozva            TEXT NOT NULL,
    CHECK (length(id) = 32),
    CHECK (length(szervezet_id) = 32),
    CHECK (length(nev) > 0),
    CHECK (length(bolt_id) = 32),
    CHECK (length(pult_id) = 32),
    CHECK (length(alkalmazott_id) = 32),
    CHECK (length(szolgaltatas_id) = 32),
    CHECK (kezdet_ora >= 0 AND kezdet_ora <= 23),
    CHECK (veg_ora >= 1 AND veg_ora <= 24),
    CHECK (veg_ora > kezdet_ora),
    CHECK (idotartam_perc > 0),
    CHECK (puffer_utana_perc >= 0),
    CHECK (min_racs_perc > 0),
    CHECK (foglalhato_arany >= 0 AND foglalhato_arany <= 1),
    CHECK (length(blokk_szabaly) > 0),
    CHECK (letrehozva LIKE '____-__-__T__:__:__Z')
);

CREATE INDEX ix_muszak_sablon_szervezet ON muszak_sablon(szervezet_id);
CREATE INDEX ix_muszak_sablon_bolt ON muszak_sablon(bolt_id);
CREATE INDEX ix_muszak_sablon_pult ON muszak_sablon(pult_id);
CREATE INDEX ix_muszak_sablon_alkalmazott ON muszak_sablon(alkalmazott_id);
CREATE INDEX ix_muszak_sablon_szolgaltatas ON muszak_sablon(szolgaltatas_id);

-- down

DROP INDEX IF EXISTS ix_muszak_sablon_szolgaltatas;
DROP INDEX IF EXISTS ix_muszak_sablon_alkalmazott;
DROP INDEX IF EXISTS ix_muszak_sablon_pult;
DROP INDEX IF EXISTS ix_muszak_sablon_bolt;
DROP INDEX IF EXISTS ix_muszak_sablon_szervezet;
DROP TABLE IF EXISTS muszak_sablon;

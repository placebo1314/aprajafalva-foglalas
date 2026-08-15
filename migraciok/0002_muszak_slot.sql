-- up

-- A projekt legfontosabb migrációja: műszak, slot, foglalás, hold,
-- események. Lásd docs/domain.md és docs/blueprint.md 3-5. szakasz.
--
-- Ugyanazok a szabályok érvényesek, mint a 0001-ben: UUID TEXT kulcsok
-- (length = 32) minden id és idegen kulcs oszlopon, ISO-8601 UTC szöveges
-- idő, minden idegen kulcs indexelve, szervezet_id minden táblán
-- (platform-varrat, blueprint 13. szakasz). A kereszttáblás konzisztenciát
-- (pl. hogy a muszak.szervezet_id megegyezik a pult.szervezet_id-jével)
-- a mag/repo/ réteg tartja fenn íráskor, ugyanúgy, mint a 0001-ben.
--
-- Az összes időoszlopon (kezdet, veg, letrehozva, letrejott, lejar,
-- idobelyeg) a `LIKE '____-__-__T__:__:__Z'` kényszer FORMAI, nem
-- tartalmi ellenőrzés: az aláhúzás bármilyen karakterre illeszkedik, nem
-- csak számjegyre (pl. 'aaaa-aa-aaTaa:aa:aaZ' is átmenne rajta). A valódi
-- számjegy-validálás az alkalmazásrétegben (mag/repo/) történik — a
-- SQLite-specifikus, motorfüggő mintaillesztő kulcsszó tiltott
-- (db-hordozhatosag skill), digit-only CHECK pedig motorfüggetlenül nem
-- írható le ennél egyszerűbben.

-- Műszak: a rendszer központi entitása. A snapshot-mezők (idotartam_perc,
-- puffer_utana_perc, min_racs_perc) a feloldott öröklődési lánc
-- (szolgáltatás alapérték → bolt → pult → alkalmazott) eredménye —
-- létrehozáskor íródnak be, és onnantól függetlenek a törzsadattól
-- (docs/domain.md, "Snapshot" szakasz). A `kezdet`/`veg` az időablak: ennek
-- a konkrét műszak-előfordulásnak a kezdete és vége, nem napi ismétlődés.
CREATE TABLE muszak (
    id                    TEXT PRIMARY KEY,
    szervezet_id          TEXT NOT NULL REFERENCES szervezet(id),
    bolt_id               TEXT NOT NULL REFERENCES bolt(id),
    pult_id               TEXT NOT NULL REFERENCES pult(id),
    alkalmazott_id        TEXT NOT NULL REFERENCES alkalmazott(id),
    szolgaltatas_id       TEXT NOT NULL REFERENCES szolgaltatas(id),
    kezdet                TEXT NOT NULL,
    veg                   TEXT NOT NULL,
    -- Snapshot: a szolgáltatás/alkalmazott öröklődési láncból befagyasztott
    -- konkrét értékek. Törzsadat-módosítás ezekre nem hat visszamenőleg
    -- (csak explicit muszak_ujraszamol()).
    idotartam_perc        INTEGER NOT NULL,
    puffer_utana_perc     INTEGER NOT NULL,
    min_racs_perc         INTEGER NOT NULL,
    -- A műszak azon hányada, amit szándékosan nem osztunk ki foglalásra
    -- (blueprint 4. szakasz, "Szabad sáv"). 1.0 = nincs szabad sáv.
    foglalhato_arany      REAL NOT NULL,
    -- Melyik BlokkStrategia generálja/kezeli a szünetblokkokat ezen a
    -- műszakon (blueprint 4. szakasz, ADR-009), pl. '{"strategia": "FixBlokk"}'.
    -- JSON szövegként — a struktúra érvényességét a mag/repo/ ellenőrzi
    -- íráskor, nem a DB: sem SQLite, sem Postgres nem ad azonos nevű,
    -- azonos szemantikájú JSON-validáló függvényt, ez motorfüggő lenne.
    blokk_szabaly         TEXT NOT NULL,
    allapot               TEXT NOT NULL,
    letrehozva            TEXT NOT NULL,
    CHECK (length(id) = 32),
    CHECK (length(szervezet_id) = 32),
    CHECK (length(bolt_id) = 32),
    CHECK (length(pult_id) = 32),
    CHECK (length(alkalmazott_id) = 32),
    CHECK (length(szolgaltatas_id) = 32),
    CHECK (kezdet LIKE '____-__-__T__:__:__Z'),
    CHECK (veg LIKE '____-__-__T__:__:__Z'),
    CHECK (veg > kezdet),
    CHECK (idotartam_perc > 0),
    CHECK (puffer_utana_perc >= 0),
    CHECK (min_racs_perc > 0),
    CHECK (foglalhato_arany >= 0 AND foglalhato_arany <= 1),
    CHECK (length(blokk_szabaly) > 0),
    CHECK (allapot IN ('aktiv', 'visszavont')),
    CHECK (letrehozva LIKE '____-__-__T__:__:__Z')
);

CREATE INDEX ix_muszak_szervezet ON muszak(szervezet_id);
CREATE INDEX ix_muszak_bolt ON muszak(bolt_id);
CREATE INDEX ix_muszak_pult ON muszak(pult_id);
CREATE INDEX ix_muszak_alkalmazott ON muszak(alkalmazott_id);
CREATE INDEX ix_muszak_szolgaltatas ON muszak(szolgaltatas_id);

-- Műszakblokk: szünet, ebéd vagy szabad sáv — egyetlen entitás, típussal
-- (blueprint 4. szakasz). Hogy a blokk kezdete/vége a saját műszakján
-- belül marad-e ("a szünet nem lóghat ki a műszakból"), azt szintén a
-- mag/repo/ ellenőrzi írásnál — egy CHECK nem tud másik sorra hivatkozni.
--
-- A `legkorabban`/`legkesobb` ablakhatár-mezők (docs/domain.md, "ebéd
-- ablakon belül mozgatható") TUDATOSAN hiányoznak: v1-ben kizárólag a
-- FixBlokk stratégia fut, ami nem mozgat (ADR-009), ezért nincs, ami
-- ezeket olvasná. Ha a MohoAthelyezo stratégia bekapcsolásra kerül
-- (ADR-009 kiváltó feltétele teljesül), ez új migrációt igényel.
CREATE TABLE muszak_blokk (
    id                    TEXT PRIMARY KEY,
    szervezet_id          TEXT NOT NULL REFERENCES szervezet(id),
    muszak_id             TEXT NOT NULL REFERENCES muszak(id),
    tipus                 TEXT NOT NULL,
    kezdet                TEXT NOT NULL,
    veg                   TEXT NOT NULL,
    -- rögzített: a blokk fix helyen van (FixBlokk), nem mozgatható.
    rogzitett             INTEGER NOT NULL,
    -- beszámít a dolgozói munkajogi kvótába (pl. az ebéd választhatóan nem).
    beszamit_kvotaba      INTEGER NOT NULL,
    letrehozva            TEXT NOT NULL,
    CHECK (length(id) = 32),
    CHECK (length(szervezet_id) = 32),
    CHECK (length(muszak_id) = 32),
    CHECK (tipus IN ('szunet', 'ebed', 'szabad_sav')),
    CHECK (kezdet LIKE '____-__-__T__:__:__Z'),
    CHECK (veg LIKE '____-__-__T__:__:__Z'),
    CHECK (veg > kezdet),
    CHECK (rogzitett IN (0, 1)),
    CHECK (beszamit_kvotaba IN (0, 1)),
    CHECK (letrehozva LIKE '____-__-__T__:__:__Z')
);

CREATE INDEX ix_muszak_blokk_szervezet ON muszak_blokk(szervezet_id);
CREATE INDEX ix_muszak_blokk_muszak ON muszak_blokk(muszak_id);

-- Slot: a műszakon belüli, ténylegesen foglalható időegység. A kapacitása
-- mindig 1 — ezt nem itt, hanem a foglalas tábla parciális UNIQUE indexe
-- garantálja (lásd lent, ADR-003). A slot állapotát (szabad/foglalt) soha
-- nem tároljuk külön mezőn: azt a hozzá tartozó aktív foglalás/hold léte
-- dönti el (docs/domain.md, "Slot"; ADR-008, "nincs foglalási ablak").
--
-- A kezdet/veg-nek a saját műszakja időablakán (muszak.kezdet/veg) belülre
-- kell esnie — ezt itt nem lehet CHECK-kel kikényszeríteni (másik sorra
-- hivatkozna), ezt a slotgenerátor garantálja létrehozáskor.
CREATE TABLE slot (
    id            TEXT PRIMARY KEY,
    szervezet_id  TEXT NOT NULL REFERENCES szervezet(id),
    muszak_id     TEXT NOT NULL REFERENCES muszak(id),
    kezdet        TEXT NOT NULL,
    veg           TEXT NOT NULL,
    letrehozva    TEXT NOT NULL,
    CHECK (length(id) = 32),
    CHECK (length(szervezet_id) = 32),
    CHECK (length(muszak_id) = 32),
    CHECK (kezdet LIKE '____-__-__T__:__:__Z'),
    CHECK (veg LIKE '____-__-__T__:__:__Z'),
    CHECK (veg > kezdet),
    CHECK (letrehozva LIKE '____-__-__T__:__:__Z')
);

CREATE INDEX ix_slot_szervezet ON slot(szervezet_id);
CREATE INDEX ix_slot_muszak ON slot(muszak_id);

-- Foglalás. A vasarlo_kulcs HMAC-SHA256 hash (64 hex karakter), soha nem
-- nyers azonosító (CLAUDE.md 2. invariáns); a kulcs_verzio jelzi, melyik
-- pepper-verzióval készült, hogy a rotáció ne érvénytelenítse csendben a
-- régi hasheket. Az allapot ma csak a két, az egyediségi index szempontjából
-- releváns értéket veszi fel — a no-show/teljesült jellegű további
-- állapotok külön migráció és döntés tárgya, amíg a pontos szóhasználat
-- nincs rögzítve.
CREATE TABLE foglalas (
    id                    TEXT PRIMARY KEY,
    szervezet_id          TEXT NOT NULL REFERENCES szervezet(id),
    slot_id               TEXT NOT NULL REFERENCES slot(id),
    vasarlo_kulcs         TEXT NOT NULL,
    kulcs_verzio          INTEGER NOT NULL,
    idempotencia_kulcs    TEXT NOT NULL,
    foglalasi_kod         TEXT NOT NULL,
    allapot               TEXT NOT NULL,
    megjegyzes            TEXT,
    letrehozva            TEXT NOT NULL,
    CHECK (length(id) = 32),
    CHECK (length(szervezet_id) = 32),
    CHECK (length(slot_id) = 32),
    CHECK (length(vasarlo_kulcs) = 64),
    CHECK (kulcs_verzio > 0),
    CHECK (length(idempotencia_kulcs) > 0),
    CHECK (length(foglalasi_kod) > 0),
    CHECK (allapot IN ('aktiv', 'lemondva')),
    CHECK (letrehozva LIKE '____-__-__T__:__:__Z')
);

CREATE INDEX ix_foglalas_szervezet ON foglalas(szervezet_id);
CREATE INDEX ix_foglalas_vasarlo ON foglalas(vasarlo_kulcs);

-- Általános index a slot_id-re — a lenti parciális UNIQUE index csak az
-- aktív sorokat fedi le, egy "az összes (lemondott is) foglalás erre a
-- slotra" lekérdezéshez ez a teljes index kell.
CREATE INDEX ix_foglalas_slot ON foglalas(slot_id);

-- Ez a dupla foglalás elleni EGYETLEN védelem (ADR-003, CLAUDE.md
-- 1. invariáns): parciális UNIQUE index, nem alkalmazásszintű számláló
-- vagy zár. Az írás mindig `INSERT ... ON CONFLICT DO NOTHING` — ha 0 sor
-- keletkezik, valaki megelőzött, ez nem hiba, hanem normál ág.
CREATE UNIQUE INDEX ix_foglalas_slot_aktiv
  ON foglalas(slot_id) WHERE allapot <> 'lemondva';

CREATE UNIQUE INDEX ix_foglalas_idempotencia ON foglalas(idempotencia_kulcs);
CREATE UNIQUE INDEX ix_foglalas_kod ON foglalas(foglalasi_kod);

-- Hold: puha zár, session-höz kötve, nem vásárlóazonosítóhoz
-- (docs/domain.md, "Hold"; a `db-hordozhatosag` skill migrációs sablonja
-- szerint). Egyetlen slotra egyszerre legfeljebb egy hold ülhet.
CREATE TABLE hold (
    id            TEXT PRIMARY KEY,
    szervezet_id  TEXT NOT NULL REFERENCES szervezet(id),
    slot_id       TEXT NOT NULL REFERENCES slot(id),
    session_id    TEXT NOT NULL,
    letrejott     TEXT NOT NULL,
    lejar         TEXT NOT NULL,
    CHECK (length(id) = 32),
    CHECK (length(szervezet_id) = 32),
    CHECK (length(slot_id) = 32),
    CHECK (length(session_id) > 0),
    CHECK (letrejott LIKE '____-__-__T__:__:__Z'),
    CHECK (lejar LIKE '____-__-__T__:__:__Z'),
    CHECK (lejar > letrejott)
);

CREATE INDEX ix_hold_szervezet ON hold(szervezet_id);
CREATE UNIQUE INDEX ix_hold_slot ON hold(slot_id);
CREATE INDEX ix_hold_lejar ON hold(lejar);

-- Események: minden állapotváltozás ide ír (foglalasi-mag skill,
-- "Eseménykibocsátás"). Az entitás két oszlopra bomlik (tipus + id), mert
-- egy esemény sokféle entitásra vonatkozhat (muszak, slot, foglalas, ...)
-- — ezt nem lehet egyetlen valódi FOREIGN KEY-jel kikényszeríteni
-- (több lehetséges szülőtábla), ezért csak hosszellenőrzés van rajta.
CREATE TABLE esemenyek (
    id              TEXT PRIMARY KEY,
    szervezet_id    TEXT NOT NULL REFERENCES szervezet(id),
    -- Szándékosan nincs CHECK IN (...) a tipus oszlopon: az eseménykatalógus
    -- bővül (foglalasi-mag skill, "Eseménykibocsátás" felsorolása csak a
    -- mai készlet), és rajta semmilyen DB-szintű logika nem múlik — ellentétben
    -- a muszak.allapot / foglalas.allapot zárt halmazaival, amelyeket az
    -- egyediségi indexek (pl. ix_foglalas_slot_aktiv) szemantikája használ.
    tipus           TEXT NOT NULL,
    entitas_tipus   TEXT NOT NULL,
    entitas_id      TEXT NOT NULL,
    idobelyeg       TEXT NOT NULL,
    -- JSON hasznos teher szövegként — lásd a muszak.blokk_szabaly
    -- oszlopnál írt indoklást a DB-szintű JSON-validálás mellőzéséről.
    hasznos_teher   TEXT NOT NULL,
    CHECK (length(id) = 32),
    CHECK (length(szervezet_id) = 32),
    CHECK (length(tipus) > 0),
    CHECK (length(entitas_tipus) > 0),
    CHECK (length(entitas_id) = 32),
    CHECK (idobelyeg LIKE '____-__-__T__:__:__Z'),
    CHECK (length(hasznos_teher) > 0)
);

CREATE INDEX ix_esemenyek_szervezet ON esemenyek(szervezet_id);
CREATE INDEX ix_esemenyek_entitas ON esemenyek(entitas_tipus, entitas_id);
CREATE INDEX ix_esemenyek_idobelyeg ON esemenyek(idobelyeg);

-- down

DROP INDEX IF EXISTS ix_esemenyek_idobelyeg;
DROP INDEX IF EXISTS ix_esemenyek_entitas;
DROP INDEX IF EXISTS ix_esemenyek_szervezet;
DROP TABLE IF EXISTS esemenyek;

DROP INDEX IF EXISTS ix_hold_lejar;
DROP INDEX IF EXISTS ix_hold_slot;
DROP INDEX IF EXISTS ix_hold_szervezet;
DROP TABLE IF EXISTS hold;

DROP INDEX IF EXISTS ix_foglalas_kod;
DROP INDEX IF EXISTS ix_foglalas_idempotencia;
DROP INDEX IF EXISTS ix_foglalas_slot_aktiv;
DROP INDEX IF EXISTS ix_foglalas_slot;
DROP INDEX IF EXISTS ix_foglalas_vasarlo;
DROP INDEX IF EXISTS ix_foglalas_szervezet;
DROP TABLE IF EXISTS foglalas;

DROP INDEX IF EXISTS ix_slot_muszak;
DROP INDEX IF EXISTS ix_slot_szervezet;
DROP TABLE IF EXISTS slot;

DROP INDEX IF EXISTS ix_muszak_blokk_muszak;
DROP INDEX IF EXISTS ix_muszak_blokk_szervezet;
DROP TABLE IF EXISTS muszak_blokk;

DROP INDEX IF EXISTS ix_muszak_szolgaltatas;
DROP INDEX IF EXISTS ix_muszak_alkalmazott;
DROP INDEX IF EXISTS ix_muszak_pult;
DROP INDEX IF EXISTS ix_muszak_bolt;
DROP INDEX IF EXISTS ix_muszak_szervezet;
DROP TABLE IF EXISTS muszak;

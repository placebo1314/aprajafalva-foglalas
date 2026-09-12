-- up

-- KÖZNYELVI NEVEK — ahogy a VÁSÁRLÓ hívja a szolgáltatást, nem ahogy a
-- bolt nevezi. Az első idegen próba nyitómondata ez volt: „Szia. Örömöt
-- szeretnék. Van nálatok? Mikor?" — a Törpilla szolgáltatása pedig
-- `nagy_orom` néven „boldogság". A modell nem jutott el az örömtől a
-- boltig, és a rendszer azt kérdezte vissza, melyik boltba szeretne
-- menni: tizennyolc fordulós beszélgetés első fordulója.
--
-- Miért TÖRZSADAT és nem prompt-szöveg: ugyanaz az elv, mint a
-- termékleírásnál (0004., blueprint 10.) — a bolti tudás szerkesztett
-- adat. Ha egy bolt holnap „vidámságot" is árul, azt az admin írja be,
-- nem mi írjuk át a promptot. A prompt ebből ÉPÜL, de nem ez a prompt.
--
-- Tárolás: vesszővel elválasztott lista egyetlen szövegmezőben. Nem
-- külön tábla, mert ez nem entitás: nincs saját azonosítója, nincs rá
-- hivatkozás, és mindig a szolgáltatásával együtt olvassuk. Ha valaha
-- külön kell (súlyozás, nyelvenkénti alak), az már más adat.
ALTER TABLE szolgaltatas ADD COLUMN koznyelvi_nevek TEXT NOT NULL DEFAULT '';

-- down

ALTER TABLE szolgaltatas DROP COLUMN koznyelvi_nevek;

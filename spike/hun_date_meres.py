"""hun-date-parser mérés a golden set dátumkifejezésein — M-1 spike.
ELDOBHATÓ KÓD.

Roadmap M-1, 4. mérés: "A hun-date-parser a mi dátumkifejezéseink hány
százalékát oldja meg." A golden set minden olyan esetét megnézi, ahol a
`varhato` (vagy `megorzott_parameterek`) tartalmaz `datum_tol`-t, lefuttatja
rajta a `hun_date_parser.text2datetime`-ot a golden set `most`
referenciaidejével, és megnézi, hogy a visszaadott bármelyik dátum-jelölt
NAPJA egyezik-e az elvárt `datum_tol` napjával.

Használat:
    python spike/hun_date_meres.py
"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

from hun_date_parser import text2datetime

GYOKER = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(GYOKER))

from spike.golden_futtato import betolt  # noqa: E402


def _elvart_datum_tol(eset) -> str | None:
    varhato = eset.varhato
    param = varhato.get("parameterek") or {}
    if "datum_tol" in param:
        return param["datum_tol"]
    megorzott = varhato.get("megorzott_parameterek") or {}
    if "datum_tol" in megorzott:
        return megorzott["datum_tol"]
    return None


def fut() -> dict:
    meta, esetek = betolt()
    most = datetime.fromisoformat(meta["most_alapertelmezett"])

    dontesek = []
    for eset in esetek:
        elvart = _elvart_datum_tol(eset)
        if elvart is None:
            continue
        elvart_nap = elvart[:10]
        try:
            jelolt = text2datetime(eset.bemenet, now=most)
        except Exception as exc:  # noqa: BLE001 - a mérés szempontjából a kivétel is bukás
            dontesek.append((eset.id, False, f"kivétel: {exc}", elvart_nap, None))
            continue

        talalt_napok = [j["start_date"].date().isoformat() for j in jelolt if j.get("start_date")]
        talalat = elvart_nap in talalt_napok
        dontesek.append((eset.id, talalat, eset.bemenet, elvart_nap, talalt_napok))

    print(f"Dátumkifejezést tartalmazó esetek: {len(dontesek)}/{len(esetek)}\n")
    helyes = 0
    for eset_id, ok, bemenet, elvart_nap, talalt in dontesek:
        jel = "OK  " if ok else "BUKIK"
        print(f"  [{jel}] {eset_id:20s} elvárt={elvart_nap}  talált={talalt}")
        if not ok:
            print(f"          bemenet: {bemenet!r}")
        helyes += ok

    arany = helyes / len(dontesek) if dontesek else 0.0
    print(f"\nHelyes dátumfeloldás: {helyes}/{len(dontesek)} = {arany:.1%}")
    return {"n": len(dontesek), "helyes": helyes, "arany": arany}


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    fut()

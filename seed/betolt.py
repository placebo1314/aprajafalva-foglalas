"""Demóadat betöltése.

Aprajafalva három boltja:

- **Szundi** — altató
- **Ügyifogyi** — petárda
- **Törpilla** — boldogság, három pulttal, a roadmap „Az első tíz lépés"
  6. pontja szerinti ritmussal:

    GipszJakab:  10 perc vásárlás, minden vásárlás után 10 perc szünet
    Törpilla:    legfeljebb 2 vásárló óránként, óránként 15 perc szünet
    Hulk Hugan:  4 órás műszak, 15 percenként foglalható, szünet nélkül

Egy hét beosztás a Törpilla bolt három pultjára (2026-12-21–27), és egy
kivételnap (2026-12-25, karácsony — a bolt zárva, a slotgenerátor ezért
nem generál rá slotot/blokkot, de a műszaksor létezik, hogy a kihagyás
ténylegesen látszódjon, ne csak hiányozzon).

Minden azonosító **determinisztikus**: `uuid5`-tel, egy fix névtérből, egy
olvasható névből származik — nem `uj_uuid()` (az `uuid4`, véletlen), hogy
a seed adat és a rá épülő tesztek stabilak maradjanak ismételt futtatások
között.
"""

from __future__ import annotations

import sys
import uuid
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from mag.repo import migracio, muszak_repo, torzsadat_repo
from mag.slot import generator
from mag.slot.blokk import FixBlokk

GYOKER = Path(__file__).resolve().parents[1]
ALAP_DB_UTVONAL = GYOKER / "aprajafalva.db"

_NEVTER = uuid.UUID("a9f5d3b0-1234-4000-8000-000000000000")
_ZONA = ZoneInfo("Europe/Budapest")
_HET_KEZDETE = date(2026, 12, 21)  # hétfő
_KIVETEL_DATUM = "2026-12-25"


def _id(nev: str) -> str:
    """Determinisztikus UUID egy olvasható névből."""
    return uuid.uuid5(_NEVTER, nev).hex


# Törpilla bolt három pultja — a rajtuk dolgozó alkalmazott ritmusa
# határozza meg a snapshot-mezőket (docs/domain.md, "Snapshot").
_TORPILLA_PULTOK = [
    {
        "nev": "Törpilla pult 1",
        "alkalmazott_nev": "GipszJakab",
        "idotartam_perc": 10,
        "puffer_utana_perc": 0,
        "min_racs_perc": 10,
        # A saját szünetritmusa (10 perc vásárlás + 10 perc szünet, minden
        # vásárlás után) már önmagában kitölti és meghatározza a napját —
        # egy emellé rendelt szabad sáv ellentmondásos lenne. Szabad sáv
        # csak Törpilla és Hulk Hugan pultján van.
        "foglalhato_arany": 1.0,
        "blokk_szabaly": {
            "szunetek": [{"tipus": "szunet", "hossz_perc": 10, "mintazat": "minden_slot_utan"}]
        },
        "kezdet_ora": 8,
        "veg_ora": 16,
    },
    {
        "nev": "Törpilla pult 2",
        "alkalmazott_nev": "Törpilla",
        "idotartam_perc": 20,
        "puffer_utana_perc": 0,
        "min_racs_perc": 20,
        "foglalhato_arany": 0.8,
        "blokk_szabaly": {
            "szunetek": [{"tipus": "szunet", "hossz_perc": 15, "mintazat": "oranta"}]
        },
        "kezdet_ora": 8,
        "veg_ora": 16,
    },
    {
        "nev": "Törpilla pult 3",
        "alkalmazott_nev": "Hulk Hugan",
        "idotartam_perc": 15,
        "puffer_utana_perc": 0,
        "min_racs_perc": 15,
        # "Szünet nélkül" = nincs generált szünetblokk, de ettől függetlenül
        # lehet szabad sáv (a kettő nem ugyanaz — a szabad sáv nem
        # munkamegszakítás, csak be nem osztott, walk-in vásárlóra
        # tartogatott idő, blueprint 4. szakasz).
        "foglalhato_arany": 0.8,
        "blokk_szabaly": {"szunetek": []},
        "kezdet_ora": 8,
        "veg_ora": 12,  # 4 órás műszak
    },
]


def betolt(db_utvonal: str | Path = ALAP_DB_UTVONAL) -> dict:
    """Betölti a teljes demóadatot. Visszaadja a legfontosabb
    azonosítókat — tesztekben és a CLI-ben egyaránt hasznos."""
    conn = migracio.kapcsolat_nyitas(str(db_utvonal))
    try:
        migracio.migral(conn)
        adat = _torzsadat_betoltese(conn)
        adat["muszakok"] = _het_beosztas_betoltese(conn, adat)
        return adat
    finally:
        conn.close()


def _torzsadat_betoltese(conn) -> dict:
    szervezet_id = torzsadat_repo.szervezet_letrehoz(
        conn,
        nev="Aprajafalva",
        idozona="Europe/Budapest",
        id_=_id("szervezet:aprajafalva"),
    )

    szundi_id = torzsadat_repo.bolt_letrehoz(
        conn, szervezet_id=szervezet_id, nev="Szundi", id_=_id("bolt:szundi")
    )
    torzsadat_repo.pult_letrehoz(
        conn,
        szervezet_id=szervezet_id,
        bolt_id=szundi_id,
        nev="Szundi pult 1",
        id_=_id("pult:szundi:1"),
    )
    torzsadat_repo.alkalmazott_letrehoz(
        conn,
        szervezet_id=szervezet_id,
        bolt_id=szundi_id,
        nev="Csendes",
        id_=_id("alkalmazott:csendes"),
    )
    torzsadat_repo.szolgaltatas_letrehoz(
        conn,
        szervezet_id=szervezet_id,
        bolt_id=szundi_id,
        nev="altató",
        alap_idotartam_perc=15,
        id_=_id("szolgaltatas:altato"),
    )

    ugyifogyi_id = torzsadat_repo.bolt_letrehoz(
        conn, szervezet_id=szervezet_id, nev="Ügyifogyi", id_=_id("bolt:ugyifogyi")
    )
    torzsadat_repo.pult_letrehoz(
        conn,
        szervezet_id=szervezet_id,
        bolt_id=ugyifogyi_id,
        nev="Ügyifogyi pult 1",
        id_=_id("pult:ugyifogyi:1"),
    )
    torzsadat_repo.alkalmazott_letrehoz(
        conn,
        szervezet_id=szervezet_id,
        bolt_id=ugyifogyi_id,
        nev="Durranó",
        id_=_id("alkalmazott:durrano"),
    )
    torzsadat_repo.szolgaltatas_letrehoz(
        conn,
        szervezet_id=szervezet_id,
        bolt_id=ugyifogyi_id,
        nev="petárda",
        alap_idotartam_perc=5,
        id_=_id("szolgaltatas:petarda"),
    )

    torpilla_id = torzsadat_repo.bolt_letrehoz(
        conn, szervezet_id=szervezet_id, nev="Törpilla", id_=_id("bolt:torpilla")
    )
    torpilla_szolgaltatas_id = torzsadat_repo.szolgaltatas_letrehoz(
        conn,
        szervezet_id=szervezet_id,
        bolt_id=torpilla_id,
        nev="boldogság",
        alap_idotartam_perc=15,
        id_=_id("szolgaltatas:boldogsag"),
    )

    torpilla_pultok = []
    for i, konfig in enumerate(_TORPILLA_PULTOK, start=1):
        pult_id = torzsadat_repo.pult_letrehoz(
            conn,
            szervezet_id=szervezet_id,
            bolt_id=torpilla_id,
            nev=konfig["nev"],
            id_=_id(f"pult:torpilla:{i}"),
        )
        alkalmazott_id = torzsadat_repo.alkalmazott_letrehoz(
            conn,
            szervezet_id=szervezet_id,
            bolt_id=torpilla_id,
            nev=konfig["alkalmazott_nev"],
            id_=_id(f"alkalmazott:{konfig['alkalmazott_nev']}"),
        )
        torpilla_pultok.append(
            {"pult_id": pult_id, "alkalmazott_id": alkalmazott_id, "konfig": konfig}
        )

    torzsadat_repo.kivetel_nap_letrehoz(
        conn,
        szervezet_id=szervezet_id,
        bolt_id=None,
        datum=_KIVETEL_DATUM,
        indok="ünnep — karácsony, minden bolt zárva",
        id_=_id("kivetel:karacsony-2026"),
    )

    return {
        "szervezet_id": szervezet_id,
        "boltok": {"szundi": szundi_id, "ugyifogyi": ugyifogyi_id, "torpilla": torpilla_id},
        "torpilla_szolgaltatas_id": torpilla_szolgaltatas_id,
        "torpilla_pultok": torpilla_pultok,
        "kivetel_datum": _KIVETEL_DATUM,
    }


def _het_beosztas_betoltese(conn, adat: dict) -> list[dict]:
    """A Törpilla bolt három pultjára egy hét műszakot hoz létre, és
    minden műszakra lefuttatja a slotgenerátort. A kivetel_nap napon
    (karácsony) a műszak sor LÉTREJÖN, de a generátor nem tesz bele
    slotot/blokkot — ez mutatja meg ténylegesen a kihagyást, nem csak
    egy hiányzó sor a beosztásban."""
    kivetel_napok = frozenset({adat["kivetel_datum"]})
    strategia = FixBlokk()
    letrehozott_muszakok = []

    for pult in adat["torpilla_pultok"]:
        konfig = pult["konfig"]
        for nap_index in range(7):
            nap = _HET_KEZDETE + timedelta(days=nap_index)
            datum_str = nap.isoformat()

            kezdet_helyi = datetime(
                nap.year, nap.month, nap.day, konfig["kezdet_ora"], 0, tzinfo=_ZONA
            )
            veg_helyi = datetime(nap.year, nap.month, nap.day, konfig["veg_ora"], 0, tzinfo=_ZONA)
            kezdet_utc = kezdet_helyi.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
            veg_utc = veg_helyi.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

            muszak_id = muszak_repo.muszak_letrehoz(
                conn,
                szervezet_id=adat["szervezet_id"],
                bolt_id=adat["boltok"]["torpilla"],
                pult_id=pult["pult_id"],
                alkalmazott_id=pult["alkalmazott_id"],
                szolgaltatas_id=adat["torpilla_szolgaltatas_id"],
                kezdet=kezdet_utc,
                veg=veg_utc,
                idotartam_perc=konfig["idotartam_perc"],
                puffer_utana_perc=konfig["puffer_utana_perc"],
                min_racs_perc=konfig["min_racs_perc"],
                foglalhato_arany=konfig["foglalhato_arany"],
                blokk_szabaly=konfig["blokk_szabaly"],
                id_=_id(f"muszak:{konfig['alkalmazott_nev']}:{datum_str}"),
            )

            muszak = muszak_repo.muszak_betoltese(conn, muszak_id)
            eredmeny = generator.general(muszak, strategia, kivetel_napok=kivetel_napok)
            if not eredmeny.kihagyva:
                muszak_repo.blokkok_slotok_mentese(
                    conn,
                    muszak_id=muszak_id,
                    szervezet_id=adat["szervezet_id"],
                    blokkok=eredmeny.blokkok,
                    slotok=eredmeny.slotok,
                )

            letrehozott_muszakok.append(
                {
                    "muszak_id": muszak_id,
                    "alkalmazott": konfig["alkalmazott_nev"],
                    "datum": datum_str,
                    "kihagyva": eredmeny.kihagyva,
                    "slot_szam": len(eredmeny.slotok),
                    "blokk_szam": len(eredmeny.blokkok),
                }
            )

    return letrehozott_muszakok


def _fo() -> None:
    # A kimenet magyar ékezetes karaktereket (ő, ű) tartalmaz — Windowson
    # az örökölt konzol-kódlap ezt nem mindig tudja kódolni közvetlen
    # `python -m seed.betolt` hívásnál (feladat.py-n keresztül futtatva a
    # PYTHONUTF8=1 már beállítja ezt, de a modul önmagában is hordozható
    # kell maradjon).
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    db_utvonal = sys.argv[1] if len(sys.argv) > 1 else str(ALAP_DB_UTVONAL)
    adat = betolt(db_utvonal)
    print(f"Betöltve: {db_utvonal}")
    print(f"  szervezet: {adat['szervezet_id']}")
    print(f"  boltok: {list(adat['boltok'].keys())}")
    generalt = [m for m in adat["muszakok"] if not m["kihagyva"]]
    kihagyott = [m for m in adat["muszakok"] if m["kihagyva"]]
    print(f"  műszakok: {len(adat['muszakok'])} (ebből {len(kihagyott)} kihagyva: kivetel_nap)")
    print(f"  generált slotok összesen: {sum(m['slot_szam'] for m in generalt)}")


if __name__ == "__main__":
    _fo()

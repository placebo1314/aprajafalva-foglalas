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

from core.repo import migracio, muszak_repo, torzsadat_repo
from core.slot import generator
from core.slot.blokk import FixedBlock

ROOT = Path(__file__).resolve().parents[1]
ALAP_DB_PATH = ROOT / "aprajafalva.db"


class AdatbazisMarFeltoltve(RuntimeError):
    """Az adatbázis már tartalmazza a demóadatot — nem nyers SQL-hiba
    (`sqlite3.IntegrityError`), hanem egy előre látott, olvasható állapot.
    Kezelése: `betolt(..., ujra=True)` vagy a `--ujra` CLI-kapcsoló, ami
    előbb kiüríti a táblákat (visszagörgeti, majd újra lefuttatja az
    összes migrációt — `core/repo/migracio.py::rollback`/`migral`), és
    csak utána tölt be újra."""


_NEVTER = uuid.UUID("a9f5d3b0-1234-4000-8000-000000000000")
_ZONE = ZoneInfo("Europe/Budapest")
_WEEK_START = date(2026, 12, 21)  # hétfő
_EXCEPTION_DATE = "2026-12-25"


def _id(name: str) -> str:
    """Determinisztikus UUID egy olvasható névből."""
    return uuid.uuid5(_NEVTER, name).hex


# Törpilla bolt három pultja — a rajtuk dolgozó alkalmazott ritmusa
# határozza meg a snapshot-mezőket (docs/domain.md, "Snapshot").
_TORPILLA_COUNTERS = [
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


def betolt(db_path: str | Path = ALAP_DB_PATH, *, ujra: bool = False) -> dict:
    """Betölti a teljes demóadatot. Visszaadja a legfontosabb
    azonosítókat — tesztekben és a CLI-ben egyaránt hasznos.

    Az azonosítók determinisztikusak (l. modul docstring) — egy már
    feltöltött adatbázisra való újrafuttatás emiatt egyediségi
    kényszerbe ütközne. `ujra=False` (alapértelmezett) esetén ezt
    előre, olvashatóan jelezzük (`AdatbazisMarFeltoltve`), nem hagyjuk,
    hogy nyers `sqlite3.IntegrityError` szálljon fel. `ujra=True`
    esetén előbb kiürítjük a sémát (visszagörgetés + újramigrálás),
    és csak utána töltünk be — így a hívó nem kell, hogy tudja, melyik
    táblát milyen sorrendben kellene törölni."""
    conn = migracio.conn_nyitas(str(db_path))
    try:
        migracio.migral(conn)
        if torzsadat_repo.orgs_list(conn):
            if not ujra:
                raise AdatbazisMarFeltoltve(
                    f"Az adatbázis már fel van töltve ({db_path}) — "
                    "használd a --ujra kapcsolót (vagy betolt(..., ujra=True))."
                )
            migracio.rollback(conn)
            migracio.migral(conn)
        data = _master_data_load(conn)
        data["muszakok"] = _week_schedule_load(conn, data)
        return data
    finally:
        conn.close()


def _master_data_load(conn) -> dict:
    org_id = torzsadat_repo.org_create(
        conn,
        name="Aprajafalva",
        timezone="Europe/Budapest",
        id_=_id("szervezet:aprajafalva"),
    )

    szundi_id = torzsadat_repo.shop_create(
        conn, org_id=org_id, name="Szundi", id_=_id("bolt:szundi")
    )
    torzsadat_repo.shop_description_update(
        conn,
        shop_id=szundi_id,
        megjelenes=(
            "Kék, csillagos homlokzat, az ajtó fölött álmos hold formájú tábla. "
            "Esténként halk zene szűrődik ki az ablakokon."
        ),
    )
    torzsadat_repo.counter_create(
        conn,
        org_id=org_id,
        shop_id=szundi_id,
        name="Szundi pult 1",
        id_=_id("pult:szundi:1"),
    )
    torzsadat_repo.employee_create(
        conn,
        org_id=org_id,
        shop_id=szundi_id,
        name="Csendes",
        id_=_id("alkalmazott:csendes"),
    )
    szundi_service_id = torzsadat_repo.service_create(
        conn,
        org_id=org_id,
        shop_id=szundi_id,
        name="altató",
        alap_duration_minute=15,
        id_=_id("szolgaltatas:altato"),
    )
    torzsadat_repo.service_description_update(
        conn,
        service_id=szundi_service_id,
        termekleiras=(
            "Gyógynövényes altatófőzet, egyénre szabott recept szerint — egy csésze, "
            "és garantáltan mély álom reggelig."
        ),
        ar="40 arany",
    )

    ugyifogyi_id = torzsadat_repo.shop_create(
        conn, org_id=org_id, name="Ügyifogyi", id_=_id("bolt:ugyifogyi")
    )
    torzsadat_repo.shop_description_update(
        conn,
        shop_id=ugyifogyi_id,
        megjelenes=(
            "Élénkpiros-sárga cégér, az ablakok mögül időnként pattogó hangok "
            "hallatszanak — ne ijedj meg, ez itt megszokott."
        ),
    )
    torzsadat_repo.counter_create(
        conn,
        org_id=org_id,
        shop_id=ugyifogyi_id,
        name="Ügyifogyi pult 1",
        id_=_id("pult:ugyifogyi:1"),
    )
    torzsadat_repo.employee_create(
        conn,
        org_id=org_id,
        shop_id=ugyifogyi_id,
        name="Durranó",
        id_=_id("alkalmazott:durrano"),
    )
    ugyifogyi_service_id = torzsadat_repo.service_create(
        conn,
        org_id=org_id,
        shop_id=ugyifogyi_id,
        name="petárda",
        alap_duration_minute=5,
        id_=_id("szolgaltatas:petarda"),
    )
    torzsadat_repo.service_description_update(
        conn,
        service_id=ugyifogyi_service_id,
        termekleiras=(
            "Kézzel készített ünnepi petárda, biztonságos gyújtózsinórral — "
            "kis és nagy méretben egyaránt kapható."
        ),
        ar="kis petárda 20 arany, nagy petárda 55 arany",
    )

    torpilla_id = torzsadat_repo.shop_create(
        conn, org_id=org_id, name="Törpilla", id_=_id("bolt:torpilla")
    )
    torzsadat_repo.shop_description_update(
        conn,
        shop_id=torpilla_id,
        megjelenes=(
            "Barátságos, virágos kirakat — az ajtóban mindig várja valaki mosollyal a betérőket."
        ),
    )
    torpilla_service_id = torzsadat_repo.service_create(
        conn,
        org_id=org_id,
        shop_id=torpilla_id,
        name="boldogság",
        alap_duration_minute=15,
        id_=_id("szolgaltatas:boldogsag"),
    )
    torzsadat_repo.service_description_update(
        conn,
        service_id=torpilla_service_id,
        termekleiras=(
            "Egy őszinte beszélgetés, egy forró tea és annyi figyelem, "
            "amennyi aznap éppen elfér a szívben."
        ),
        ar="adomány alapú",
    )

    torpilla_counters = []
    for i, config in enumerate(_TORPILLA_COUNTERS, start=1):
        counter_id = torzsadat_repo.counter_create(
            conn,
            org_id=org_id,
            shop_id=torpilla_id,
            name=config["nev"],
            id_=_id(f"pult:torpilla:{i}"),
        )
        employee_id = torzsadat_repo.employee_create(
            conn,
            org_id=org_id,
            shop_id=torpilla_id,
            name=config["alkalmazott_nev"],
            id_=_id(f"alkalmazott:{config['alkalmazott_nev']}"),
        )
        torpilla_counters.append(
            {"pult_id": counter_id, "alkalmazott_id": employee_id, "konfig": config}
        )

    torzsadat_repo.exception_day_create(
        conn,
        org_id=org_id,
        shop_id=None,
        date=_EXCEPTION_DATE,
        reason="ünnep — karácsony, minden bolt zárva",
        id_=_id("kivetel:karacsony-2026"),
    )

    return {
        "szervezet_id": org_id,
        "boltok": {"szundi": szundi_id, "ugyifogyi": ugyifogyi_id, "torpilla": torpilla_id},
        "torpilla_szolgaltatas_id": torpilla_service_id,
        "torpilla_pultok": torpilla_counters,
        "kivetel_datum": _EXCEPTION_DATE,
    }


def _week_schedule_load(conn, data: dict) -> list[dict]:
    """A Törpilla bolt három pultjára egy hét műszakot hoz létre, és
    minden műszakra lefuttatja a slotgenerátort. A kivetel_nap napon
    (karácsony) a műszak sor LÉTREJÖN, de a generátor nem tesz bele
    slotot/blokkot — ez mutatja meg ténylegesen a kihagyást, nem csak
    egy hiányzó sor a beosztásban."""
    exception_days = frozenset({data["kivetel_datum"]})
    strategia = FixedBlock()
    created_shifts = []

    for counter in data["torpilla_pultok"]:
        config = counter["konfig"]
        for day_index in range(7):
            day = _WEEK_START + timedelta(days=day_index)
            date_str = day.isoformat()

            start_local = datetime(
                day.year, day.month, day.day, config["kezdet_ora"], 0, tzinfo=_ZONE
            )
            end_local = datetime(day.year, day.month, day.day, config["veg_ora"], 0, tzinfo=_ZONE)
            start_utc = start_local.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
            end_utc = end_local.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

            shift_id = muszak_repo.shift_create(
                conn,
                org_id=data["szervezet_id"],
                shop_id=data["boltok"]["torpilla"],
                counter_id=counter["pult_id"],
                employee_id=counter["alkalmazott_id"],
                service_id=data["torpilla_szolgaltatas_id"],
                start=start_utc,
                end=end_utc,
                duration_minute=config["idotartam_perc"],
                buffer_after_minute=config["puffer_utana_perc"],
                min_grid_minute=config["min_racs_perc"],
                bookable_ratio=config["foglalhato_arany"],
                block_rule=config["blokk_szabaly"],
                id_=_id(f"muszak:{config['alkalmazott_nev']}:{date_str}"),
            )

            shift = muszak_repo.shift_load(conn, shift_id)
            result = generator.generate(shift, strategia, exception_days=exception_days)
            if not result.skipped:
                muszak_repo.blocks_slots_save(
                    conn,
                    shift_id=shift_id,
                    org_id=data["szervezet_id"],
                    blocks=result.blocks,
                    slots=result.slots,
                )

            created_shifts.append(
                {
                    "muszak_id": shift_id,
                    "alkalmazott": config["alkalmazott_nev"],
                    "datum": date_str,
                    "kihagyva": result.skipped,
                    "slot_szam": len(result.slots),
                    "blokk_szam": len(result.blocks),
                }
            )

    return created_shifts


def _fo() -> None:
    # A kimenet magyar ékezetes karaktereket (ő, ű) tartalmaz — Windowson
    # az örökölt konzol-kódlap ezt nem mindig tudja kódolni közvetlen
    # `python -m seed.betolt` hívásnál (feladat.py-n keresztül futtatva a
    # PYTHONUTF8=1 már beállítja ezt, de a modul önmagában is hordozható
    # kell maradjon).
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

    argv = sys.argv[1:]
    ujra = "--ujra" in argv
    pozicionalis = [a for a in argv if a != "--ujra"]
    db_path = pozicionalis[0] if pozicionalis else str(ALAP_DB_PATH)

    try:
        data = betolt(db_path, ujra=ujra)
    except AdatbazisMarFeltoltve as exc:
        # Olvasható üzenet, nem nyers traceback — a hívó (feladat.py
        # seed) ebből tudja, mit kell tennie.
        print(str(exc))
        raise SystemExit(1) from None

    if ujra:
        print(f"Újratöltve: {db_path}")
    else:
        print(f"Betöltve: {db_path}")
    print(f"  szervezet: {data['szervezet_id']}")
    print(f"  boltok: {list(data['boltok'].keys())}")
    generated = [m for m in data["muszakok"] if not m["kihagyva"]]
    skipped = [m for m in data["muszakok"] if m["kihagyva"]]
    print(f"  műszakok: {len(data['muszakok'])} (ebből {len(skipped)} kihagyva: kivetel_nap)")
    print(f"  generált slotok összesen: {sum(m['slot_szam'] for m in generated)}")


if __name__ == "__main__":
    _fo()

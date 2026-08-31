"""Demóadat betöltése.

Aprajafalva három boltja, **mindhárom egy hét beosztással**
(2026-12-21–27) — de három KÜLÖNBÖZŐ ritmusban:

- **Szundi** — altató. Hosszú, ritka időpontok: 30 perc, óránként egy,
  a fele szabad sáv; esti bolt (14-20 óra). Napi ~6 időpont.
- **Ügyifogyi** — petárda. Rövid, sűrű időpontok: 5 perc, 10 perces
  rácson, óránként 10 perc szünettel (9-17 óra). Napi ~64 időpont.
- **Törpilla** — boldogság, három pulttal, a roadmap „Az első tíz
  lépés" 6. pontja szerinti ritmussal (8-16 óra):

    GipszJakab:  10 perc vásárlás, minden vásárlás után 10 perc szünet
    Törpilla:    legfeljebb 2 vásárló óránként, óránként 15 perc szünet
    Hulk Hugan:  4 órás műszak, 15 percenként foglalható, szünet nélkül

**Miért kap mindhárom bolt beosztást** (2026-08-30): korábban csak a
Törpillában volt műszak, tehát a másik két boltra irányuló minden kérés
`nincs_meghirdetett_idopont`-ra futott. Ez a DEMÓADAT tulajdonsága
volt, nem a rendszeré — de a próbákban megkülönböztethetetlen volt egy
párbeszédhibától, és a mért kiutak nagy része innen jött.

Plusz egy kivételnap (2026-12-25, karácsony — minden bolt zárva, a
slotgenerátor ezért nem generál rá slotot/blokkot, de a műszaksor
létezik, hogy a kihagyás ténylegesen látszódjon, ne csak hiányozzon).

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


# MINDHÁROM BOLT pultjai, boltonként — a rajtuk dolgozó alkalmazott
# ritmusa határozza meg a snapshot-mezőket (docs/domain.md, "Snapshot").
#
# **Miért kap mindhárom bolt beosztást** (2026-08-30). Korábban csak a
# Törpillában volt műszak, tehát a másik két boltra irányuló MINDEN
# kérés `nincs_meghirdetett_idopont`-ra futott. Ez a demóadat
# tulajdonsága volt, nem a rendszeré — de a kézi és a fej nélküli
# próbákban megkülönböztethetetlen volt egy párbeszédhibától: a
# kiutak nagy része innen jött, és minden mérés, ami a beszélgetés
# minőségét nézte, ezen a zajon át nézte.
#
# A három ritmus SZÁNDÉKOSAN különbözik — így a demóadaton az is
# látszik, hogy ugyanaz a kérés máshogy néz ki egy hosszú, ritka és
# egy rövid, sűrű beosztáson:
#
#   Szundi     — hosszú, RITKA: 30 perces időpont óránként, fél nap
#                szabad sáv (esti bolt, 14-20 óra)
#   Ügyifogyi  — rövid, SŰRŰ: 5 perces időpont 10 percenként, óránként
#                10 perc szünettel (9-17 óra)
#   Törpilla   — a roadmap három ritmusa, három pulton (8-16 óra)
_PULTOK: dict[str, list[dict]] = {}

_PULTOK["szundi"] = [
    {
        "nev": "Szundi pult 1",
        "alkalmazott_nev": "Csendes",
        # HOSSZÚ időpont, RITKÁN: 30 perc, de csak óránként indul egy
        # (a rács 60 perc), és a fele szabad sáv marad — egy altató
        # kiválasztása nem sietős munka.
        "idotartam_perc": 30,
        "puffer_utana_perc": 0,
        "min_racs_perc": 60,
        "foglalhato_arany": 0.5,
        "blokk_szabaly": {"szunetek": []},
        "kezdet_ora": 14,
        "veg_ora": 20,
    },
]

_PULTOK["ugyifogyi"] = [
    {
        "nev": "Ügyifogyi pult 1",
        "alkalmazott_nev": "Durranó",
        # RÖVID időpont, SŰRŰN: 5 perc, 10 perces rácson, óránként 10
        # perc szünettel. Egy petárda kiválasztása pár perc.
        "idotartam_perc": 5,
        "puffer_utana_perc": 0,
        "min_racs_perc": 10,
        "foglalhato_arany": 0.9,
        "blokk_szabaly": {
            "szunetek": [{"tipus": "szunet", "hossz_perc": 10, "mintazat": "oranta"}]
        },
        "kezdet_ora": 9,
        "veg_ora": 17,
    },
]

_PULTOK["torpilla"] = [
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
            "A Pihenő utca legvégén, a patak melletti utolsó ház — kék, csillagos "
            "homlokzat, az ajtó fölött álmos hold formájú tábla. Kívülről alacsonynak "
            "látszik, mert félig a domboldalba épült. Belül félhomály van, a pult mögött "
            "polcokon sorakoznak a cimkézett üvegcsék, a sarokban mindig ég egy mécses. "
            "Esténként halk zene szűrődik ki az ablakokon. Aki belép, előbb leül egy "
            "fonott székre — az altatót ülve mérik ki."
        ),
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
            "Gyógynövényes altatófőzet, egyénre szabott recept szerint: citromfű, "
            "macskagyökér és egy kanál akácméz, langyosan kimérve. A pultos végigkérdezi, "
            "mi tartja ébren a vásárlót, és aszerint állítja össze — egy csésze, és mély "
            "álom reggelig. Nem altatópor és nem orvosság: aki gyógyszert szed, annak a "
            "gyengébb, koffeinmentes változat jár. Elvitelre lezárt üvegcsében is kérhető."
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
            "A Durranó tér közepén, a kúttal szemben — élénkpiros-sárga cégér, rajta egy "
            "szikrázó petárda. Az ablakok mögül időnként pattogó hangok hallatszanak; ne "
            "ijedj meg, ez itt megszokott. A bejárat előtt homokláda áll (ez a próbahely), "
            "belül egyetlen hosszú pult, mögötte fémdobozokban a készáru. A falon tábla "
            "sorolja, mit tilos: a boltban gyújtani szigorúan tilos."
        ),
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
            "Kézzel készített ünnepi petárda, biztonságos, lassan égő gyújtózsinórral. "
            "A kis petárda tenyérnyi, halk pukkanás, gyerekeknek is odaadható felnőtt "
            "mellett; a nagy petárda kétmaréknyi, hangos, és csak nyílt téren gyújtható. "
            "Mindkettő nedvességálló papírban jön, gyújtózsinór-hosszal a dobozon. "
            "A pultos minden vásárlásnál elmondja a három szabályt, ez benne van az "
            "időpont hosszában."
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
            "A Fő utca 7., a pékség és a kút között — barátságos, virágos kirakat, az "
            "ajtóban mindig várja valaki mosollyal a betérőket. Nincs cégér, csak egy "
            "kézzel festett szív az ajtóüvegen. Belül három kis asztal áll egymástól "
            "távol (ez a három pult), mindegyiken kancsó víz és egy doboz zsebkendő. "
            "A várakozóban könyvek és egy alvó macska. Aki csak beülni jön, azt is "
            "beengedik — de időpont nélkül nem biztos, hogy sorra kerül."
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
            "Egy őszinte beszélgetés, egy forró tea és annyi figyelem, amennyi aznap "
            "éppen elfér a szívben. Nem terápia és nem tanácsadás: a pultos nem mond meg "
            "semmit, csak végighallgat, és a végén kérdez egyet. Aki nem akar beszélni, "
            "ülhet csendben is — az is boldogság-időpont. Ha valakinek orvosi segítség "
            "kell, a Törpilla ezt kimondja, és nem tartja bent."
        ),
        ar="adomány alapú",
    )

    boltok = {"szundi": szundi_id, "ugyifogyi": ugyifogyi_id, "torpilla": torpilla_id}
    szolgaltatasok = {
        "szundi": szundi_service_id,
        "ugyifogyi": ugyifogyi_service_id,
        "torpilla": torpilla_service_id,
    }

    # PULTOK ÉS ALKALMAZOTTAK — mindhárom boltra ugyanaz a ciklus. Az
    # azonosítók továbbra is determinisztikusak (`_id`), tehát a
    # meglévő seed-adatra épülő tesztek azonosítói nem mozdulnak el.
    pultok: dict[str, list[dict]] = {}
    for bolt_slug, konfigok in _PULTOK.items():
        pultok[bolt_slug] = []
        for i, config in enumerate(konfigok, start=1):
            counter_id = torzsadat_repo.counter_create(
                conn,
                org_id=org_id,
                shop_id=boltok[bolt_slug],
                name=config["nev"],
                id_=_id(f"pult:{bolt_slug}:{i}"),
            )
            employee_id = torzsadat_repo.employee_create(
                conn,
                org_id=org_id,
                shop_id=boltok[bolt_slug],
                name=config["alkalmazott_nev"],
                id_=_id(f"alkalmazott:{config['alkalmazott_nev']}"),
            )
            pultok[bolt_slug].append(
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
        "boltok": boltok,
        "szolgaltatasok": szolgaltatasok,
        "pultok": pultok,
        "kivetel_datum": _EXCEPTION_DATE,
    }


def _week_schedule_load(conn, data: dict) -> list[dict]:
    """MINDHÁROM bolt minden pultjára egy hét műszakot hoz létre, és
    minden műszakra lefuttatja a slotgenerátort. A kivetel_nap napon
    (karácsony) a műszak sor LÉTREJÖN, de a generátor nem tesz bele
    slotot/blokkot — ez mutatja meg ténylegesen a kihagyást, nem csak
    egy hiányzó sor a beosztásban.

    **Korábban csak a Törpilla kapott beosztást**, és emiatt a másik két
    boltra irányuló minden kérés üres eredményre futott — a próbákban
    ez megkülönböztethetetlen volt egy párbeszédhibától (l. `_PULTOK`
    fejlécének magyarázata)."""
    exception_days = frozenset({data["kivetel_datum"]})
    strategia = FixedBlock()
    created_shifts = []

    pultok = [
        (bolt_slug, counter)
        for bolt_slug, counters in data["pultok"].items()
        for counter in counters
    ]
    for bolt_slug, counter in pultok:
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
                shop_id=data["boltok"][bolt_slug],
                counter_id=counter["pult_id"],
                employee_id=counter["alkalmazott_id"],
                service_id=data["szolgaltatasok"][bolt_slug],
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
                    "bolt": bolt_slug,
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

"""Programozott (nem CLI-argv) API az admin felülethez.

Ez a `felulet/admin/` egyetlen belépési pontja a maghoz — a `felulet/`
modul CLAUDE.md szabálya szerint importálhat a `mag/`-ból, de a SQL-hez
nem nyúlhat közvetlenül (CLAUDE.md 5. invariáns: "Minden SQL a
mag/repo/-ban van"). Ez a modul csak a `mag/repo/` függvényeit hívja és
orchestrálja, saját SQL-t nem tartalmaz.

A kapcsolat élettartamát a hívó (a felület) kezeli — ugyanúgy, ahogy a
`mag/api/cli.py` egyes parancsai is teszik, csak azok parancsonként egy
kapcsolatot nyitnak/zárnak, itt a hívó (egy hosszú életű felületi
folyamat) egyetlen kapcsolatot tarthat nyitva több híváson át.
"""

from __future__ import annotations

import sqlite3
from collections import defaultdict
from datetime import date as _date
from datetime import timedelta

from core.modell.shift import Block
from core.repo import foglalas_repo, muszak_repo, sablon_repo, torzsadat_repo
from core.slot import generator
from core.slot.blokk import FixedBlock
from core.szabalyok import kenyszerek

# Két KÜLÖNBÖZŐ "sablon" fogalom van ebben a modulban, szándékosan más
# névvel: a lenti `SABLONOK` a "műszak felvitele" űrlap MEZŐ-előtöltése
# (statikus, kódban rögzített, pult/alkalmazott/szolgáltatás/időablak
# NÉLKÜL) — a `muszak_sablon_*` függvények viszont a `muszak_sablon`
# táblát (migraciok/0003) kezelik: EGY MEGLÉVŐ MŰSZAKBÓL elmentett,
# perzisztens, pult+alkalmazott+szolgáltatás+időablak+blokkszabály
# tartalmú recept, ami napra/hétre alkalmazható (roadmap M1 kilépési
# feltétele: "egy hónapnyi beosztás felvitele percekben mérhető").

# Sablonok a "műszak felvitele" űrlaphoz (felulet/admin/) — a snapshot-mezők
# (idotartam_perc, puffer_utana_perc, min_racs_perc, foglalhato_arany,
# blokk_szabaly) kitöltésének gyorsítására, a seed/betolt.py három
# Törpilla-pult mintája alapján (roadmap "Az első tíz lépés" 6. pontja).
# Az admin ettől függetlenül felülírhatja a mezőket — a sablon csak
# kiindulás, nem kényszer.
TEMPLATES: dict[str, dict] = {
    "gyors_penztar": {
        "cimke": "Gyors pénztár (10 perc + 10 perc szünet minden vásárlás után)",
        "idotartam_perc": 10,
        "puffer_utana_perc": 0,
        "min_racs_perc": 10,
        "foglalhato_arany": 1.0,
        "blokk_szabaly": {
            "szunetek": [{"tipus": "szunet", "hossz_perc": 10, "mintazat": "minden_slot_utan"}]
        },
    },
    "orankent_ketto": {
        "cimke": "Óránként legfeljebb kettő (20 perc, óránként 15 perc szünet, 20% szabad sáv)",
        "idotartam_perc": 20,
        "puffer_utana_perc": 0,
        "min_racs_perc": 20,
        "foglalhato_arany": 0.8,
        "blokk_szabaly": {
            "szunetek": [{"tipus": "szunet", "hossz_perc": 15, "mintazat": "oranta"}]
        },
    },
    "szunet_nelkul": {
        "cimke": "Szünet nélkül (15 perc, 20% szabad sáv, nincs generált szünet)",
        "idotartam_perc": 15,
        "puffer_utana_perc": 0,
        "min_racs_perc": 15,
        "foglalhato_arany": 0.8,
        "blokk_szabaly": {"szunetek": []},
    },
    "egyedi": {
        "cimke": "Egyedi — minden mező kézzel",
        "idotartam_perc": None,
        "puffer_utana_perc": None,
        "min_racs_perc": None,
        "foglalhato_arany": None,
        "blokk_szabaly": {"szunetek": []},
    },
}


def orgs(conn: sqlite3.Connection) -> list[dict]:
    return torzsadat_repo.orgs_list(conn)


def shops(conn: sqlite3.Connection, *, org_id: str) -> list[dict]:
    return torzsadat_repo.shops_list(conn, org_id=org_id)


def counters(conn: sqlite3.Connection, *, shop_id: str) -> list[dict]:
    return torzsadat_repo.counters_list(conn, shop_id=shop_id)


def employees(conn: sqlite3.Connection, *, shop_id: str) -> list[dict]:
    return torzsadat_repo.employees_list(conn, shop_id=shop_id)


def services(conn: sqlite3.Connection, *, shop_id: str) -> list[dict]:
    return torzsadat_repo.services_list(conn, shop_id=shop_id)


# ---------------------------------------------------------------------
# Törzsadat-szerkesztés (bolt, pult, alkalmazott, szolgáltatás, kivétel
# nap) — a `felulet/admin/` mai formája a demóadatra (seed/betolt.py)
# támaszkodott, ez a szakasz teszi lehetővé, hogy az admin maga is
# felvigyen/szerkesszen törzsadatot. Minden függvény `hiba` kulccsal tér
# vissza kivétel helyett, ugyanazzal a mintával, mint `muszak_felvitel` —
# a `nev` mezőkön lévő `CHECK (length(nev) > 0)` (migraciok/0001) nyers
# `IntegrityError`-t adna üres névre, ezt itt előre elkapjuk.
# ---------------------------------------------------------------------


def shop_add(conn: sqlite3.Connection, *, org_id: str, name: str) -> dict:
    name = name.strip()
    if not name:
        return {"bolt_id": None, "hiba": "A bolt neve nem lehet üres."}
    shop_id = torzsadat_repo.shop_create(conn, org_id=org_id, name=name)
    return {"bolt_id": shop_id, "hiba": None}


def shop_update(conn: sqlite3.Connection, *, shop_id: str, name: str) -> dict:
    name = name.strip()
    if not name:
        return {"hiba": "A bolt neve nem lehet üres."}
    torzsadat_repo.shop_update(conn, shop_id=shop_id, name=name)
    return {"hiba": None}


def shop_description_update(conn: sqlite3.Connection, *, shop_id: str, megjelenes: str) -> dict:
    """A "Bolti tudás" mező (docs/blueprint.md 10. szakasz) — ezt a
    `bolt_info` eszköz olvassa vissza, a modell sosem generálja. Üres
    string érvényes érték ("nincs még megadva"), nincs rajta
    `nem lehet üres` ellenőrzés, ellentétben a névvel."""
    torzsadat_repo.shop_description_update(conn, shop_id=shop_id, megjelenes=megjelenes.strip())
    return {"hiba": None}


def counter_add(conn: sqlite3.Connection, *, org_id: str, shop_id: str, name: str) -> dict:
    name = name.strip()
    if not name:
        return {"pult_id": None, "hiba": "A pult neve nem lehet üres."}
    counter_id = torzsadat_repo.counter_create(conn, org_id=org_id, shop_id=shop_id, name=name)
    return {"pult_id": counter_id, "hiba": None}


def counter_update(conn: sqlite3.Connection, *, counter_id: str, name: str) -> dict:
    name = name.strip()
    if not name:
        return {"hiba": "A pult neve nem lehet üres."}
    torzsadat_repo.counter_update(conn, counter_id=counter_id, name=name)
    return {"hiba": None}


def employee_add(conn: sqlite3.Connection, *, org_id: str, shop_id: str, name: str) -> dict:
    name = name.strip()
    if not name:
        return {"alkalmazott_id": None, "hiba": "Az alkalmazott neve nem lehet üres."}
    employee_id = torzsadat_repo.employee_create(conn, org_id=org_id, shop_id=shop_id, name=name)
    return {"alkalmazott_id": employee_id, "hiba": None}


def employee_update(conn: sqlite3.Connection, *, employee_id: str, name: str) -> dict:
    name = name.strip()
    if not name:
        return {"hiba": "Az alkalmazott neve nem lehet üres."}
    torzsadat_repo.employee_update(conn, employee_id=employee_id, name=name)
    return {"hiba": None}


def service_add(
    conn: sqlite3.Connection,
    *,
    org_id: str,
    shop_id: str,
    name: str,
    alap_duration_minute: int,
) -> dict:
    name = name.strip()
    if not name:
        return {"szolgaltatas_id": None, "hiba": "A szolgáltatás neve nem lehet üres."}
    if alap_duration_minute <= 0:
        return {
            "szolgaltatas_id": None,
            "hiba": "Az alapértelmezett időtartam pozitív kell legyen.",
        }
    service_id = torzsadat_repo.service_create(
        conn,
        org_id=org_id,
        shop_id=shop_id,
        name=name,
        alap_duration_minute=alap_duration_minute,
    )
    return {"szolgaltatas_id": service_id, "hiba": None}


def service_update(
    conn: sqlite3.Connection, *, service_id: str, name: str, alap_duration_minute: int
) -> dict:
    name = name.strip()
    if not name:
        return {"hiba": "A szolgáltatás neve nem lehet üres."}
    if alap_duration_minute <= 0:
        return {"hiba": "Az alapértelmezett időtartam pozitív kell legyen."}
    torzsadat_repo.service_update(
        conn,
        service_id=service_id,
        name=name,
        alap_duration_minute=alap_duration_minute,
    )
    return {"hiba": None}


def service_description_update(
    conn: sqlite3.Connection, *, service_id: str, termekleiras: str, ar: str
) -> dict:
    """A "Bolti tudás" mezők (docs/blueprint.md 10. szakasz) — a
    `bolt_info` eszköz `termek`/`ar` ága ezt olvassa vissza. Az `ar`
    mezőt a kapuőr ma is elutasítja szabad kérdésben (golden set
    `kapuor-02`) — ez a szerkesztés attól függetlenül lehetséges, a
    tárolás és a kiadás két külön döntés."""
    torzsadat_repo.service_description_update(
        conn,
        service_id=service_id,
        termekleiras=termekleiras.strip(),
        ar=ar.strip(),
    )
    return {"hiba": None}


def exception_day_add(
    conn: sqlite3.Connection,
    *,
    org_id: str,
    shop_id: str | None,
    date: str,
    reason: str,
) -> dict:
    reason = reason.strip()
    if not reason:
        return {"kivetel_id": None, "hiba": "Az indok nem lehet üres."}
    try:
        _date.fromisoformat(date)
    except ValueError:
        return {"kivetel_id": None, "hiba": f"Érvénytelen dátum: {date!r} (ÉÉÉÉ-HH-NN kell)."}
    exception_id = torzsadat_repo.exception_day_create(
        conn, org_id=org_id, shop_id=shop_id, date=date, reason=reason
    )
    return {"kivetel_id": exception_id, "hiba": None}


def exception_days(
    conn: sqlite3.Connection, *, org_id: str, shop_id: str | None = None
) -> list[dict]:
    return torzsadat_repo.exception_days_in_detail_list(conn, org_id=org_id, shop_id=shop_id)


def week_shifts(
    conn: sqlite3.Connection,
    *,
    org_id: str,
    week_start_date: str,
    shop_id: str | None = None,
) -> list[dict]:
    """Egy hét (7 nap, `het_kezdete_datum`-tól, 'YYYY-MM-DD') műszakjai —
    a naptárnézet ('felulet/admin/') ezt rendezi pultok/napok szerint."""
    from core.slot._idomatek import add_minute

    date_tol = f"{week_start_date}T00:00:00Z"
    date_ig = add_minute(date_tol, 7 * 24 * 60)
    return muszak_repo.shifts_list(
        conn,
        org_id=org_id,
        shop_id=shop_id,
        date_tol=date_tol,
        date_ig=date_ig,
    )


def shift_details(conn: sqlite3.Connection, *, shift_id: str) -> dict:
    """Egy műszak blokkjai és slotjai (állapottal együtt) — a naptárnézet
    egy műszakra kattintva ezt jeleníti meg."""
    return {
        "blokkok": muszak_repo.blocks_list(conn, shift_id=shift_id),
        "slotok": foglalas_repo.slot_statuses_list(conn, shift_id=shift_id),
    }


def shift_felvitel(
    conn: sqlite3.Connection,
    *,
    org_id: str,
    shop_id: str,
    counter_id: str,
    employee_id: str,
    service_id: str,
    start: str,
    end: str,
    duration_minute: int,
    buffer_after_minute: int,
    min_grid_minute: int,
    bookable_ratio: float,
    block_rule: dict,
) -> dict:
    """Műszak felvitele ÉS slot/blokk generálás egy lépésben — ezt hívja
    az admin felület "műszak felvitele" űrlapja a mentés gombra kattintva.

    Ugyanazt a lépéssort követi, mint `mag/api/cli.py::_slotok` és
    `seed/betolt.py::_het_beosztas_betoltese`: létrehozza a műszakot,
    visszatölti (a snapshot-mezők a `Muszak` dataclass-hoz kellenek),
    lefuttatja a generátort a szervezet kivételnapjaival, és — ha nem lett
    kihagyva — elmenti a blokkokat/slotokat egyetlen tranzakcióban.

    Az időablakot ELŐZETESEN ellenőrzi: a `muszak` tábla `CHECK (veg >
    kezdet)` kényszere (migraciok/0002) amúgy is elutasítaná a fordított
    vagy nulla hosszú ablakot, de nyers `sqlite3.IntegrityError`-ral —
    ez itt, a szolgáltatásrétegben, ÉRTELMES elutasítássá alakul (`hiba`
    kulcs a visszaadott dict-ben, nincs kivétel, és a hívó (a felület)
    egységesen tudja megjeleníteni). A `mag/repo/` rétegen és a
    kényszeren magán ez nem változtat."""
    if end <= start:
        return {
            "muszak_id": None,
            "kihagyva": False,
            "kihagyas_oka": None,
            "slot_szam": 0,
            "blokk_szam": 0,
            "hiba": (
                f"A műszak vége ({end}) nem lehet korábbi vagy egyenlő, mint a kezdete ({start})."
            ),
        }

    shift_id = muszak_repo.shift_create(
        conn,
        org_id=org_id,
        shop_id=shop_id,
        counter_id=counter_id,
        employee_id=employee_id,
        service_id=service_id,
        start=start,
        end=end,
        duration_minute=duration_minute,
        buffer_after_minute=buffer_after_minute,
        min_grid_minute=min_grid_minute,
        bookable_ratio=bookable_ratio,
        block_rule=block_rule,
    )
    shift = muszak_repo.shift_load(conn, shift_id)
    exception_days = muszak_repo.exception_days_list(conn, org_id=org_id)
    result = generator.generate(shift, FixedBlock(), exception_days=exception_days)
    if not result.skipped:
        muszak_repo.blocks_slots_save(
            conn,
            shift_id=shift_id,
            org_id=org_id,
            blocks=result.blocks,
            slots=result.slots,
        )
    return {
        "muszak_id": shift_id,
        "kihagyva": result.skipped,
        "kihagyas_oka": result.skip_oka,
        "slot_szam": len(result.slots),
        "blokk_szam": len(result.blocks),
        "hiba": None,
    }


def bookings(conn: sqlite3.Connection, *, org_id: str, shop_id: str | None = None) -> list[dict]:
    return foglalas_repo.bookings_list(conn, org_id=org_id, shop_id=shop_id)


def booking_lemond(conn: sqlite3.Connection, *, booking_code: str) -> foglalas_repo.Result:
    return foglalas_repo.booking_lemond(conn, booking_code)


# ---------------------------------------------------------------------
# Műszak-sablonok (muszak_sablon tábla, migraciok/0003) — lásd a modul
# tetején lévő megjegyzést a két "sablon" fogalom közti különbségről.
# ---------------------------------------------------------------------


def shift_template_save(conn: sqlite3.Connection, *, shift_id: str, name: str) -> dict:
    """Sablon mentése egy MEGLÉVŐ műszakból: pult, alkalmazott,
    szolgáltatás, napi óra-időablak (a `kezdet`/`veg` óra-részéből) és a
    snapshot-mezők (idotartam_perc, stb.) + blokkszabály.

    Csak AZONOS NAPI, óra-határra eső időablakot tud sablonná menteni
    (lásd migraciok/0003 megjegyzése) — ha a műszak éjfélen átnyúlik vagy
    a kezdete/vége nem kerek óra, ÉRTELMES elutasítást ad (`hiba` kulcs),
    nem kivételt."""
    base_data = muszak_repo.shift_alapadatai(conn, shift_id=shift_id)
    if base_data is None:
        return {"sablon_id": None, "hiba": f"Nincs ilyen műszak: {shift_id}"}

    start_date, start_hour_part = base_data["kezdet"][:10], base_data["kezdet"][11:19]
    end_date, end_hour_part = base_data["veg"][:10], base_data["veg"][11:19]
    if start_date != end_date:
        return {
            "sablon_id": None,
            "hiba": "Éjfélen átnyúló műszakból ma nem menthető sablon (lásd migraciok/0003).",
        }
    if start_hour_part[3:] != "00:00" or end_hour_part[3:] != "00:00":
        return {
            "sablon_id": None,
            "hiba": "A sablon csak kerek órára eső időablakot tud menteni.",
        }

    start_hour = int(start_hour_part[:2])
    end_hour = int(end_hour_part[:2])
    if end_hour == 0:  # éjfél, mint záró óra — 24-ként kezeljük (lásd CHECK)
        end_hour = 24

    template_id = sablon_repo.template_create(
        conn,
        org_id=base_data["szervezet_id"],
        name=name,
        shop_id=base_data["bolt_id"],
        counter_id=base_data["pult_id"],
        employee_id=base_data["alkalmazott_id"],
        service_id=base_data["szolgaltatas_id"],
        start_hour=start_hour,
        end_hour=end_hour,
        duration_minute=base_data["idotartam_perc"],
        buffer_after_minute=base_data["puffer_utana_perc"],
        min_grid_minute=base_data["min_racs_perc"],
        bookable_ratio=base_data["foglalhato_arany"],
        block_rule=base_data["blokk_szabaly"],
    )
    return {"sablon_id": template_id, "hiba": None}


def shift_templates(
    conn: sqlite3.Connection, *, org_id: str, shop_id: str | None = None
) -> list[dict]:
    return sablon_repo.templates_list(conn, org_id=org_id, shop_id=shop_id)


def shift_template_apply_for_day(conn: sqlite3.Connection, *, template_id: str, date: str) -> dict:
    """A sablont egyetlen napra alkalmazza — létrehozza a műszakot és
    lefuttatja a generátort, ugyanúgy, mint `muszak_felvitel`."""
    template = sablon_repo.template_load(conn, template_id=template_id)
    if template is None:
        return {"hiba": f"Nincs ilyen sablon: {template_id}", "muszak_id": None}

    start = f"{date}T{template['kezdet_ora']:02d}:00:00Z"
    end_hour = template["veg_ora"]
    if end_hour == 24:
        end_day = _date.fromisoformat(date) + timedelta(days=1)
        end = f"{end_day.isoformat()}T00:00:00Z"
    else:
        end = f"{date}T{end_hour:02d}:00:00Z"

    return shift_felvitel(
        conn,
        org_id=template["szervezet_id"],
        shop_id=template["bolt_id"],
        counter_id=template["pult_id"],
        employee_id=template["alkalmazott_id"],
        service_id=template["szolgaltatas_id"],
        start=start,
        end=end,
        duration_minute=template["idotartam_perc"],
        buffer_after_minute=template["puffer_utana_perc"],
        min_grid_minute=template["min_racs_perc"],
        bookable_ratio=template["foglalhato_arany"],
        block_rule=template["blokk_szabaly"],
    )


def shift_template_apply_for_week(
    conn: sqlite3.Connection, *, template_id: str, week_start_date: str
) -> list[dict]:
    """A sablont a hét mind a 7 napjára alkalmazza (a seed/betolt.py
    heti mintáját követve — egy sablon egy pultra napi ismétlődés).
    Kivételnapra eső nap a szokásos módon (`generator.general`)
    kihagyásra kerül, de a `muszak` sor létrejön — ez NEM hiba, a
    visszaadott lista elemén `kihagyva: True` jelzi."""
    week_start = _date.fromisoformat(week_start_date)
    results = []
    for day_index in range(7):
        day = week_start + timedelta(days=day_index)
        results.append(
            shift_template_apply_for_day(conn, template_id=template_id, date=day.isoformat())
        )
    return results


def week_copy(
    conn: sqlite3.Connection,
    *,
    org_id: str,
    source_week_start: str,
    target_week_start: str,
    shop_id: str | None = None,
) -> list[dict]:
    """A `forras_het_kezdete` hetén ténylegesen létező műszakokat
    lemásolja a `cel_het_kezdete` hetére — minden műszakot annyi nappal
    tol el, amennyi a két hét kezdete közti eltolás. A kivételnapra eső
    célnapok a szokásos módon (`generator.general`) kihagyásra kerülnek,
    a `muszak` sor viszont létrejön (`kihagyva: True` az adott elemen).

    Ez KÜLÖNBÖZIK a `muszak_sablon_alkalmazasa_hetre`-től: az egy
    ELMENTETT sablont ismétel minden napra, ez itt a forrás hét TÉNYLEGES,
    változatos beosztását (több pult, eltérő napi mintázat) másolja át,
    sablon nélkül."""
    offset_day = (
        _date.fromisoformat(target_week_start) - _date.fromisoformat(source_week_start)
    ).days
    source_shifts = week_shifts(
        conn,
        org_id=org_id,
        week_start_date=source_week_start,
        shop_id=shop_id,
    )
    results = []
    for shift in source_shifts:
        base_data = muszak_repo.shift_alapadatai(conn, shift_id=shift["muszak_id"])
        new_start = _date_shift_by(base_data["kezdet"], offset_day)
        new_end = _date_shift_by(base_data["veg"], offset_day)
        results.append(
            shift_felvitel(
                conn,
                org_id=org_id,
                shop_id=shift["bolt_id"],
                counter_id=shift["pult_id"],
                employee_id=shift["alkalmazott_id"],
                service_id=shift["szolgaltatas_id"],
                start=new_start,
                end=new_end,
                duration_minute=base_data["idotartam_perc"],
                buffer_after_minute=base_data["puffer_utana_perc"],
                min_grid_minute=base_data["min_racs_perc"],
                bookable_ratio=base_data["foglalhato_arany"],
                block_rule=base_data["blokk_szabaly"],
            )
        )
    return results


def _date_shift_by(timestamp: str, day: int) -> str:
    """`idobelyeg` (ISO-8601 UTC, pl. '2026-08-18T08:00:00Z') `nap` nappal
    eltolva — a `mag/slot/_idomatek.hozzaad_perc`-hez hasonló, de napban,
    nem percben számol (a hét-másolás mindig egész napokkal tol)."""
    from core.slot._idomatek import add_minute

    return add_minute(timestamp, day * 24 * 60)


# ---------------------------------------------------------------------
# Ütközéslista — a mag/szabalyok/kenyszerek.py-ra épül, nem duplikálja a
# kemény kényszerek logikáját, csak hívja és formázza az eredményt.
# ---------------------------------------------------------------------

# A kenyszerek.ellenoriz() két paramétere ("nincs bennük egyetlen helyes
# érték", lásd a modul docstringje) bolt-/profilfüggő — amíg nincs profil-
# rendszer (blueprint 7. szakasz, "Kényszerkapcsolók" — profilok, még nem
# épült meg), ez a két érték csak egy ÁTMENETI, felülírható alapértelmezés
# az ütközéslistához, NEM egy törzsadatban rögzített, végleges szabály.
_ALAP_MIN_ALL_BREAK_MINUTE = 20
_ALAP_MAX_CONTINUOUS_WORK_MINUTE = 360


def conflict_list(
    conn: sqlite3.Connection,
    *,
    org_id: str,
    shop_id: str | None = None,
    min_all_break_minute: int = _ALAP_MIN_ALL_BREAK_MINUTE,
    max_continuous_work_minute: int = _ALAP_MAX_CONTINUOUS_WORK_MINUTE,
) -> list[dict]:
    """Problémás műszakok listája — az admin felület "Ütközéslista"
    nézetének. Három ok miatt kerülhet ide egy tétel:

    - `kenyszer_sertes`: a `mag/szabalyok/kenyszerek.py::ellenoriz()`
      valamelyik kemény kényszert megsértve találta (a logika onnan jön,
      itt csak hívjuk és a KenyszerSertes-eket dict-té alakítjuk).
    - `nulla_slot`: a műszak nulla slotot generált, ÉS a napja NEM
      kivétel nap (kivétel napon a nulla slot szándékos, nem hiba).
    - `atfedes`: két műszak UGYANAZON a pulton időben átfedi egymást.

    Az egész szervezetet (vagy egy boltot) végignézi, nem egyetlen hetet —
    ez audit-nézet, nem naptár."""
    shifts = muszak_repo.shifts_list(conn, org_id=org_id, shop_id=shop_id)
    exception_days = muszak_repo.exception_days_list(conn, org_id=org_id, shop_id=shop_id)

    problems: list[dict] = []

    for m in shifts:
        exception_on_day_has = m["kezdet"][:10] in exception_days

        # Kivétel napon a műszak SOR létezik, de a generátor szándékosan
        # nem tett bele blokkot/slotot (lásd generator.general() és
        # seed/betolt.py::_het_beosztas_betoltese docstringje) — üres
        # blokklistán a kenyszerek.ellenoriz() jogosan jelezne "nincs
        # szünet" hibát, de ez itt NEM valódi sértés, csak a kihagyás
        # mellékhatása. Ezért kivétel napon nem futtatjuk a kényszer-
        # ellenőrzést.
        if not exception_on_day_has:
            shift_obj = muszak_repo.shift_load(conn, shift_id=m["muszak_id"])
            # A repo dict kulcsai a séma nyelvét követik (kezdet/veg/...),
            # a Block dataclass mezői viszont angolra fordultak (start/
            # end/...) — ezért itt NEM lehet vak **b szétbontás, a
            # leképezést explicit kell megadni.
            blocks = [
                Block(
                    tipus=b["tipus"],
                    start=b["kezdet"],
                    end=b["veg"],
                    fixed=b["rogzitett"],
                    counts_toward_into_quota=b["beszamit_kvotaba"],
                )
                for b in muszak_repo.blocks_list(conn, shift_id=m["muszak_id"])
            ]
            for violation in kenyszerek.check(
                shift_obj,
                blocks,
                min_all_break_minute=min_all_break_minute,
                max_continuous_work_minute=max_continuous_work_minute,
            ):
                problems.append(_problem(m, "kenyszer_sertes", violation.rule, violation.message))

        if m["slot_szam"] == 0 and not exception_on_day_has:
            problems.append(
                _problem(
                    m,
                    "nulla_slot",
                    "nulla_slot",
                    f"A műszak ({m['kezdet']}–{m['veg']}) nulla slotot generált, "
                    "és a napja nincs a kivételnapok között.",
                )
            )

    per_counter: dict[str, list[dict]] = defaultdict(list)
    for m in shifts:
        per_counter[m["pult_id"]].append(m)
    for counter_shifts in per_counter.values():
        rendezve = sorted(counter_shifts, key=lambda m: m["kezdet"])
        for previous, next in zip(rendezve, rendezve[1:], strict=False):
            if previous["veg"] > next["kezdet"]:
                problems.append(
                    _problem(
                        previous,
                        "atfedes",
                        "atfedo_muszak",
                        f"Átfedő műszakok ugyanazon a pulton ({previous['pult_nev']}): "
                        f"{previous['kezdet']}–{previous['veg']} és "
                        f"{next['kezdet']}–{next['veg']} "
                        f"({previous['alkalmazott_nev']} / {next['alkalmazott_nev']}).",
                        other_shift_id=next["muszak_id"],
                    )
                )

    return problems


def _problem(
    m: dict, tipus: str, rule: str, message: str, *, other_shift_id: str | None = None
) -> dict:
    return {
        "tipus": tipus,
        "szabaly": rule,
        "uzenet": message,
        "muszak_id": m["muszak_id"],
        "masik_muszak_id": other_shift_id,
        "bolt_nev": m["bolt_nev"],
        "pult_nev": m["pult_nev"],
        "alkalmazott_nev": m["alkalmazott_nev"],
        "kezdet": m["kezdet"],
        "veg": m["veg"],
    }

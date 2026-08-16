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

from mag.repo import foglalas_repo, muszak_repo, torzsadat_repo
from mag.slot import generator
from mag.slot.blokk import FixBlokk

# Sablonok a "műszak felvitele" űrlaphoz (felulet/admin/) — a snapshot-mezők
# (idotartam_perc, puffer_utana_perc, min_racs_perc, foglalhato_arany,
# blokk_szabaly) kitöltésének gyorsítására, a seed/betolt.py három
# Törpilla-pult mintája alapján (roadmap "Az első tíz lépés" 6. pontja).
# Az admin ettől függetlenül felülírhatja a mezőket — a sablon csak
# kiindulás, nem kényszer.
SABLONOK: dict[str, dict] = {
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


def szervezetek(conn: sqlite3.Connection) -> list[dict]:
    return torzsadat_repo.szervezetek_lekerdezese(conn)


def boltok(conn: sqlite3.Connection, *, szervezet_id: str) -> list[dict]:
    return torzsadat_repo.boltok_lekerdezese(conn, szervezet_id=szervezet_id)


def pultok(conn: sqlite3.Connection, *, bolt_id: str) -> list[dict]:
    return torzsadat_repo.pultok_lekerdezese(conn, bolt_id=bolt_id)


def alkalmazottak(conn: sqlite3.Connection, *, bolt_id: str) -> list[dict]:
    return torzsadat_repo.alkalmazottak_lekerdezese(conn, bolt_id=bolt_id)


def szolgaltatasok(conn: sqlite3.Connection, *, bolt_id: str) -> list[dict]:
    return torzsadat_repo.szolgaltatasok_lekerdezese(conn, bolt_id=bolt_id)


def het_muszakjai(
    conn: sqlite3.Connection,
    *,
    szervezet_id: str,
    het_kezdete_datum: str,
    bolt_id: str | None = None,
) -> list[dict]:
    """Egy hét (7 nap, `het_kezdete_datum`-tól, 'YYYY-MM-DD') műszakjai —
    a naptárnézet ('felulet/admin/') ezt rendezi pultok/napok szerint."""
    from mag.slot._idomatek import hozzaad_perc

    datum_tol = f"{het_kezdete_datum}T00:00:00Z"
    datum_ig = hozzaad_perc(datum_tol, 7 * 24 * 60)
    return muszak_repo.muszakok_lekerdezese(
        conn,
        szervezet_id=szervezet_id,
        bolt_id=bolt_id,
        datum_tol=datum_tol,
        datum_ig=datum_ig,
    )


def muszak_reszletei(conn: sqlite3.Connection, *, muszak_id: str) -> dict:
    """Egy műszak blokkjai és slotjai (állapottal együtt) — a naptárnézet
    egy műszakra kattintva ezt jeleníti meg."""
    return {
        "blokkok": muszak_repo.blokkok_lekerdezese(conn, muszak_id=muszak_id),
        "slotok": foglalas_repo.slot_allapotok_lekerdezese(conn, muszak_id=muszak_id),
    }


def muszak_felvitel(
    conn: sqlite3.Connection,
    *,
    szervezet_id: str,
    bolt_id: str,
    pult_id: str,
    alkalmazott_id: str,
    szolgaltatas_id: str,
    kezdet: str,
    veg: str,
    idotartam_perc: int,
    puffer_utana_perc: int,
    min_racs_perc: int,
    foglalhato_arany: float,
    blokk_szabaly: dict,
) -> dict:
    """Műszak felvitele ÉS slot/blokk generálás egy lépésben — ezt hívja
    az admin felület "műszak felvitele" űrlapja a mentés gombra kattintva.

    Ugyanazt a lépéssort követi, mint `mag/api/cli.py::_slotok` és
    `seed/betolt.py::_het_beosztas_betoltese`: létrehozza a műszakot,
    visszatölti (a snapshot-mezők a `Muszak` dataclass-hoz kellenek),
    lefuttatja a generátort a szervezet kivételnapjaival, és — ha nem lett
    kihagyva — elmenti a blokkokat/slotokat egyetlen tranzakcióban."""
    muszak_id = muszak_repo.muszak_letrehoz(
        conn,
        szervezet_id=szervezet_id,
        bolt_id=bolt_id,
        pult_id=pult_id,
        alkalmazott_id=alkalmazott_id,
        szolgaltatas_id=szolgaltatas_id,
        kezdet=kezdet,
        veg=veg,
        idotartam_perc=idotartam_perc,
        puffer_utana_perc=puffer_utana_perc,
        min_racs_perc=min_racs_perc,
        foglalhato_arany=foglalhato_arany,
        blokk_szabaly=blokk_szabaly,
    )
    muszak = muszak_repo.muszak_betoltese(conn, muszak_id)
    kivetel_napok = muszak_repo.kivetel_napok_lekerdezese(conn, szervezet_id=szervezet_id)
    eredmeny = generator.general(muszak, FixBlokk(), kivetel_napok=kivetel_napok)
    if not eredmeny.kihagyva:
        muszak_repo.blokkok_slotok_mentese(
            conn,
            muszak_id=muszak_id,
            szervezet_id=szervezet_id,
            blokkok=eredmeny.blokkok,
            slotok=eredmeny.slotok,
        )
    return {
        "muszak_id": muszak_id,
        "kihagyva": eredmeny.kihagyva,
        "kihagyas_oka": eredmeny.kihagyas_oka,
        "slot_szam": len(eredmeny.slotok),
        "blokk_szam": len(eredmeny.blokkok),
    }


def foglalasok(
    conn: sqlite3.Connection, *, szervezet_id: str, bolt_id: str | None = None
) -> list[dict]:
    return foglalas_repo.foglalasok_lekerdezese(conn, szervezet_id=szervezet_id, bolt_id=bolt_id)


def foglalas_lemond(conn: sqlite3.Connection, *, foglalasi_kod: str) -> foglalas_repo.Eredmeny:
    return foglalas_repo.foglalas_lemond(conn, foglalasi_kod)

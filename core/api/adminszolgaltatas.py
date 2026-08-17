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
from datetime import date, timedelta

from mag.modell.muszak import Blokk
from mag.repo import foglalas_repo, muszak_repo, sablon_repo, torzsadat_repo
from mag.slot import generator
from mag.slot.blokk import FixBlokk
from mag.szabalyok import kenyszerek

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


# ---------------------------------------------------------------------
# Törzsadat-szerkesztés (bolt, pult, alkalmazott, szolgáltatás, kivétel
# nap) — a `felulet/admin/` mai formája a demóadatra (seed/betolt.py)
# támaszkodott, ez a szakasz teszi lehetővé, hogy az admin maga is
# felvigyen/szerkesszen törzsadatot. Minden függvény `hiba` kulccsal tér
# vissza kivétel helyett, ugyanazzal a mintával, mint `muszak_felvitel` —
# a `nev` mezőkön lévő `CHECK (length(nev) > 0)` (migraciok/0001) nyers
# `IntegrityError`-t adna üres névre, ezt itt előre elkapjuk.
# ---------------------------------------------------------------------


def bolt_hozzaadasa(conn: sqlite3.Connection, *, szervezet_id: str, nev: str) -> dict:
    nev = nev.strip()
    if not nev:
        return {"bolt_id": None, "hiba": "A bolt neve nem lehet üres."}
    bolt_id = torzsadat_repo.bolt_letrehoz(conn, szervezet_id=szervezet_id, nev=nev)
    return {"bolt_id": bolt_id, "hiba": None}


def bolt_szerkesztese(conn: sqlite3.Connection, *, bolt_id: str, nev: str) -> dict:
    nev = nev.strip()
    if not nev:
        return {"hiba": "A bolt neve nem lehet üres."}
    torzsadat_repo.bolt_szerkesztese(conn, bolt_id=bolt_id, nev=nev)
    return {"hiba": None}


def pult_hozzaadasa(conn: sqlite3.Connection, *, szervezet_id: str, bolt_id: str, nev: str) -> dict:
    nev = nev.strip()
    if not nev:
        return {"pult_id": None, "hiba": "A pult neve nem lehet üres."}
    pult_id = torzsadat_repo.pult_letrehoz(
        conn, szervezet_id=szervezet_id, bolt_id=bolt_id, nev=nev
    )
    return {"pult_id": pult_id, "hiba": None}


def pult_szerkesztese(conn: sqlite3.Connection, *, pult_id: str, nev: str) -> dict:
    nev = nev.strip()
    if not nev:
        return {"hiba": "A pult neve nem lehet üres."}
    torzsadat_repo.pult_szerkesztese(conn, pult_id=pult_id, nev=nev)
    return {"hiba": None}


def alkalmazott_hozzaadasa(
    conn: sqlite3.Connection, *, szervezet_id: str, bolt_id: str, nev: str
) -> dict:
    nev = nev.strip()
    if not nev:
        return {"alkalmazott_id": None, "hiba": "Az alkalmazott neve nem lehet üres."}
    alkalmazott_id = torzsadat_repo.alkalmazott_letrehoz(
        conn, szervezet_id=szervezet_id, bolt_id=bolt_id, nev=nev
    )
    return {"alkalmazott_id": alkalmazott_id, "hiba": None}


def alkalmazott_szerkesztese(conn: sqlite3.Connection, *, alkalmazott_id: str, nev: str) -> dict:
    nev = nev.strip()
    if not nev:
        return {"hiba": "Az alkalmazott neve nem lehet üres."}
    torzsadat_repo.alkalmazott_szerkesztese(conn, alkalmazott_id=alkalmazott_id, nev=nev)
    return {"hiba": None}


def szolgaltatas_hozzaadasa(
    conn: sqlite3.Connection,
    *,
    szervezet_id: str,
    bolt_id: str,
    nev: str,
    alap_idotartam_perc: int,
) -> dict:
    nev = nev.strip()
    if not nev:
        return {"szolgaltatas_id": None, "hiba": "A szolgáltatás neve nem lehet üres."}
    if alap_idotartam_perc <= 0:
        return {
            "szolgaltatas_id": None,
            "hiba": "Az alapértelmezett időtartam pozitív kell legyen.",
        }
    szolgaltatas_id = torzsadat_repo.szolgaltatas_letrehoz(
        conn,
        szervezet_id=szervezet_id,
        bolt_id=bolt_id,
        nev=nev,
        alap_idotartam_perc=alap_idotartam_perc,
    )
    return {"szolgaltatas_id": szolgaltatas_id, "hiba": None}


def szolgaltatas_szerkesztese(
    conn: sqlite3.Connection, *, szolgaltatas_id: str, nev: str, alap_idotartam_perc: int
) -> dict:
    nev = nev.strip()
    if not nev:
        return {"hiba": "A szolgáltatás neve nem lehet üres."}
    if alap_idotartam_perc <= 0:
        return {"hiba": "Az alapértelmezett időtartam pozitív kell legyen."}
    torzsadat_repo.szolgaltatas_szerkesztese(
        conn,
        szolgaltatas_id=szolgaltatas_id,
        nev=nev,
        alap_idotartam_perc=alap_idotartam_perc,
    )
    return {"hiba": None}


def kivetel_nap_hozzaadasa(
    conn: sqlite3.Connection,
    *,
    szervezet_id: str,
    bolt_id: str | None,
    datum: str,
    indok: str,
) -> dict:
    indok = indok.strip()
    if not indok:
        return {"kivetel_id": None, "hiba": "Az indok nem lehet üres."}
    try:
        date.fromisoformat(datum)
    except ValueError:
        return {"kivetel_id": None, "hiba": f"Érvénytelen dátum: {datum!r} (ÉÉÉÉ-HH-NN kell)."}
    kivetel_id = torzsadat_repo.kivetel_nap_letrehoz(
        conn, szervezet_id=szervezet_id, bolt_id=bolt_id, datum=datum, indok=indok
    )
    return {"kivetel_id": kivetel_id, "hiba": None}


def kivetel_napok(
    conn: sqlite3.Connection, *, szervezet_id: str, bolt_id: str | None = None
) -> list[dict]:
    return torzsadat_repo.kivetel_napok_reszletesen_lekerdezese(
        conn, szervezet_id=szervezet_id, bolt_id=bolt_id
    )


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
    kihagyva — elmenti a blokkokat/slotokat egyetlen tranzakcióban.

    Az időablakot ELŐZETESEN ellenőrzi: a `muszak` tábla `CHECK (veg >
    kezdet)` kényszere (migraciok/0002) amúgy is elutasítaná a fordított
    vagy nulla hosszú ablakot, de nyers `sqlite3.IntegrityError`-ral —
    ez itt, a szolgáltatásrétegben, ÉRTELMES elutasítássá alakul (`hiba`
    kulcs a visszaadott dict-ben, nincs kivétel, és a hívó (a felület)
    egységesen tudja megjeleníteni). A `mag/repo/` rétegen és a
    kényszeren magán ez nem változtat."""
    if veg <= kezdet:
        return {
            "muszak_id": None,
            "kihagyva": False,
            "kihagyas_oka": None,
            "slot_szam": 0,
            "blokk_szam": 0,
            "hiba": (
                f"A műszak vége ({veg}) nem lehet korábbi vagy egyenlő, mint a kezdete ({kezdet})."
            ),
        }

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
        "hiba": None,
    }


def foglalasok(
    conn: sqlite3.Connection, *, szervezet_id: str, bolt_id: str | None = None
) -> list[dict]:
    return foglalas_repo.foglalasok_lekerdezese(conn, szervezet_id=szervezet_id, bolt_id=bolt_id)


def foglalas_lemond(conn: sqlite3.Connection, *, foglalasi_kod: str) -> foglalas_repo.Eredmeny:
    return foglalas_repo.foglalas_lemond(conn, foglalasi_kod)


# ---------------------------------------------------------------------
# Műszak-sablonok (muszak_sablon tábla, migraciok/0003) — lásd a modul
# tetején lévő megjegyzést a két "sablon" fogalom közti különbségről.
# ---------------------------------------------------------------------


def muszak_sablon_mentese(conn: sqlite3.Connection, *, muszak_id: str, nev: str) -> dict:
    """Sablon mentése egy MEGLÉVŐ műszakból: pult, alkalmazott,
    szolgáltatás, napi óra-időablak (a `kezdet`/`veg` óra-részéből) és a
    snapshot-mezők (idotartam_perc, stb.) + blokkszabály.

    Csak AZONOS NAPI, óra-határra eső időablakot tud sablonná menteni
    (lásd migraciok/0003 megjegyzése) — ha a műszak éjfélen átnyúlik vagy
    a kezdete/vége nem kerek óra, ÉRTELMES elutasítást ad (`hiba` kulcs),
    nem kivételt."""
    alapadat = muszak_repo.muszak_alapadatai(conn, muszak_id=muszak_id)
    if alapadat is None:
        return {"sablon_id": None, "hiba": f"Nincs ilyen műszak: {muszak_id}"}

    kezdet_datum, kezdet_ora_resz = alapadat["kezdet"][:10], alapadat["kezdet"][11:19]
    veg_datum, veg_ora_resz = alapadat["veg"][:10], alapadat["veg"][11:19]
    if kezdet_datum != veg_datum:
        return {
            "sablon_id": None,
            "hiba": "Éjfélen átnyúló műszakból ma nem menthető sablon (lásd migraciok/0003).",
        }
    if kezdet_ora_resz[3:] != "00:00" or veg_ora_resz[3:] != "00:00":
        return {
            "sablon_id": None,
            "hiba": "A sablon csak kerek órára eső időablakot tud menteni.",
        }

    kezdet_ora = int(kezdet_ora_resz[:2])
    veg_ora = int(veg_ora_resz[:2])
    if veg_ora == 0:  # éjfél, mint záró óra — 24-ként kezeljük (lásd CHECK)
        veg_ora = 24

    sablon_id = sablon_repo.sablon_letrehoz(
        conn,
        szervezet_id=alapadat["szervezet_id"],
        nev=nev,
        bolt_id=alapadat["bolt_id"],
        pult_id=alapadat["pult_id"],
        alkalmazott_id=alapadat["alkalmazott_id"],
        szolgaltatas_id=alapadat["szolgaltatas_id"],
        kezdet_ora=kezdet_ora,
        veg_ora=veg_ora,
        idotartam_perc=alapadat["idotartam_perc"],
        puffer_utana_perc=alapadat["puffer_utana_perc"],
        min_racs_perc=alapadat["min_racs_perc"],
        foglalhato_arany=alapadat["foglalhato_arany"],
        blokk_szabaly=alapadat["blokk_szabaly"],
    )
    return {"sablon_id": sablon_id, "hiba": None}


def muszak_sablonok(
    conn: sqlite3.Connection, *, szervezet_id: str, bolt_id: str | None = None
) -> list[dict]:
    return sablon_repo.sablonok_lekerdezese(conn, szervezet_id=szervezet_id, bolt_id=bolt_id)


def muszak_sablon_alkalmazasa_napra(
    conn: sqlite3.Connection, *, sablon_id: str, datum: str
) -> dict:
    """A sablont egyetlen napra alkalmazza — létrehozza a műszakot és
    lefuttatja a generátort, ugyanúgy, mint `muszak_felvitel`."""
    sablon = sablon_repo.sablon_betoltese(conn, sablon_id=sablon_id)
    if sablon is None:
        return {"hiba": f"Nincs ilyen sablon: {sablon_id}", "muszak_id": None}

    kezdet = f"{datum}T{sablon['kezdet_ora']:02d}:00:00Z"
    veg_ora = sablon["veg_ora"]
    if veg_ora == 24:
        veg_nap = date.fromisoformat(datum) + timedelta(days=1)
        veg = f"{veg_nap.isoformat()}T00:00:00Z"
    else:
        veg = f"{datum}T{veg_ora:02d}:00:00Z"

    return muszak_felvitel(
        conn,
        szervezet_id=sablon["szervezet_id"],
        bolt_id=sablon["bolt_id"],
        pult_id=sablon["pult_id"],
        alkalmazott_id=sablon["alkalmazott_id"],
        szolgaltatas_id=sablon["szolgaltatas_id"],
        kezdet=kezdet,
        veg=veg,
        idotartam_perc=sablon["idotartam_perc"],
        puffer_utana_perc=sablon["puffer_utana_perc"],
        min_racs_perc=sablon["min_racs_perc"],
        foglalhato_arany=sablon["foglalhato_arany"],
        blokk_szabaly=sablon["blokk_szabaly"],
    )


def muszak_sablon_alkalmazasa_hetre(
    conn: sqlite3.Connection, *, sablon_id: str, het_kezdete_datum: str
) -> list[dict]:
    """A sablont a hét mind a 7 napjára alkalmazza (a seed/betolt.py
    heti mintáját követve — egy sablon egy pultra napi ismétlődés).
    Kivételnapra eső nap a szokásos módon (`generator.general`)
    kihagyásra kerül, de a `muszak` sor létrejön — ez NEM hiba, a
    visszaadott lista elemén `kihagyva: True` jelzi."""
    het_kezdete = date.fromisoformat(het_kezdete_datum)
    eredmenyek = []
    for nap_index in range(7):
        nap = het_kezdete + timedelta(days=nap_index)
        eredmenyek.append(
            muszak_sablon_alkalmazasa_napra(conn, sablon_id=sablon_id, datum=nap.isoformat())
        )
    return eredmenyek


def het_masolasa(
    conn: sqlite3.Connection,
    *,
    szervezet_id: str,
    forras_het_kezdete: str,
    cel_het_kezdete: str,
    bolt_id: str | None = None,
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
    eltolas_nap = (
        date.fromisoformat(cel_het_kezdete) - date.fromisoformat(forras_het_kezdete)
    ).days
    forras_muszakok = het_muszakjai(
        conn,
        szervezet_id=szervezet_id,
        het_kezdete_datum=forras_het_kezdete,
        bolt_id=bolt_id,
    )
    eredmenyek = []
    for muszak in forras_muszakok:
        alapadat = muszak_repo.muszak_alapadatai(conn, muszak_id=muszak["muszak_id"])
        uj_kezdet = _datum_eltol(alapadat["kezdet"], eltolas_nap)
        uj_veg = _datum_eltol(alapadat["veg"], eltolas_nap)
        eredmenyek.append(
            muszak_felvitel(
                conn,
                szervezet_id=szervezet_id,
                bolt_id=muszak["bolt_id"],
                pult_id=muszak["pult_id"],
                alkalmazott_id=muszak["alkalmazott_id"],
                szolgaltatas_id=muszak["szolgaltatas_id"],
                kezdet=uj_kezdet,
                veg=uj_veg,
                idotartam_perc=alapadat["idotartam_perc"],
                puffer_utana_perc=alapadat["puffer_utana_perc"],
                min_racs_perc=alapadat["min_racs_perc"],
                foglalhato_arany=alapadat["foglalhato_arany"],
                blokk_szabaly=alapadat["blokk_szabaly"],
            )
        )
    return eredmenyek


def _datum_eltol(idobelyeg: str, nap: int) -> str:
    """`idobelyeg` (ISO-8601 UTC, pl. '2026-08-18T08:00:00Z') `nap` nappal
    eltolva — a `mag/slot/_idomatek.hozzaad_perc`-hez hasonló, de napban,
    nem percben számol (a hét-másolás mindig egész napokkal tol)."""
    from mag.slot._idomatek import hozzaad_perc

    return hozzaad_perc(idobelyeg, nap * 24 * 60)


# ---------------------------------------------------------------------
# Ütközéslista — a mag/szabalyok/kenyszerek.py-ra épül, nem duplikálja a
# kemény kényszerek logikáját, csak hívja és formázza az eredményt.
# ---------------------------------------------------------------------

# A kenyszerek.ellenoriz() két paramétere ("nincs bennük egyetlen helyes
# érték", lásd a modul docstringje) bolt-/profilfüggő — amíg nincs profil-
# rendszer (blueprint 7. szakasz, "Kényszerkapcsolók" — profilok, még nem
# épült meg), ez a két érték csak egy ÁTMENETI, felülírható alapértelmezés
# az ütközéslistához, NEM egy törzsadatban rögzített, végleges szabály.
_ALAP_MIN_OSSZES_SZUNET_PERC = 20
_ALAP_MAX_FOLYAMATOS_MUNKA_PERC = 360


def utkozeslista(
    conn: sqlite3.Connection,
    *,
    szervezet_id: str,
    bolt_id: str | None = None,
    min_osszes_szunet_perc: int = _ALAP_MIN_OSSZES_SZUNET_PERC,
    max_folyamatos_munka_perc: int = _ALAP_MAX_FOLYAMATOS_MUNKA_PERC,
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
    muszakok = muszak_repo.muszakok_lekerdezese(conn, szervezet_id=szervezet_id, bolt_id=bolt_id)
    kivetel_napok = muszak_repo.kivetel_napok_lekerdezese(
        conn, szervezet_id=szervezet_id, bolt_id=bolt_id
    )

    problemak: list[dict] = []

    for m in muszakok:
        kivetel_napon_van = m["kezdet"][:10] in kivetel_napok

        # Kivétel napon a műszak SOR létezik, de a generátor szándékosan
        # nem tett bele blokkot/slotot (lásd generator.general() és
        # seed/betolt.py::_het_beosztas_betoltese docstringje) — üres
        # blokklistán a kenyszerek.ellenoriz() jogosan jelezne "nincs
        # szünet" hibát, de ez itt NEM valódi sértés, csak a kihagyás
        # mellékhatása. Ezért kivétel napon nem futtatjuk a kényszer-
        # ellenőrzést.
        if not kivetel_napon_van:
            muszak_obj = muszak_repo.muszak_betoltese(conn, muszak_id=m["muszak_id"])
            blokkok = [
                Blokk(**b) for b in muszak_repo.blokkok_lekerdezese(conn, muszak_id=m["muszak_id"])
            ]
            for sertes in kenyszerek.ellenoriz(
                muszak_obj,
                blokkok,
                min_osszes_szunet_perc=min_osszes_szunet_perc,
                max_folyamatos_munka_perc=max_folyamatos_munka_perc,
            ):
                problemak.append(_problema(m, "kenyszer_sertes", sertes.szabaly, sertes.uzenet))

        if m["slot_szam"] == 0 and not kivetel_napon_van:
            problemak.append(
                _problema(
                    m,
                    "nulla_slot",
                    "nulla_slot",
                    f"A műszak ({m['kezdet']}–{m['veg']}) nulla slotot generált, "
                    "és a napja nincs a kivételnapok között.",
                )
            )

    pultonkent: dict[str, list[dict]] = defaultdict(list)
    for m in muszakok:
        pultonkent[m["pult_id"]].append(m)
    for pult_muszakok in pultonkent.values():
        rendezve = sorted(pult_muszakok, key=lambda m: m["kezdet"])
        for elozo, kovetkezo in zip(rendezve, rendezve[1:], strict=False):
            if elozo["veg"] > kovetkezo["kezdet"]:
                problemak.append(
                    _problema(
                        elozo,
                        "atfedes",
                        "atfedo_muszak",
                        f"Átfedő műszakok ugyanazon a pulton ({elozo['pult_nev']}): "
                        f"{elozo['kezdet']}–{elozo['veg']} és "
                        f"{kovetkezo['kezdet']}–{kovetkezo['veg']} "
                        f"({elozo['alkalmazott_nev']} / {kovetkezo['alkalmazott_nev']}).",
                        masik_muszak_id=kovetkezo["muszak_id"],
                    )
                )

    return problemak


def _problema(
    m: dict, tipus: str, szabaly: str, uzenet: str, *, masik_muszak_id: str | None = None
) -> dict:
    return {
        "tipus": tipus,
        "szabaly": szabaly,
        "uzenet": uzenet,
        "muszak_id": m["muszak_id"],
        "masik_muszak_id": masik_muszak_id,
        "bolt_nev": m["bolt_nev"],
        "pult_nev": m["pult_nev"],
        "alkalmazott_nev": m["alkalmazott_nev"],
        "kezdet": m["kezdet"],
        "veg": m["veg"],
    }

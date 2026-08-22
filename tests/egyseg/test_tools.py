"""Egységtesztek a hat eszközre (`assistant/tools/`), LLM nélkül
(eszkoz-szerzodes skill: "Minden eszköz LLM nélkül hívható és tesztelt").

A séma-validáció (`semaellenorzo.py`) és a katalógus-feloldás
(`katalogus.py`) itt nem külön fájlban, hanem a tool-tesztek részeként —
minden hibaágat legalább egy eszközön keresztül lefedünk, hogy a teszt a
tényleges hívási felületet gyakorolja, ne csak a belső segédfüggvényeket.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from assistant.tools import (
    bolt_info,
    foglalas_athelyezes,
    foglalas_lekerdezes,
    foglalas_lemondas,
    foglalas_letrehozas,
    hiba,
    katalogus,
    semaellenorzo,
    semak,
    szabad_idopontok,
)
from core.repo import foglalas_repo, migracio, muszak_repo, torzsadat_repo
from core.slot import generator
from core.slot.blokk import FixedBlock


def _jovoben(minute: int = 5) -> str:
    return (datetime.now(UTC) + timedelta(minutes=minute)).strftime("%Y-%m-%dT%H:%M:%SZ")


def _conn(tmp_path):
    conn = migracio.conn_nyitas(str(tmp_path / "teszt.db"))
    migracio.migral(conn)
    return conn


def _seed(conn) -> dict:
    """Minimális, de a katalógus NEVEIT követő adat — 'Ügyifogyi'
    boltban egy 'petárda' szolgáltatással, egy generált slottal."""
    org_id = torzsadat_repo.org_create(conn, name="Aprajafalva", timezone="Europe/Budapest")
    shop_id = torzsadat_repo.shop_create(conn, org_id=org_id, name="Ügyifogyi")
    counter_id = torzsadat_repo.counter_create(conn, org_id=org_id, shop_id=shop_id, name="Pult 1")
    employee_id = torzsadat_repo.employee_create(
        conn, org_id=org_id, shop_id=shop_id, name="Durranó"
    )
    service_id = torzsadat_repo.service_create(
        conn, org_id=org_id, shop_id=shop_id, name="petárda", alap_duration_minute=5
    )
    shift_id = muszak_repo.shift_create(
        conn,
        org_id=org_id,
        shop_id=shop_id,
        counter_id=counter_id,
        employee_id=employee_id,
        service_id=service_id,
        start="2026-08-18T06:00:00Z",
        end="2026-08-18T07:00:00Z",
        duration_minute=15,
        buffer_after_minute=0,
        min_grid_minute=15,
        bookable_ratio=1.0,
        block_rule={"szunetek": []},
    )
    shift = muszak_repo.shift_load(conn, shift_id)
    result = generator.generate(shift, FixedBlock())
    muszak_repo.blocks_slots_save(
        conn, shift_id=shift_id, org_id=org_id, blocks=result.blocks, slots=result.slots
    )
    slot_id = conn.execute(
        "SELECT id FROM slot WHERE muszak_id = ? ORDER BY kezdet LIMIT 1", (shift_id,)
    ).fetchone()[0]
    return {"org_id": org_id, "shop_id": shop_id, "service_id": service_id, "slot_id": slot_id}


# --- semaellenorzo -----------------------------------------------------


def test_ellenoriz_hianyzo_kotelezo_mezo():
    sema = semak.SEMAK["bolt_info"]["v1"]
    hibak = semaellenorzo.ellenoriz(sema, {"bolt_id": "torpilla"})
    assert any("mit" in h for h in hibak)


def test_ellenoriz_ismeretlen_mezo_additional_false():
    sema = semak.SEMAK["bolt_info"]["v1"]
    hibak = semaellenorzo.ellenoriz(
        sema, {"bolt_id": "torpilla", "mit": "cim", "session_id": "s", "kitalalt": 1}
    )
    assert any("kitalalt" in h for h in hibak)


def test_ellenoriz_ervenytelen_enum():
    sema = semak.SEMAK["bolt_info"]["v1"]
    hibak = semaellenorzo.ellenoriz(
        sema, {"bolt_id": "nemletezo_bolt", "mit": "cim", "session_id": "s"}
    )
    assert any("bolt_id" in h for h in hibak)


def test_ellenoriz_ervenyes_nincs_hiba():
    sema = semak.SEMAK["bolt_info"]["v1"]
    hibak = semaellenorzo.ellenoriz(sema, {"bolt_id": "torpilla", "mit": "cim", "session_id": "s"})
    assert hibak == []


# --- katalogus -----------------------------------------------------------


def test_katalogus_bolt_felold_ismert(tmp_path):
    conn = _conn(tmp_path)
    ctx = _seed(conn)
    assert katalogus.bolt_id_felold(conn, ctx["org_id"], "ugyifogyi") == ctx["shop_id"]


def test_katalogus_bolt_felold_ismeretlen_slug(tmp_path):
    conn = _conn(tmp_path)
    ctx = _seed(conn)
    assert katalogus.bolt_id_felold(conn, ctx["org_id"], "nemletezo") is None


def test_katalogus_szolgaltatas_felold_tobb_slug_egy_szolgaltatasra(tmp_path):
    conn = _conn(tmp_path)
    ctx = _seed(conn)
    kis = katalogus.szolgaltatas_id_felold(conn, ctx["org_id"], "kis_petarda")
    nagy = katalogus.szolgaltatas_id_felold(conn, ctx["org_id"], "nagy_petarda")
    assert kis == nagy == ctx["service_id"]


# --- szabad_idopontok ----------------------------------------------------


def test_szabad_idopontok_sikeres_hold_kerul_a_jeloltekre(tmp_path):
    conn = _conn(tmp_path)
    ctx = _seed(conn)
    eredmeny = szabad_idopontok.hivas(
        conn,
        {
            "bolt_id": "ugyifogyi",
            "datum_tol": "2026-08-18T00:00:00Z",
            "datum_ig": "2026-08-18T23:59:59Z",
            "session_id": "session-1",
        },
        org_id=ctx["org_id"],
    )
    assert eredmeny["sikeres"] is True
    assert eredmeny["jeloltek"]
    for jelolt in eredmeny["jeloltek"]:
        assert foglalas_repo.slot_free(conn, jelolt["slot_id"]) is False  # hold ül rajta


def test_szabad_idopontok_ervenytelen_parameter(tmp_path):
    conn = _conn(tmp_path)
    ctx = _seed(conn)
    eredmeny = szabad_idopontok.hivas(
        conn, {"bolt_id": "ugyifogyi", "session_id": "s"}, org_id=ctx["org_id"]
    )
    assert eredmeny["sikeres"] is False
    assert eredmeny["ok"] == "ervenytelen_parameter"


def test_szabad_idopontok_semmi_nincs_meghirdetve_nem_tunik_teltnek(tmp_path):
    """A `_seed` egyetlen slotja 2026-08-18-án van; 2099-től nézve a
    boltnak NINCS meghirdetett beosztása. A helyes válasz ezért NEM az,
    hogy "nincs szabad hely" (az teltnek mutatná egy üres naptárat),
    hanem hogy erre az időszakra nincs meghirdetve időpont."""
    conn = _conn(tmp_path)
    ctx = _seed(conn)
    eredmeny = szabad_idopontok.hivas(
        conn,
        {
            "bolt_id": "ugyifogyi",
            "datum_tol": "2099-01-01T00:00:00Z",
            "datum_ig": "2099-01-02T00:00:00Z",
            "session_id": "session-1",
        },
        org_id=ctx["org_id"],
    )
    assert eredmeny == hiba.hiba_eredmeny(
        hiba.Ok.NINCS_MEGHIRDETETT_IDOPONT, "nincs_meghirdetett_idopont", alternativ_dimenzio=None
    )


def test_szabad_idopontok_van_beosztas_de_betelt_szukosseget_jelez(tmp_path):
    """A megkülönböztetés másik fele: ha VAN meghirdetett beosztás, csak
    éppen minden hely elkelt, akkor az valódi szűkösség — ilyenkor a
    "nincs szabad hely" a helyes (és igaz) válasz."""
    conn = _conn(tmp_path)
    ctx = _seed(conn)

    # Minden slotot lefoglalunk, hogy a beosztás LÉTEZZEN, de tele legyen.
    slot_id_k = [sor[0] for sor in conn.execute("SELECT id FROM slot ORDER BY kezdet").fetchall()]
    for i, slot_id in enumerate(slot_id_k):
        foglalas_repo.booking_create(
            conn,
            slot_id=slot_id,
            customer_key=f"{i:064d}",
            idempotency_key=f"betelt-{i}",
            session_id=f"betelt-session-{i}",
        )

    eredmeny = szabad_idopontok.hivas(
        conn,
        {
            "bolt_id": "ugyifogyi",
            "datum_tol": "2026-08-18T00:00:00Z",
            "datum_ig": "2026-08-18T23:59:59Z",
            "session_id": "session-1",
        },
        org_id=ctx["org_id"],
    )
    assert eredmeny["sikeres"] is False
    assert eredmeny["ok"] == "nincs_szabad_hely"
    assert eredmeny["uzenet_kulcs"] == "nincs_szabad_hely_az_ablakban"


def test_szabad_idopontok_alternativ_dimenzio_napszak(tmp_path):
    """A kért ablakban (2026-08-18, csak "este") nincs jelölt — az
    egyetlen slot ezen a napon van, de "barmikor" napszakkal
    megtalálható: az alternatíva dimenziója "napszak"."""
    conn = _conn(tmp_path)
    ctx = _seed(conn)
    eredmeny = szabad_idopontok.hivas(
        conn,
        {
            "bolt_id": "ugyifogyi",
            "datum_tol": "2026-08-18T00:00:00Z",
            "datum_ig": "2026-08-18T23:59:59Z",
            "napszak": "este",
            "session_id": "session-1",
        },
        org_id=ctx["org_id"],
    )
    assert eredmeny["sikeres"] is False
    assert eredmeny["alternativ_dimenzio"] == "napszak"


def test_szabad_idopontok_alternativ_dimenzio_nap(tmp_path):
    """A kért napon (2026-08-17, kedd ELŐTTI nap) nincs semmi, de a
    slot ugyanazon a héten (2026-08-18) van — az alternatíva
    dimenziója "nap", nem "napszak" (a "barmikor" napszak sem segítene
    az eredeti napon)."""
    conn = _conn(tmp_path)
    ctx = _seed(conn)
    eredmeny = szabad_idopontok.hivas(
        conn,
        {
            "bolt_id": "ugyifogyi",
            "datum_tol": "2026-08-17T00:00:00Z",
            "datum_ig": "2026-08-17T23:59:59Z",
            "session_id": "session-1",
        },
        org_id=ctx["org_id"],
    )
    assert eredmeny["sikeres"] is False
    assert eredmeny["alternativ_dimenzio"] == "nap"


def test_szabad_idopontok_alternativ_dimenzio_het(tmp_path):
    """A kért hét (2026-08-10 - 2026-08-16) teljesen üres, de a
    KÖVETKEZŐ héten (2026-08-18) van a slot — az alternatíva
    dimenziója "het"."""
    conn = _conn(tmp_path)
    ctx = _seed(conn)
    eredmeny = szabad_idopontok.hivas(
        conn,
        {
            "bolt_id": "ugyifogyi",
            "datum_tol": "2026-08-10T00:00:00Z",
            "datum_ig": "2026-08-16T23:59:59Z",
            "session_id": "session-1",
        },
        org_id=ctx["org_id"],
    )
    assert eredmeny["sikeres"] is False
    assert eredmeny["alternativ_dimenzio"] == "het"


def test_szabad_idopontok_alternativ_dimenzio_nap_megorzi_a_kert_napszakot(tmp_path):
    """A 'nap' (és 'het') dimenzió próbája a kért napszakot VÁLTOZATLANUL
    hagyja — blueprint 5. szakasz: "péntek délelőtt jövő héten", a
    napszak kemény, csak a hét puha. Egy másik napon, de MÁS napszakban
    szabad időpont nem számít 'nap' alternatívának — különben hamis
    pozitívot adna, olyat ajánlva, ami a vásárló tényleges kérésének
    (itt: délelőtt) nem felel meg."""
    conn = _conn(tmp_path)
    ctx = _seed(conn)  # 2026-08-18 (kedd), helyi 08:00-09:00 (délelőtt)

    # Második műszak UGYANAZON a héten (2026-08-20, csütörtök), de ESTE
    # (helyi 20:00-21:00, UTC 18:00-19:00 nyáron/CEST) — a régi (javítás
    # előtti) kód ezt tévesen 'nap' alternatívaként ajánlotta volna.
    counter_id = torzsadat_repo.counter_create(
        conn, org_id=ctx["org_id"], shop_id=ctx["shop_id"], name="Pult 2"
    )
    employee_id = torzsadat_repo.employee_create(
        conn, org_id=ctx["org_id"], shop_id=ctx["shop_id"], name="Ügyifogyi Este"
    )
    shift_id = muszak_repo.shift_create(
        conn,
        org_id=ctx["org_id"],
        shop_id=ctx["shop_id"],
        counter_id=counter_id,
        employee_id=employee_id,
        service_id=ctx["service_id"],
        start="2026-08-20T18:00:00Z",
        end="2026-08-20T19:00:00Z",
        duration_minute=15,
        buffer_after_minute=0,
        min_grid_minute=15,
        bookable_ratio=1.0,
        block_rule={"szunetek": []},
    )
    shift = muszak_repo.shift_load(conn, shift_id)
    eredmeny_generalas = generator.generate(shift, FixedBlock())
    muszak_repo.blocks_slots_save(
        conn,
        shift_id=shift_id,
        org_id=ctx["org_id"],
        blocks=eredmeny_generalas.blocks,
        slots=eredmeny_generalas.slots,
    )

    # A kért nap (2026-08-19, szerda) üres — sem a délelőtti (08-18),
    # sem az esti (08-20) slot nincs ezen a napon.
    eredmeny = szabad_idopontok.hivas(
        conn,
        {
            "bolt_id": "ugyifogyi",
            "datum_tol": "2026-08-19T00:00:00Z",
            "datum_ig": "2026-08-19T23:59:59Z",
            "napszak": "delelott",
            "session_id": "session-1",
        },
        org_id=ctx["org_id"],
    )
    assert eredmeny["sikeres"] is False
    # NEM "nap" — az egyetlen másik napi (08-20) slot este van, nem
    # délelőtt, tehát nem valódi alternatíva erre a kérésre.
    assert eredmeny["alternativ_dimenzio"] is None


def test_szabad_idopontok_ismeretlen_szolgaltatas(tmp_path):
    conn = _conn(tmp_path)
    ctx = _seed(conn)
    eredmeny = szabad_idopontok.hivas(
        conn,
        {
            "bolt_id": "ugyifogyi",
            "szolgaltatas_id": "nagy_orom",  # Törpilláé, nem Ügyifogyié
            "datum_tol": "2026-08-18T00:00:00Z",
            "datum_ig": "2026-08-18T23:59:59Z",
            "session_id": "session-1",
        },
        org_id=ctx["org_id"],
    )
    assert eredmeny["sikeres"] is False
    assert eredmeny["ok"] == "ismeretlen_szolgaltatas"


# --- foglalas_letrehozas ---------------------------------------------------


def test_foglalas_letrehozas_sikeres(tmp_path):
    conn = _conn(tmp_path)
    ctx = _seed(conn)
    eredmeny = foglalas_letrehozas.hivas(
        conn,
        {
            "slot_id": ctx["slot_id"],
            "vasarlo_kulcs_hash": "a" * 64,
            "idempotencia_kulcs": "idem-1",
            "session_id": "session-1",
        },
    )
    assert eredmeny["sikeres"] is True
    assert len(eredmeny["foglalasi_kod"]) == 8


def test_foglalas_letrehozas_nincs_ilyen_slot(tmp_path):
    conn = _conn(tmp_path)
    _seed(conn)
    eredmeny = foglalas_letrehozas.hivas(
        conn,
        {
            "slot_id": "nemletezo",
            "vasarlo_kulcs_hash": "a" * 64,
            "idempotencia_kulcs": "idem-1",
            "session_id": "session-1",
        },
    )
    assert eredmeny["sikeres"] is False
    assert eredmeny["ok"] == "ervenytelen_parameter"


def test_foglalas_letrehozas_megeloztek(tmp_path):
    conn = _conn(tmp_path)
    ctx = _seed(conn)
    foglalas_repo.booking_create(conn, ctx["slot_id"], "b" * 64, "mas-idem", "session-mas")

    eredmeny = foglalas_letrehozas.hivas(
        conn,
        {
            "slot_id": ctx["slot_id"],
            "vasarlo_kulcs_hash": "a" * 64,
            "idempotencia_kulcs": "idem-1",
            "session_id": "session-1",
        },
    )
    assert eredmeny["sikeres"] is False
    assert eredmeny["ok"] == "megeloztek"


# --- foglalas_athelyezes ---------------------------------------------------


def test_foglalas_athelyezes_sikeres(tmp_path):
    conn = _conn(tmp_path)
    ctx = _seed(conn)
    foglalas_repo.booking_create(conn, ctx["slot_id"], "a" * 64, "idem-eredeti", "session-1")
    code = conn.execute(
        "SELECT foglalasi_kod FROM foglalas WHERE slot_id = ?", (ctx["slot_id"],)
    ).fetchone()[0]
    masik_slot = conn.execute(
        "SELECT id FROM slot WHERE muszak_id = "
        "(SELECT muszak_id FROM slot WHERE id = ?) AND id <> ? LIMIT 1",
        (ctx["slot_id"], ctx["slot_id"]),
    ).fetchone()[0]

    eredmeny = foglalas_athelyezes.hivas(
        conn,
        {
            "foglalasi_kod": code,
            "uj_slot_id": masik_slot,
            "idempotencia_kulcs": "idem-athelyezes",
            "session_id": "session-1",
        },
    )
    assert eredmeny["sikeres"] is True
    assert eredmeny["foglalasi_kod"] != code


def test_foglalas_athelyezes_ervenytelen_kod(tmp_path):
    conn = _conn(tmp_path)
    ctx = _seed(conn)
    eredmeny = foglalas_athelyezes.hivas(
        conn,
        {
            "foglalasi_kod": "NEMLETEZO",
            "uj_slot_id": ctx["slot_id"],
            "idempotencia_kulcs": "idem-1",
            "session_id": "session-1",
        },
    )
    assert eredmeny["sikeres"] is False
    assert eredmeny["ok"] == "ervenytelen_kod"


# --- foglalas_lekerdezes ---------------------------------------------------


def test_foglalas_lekerdezes_sajat_foglalasok(tmp_path):
    conn = _conn(tmp_path)
    ctx = _seed(conn)
    foglalas_repo.booking_create(conn, ctx["slot_id"], "a" * 64, "idem-1", "session-1")

    eredmeny = foglalas_lekerdezes.hivas(
        conn, {"vasarlo_kulcs_hash": "a" * 64, "session_id": "session-1"}
    )
    assert eredmeny["sikeres"] is True
    assert len(eredmeny["foglalasok"]) == 1


def test_foglalas_lekerdezes_nincs_foglalas_ures_lista(tmp_path):
    conn = _conn(tmp_path)
    _seed(conn)
    eredmeny = foglalas_lekerdezes.hivas(
        conn, {"vasarlo_kulcs_hash": "c" * 64, "session_id": "session-1"}
    )
    assert eredmeny["sikeres"] is True
    assert eredmeny["foglalasok"] == []


# --- foglalas_lemondas ---------------------------------------------------


def test_foglalas_lemondas_sikeres(tmp_path):
    conn = _conn(tmp_path)
    ctx = _seed(conn)
    foglalas_repo.booking_create(conn, ctx["slot_id"], "a" * 64, "idem-1", "session-1")
    code = conn.execute(
        "SELECT foglalasi_kod FROM foglalas WHERE slot_id = ?", (ctx["slot_id"],)
    ).fetchone()[0]

    eredmeny = foglalas_lemondas.hivas(conn, {"foglalasi_kod": code, "session_id": "session-1"})
    assert eredmeny == hiba.sikeres_eredmeny()


def test_foglalas_lemondas_mar_lemondva(tmp_path):
    conn = _conn(tmp_path)
    ctx = _seed(conn)
    foglalas_repo.booking_create(conn, ctx["slot_id"], "a" * 64, "idem-1", "session-1")
    code = conn.execute(
        "SELECT foglalasi_kod FROM foglalas WHERE slot_id = ?", (ctx["slot_id"],)
    ).fetchone()[0]
    foglalas_lemondas.hivas(conn, {"foglalasi_kod": code, "session_id": "session-1"})

    eredmeny = foglalas_lemondas.hivas(conn, {"foglalasi_kod": code, "session_id": "session-1"})
    assert eredmeny["sikeres"] is False
    assert eredmeny["ok"] == "mar_lemondva"


# --- bolt_info -----------------------------------------------------------


def test_bolt_info_cim(tmp_path):
    conn = _conn(tmp_path)
    ctx = _seed(conn)
    eredmeny = bolt_info.hivas(
        conn, {"bolt_id": "ugyifogyi", "mit": "cim", "session_id": "s"}, org_id=ctx["org_id"]
    )
    assert eredmeny["sikeres"] is True
    assert eredmeny["cim"] == katalogus.BOLT_INFO_STATIKUS["ugyifogyi"]["cim"]


def test_bolt_info_idotartam_valodi_szolgaltatas_adatbol(tmp_path):
    conn = _conn(tmp_path)
    ctx = _seed(conn)
    eredmeny = bolt_info.hivas(
        conn,
        {"bolt_id": "ugyifogyi", "mit": "idotartam", "session_id": "s"},
        org_id=ctx["org_id"],
    )
    assert eredmeny["sikeres"] is True
    assert eredmeny["szolgaltatasok"] == [{"nev": "petárda", "idotartam_perc": 5}]


def test_bolt_info_megjelenes_ures_alapertelmezetten(tmp_path):
    conn = _conn(tmp_path)
    ctx = _seed(conn)
    eredmeny = bolt_info.hivas(
        conn,
        {"bolt_id": "ugyifogyi", "mit": "megjelenes", "session_id": "s"},
        org_id=ctx["org_id"],
    )
    assert eredmeny == hiba.sikeres_eredmeny(megjelenes="")


def test_bolt_info_megjelenes_szerkesztett_ertek(tmp_path):
    conn = _conn(tmp_path)
    ctx = _seed(conn)
    conn.execute("UPDATE bolt SET megjelenes = ? WHERE id = ?", ("piros cégér", ctx["shop_id"]))
    eredmeny = bolt_info.hivas(
        conn,
        {"bolt_id": "ugyifogyi", "mit": "megjelenes", "session_id": "s"},
        org_id=ctx["org_id"],
    )
    assert eredmeny == hiba.sikeres_eredmeny(megjelenes="piros cégér")


def test_bolt_info_termek_ures_alapertelmezetten(tmp_path):
    conn = _conn(tmp_path)
    ctx = _seed(conn)
    eredmeny = bolt_info.hivas(
        conn, {"bolt_id": "ugyifogyi", "mit": "termek", "session_id": "s"}, org_id=ctx["org_id"]
    )
    assert eredmeny["sikeres"] is True
    assert eredmeny["szolgaltatasok"] == [{"nev": "petárda", "termekleiras": ""}]


def test_bolt_info_ar_ures_alapertelmezetten(tmp_path):
    conn = _conn(tmp_path)
    ctx = _seed(conn)
    eredmeny = bolt_info.hivas(
        conn, {"bolt_id": "ugyifogyi", "mit": "ar", "session_id": "s"}, org_id=ctx["org_id"]
    )
    assert eredmeny["sikeres"] is True
    assert eredmeny["szolgaltatasok"] == [{"nev": "petárda", "ar": ""}]


def test_bolt_info_termek_es_ar_szerkesztett_ertek(tmp_path):
    conn = _conn(tmp_path)
    ctx = _seed(conn)
    conn.execute(
        "UPDATE szolgaltatas SET termekleiras = ?, ar = ? WHERE id = ?",
        ("durranó, fényes", "150 arany", ctx["service_id"]),
    )
    termek = bolt_info.hivas(
        conn, {"bolt_id": "ugyifogyi", "mit": "termek", "session_id": "s"}, org_id=ctx["org_id"]
    )
    ar = bolt_info.hivas(
        conn, {"bolt_id": "ugyifogyi", "mit": "ar", "session_id": "s"}, org_id=ctx["org_id"]
    )
    assert termek["szolgaltatasok"] == [{"nev": "petárda", "termekleiras": "durranó, fényes"}]
    assert ar["szolgaltatasok"] == [{"nev": "petárda", "ar": "150 arany"}]


def test_bolt_info_ismeretlen_bolt(tmp_path):
    conn = _conn(tmp_path)
    ctx = _seed(conn)
    eredmeny = bolt_info.hivas(
        conn, {"bolt_id": "torpilla", "mit": "cim", "session_id": "s"}, org_id=ctx["org_id"]
    )
    assert eredmeny["sikeres"] is False
    assert eredmeny["ok"] == "ismeretlen_bolt"

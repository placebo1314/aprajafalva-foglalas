"""A `kinalat` eszköz és a bemutatkozás (ADR-032).

**Mért hiány**: az első idegen próbában a rendszer feltételezte, hogy a
vásárló ismeri a boltokat. Ez a fájl azt őrzi, hogy a válasz a
TÖRZSADATBÓL jöjjön — mert ha sablonba égetnénk, egy admin-oldali
átírás után a rendszer mást mondana, mint amit a tábla tartalmaz.
"""

from __future__ import annotations

from assistant.tools import kinalat
from assistant.valasz import bemutatkozas_szoveg, bolt_tetel_mondva
from core.repo import migracio, torzsadat_repo


def _conn(tmp_path):
    conn = migracio.conn_nyitas(str(tmp_path / "teszt.db"))
    migracio.migral(conn)
    return conn


def _seed(conn) -> str:
    """Két bolt, egy-egy szolgáltatással — a katalógus SORRENDJE a
    `katalogus.BOLT_NEVEK`-é, nem az adatbázisé."""
    org_id = torzsadat_repo.org_create(conn, name="Aprajafalva", timezone="Europe/Budapest")
    for bolt_nev, szolgaltatas, leiras in (
        ("Szundi", "altató", "Gyógynövényes főzet. Egy csésze, és mély álom."),
        ("Ügyifogyi", "petárda", "Kézzel készített ünnepi petárda. Két méretben."),
    ):
        bolt_id = torzsadat_repo.shop_create(conn, org_id=org_id, name=bolt_nev)
        szolgaltatas_id = torzsadat_repo.service_create(
            conn, org_id=org_id, shop_id=bolt_id, name=szolgaltatas, alap_duration_minute=15
        )
        torzsadat_repo.service_description_update(
            conn, service_id=szolgaltatas_id, termekleiras=leiras, ar="titok"
        )
    return org_id


def test_a_katalogus_a_torzsadatbol_jon(tmp_path):
    conn = _conn(tmp_path)
    org_id = _seed(conn)

    eredmeny = kinalat.hivas(conn, {"session_id": "s"}, org_id=org_id)

    assert eredmeny["sikeres"] is True
    assert [b["nev"] for b in eredmeny["boltok"]] == ["Szundi", "Ügyifogyi"]
    assert eredmeny["boltok"][0]["szolgaltatasok"][0]["nev"] == "altató"


def test_a_leiras_elso_mondata_megy_ki(tmp_path):
    """A teljes termékleírás több mondat — egy katalógusban az első
    elég; a részletet a `bolt_info` adja, ha rákérdeznek."""
    conn = _conn(tmp_path)
    org_id = _seed(conn)

    eredmeny = kinalat.hivas(conn, {"session_id": "s"}, org_id=org_id)

    assert eredmeny["boltok"][0]["szolgaltatasok"][0]["leiras"] == "Gyógynövényes főzet."


def test_az_ar_nem_megy_ki(tmp_path):
    """Ugyanaz a kimeneti tiltás, mint a `bolt_info` termék-ágán: az ár
    ezen a csatornán nem engedélyezett tényválasz."""
    conn = _conn(tmp_path)
    org_id = _seed(conn)

    eredmeny = kinalat.hivas(conn, {"session_id": "s"}, org_id=org_id)

    assert "titok" not in str(eredmeny)
    for bolt in eredmeny["boltok"]:
        for szolgaltatas in bolt["szolgaltatasok"]:
            assert "ar" not in szolgaltatas


def test_egy_boltra_szukitheto(tmp_path):
    conn = _conn(tmp_path)
    org_id = _seed(conn)

    eredmeny = kinalat.hivas(conn, {"session_id": "s", "bolt_id": "szundi"}, org_id=org_id)

    assert [b["nev"] for b in eredmeny["boltok"]] == ["Szundi"]


def test_ismeretlen_bolt_hibat_ad(tmp_path):
    conn = _conn(tmp_path)
    org_id = _seed(conn)

    eredmeny = kinalat.hivas(conn, {"session_id": "s", "bolt_id": "torpilla"}, org_id=org_id)

    assert eredmeny["sikeres"] is False


# -- a mondat ---------------------------------------------------------


def _boltok() -> list[dict]:
    return [
        {
            "bolt_id": "szundi",
            "nev": "Szundi",
            "szolgaltatasok": [{"nev": "altató", "leiras": "L."}],
        },
        {
            "bolt_id": "ugyifogyi",
            "nev": "Ügyifogyi",
            "szolgaltatasok": [{"nev": "petárda", "leiras": "P."}],
        },
    ]


def test_a_koszones_felsorolja_a_boltokat_ragozva():
    szoveg = bemutatkozas_szoveg(_boltok(), koszones=True)

    assert "a Szundiba altatóért" in szoveg
    assert "az Ügyifogyiba petárdáért" in szoveg
    assert szoveg.endswith("?"), "a bemutatkozás kérdéssel zárul — választani kell"


def test_egy_bolt_eseten_a_LEIRAS_megy_ki():
    """Egy boltnál már nem választásról van szó, hanem arról, mit kap."""
    szoveg = bemutatkozas_szoveg(_boltok()[:1])

    assert "Szundi — altató" in szoveg
    assert "L." in szoveg


def test_a_tetel_egy_helyen_kesziil():
    """Ugyanaz a tétel kell a köszönéshez, a katalógushoz és a
    beszélhető zárt kérdéshez — egy helyen, hogy ne driftelhessenek."""
    assert bolt_tetel_mondva("Törpilla", [{"nev": "boldogság"}]) == "a Törpillába boldogságért"

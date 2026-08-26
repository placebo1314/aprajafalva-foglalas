"""Egységtesztek a frusztráció-felismerésre (`assistant/frusztracio.py`).

A jel-felismerés determinisztikus (nem modellmunka, blueprint 10.
szakasz), ezért itt LLM nélkül, közvetlenül tesztelhető. A modul
docstringje indokolja, miért helyénvaló itt a kulcsszólista, miközben az
ÉRTELMEZÉSNÉL elutasítottuk: ott a döntés múlik rajta, itt csak egy
felajánlás."""

from __future__ import annotations

from assistant.frusztracio import Frusztracio, kimondott_jel

# --- kimondott jel ----------------------------------------------------


def test_kimondott_jel_elakadasra_igaz():
    assert kimondott_jel("nem értem, mit kell csinálni")
    assert kimondott_jel("Már mondtam, hogy keddre!")
    assert kimondott_jel("elegem van ebből")
    assert kimondott_jel("ez így nem működik")


def test_kimondott_jel_hasznos_mondatra_hamis():
    """A "nem jó a kedd" NEM frusztráció, hanem előrevivő információ —
    ha ezt is jelnek vennénk, minden alkudozás kiúthoz vezetne."""
    assert not kimondott_jel("nem jó a kedd, inkább szerda")
    assert not kimondott_jel("Törpillához mennék holnap")
    assert not kimondott_jel("mégsem, maradjunk a keddnél")


def test_kimondott_jel_tajszolasi_alakot_is_lat():
    """A normalizálón át megy — a tájszólás nem bújhat ki alóla."""
    assert kimondott_jel("hát ién nem értem, hogy kell ezt")


# --- pontozás ---------------------------------------------------------


def test_eredmenytelen_fordulok_osszeadodnak():
    f = Frusztracio()
    for _ in range(3):
        f.fordulo("mennék", "visszakerdezes")
        assert not f.kiutat_kell()

    f.fordulo("mennék", "visszakerdezes")

    assert f.kiutat_kell()


def test_kimondott_jel_gyorsabban_visz_kiuthoz():
    """Két kimondott panasz elég — a vásárló szava többet nyom, mint a
    mi számlálónk."""
    f = Frusztracio()
    f.fordulo("nem értem", "visszakerdezes")  # 2 + 1
    assert not f.kiutat_kell()

    f.fordulo("már mondtam", "visszakerdezes")  # +3

    assert f.kiutat_kell()


def test_sikeres_ajanlat_nullaz():
    """Ha a beszélgetés jó irányba fordul, a korábbi döccenőket nem
    hordozzuk tovább."""
    f = Frusztracio()
    f.fordulo("nem értem", "visszakerdezes")
    f.fordulo("Törpillához mennék", "ajanlat")

    assert f.pont == 0
    assert not f.kiutat_kell()


def test_kiut_kiadasa_nullaz_de_szamon_tartja():
    f = Frusztracio()
    for _ in range(4):
        f.fordulo("mennék", "visszakerdezes")
    assert f.kiutat_kell()

    f.kiut_kiadva()

    assert not f.kiutat_kell()
    assert f.kiut_ajanlva == 1


# --- a MÁSODIK kiút: emberhez irányítás -------------------------------


def test_emberhez_kell_csak_kiut_utan_es_kimondott_panaszra():
    """A második kiút feltétele MÁS, mint az elsőé: az elsőhöz
    pontgyűjtés kell (onnan tudjuk meg, hogy baj van), a másodikhoz
    az, hogy a felajánlott kiút UTÁN a vásárló még mindig elakadt."""
    f = Frusztracio()
    # Kiút előtt a kimondott panasz önmagában nem visz emberhez.
    assert not f.emberhez_kell("nem értem, mit kell csinálni")

    f.kiut_kiadva()

    assert f.emberhez_kell("nem értem, mit kell csinálni")
    # …de egy előrevivő mondat NEM: az azt jelenti, hogy a kiút hatott.
    assert not f.emberhez_kell("akkor legyen a Törpilla")


def test_emberhez_kell_nem_gyujt_ujabb_pontot():
    """A pontszám az ELSŐ kiúthoz való. A második kérdése nem az, hogy
    „mennyire rossz", hanem hogy „a javaslatunk segített-e" — arra egy
    kimondott panasz a válasz."""
    f = Frusztracio()
    f.kiut_kiadva()
    assert f.pont == 0
    assert not f.kiutat_kell()
    assert f.emberhez_kell("nem értem")

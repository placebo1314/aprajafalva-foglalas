"""A redaktáló (`privacy/redakcio/`) és a próba-napló redaktálásának
tesztjei — CLAUDE.md 2. invariáns: "nyers vásárlóazonosító soha nem
kerül lemezre, logba vagy trace-be".

A teszt két szinten bizonyít:

1. **A modul szintjén** — a felismert alakokat eltakarja, a NEM
   személyes adatot (dátum, óra, foglalási kód) érintetlenül hagyja.
   Ez a második fele legalább olyan fontos: egy túl mohó redaktáló
   használhatatlanná tenné a naplót.
2. **A napló szintjén** — a `ui/vasarlo.py::_proba_naplo_ir` ténylegesen
   redaktálva ír, nem csak "meg lehetne hívni rá a redaktálót".
"""

from __future__ import annotations

import json

import pytest

from privacy.redakcio import (
    redaktal,
    redaktal_ertekek,
    tartalmaz_szemelyes_adatot,
)


@pytest.mark.parametrize(
    "bemenet,varhato_cimke",
    [
        ("A telefonszámom 06301234567, hívjatok.", "<TELEFON>"),
        ("Hívj a +36 30 123 4567 számon", "<TELEFON>"),
        ("Elérsz a 0036301234567 számon", "<TELEFON>"),
        ("A TAJ-om 123 456 789.", "<AZONOSITO>"),
        ("A TAJ-om 123-456-789", "<AZONOSITO>"),
        ("Az adóazonosítóm 8412345678", "<AZONOSITO>"),
        ("Az igazolványom 123456AB", "<AZONOSITO>"),
        ("A kártyaszámom 4111 1111 1111 1111", "<BANKKARTYA>"),
        ("Az emailem valaki@pelda.hu", "<EMAIL>"),
        ("Jó napot. Én a Marika vagyok.", "<NEV>"),
        ("A nevem Kovács János, időpontot kérek.", "<NEV>"),
    ],
)
def test_redaktal_eltakarja_a_szemelyes_adatot(bemenet: str, varhato_cimke: str) -> None:
    eredmeny = redaktal(bemenet)
    assert varhato_cimke in eredmeny
    assert tartalmaz_szemelyes_adatot(bemenet)


@pytest.mark.parametrize(
    "bemenet",
    [
        # Dátum — NEM személyes adat, és a napló használhatatlan lenne
        # nélküle.
        "Szeretnék időpontot jövő hét keddre, 2026-08-25-re.",
        "datum_tol: 2026-08-25T00:00:00Z",
        # Óra, preferencia.
        "Kb 10 körül lenne jó holnap délelőtt",
        "holnap 10:30-kor",
        # Foglalási kód — a rendszer állítja elő, nem a vásárló hozza;
        # a hibakereséshez pont ez kell.
        "Le szeretném mondani a foglalásomat, a kód X7K2M9QP.",
        # Évszám egy abszurd kérésben (robusztussági halmaz).
        "szeretnék időpontot 1823-ra",
        # Sima mondat, minden szám nélkül.
        "Petárdázni szeretnék kedden délelőtt.",
    ],
)
def test_redaktal_nem_bantja_a_nem_szemelyes_adatot(bemenet: str) -> None:
    assert redaktal(bemenet) == bemenet
    assert not tartalmaz_szemelyes_adatot(bemenet)


def test_foglalasi_kod_abece_egyezik_a_maggal() -> None:
    """A `privacy/redakcio` a foglalási kód ábécéjét MÁSOLATBAN tartja
    (a `privacy/` nem függhet a `core/`-tól, CLAUDE.md "Modulhatárok") —
    ez a teszt akadályozza meg a szétdriftelést.

    Ha a mag ábécéje vagy a kódhossz megváltozik, EZ bukik, és nem a
    redaktálás romlik el csendben (egy valódi foglalási kódot
    `<AZONOSITO>`-ra cserélve, vagy ami rosszabb: egy személyi
    igazolványszámot kódnak nézve és nyersen lemezre írva)."""
    from core.repo import foglalas_repo
    from privacy import redakcio

    assert redakcio._FOGLALASI_KOD_ABC == foglalas_repo._CODE_ABC
    assert redakcio._FOGLALASI_KOD_HOSSZ == foglalas_repo._CODE_LENGTH


def test_valodi_foglalasi_kod_nem_redaktalodik() -> None:
    """Amit a mag ténylegesen előállít, azt a redaktáló nem takarhatja
    el — különben a napló használhatatlanná válna hibakereséshez."""
    from core.repo.foglalas_repo import _new_booking_code

    for _ in range(50):
        kod = _new_booking_code()
        assert redaktal(f"a kód {kod}") == f"a kód {kod}"


def test_redaktal_idempotens() -> None:
    """Egy már redaktált szöveg újra redaktálva ugyanaz — a címkék maguk
    nem illeszkednek egyik mintára sem."""
    egyszer = redaktal("A számom 06301234567 és az emailem a@b.hu")
    assert redaktal(egyszer) == egyszer


def test_redaktal_none_marad_none() -> None:
    """A hiány nem üres string — a napló `normalizalt` mezője lehet
    `None`, és annak `None`-ként kell maradnia."""
    assert redaktal(None) is None


def test_redaktal_ertekek_rekurziv() -> None:
    adat = {
        "bolt_id": "torpilla",
        "foglalasi_kod": "06301234567",
        "beagyazott": {"jegyzet": "hívj a 0036301234567 számon"},
        "lista": ["valaki@pelda.hu", "torpilla"],
    }
    eredmeny = redaktal_ertekek(adat)
    assert eredmeny["bolt_id"] == "torpilla"
    assert eredmeny["foglalasi_kod"] == "<TELEFON>"
    assert eredmeny["beagyazott"]["jegyzet"] == "hívj a <TELEFON> számon"
    assert eredmeny["lista"] == ["<EMAIL>", "torpilla"]
    # A KULCSOKAT nem bántja — azok zárt halmazból jövő mezőnevek.
    assert set(adat) == set(eredmeny)


def test_redaktal_ertekek_nem_string_tipust_meghagy() -> None:
    assert redaktal_ertekek({"preferalt_ora": 10, "kesz": True, "nincs": None}) == {
        "preferalt_ora": 10,
        "kesz": True,
        "nincs": None,
    }


def test_proba_naplo_redaktalva_ir(tmp_path, monkeypatch) -> None:
    """A napló-író TÉNYLEGESEN redaktál — ez az invariáns bizonyítéka.

    A `ui.vasarlo` importja Tkintert húz be, de nem példányosít ablakot:
    a `_proba_naplo_ir` modulszintű függvény, fej nélkül is hívható."""
    ui_vasarlo = pytest.importorskip("ui.vasarlo")
    naplo = tmp_path / "probak.jsonl"
    monkeypatch.setattr(ui_vasarlo, "PROBA_NAPLO_UTVONAL", naplo)

    ui_vasarlo._proba_naplo_ir(
        "Jó napot, a számom 06301234567, időpontot kérnék.",
        {
            "eszkoz": "visszakerdez",
            "parameterek": {"hianyzo_mezo": "bolt_id", "foglalasi_kod": "06301234567"},
            "bizonyossag": {"eszkoz": 1.0},
        },
        "szabaly",
        normalizalt="Jó napot, a számom 06301234567, időpontot kérnék.",
        valasz_tipus="visszakerdezes",
    )

    nyers = naplo.read_text(encoding="utf-8")
    assert "06301234567" not in nyers
    sor = json.loads(nyers.strip())
    assert sor["bemenet"] == "Jó napot, a számom <TELEFON>, időpontot kérnék."
    assert sor["normalizalt"] == "Jó napot, a számom <TELEFON>, időpontot kérnék."
    assert sor["parameterek"]["foglalasi_kod"] == "<TELEFON>"
    # Ami NEM személyes adat, az megmarad — a napló különben
    # használhatatlan lenne hibakeresésre.
    assert sor["parameterek"]["hianyzo_mezo"] == "bolt_id"
    assert sor["reteg"] == "szabaly"

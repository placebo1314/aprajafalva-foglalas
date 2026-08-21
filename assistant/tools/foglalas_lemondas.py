"""`foglalas_lemondas` — lemondás foglalási kóddal (eszkoz-szerzodes
skill táblázata: "foglalási kód" az azonosítás, nem a vásárlóazonosító —
a kód önmagában elég, csak a foglaló kapja meg, blueprint 8. szakasz)."""

from __future__ import annotations

from assistant.tools import hiba, semaellenorzo, semak
from core.repo import foglalas_repo


def hivas(conn, parameterek: dict) -> dict:
    sema = semak.SEMAK["foglalas_lemondas"][semak.legutobbi_verzio("foglalas_lemondas")]
    hibak = semaellenorzo.ellenoriz(sema, parameterek)
    if hibak:
        return hiba.hiba_eredmeny(hiba.Ok.ERVENYTELEN_PARAMETER, "ervenytelen_kereses")

    eredmeny = foglalas_repo.booking_lemond(conn, parameterek["foglalasi_kod"])

    if eredmeny is foglalas_repo.Result.NO_ILYEN:
        return hiba.hiba_eredmeny(hiba.Ok.ERVENYTELEN_KOD, "ervenytelen_foglalasi_kod")
    if eredmeny is foglalas_repo.Result.ALREADY_CANCELLED:
        return hiba.hiba_eredmeny(hiba.Ok.MAR_LEMONDVA, "mar_lemondott_foglalas")

    return hiba.sikeres_eredmeny()

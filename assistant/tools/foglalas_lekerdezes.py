"""`foglalas_lekerdezes` — "mik a foglalásaim" (eszkoz-szerzodes skill
táblázata: "igen, rate limit"). A rate limitet ez az eszköz NEM végzi —
az az orchestrator/session réteg dolga (blueprint 8. szakasz,
"Enumeráció-védelem"), ez az eszköz csak listáz."""

from __future__ import annotations

from assistant.tools import hiba, semaellenorzo, semak
from core.repo import foglalas_repo


def hivas(conn, parameterek: dict) -> dict:
    sema = semak.SEMAK["foglalas_lekerdezes"][semak.legutobbi_verzio("foglalas_lekerdezes")]
    hibak = semaellenorzo.ellenoriz(sema, parameterek)
    if hibak:
        return hiba.hiba_eredmeny(hiba.Ok.ERVENYTELEN_PARAMETER, "ervenytelen_kereses")

    foglalasok = foglalas_repo.bookings_list_by_customer(
        conn, customer_key=parameterek["vasarlo_kulcs_hash"]
    )
    return hiba.sikeres_eredmeny(foglalasok=foglalasok)

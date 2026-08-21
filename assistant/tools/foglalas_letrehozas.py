"""`foglalas_letrehozas` — hold véglegesítése (eszkoz-szerzodes skill
táblázata: "hold véglegesítése", azonosítás kell).

A hívónak (orchestrator) NEM kell előzetesen ellenőriznie, hogy a
`slot_id`-n van-e hold TŐLE — a `booking_create` bármely szabad slotra
sikerrel jár, a hold csak advisory jelzés más session-eknek (foglalasi-mag
skill, "Hold"), nem tulajdonjog-ellenőrzés."""

from __future__ import annotations

from assistant.tools import hiba, semaellenorzo, semak
from core.repo import foglalas_repo


def hivas(conn, parameterek: dict) -> dict:
    sema = semak.SEMAK["foglalas_letrehozas"][semak.legutobbi_verzio("foglalas_letrehozas")]
    hibak = semaellenorzo.ellenoriz(sema, parameterek)
    if hibak:
        return hiba.hiba_eredmeny(hiba.Ok.ERVENYTELEN_PARAMETER, "ervenytelen_kereses")

    eredmeny = foglalas_repo.booking_create(
        conn,
        parameterek["slot_id"],
        parameterek["vasarlo_kulcs_hash"],
        parameterek["idempotencia_kulcs"],
        parameterek["session_id"],
    )

    if eredmeny is foglalas_repo.Result.NO_ILYEN:
        return hiba.hiba_eredmeny(hiba.Ok.ERVENYTELEN_PARAMETER, "nincs_ilyen_slot")
    if eredmeny is foglalas_repo.Result.PREEMPTED:
        return hiba.hiba_eredmeny(hiba.Ok.MEGELOZTEK, "slot_elfogyott")

    booking = foglalas_repo.booking_query_idempotency_by(conn, parameterek["idempotencia_kulcs"])
    return hiba.sikeres_eredmeny(foglalasi_kod=booking["foglalasi_kod"])

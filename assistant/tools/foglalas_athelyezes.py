"""`foglalas_athelyezes` — egy meglévő foglalás áthelyezése másik slotra
(eszkoz-szerzodes skill táblázata: "foglalási kód" kell azonosításnak,
nem a `vasarlo_kulcs_hash` — a foglalási kód önmagában elég, mert azt
csak a foglaló kapja meg, blueprint 8. szakasz).

Az `uj_slot_id`-t az orchestrator adja meg, miután a `szabad_idopontok`
eszközzel megkereste és holdolta az új jelöltet — ez az eszköz maga nem
keres, csak véglegesíti az áthelyezést (`core/repo/foglalas_repo.py::
booking_move`, atomi: vagy mindkettő sikerül, vagy egyik sem)."""

from __future__ import annotations

from assistant.tools import hiba, semaellenorzo, semak
from core.repo import foglalas_repo


def hivas(conn, parameterek: dict) -> dict:
    sema = semak.SEMAK["foglalas_athelyezes"][semak.legutobbi_verzio("foglalas_athelyezes")]
    hibak = semaellenorzo.ellenoriz(sema, parameterek)
    if hibak:
        return hiba.hiba_eredmeny(hiba.Ok.ERVENYTELEN_PARAMETER, "ervenytelen_kereses")

    eredmeny = foglalas_repo.booking_move(
        conn,
        parameterek["foglalasi_kod"],
        parameterek["uj_slot_id"],
        parameterek["idempotencia_kulcs"],
    )

    if eredmeny is foglalas_repo.Result.NO_ILYEN:
        return hiba.hiba_eredmeny(hiba.Ok.ERVENYTELEN_KOD, "ervenytelen_foglalasi_kod")
    if eredmeny is foglalas_repo.Result.ALREADY_CANCELLED:
        return hiba.hiba_eredmeny(hiba.Ok.MAR_LEMONDVA, "mar_lemondott_foglalas")
    if eredmeny is foglalas_repo.Result.PREEMPTED:
        return hiba.hiba_eredmeny(hiba.Ok.MEGELOZTEK, "uj_slot_elfogyott")

    booking = foglalas_repo.booking_query_idempotency_by(conn, parameterek["idempotencia_kulcs"])
    return hiba.sikeres_eredmeny(foglalasi_kod=booking["foglalasi_kod"])

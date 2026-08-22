"""Normalizáló szótár — tájszólási alakok, rövidítések köznyelvi formára,
az értelmező (és a `hun_date_parser`) elé (blueprint 7. szakasz, "Négy
technika", 1. pont: "adminból szerkeszthető táblázat, nem modellmunka").

A bejegyzések a golden set (`tests/golden/nyelvi_alap.yaml`) tájszólás-
és szleng-eseteiből jönnek. **Csapdaszavak külön jelezve**: a "hónap" itt
NEM a naptári hónap, hanem tájszólási "holnap" — ha ezt köznyelvi
jelentéssel (calendar hónap) fordítanánk, az rosszabb lenne, mint egy
visszakérdezés."""

from __future__ import annotations

import re

# Sorrend számít: hosszabb/pontosabb minták előrébb, hogy egy rövidebb
# minta ne foglalja el helytelenül egy hosszabb helyét (pl. "csüt" a
# "csütörtökön"-ben már ne cserélődjön újra).
_SZOTAR: list[tuple[str, str]] = [
    (r"\bhónap\b", "holnap"),  # csapdaszó — l. modul docstring
    (r"\bpíntök\w*", "péntek"),
    (r"\bcsüt\b", "csütörtök"),
    (r"\bmöggy\w*", "megy"),
    (r"\bvóna\b", "volna"),
    (r"\bkéretnék\b", "kérnék"),
    (r"\bhun\b", "hol"),
    (r"\bahun\b", "ahol"),
    (r"\bárullyák\b", "árulják"),
    # Szinonima, nem tájszólás: a `hun_date_parser` a "jövő" jelzőt
    # ismeri, a vele azonos jelentésű "következő"-t NEM — emiatt a
    # "következő héten pénteken" a FOLYÓ hét péntekjére oldódott fel.
    # A csere itt (a dátumparser ELŐTT) általános: minden "következő
    # <időegység>" szerkezetre hat, nem egy konkrét mondatra.
    (r"\bk[öo]vetkez[őo]\b", "jövő"),
]

_MINTAK = [(re.compile(minta, re.IGNORECASE), csere) for minta, csere in _SZOTAR]


def normalizal(szoveg: str) -> str:
    """A megadott mintákat lecseréli — a szó melletti írásjeleket,
    nagybetűzést egyébként érintetlenül hagyja, csak a szótári mintákat
    érinti."""
    for minta, csere in _MINTAK:
        szoveg = minta.sub(csere, szoveg)
    return szoveg

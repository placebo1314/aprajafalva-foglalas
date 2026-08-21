"""A hat eszköz, amin keresztül az asszisztens a maghoz beszél
(eszkoz-szerzodes skill). Minden eszköz `hivas(conn, parameterek, *,
session_id) -> dict` alakú, LLM nélkül hívható és tesztelt.

Ha egy hetedik eszköz kerülne be, az ADR-t érdemel — a felület szűkössége
védelem, nem korlát."""

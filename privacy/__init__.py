"""Adatvédelmi réteg — HMAC-hashelés, redaktálás (CLAUDE.md 2. invariáns).

Ma csak egy ideiglenes hash-helyettesítő van itt (`hash_ideiglenes.py`)
— a végleges HMAC+pepper implementáció (`adatvedelem` skill) M5 előtt
nem készül el, addig ez tartja a modulhatárt: a nyers azonosító sehol
máshol (pl. `ui/vasarlo.py`) nem jelenhet meg kódban, csak itt."""

"""UUID-azonosító generálás.

Minden elsődleges kulcs UUID, TEXT oszlopban (CLAUDE.md, "Minden elsődleges
kulcs UUID"). Ez az egyetlen hely, ahol ezt generáljuk — nem duplikáljuk
modulonként.
"""

from __future__ import annotations

import uuid


def uj_uuid() -> str:
    """32 karakteres hex UUID, a `length(id) = 32` CHECK-eknek megfelelően."""
    return uuid.uuid4().hex

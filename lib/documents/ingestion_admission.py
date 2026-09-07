"""Serialize participating original writers before duplicate lookup and document locks.

This is distinct from the storage cleanup lock, which follows document locks.
No caller may acquire this admission namespace while already holding a document.
"""

from hashlib import sha256
from typing import Any
from uuid import UUID


def lock_original_admission(cur: Any, household_id: UUID, content_sha256: str) -> None:
    key = sha256(
        f"structura-original-admission-v1:{household_id}:{content_sha256}".encode()
    ).digest()
    cur.execute("SELECT pg_advisory_xact_lock(%s)", (int.from_bytes(key[:8], "big", signed=True),))

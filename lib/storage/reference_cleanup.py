from __future__ import annotations

from contextlib import suppress
from typing import Any

from lib.db.connection import db_connection
from lib.storage.service import StoredObject, remove_empty_hash_dir


def lock_content_hash(cur: Any, sha256: str) -> None:
    lock_key = int.from_bytes(bytes.fromhex(sha256[:16]), byteorder="big", signed=True)
    cur.execute("SELECT pg_advisory_xact_lock(%s)", (lock_key,))


def cleanup_unreferenced_stored_object(stored: StoredObject | None) -> None:
    if not stored or not stored.created:
        return
    with suppress(Exception):
        with db_connection() as conn:
            with conn.cursor() as cur:
                lock_content_hash(cur, stored.sha256)
                if _is_object_referenced(cur, stored):
                    conn.commit()
                    return
                stored.path.unlink(missing_ok=True)
                remove_empty_hash_dir(stored.path)
            conn.commit()


def _is_object_referenced(cur: Any, stored: StoredObject) -> bool:
    cur.execute(
        """
        SELECT EXISTS (
          SELECT 1
          FROM document_assets
          WHERE uri = %s
             OR sha256 = %s
        ) AS referenced
        """,
        (stored.uri, stored.sha256),
    )
    row = cur.fetchone()
    return bool(row and row["referenced"])

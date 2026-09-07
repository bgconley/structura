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
    if row and row["referenced"]:
        return True
    # A rolling migration can still call cleanup before 098 exists. No candidate
    # references can exist then; avoid resolving its table in that SQL statement.
    cur.execute("SELECT to_regclass('structura.document_generation_render_assets') AS relation")
    if not cur.fetchone()["relation"]:
        return False
    cur.execute(
        """SELECT EXISTS (
          SELECT 1 FROM document_generation_render_assets
          WHERE asset_json->>'uri' = %s OR asset_json->'source'->>'image_sha256' = %s
        ) AS referenced""",
        (stored.uri, stored.sha256),
    )
    return bool(cur.fetchone()["referenced"])

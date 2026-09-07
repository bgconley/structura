from __future__ import annotations

from collections.abc import Callable
from contextlib import suppress
from pathlib import Path
from typing import Any, Literal

from lib.db.connection import db_connection
from lib.storage.directory_durability import sync_directory
from lib.storage.service import StoredObject, remove_empty_hash_dir
from lib.storage.verified_publication import PublicationConflict


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
    if cur.fetchone()["referenced"]:
        return True
    cur.execute("SELECT to_regclass('structura.document_parse_page_render_assets') AS relation")
    if not cur.fetchone()["relation"]:
        return False
    cur.execute(
        """SELECT EXISTS (
          SELECT 1 FROM document_parse_page_render_assets
          WHERE asset_json->>'uri' = %s OR asset_json->'render'->>'image_sha256' = %s
        ) AS referenced""",
        (stored.uri, stored.sha256),
    )
    return bool(cur.fetchone()["referenced"])


def cleanup_verified_unreferenced_object(
    stored: StoredObject,
    identity_matches: Callable[[], bool],
) -> Literal["removed", "already_missing", "referenced"]:
    """Strict cleanup; caller retains reservation if any confirmation fails.

    The callback only performs bounded non-following filesystem metadata reads.
    It runs after SQL waits immediately before unlink; no hashing or network IO.
    Unlike best-effort legacy cleanup, failures are deliberately not suppressed.
    """
    with db_connection() as conn, conn.cursor() as cur:
        lock_content_hash(cur, stored.sha256)
        if _is_object_referenced(cur, stored):
            return "referenced"
        try:
            stored.path.lstat()
        except FileNotFoundError:
            _sync_cleanup_parents(stored.path)
            return "already_missing"
        if not identity_matches():
            raise PublicationConflict("Original cleanup identity changed.")
        stored.path.unlink()
        # Retain empty directories: removing them without persisting their own
        # parent entries can resurrect a link after upload capacity is released.
        _sync_cleanup_parents(stored.path)
        conn.commit()
        return "removed"


def _sync_cleanup_parents(path: Path) -> None:
    """Confirm removal, including retries after an earlier unlink/fsync failure.

    A missing leaf or parent still needs its surviving ancestor entry synced.
    Do not create directories or follow symlinks. Sync visible ancestors through
    the filesystem anchor so concurrent/retried directory removal is also bound.
    """
    if not path.is_absolute() or len(path.parents) > 256:
        raise PublicationConflict("Original cleanup path is invalid.")
    for parent in path.parents:
        try:
            sync_directory(parent)
        except FileNotFoundError:
            continue

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from urllib.parse import quote, urlparse, urlunparse
from uuid import uuid4

import psycopg
from psycopg import sql

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

SAFE_DATABASE_NAME_RE = re.compile(r"^structura_restore_(source|restored)_[a-f0-9]{16}$")


def main() -> int:
    base_url = os.environ.get("STRUCTURA_INTEGRATION_BASE_DATABASE_URL")
    if not base_url:
        raise SystemExit("STRUCTURA_INTEGRATION_BASE_DATABASE_URL is required.")
    admin_url = _database_url_with_name(base_url, "postgres")
    suffix = uuid4().hex[:16]
    source_name = f"structura_restore_source_{suffix}"
    restored_name = f"structura_restore_restored_{suffix}"
    source_url = _database_url_with_name(base_url, source_name)
    restored_url = _database_url_with_name(base_url, restored_name)

    try:
        _create_database(admin_url, source_name)
        _migrate_database(source_url)
        sentinel_id = _insert_sentinel(source_url)
        _clone_database(admin_url, source_name, restored_name)
        _verify_restore(restored_url, sentinel_id)
        print(
            json.dumps(
                {
                    "status": "ok",
                    "sourceDatabase": source_name,
                    "restoredDatabase": restored_name,
                    "sentinelId": sentinel_id,
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 0
    finally:
        _drop_database(admin_url, restored_name)
        _drop_database(admin_url, source_name)


def _database_url_with_name(url: str, database_name: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in {"postgresql", "postgres"} or not parsed.netloc:
        raise SystemExit("Database URL must be a postgresql:// URL.")
    return urlunparse(parsed._replace(path=f"/{quote(database_name)}"))


def _create_database(admin_url: str, database_name: str) -> None:
    _validate_database_name(database_name)
    with psycopg.connect(admin_url, autocommit=True) as conn:
        conn.execute(  # nosemgrep
            sql.SQL("CREATE DATABASE {}").format(sql.Identifier(database_name))
        )


def _migrate_database(database_url: str) -> None:
    from lib.db.migrations import apply_baseline_migrations

    applied = apply_baseline_migrations(database_url, ROOT / "database")
    if not applied:
        raise SystemExit("Restore rehearsal source database did not apply migrations.")


def _insert_sentinel(database_url: str) -> int:
    with psycopg.connect(database_url) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO structura.audit_events
                  (entity_type, event_name, actor_label, payload_json)
                VALUES
                  ('restore_rehearsal', 'restore_rehearsal_sentinel', 'release-gate',
                   '{"purpose":"backup_restore_rehearsal"}'::jsonb)
                RETURNING id
                """
            )
            row = cur.fetchone()
            if row is None:
                raise SystemExit("Restore rehearsal sentinel insert returned no id.")
            sentinel_id = int(row[0])
        conn.commit()
    return sentinel_id


def _clone_database(admin_url: str, source_name: str, restored_name: str) -> None:
    _validate_database_name(source_name)
    _validate_database_name(restored_name)
    with psycopg.connect(admin_url, autocommit=True) as conn:
        conn.execute(
            sql.SQL("SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = %s"),
            (source_name,),
        )
        conn.execute(  # nosemgrep
            sql.SQL("CREATE DATABASE {} WITH TEMPLATE {}").format(
                sql.Identifier(restored_name),
                sql.Identifier(source_name),
            )
        )


def _verify_restore(database_url: str, sentinel_id: int) -> None:
    with psycopg.connect(database_url) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM structura.schema_migrations")
            migration_row = cur.fetchone()
            if migration_row is None:
                raise SystemExit("Restored database returned no migration count.")
            migration_count = int(migration_row[0])
            cur.execute(
                """
                SELECT payload_json ->> 'purpose'
                FROM structura.audit_events
                WHERE id = %s
                """,
                (sentinel_id,),
            )
            restored_purpose = cur.fetchone()
    if migration_count <= 0:
        raise SystemExit("Restored database has no migration records.")
    if not restored_purpose or restored_purpose[0] != "backup_restore_rehearsal":
        raise SystemExit("Restored database is missing rehearsal sentinel data.")


def _drop_database(admin_url: str, database_name: str) -> None:
    _validate_database_name(database_name)
    with psycopg.connect(admin_url, autocommit=True) as conn:
        conn.execute(
            "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = %s",
            (database_name,),
        )
        conn.execute(  # nosemgrep
            sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(database_name))
        )


def _validate_database_name(database_name: str) -> None:
    if not SAFE_DATABASE_NAME_RE.fullmatch(database_name):
        raise SystemExit("Restore rehearsal database name is not safe.")


if __name__ == "__main__":
    raise SystemExit(main())

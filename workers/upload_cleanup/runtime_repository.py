"""Bounded startup target checks and content-free persisted maintenance health."""

import os
from collections.abc import Mapping

import psycopg
from psycopg.conninfo import conninfo_to_dict
from psycopg.types.json import Jsonb

from lib.uploads.transactions import upload_connection


class CleanupRuntimeUnavailable(Exception):
    """Static machine category only; no raw connection or storage diagnostics."""


def validate_runtime_database(expected_name: str) -> None:
    url = os.environ.get("STRUCTURA_DATABASE_URL")
    if not url or not os.environ.get("STRUCTURA_RUNTIME_ROOT"):
        raise CleanupRuntimeUnavailable("cleanup_configuration_unavailable")
    try:
        if conninfo_to_dict(url).get("dbname") != expected_name:
            raise CleanupRuntimeUnavailable("cleanup_database_mismatch")
        with upload_connection() as conn, conn.cursor() as cur:
            if conn.info.dbname != expected_name:
                raise CleanupRuntimeUnavailable("cleanup_database_mismatch")
            cur.execute("SELECT to_regclass('structura.schema_migrations') IS NOT NULL AS present")
            present = cur.fetchone()
            if present is None or not present["present"]:
                raise CleanupRuntimeUnavailable("cleanup_migration_unavailable")
            cur.execute(
                "SELECT EXISTS(SELECT 1 FROM schema_migrations WHERE script_name=%s) AS applied",
                ("104_completion_upload_attempts.sql",),
            )
            applied = cur.fetchone()
            if applied is None or not applied["applied"]:
                raise CleanupRuntimeUnavailable("cleanup_migration_unavailable")
    except psycopg.Error:
        raise CleanupRuntimeUnavailable("cleanup_database_unavailable") from None


def record_cleanup_health(status: str, metrics: Mapping[str, object]) -> None:
    with upload_connection() as conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO service_health_snapshots(service_name,status,metrics_json) "
            "VALUES(%s,%s,%s)",
            ("worker-upload-cleanup", status, Jsonb(dict(metrics))),
        )
        conn.commit()

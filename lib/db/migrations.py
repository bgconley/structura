from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

BASELINE_SQL_FILES = (
    "001_extensions.sql",
    "010_types_and_enums.sql",
    "020_core_tables.sql",
    "025_baseline_identity_acl_candidate_rules.sql",
    "030_constraints_and_triggers.sql",
    "040_indexes_bm25_pgvector.sql",
    "050_views_and_functions.sql",
    "060_seed_taxonomies.sql",
    "065_pipeline_jobs_household_scope.sql",
    "066_folder_household_uniqueness.sql",
    "067_document_read_acl_function.sql",
    "068_phase4_extraction_review.sql",
    "069_phase5_search.sql",
    "071_phase5_search_guardrails.sql",
    "072_phase6_automation.sql",
)


@dataclass(frozen=True)
class MigrationPlan:
    database_dir: Path
    scripts: tuple[Path, ...]

    def sql_batches(self) -> list[tuple[str, str]]:
        return [(script.name, script.read_text(encoding="utf-8")) for script in self.scripts]


def baseline_migration_plan(database_dir: str | Path) -> MigrationPlan:
    root = Path(database_dir)
    scripts = tuple(root / name for name in BASELINE_SQL_FILES)
    missing = [script for script in scripts if not script.exists()]
    if missing:
        missing_text = ", ".join(str(script) for script in missing)
        raise FileNotFoundError(f"Missing baseline SQL files: {missing_text}")
    return MigrationPlan(database_dir=root, scripts=scripts)


def _checksum(sql: str) -> str:
    return hashlib.sha256(sql.encode("utf-8")).hexdigest()


def _ensure_migration_table(cur: Any) -> None:
    cur.execute("CREATE SCHEMA IF NOT EXISTS structura")
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS structura.schema_migrations (
          script_name text PRIMARY KEY,
          checksum_sha256 text NOT NULL,
          applied_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )


def _applied_migrations(cur: Any) -> dict[str, str]:
    cur.execute("SELECT script_name, checksum_sha256 FROM structura.schema_migrations")
    return {row[0]: row[1] for row in cur.fetchall()}


def _record_migration(cur: Any, name: str, checksum_sha256: str) -> None:
    cur.execute(
        """
        INSERT INTO structura.schema_migrations (script_name, checksum_sha256)
        VALUES (%s, %s)
        ON CONFLICT (script_name) DO NOTHING
        """,
        (name, checksum_sha256),
    )


def _legacy_script_already_present(cur: Any, name: str) -> bool:
    markers = {
        "010_types_and_enums.sql": (
            "SELECT to_regtype('structura.document_family_enum') IS NOT NULL"
        ),
        "020_core_tables.sql": "SELECT to_regclass('structura.documents') IS NOT NULL",
        "025_baseline_identity_acl_candidate_rules.sql": (
            "SELECT to_regclass('structura.service_health_snapshots') IS NOT NULL"
        ),
        "030_constraints_and_triggers.sql": """
            SELECT EXISTS (
              SELECT 1
              FROM pg_trigger t
              JOIN pg_class c ON c.oid = t.tgrelid
              JOIN pg_namespace n ON n.oid = c.relnamespace
              WHERE n.nspname = 'structura'
                AND c.relname = 'pipeline_jobs'
                AND t.tgname = 'trg_pipeline_jobs_updated_at'
                AND NOT t.tgisinternal
            )
        """,
        "040_indexes_bm25_pgvector.sql": (
            "SELECT to_regclass('structura.sessions_user_expires_idx') IS NOT NULL"
        ),
        "050_views_and_functions.sql": (
            "SELECT to_regclass('structura.document_summary_v') IS NOT NULL"
        ),
    }
    marker = markers.get(name)
    if not marker:
        return False
    cur.execute(marker)
    return bool(cur.fetchone()[0])


def apply_baseline_migrations(database_url: str, database_dir: str | Path) -> list[str]:
    import psycopg

    plan = baseline_migration_plan(database_dir)
    applied: list[str] = []
    with psycopg.connect(database_url) as conn:
        with conn.cursor() as cur:
            _ensure_migration_table(cur)
            known = _applied_migrations(cur)
            for name, sql in plan.sql_batches():
                checksum_sha256 = _checksum(sql)
                if name in known:
                    if known[name] != checksum_sha256:
                        raise RuntimeError(
                            f"Migration {name} checksum changed after it was applied."
                        )
                    continue
                if _legacy_script_already_present(cur, name):
                    _record_migration(cur, name, checksum_sha256)
                    continue
                # Baseline SQL is loaded from the repository migration directory, not user input.
                cur.execute(sql)  # pyright: ignore[reportCallIssue,reportArgumentType]
                _record_migration(cur, name, checksum_sha256)
                applied.append(name)
        conn.commit()
    return applied

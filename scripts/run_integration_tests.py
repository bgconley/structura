from __future__ import annotations

import os
import re
import shutil
import sys
import tempfile
from pathlib import Path
from urllib.parse import quote, urlparse, urlunparse
from uuid import uuid4

import psycopg
from psycopg import sql

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
DEFAULT_DATABASE_URL = "postgresql://structura:structura@localhost:5432/structura"
SAFE_DATABASE_NAME_RE = re.compile(r"^structura_it_[a-f0-9]{16}$")


def main() -> int:
    base_url = (
        os.environ.get("STRUCTURA_INTEGRATION_BASE_DATABASE_URL")
        or os.environ.get("STRUCTURA_TEST_DATABASE_URL")
        or os.environ.get("STRUCTURA_DATABASE_URL")
        or DEFAULT_DATABASE_URL
    )
    admin_url = os.environ.get("STRUCTURA_TEST_ADMIN_DATABASE_URL") or _database_url_with_name(
        base_url,
        "postgres",
    )
    test_database = f"structura_it_{uuid4().hex[:16]}"
    test_url = _database_url_with_name(base_url, test_database)
    runtime_root = Path(
        os.environ.get("STRUCTURA_INTEGRATION_RUNTIME_ROOT")
        or tempfile.mkdtemp(prefix="structura-it-runtime-")
    )
    generated_runtime_root = "STRUCTURA_INTEGRATION_RUNTIME_ROOT" not in os.environ
    env = {
        **os.environ,
        "STRUCTURA_DATABASE_URL": test_url,
        "STRUCTURA_TEST_DATABASE_URL": test_url,
        "STRUCTURA_RUNTIME_ROOT": str(runtime_root),
        "STRUCTURA_ENV": "test",
    }
    created_database = False

    try:
        _create_database(admin_url, test_database)
        created_database = True
        os.environ.update(env)
        _run_migrations()
        pytest_args = sys.argv[1:] or ["-q", "tests/integration"]
        return _run_pytest(pytest_args)
    finally:
        if created_database:
            _drop_database(admin_url, test_database)
        if generated_runtime_root:
            shutil.rmtree(runtime_root, ignore_errors=True)


def _database_url_with_name(url: str, database_name: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in {"postgresql", "postgres"} or not parsed.netloc:
        raise SystemExit("Database URL must be a postgresql:// URL.")
    return urlunparse(parsed._replace(path=f"/{quote(database_name)}"))


def _create_database(admin_url: str, database_name: str) -> None:
    _validate_database_name(database_name)
    with psycopg.connect(admin_url, autocommit=True) as conn:
        # Name is generated, regex-validated, and quoted as an identifier.
        # nosemgrep
        conn.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(database_name)))


def _run_migrations() -> None:
    from lib.config import get_settings
    from lib.db.migrations import apply_baseline_migrations, baseline_migration_plan

    get_settings.cache_clear()
    settings = get_settings()
    plan = baseline_migration_plan(settings.database_dir)
    print("Applying Structura baseline migrations:")
    for script in plan.scripts:
        print(f"  - {script.name}")
    applied = apply_baseline_migrations(settings.database_url, settings.database_dir)
    print(f"Applied {len(applied)} migration scripts.")


def _run_pytest(pytest_args: list[str]) -> int:
    import pytest

    return int(pytest.main(pytest_args))


def _drop_database(admin_url: str, database_name: str) -> None:
    _validate_database_name(database_name)
    with psycopg.connect(admin_url, autocommit=True) as conn:
        conn.execute(
            "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = %s",
            (database_name,),
        )
        conn.execute(
            # Name is generated, regex-validated, and quoted as an identifier.
            # nosemgrep
            sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(
                sql.Identifier(database_name),
            )
        )


def _validate_database_name(database_name: str) -> None:
    if not SAFE_DATABASE_NAME_RE.fullmatch(database_name):
        raise SystemExit("Integration test database name is not safe.")


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from urllib.parse import quote, urlparse, urlunparse
from uuid import uuid4

import psycopg
from psycopg import sql

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATABASE_URL = "postgresql://structura:structura@localhost:5432/structura"


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
        subprocess.run(
            [sys.executable, "scripts/migrate.py"],
            cwd=ROOT,
            env=env,
            check=True,
        )
        pytest_args = sys.argv[1:] or ["-q", "tests/integration"]
        completed = subprocess.run(
            [sys.executable, "-m", "pytest", *pytest_args],
            cwd=ROOT,
            env=env,
            check=False,
        )
        return int(completed.returncode)
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
    with psycopg.connect(admin_url, autocommit=True) as conn:
        conn.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(database_name)))


def _drop_database(admin_url: str, database_name: str) -> None:
    with psycopg.connect(admin_url, autocommit=True) as conn:
        conn.execute(
            "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = %s",
            (database_name,),
        )
        conn.execute(
            sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(
                sql.Identifier(database_name),
            )
        )


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

from contextlib import contextmanager
from types import SimpleNamespace

import pytest
from psycopg.conninfo import conninfo_to_dict

from scripts import run_integration_tests as runner

DATABASE = "structura_it_0123456789abcdef"


@pytest.mark.parametrize(
    "source",
    [
        "postgresql://localhost/structura",
        "postgresql://localhost/structura?dbname=structura&sslmode=disable",
        "postgresql://localhost/ignored?dbname=first&dbname=structura",
        "postgresql://localhost/ignored?%64bname=structura",
    ],
)
def test_generated_database_overrides_every_libpq_query_name(source):
    selected = conninfo_to_dict(runner._database_url_with_name(source, DATABASE))
    assert selected["dbname"] == DATABASE
    if "sslmode" in source:
        assert selected["sslmode"] == "disable"
    assert (
        conninfo_to_dict(runner._database_url_with_name(source, "postgres"))["dbname"] == "postgres"
    )


@pytest.mark.parametrize("actual", ["structura", "structura_it_fedcba9876543210", DATABASE])
def test_actual_connection_must_equal_generated_database(monkeypatch, actual):
    @contextmanager
    def connect(url, *, connect_timeout):
        assert conninfo_to_dict(url)["dbname"] == DATABASE
        assert connect_timeout == 5
        yield SimpleNamespace(info=SimpleNamespace(dbname=actual))

    monkeypatch.setattr(runner.psycopg, "connect", connect)
    if actual == DATABASE:
        runner._verify_test_database(f"postgresql://localhost/{DATABASE}", DATABASE)
    else:
        with pytest.raises(SystemExit, match="differs"):
            runner._verify_test_database(f"postgresql://localhost/{DATABASE}", DATABASE)


def test_mismatched_connection_never_runs_migrations_or_tests(monkeypatch, tmp_path):
    events = []
    monkeypatch.setenv("STRUCTURA_INTEGRATION_BASE_DATABASE_URL", "postgresql://localhost/postgres")
    monkeypatch.setenv("STRUCTURA_INTEGRATION_RUNTIME_ROOT", str(tmp_path))
    monkeypatch.setattr(runner, "_create_database", lambda *_: events.append("created"))
    monkeypatch.setattr(runner, "_drop_database", lambda *_: events.append("dropped"))

    def reject(*_):
        raise SystemExit("Controlled connected database mismatch")

    def forbidden(*_):
        raise AssertionError("Isolation mismatch must prevent migrations and tests")

    monkeypatch.setattr(runner, "_verify_test_database", reject)
    monkeypatch.setattr(runner, "_run_migrations", forbidden)
    monkeypatch.setattr(runner, "_run_pytest", forbidden)
    with pytest.raises(SystemExit, match="mismatch"):
        runner.main()
    assert events == ["created", "dropped"]

from __future__ import annotations

from contextlib import contextmanager
from types import SimpleNamespace

import pytest

from scripts.gpu import probe_database

DATABASE = "structura_it_0123456789abcdef"


@pytest.mark.parametrize(
    "dsn",
    [
        f"postgresql://localhost/{DATABASE}",
        f"host=localhost dbname={DATABASE}",
        f"postgresql://localhost/ignored?dbname={DATABASE}",
    ],
)
def test_guard_uses_resolved_libpq_database_name(dsn):
    assert probe_database.isolated_database_name(dsn) == DATABASE


@pytest.mark.parametrize(
    "dsn",
    [
        f"postgresql://localhost/{DATABASE}?dbname=structura",
        f"postgresql://localhost/{DATABASE}?dbname=structura_it_0123456789abcdeg",
        "postgresql://localhost/structura",
        "host=localhost",
        "invalid configuration includes private text",
    ],
)
def test_invalid_or_overridden_database_fails_before_connect(monkeypatch, dsn):
    def forbidden(*args, **kwargs):
        raise AssertionError("Rejected namespace must not open a database connection")

    monkeypatch.setattr(probe_database, "db_connection", forbidden)
    with pytest.raises(RuntimeError, match="Probe"):
        probe_database.verify_isolated_database(dsn)


@pytest.mark.parametrize("connected_name", ["structura", "structura_it_fedcba9876543210", DATABASE])
def test_actual_connection_name_must_match_resolved_declaration(monkeypatch, connected_name):
    observed = []

    @contextmanager
    def connection(database_url, *, connect_timeout):
        observed.append((database_url, connect_timeout))
        yield SimpleNamespace(info=SimpleNamespace(dbname=connected_name))

    monkeypatch.setattr(probe_database, "db_connection", connection)
    url = f"postgresql://localhost/{DATABASE}"
    if connected_name == DATABASE:
        assert probe_database.verify_isolated_database(url) == DATABASE
    else:
        with pytest.raises(RuntimeError, match="Connected probe database"):
            probe_database.verify_isolated_database(url)
    assert observed == [(url, 5)]


def test_register_source_cannot_bootstrap_before_actual_database_verification(
    monkeypatch, tmp_path
):
    from scripts.gpu import probe_persisted_parse

    def reject(database_url):
        raise RuntimeError("Controlled actual database mismatch")

    def forbidden(*args, **kwargs):
        raise AssertionError("No authentication or source writes may precede the guard")

    monkeypatch.setattr(probe_persisted_parse, "verify_isolated_database", reject)
    monkeypatch.setattr(probe_persisted_parse, "AuthService", forbidden)
    with pytest.raises(RuntimeError, match="actual database mismatch"):
        probe_persisted_parse.register_source(tmp_path, b"controlled original")

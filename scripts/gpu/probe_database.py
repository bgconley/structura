"""Fail-closed database namespace guard for disposable diagnostic probes only."""

from __future__ import annotations

import re
from typing import Any

import psycopg
from psycopg.conninfo import conninfo_to_dict

from lib.db.connection import db_connection


def isolated_database_name(database_url: str) -> str:
    """Use libpq parsing: URI query parameters may override the URL path."""
    try:
        name = conninfo_to_dict(database_url).get("dbname", "")
    except psycopg.Error:
        raise RuntimeError("Probe database configuration is invalid.") from None
    if not isinstance(name, str) or not re.fullmatch(r"structura_it_[a-f0-9]{16}", name):
        raise RuntimeError("Probe requires an explicitly isolated integration database.")
    return name


def assert_isolated_connection(conn: Any, expected_name: str) -> None:
    """Check the actual connection before any probe reads or mutations."""
    if (
        not re.fullmatch(r"structura_it_[a-f0-9]{16}", expected_name)
        or conn.info.dbname != expected_name
    ):
        raise RuntimeError("Connected probe database differs from its isolated declaration.")


def verify_isolated_database(database_url: str) -> str:
    """Validate both resolved configuration and an actual bounded connection."""
    expected = isolated_database_name(database_url)
    try:
        with db_connection(database_url, connect_timeout=5) as conn:
            assert_isolated_connection(conn, expected)
    except psycopg.Error:
        raise RuntimeError("Isolated probe database could not be verified.") from None
    return expected

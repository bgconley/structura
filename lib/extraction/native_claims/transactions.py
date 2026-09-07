"""Bounded database transactions shared by immutable claim interpretations."""

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from lib.db.connection import db_connection


@contextmanager
def claim_transaction() -> Iterator[Any]:
    with db_connection(connect_timeout=5) as conn, conn.cursor() as cur:
        cur.execute("SET LOCAL lock_timeout='2s'")
        cur.execute("SET LOCAL statement_timeout='5s'")
        yield cur
        conn.commit()

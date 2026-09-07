"""Short bounded upload transactions; callers perform all body/hash IO outside."""

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import psycopg

from lib.db.connection import db_connection


@contextmanager
def upload_connection() -> Iterator[psycopg.Connection[dict[str, Any]]]:
    with db_connection(connect_timeout=5) as conn:
        with conn.cursor() as cur:
            cur.execute("SET LOCAL statement_timeout='5s'")
            cur.execute("SET LOCAL lock_timeout='3s'")
        yield conn

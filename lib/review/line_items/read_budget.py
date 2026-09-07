"""Bound current all-row line reads until batched/paginated reads land under G2."""

from collections.abc import Iterator
from contextlib import contextmanager
from time import monotonic
from typing import Any

from lib.db.connection import db_connection


class LineReadCursor:
    def __init__(self, cursor: Any, deadline: float):
        self._cursor = cursor
        self._deadline = deadline

    def execute(self, query: Any, params: Any = None) -> Any:
        # Each individual server statement is also capped at five seconds. This
        # budget stops an unpaginated collection from issuing queries indefinitely.
        if monotonic() >= self._deadline:
            raise TimeoutError("Line authority read budget exceeded.")
        return self._cursor.execute(query, params)

    def fetchone(self) -> Any:
        return self._cursor.fetchone()

    def fetchall(self) -> Any:
        return self._cursor.fetchall()


@contextmanager
def bounded_line_read() -> Iterator[LineReadCursor]:
    with db_connection() as conn, conn.cursor() as cur:
        cur.execute("SET LOCAL statement_timeout='5s'")
        cur.execute("SET LOCAL lock_timeout='2s'")
        yield LineReadCursor(cur, monotonic() + 20)

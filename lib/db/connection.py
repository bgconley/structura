from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any, cast

import psycopg
from psycopg.rows import dict_row

from lib.config import get_settings


@contextmanager
def db_connection(database_url: str | None = None) -> Iterator[psycopg.Connection[dict[str, Any]]]:
    settings = get_settings()
    url = database_url or settings.database_url
    row_factory = cast(Any, dict_row)
    with psycopg.connect(url, row_factory=row_factory) as raw_conn:
        conn = cast(psycopg.Connection[dict[str, Any]], raw_conn)
        with conn.cursor() as cur:
            cur.execute("SET search_path TO structura, public")
        yield conn

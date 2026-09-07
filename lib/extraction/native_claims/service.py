"""Bounded candidate-run transactions; no model or public publication side effects."""

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from lib.auth.request_authority import RequestCredential
from lib.db.connection import db_connection
from lib.document_processing.models import ProcessingBinding
from lib.extraction.native_claims.models import (
    NativeClaimBinding,
    NativeClaimConfiguration,
    NativePageRequest,
)
from lib.extraction.native_claims.page_repository import persist_page
from lib.extraction.native_claims.projection import diagnostic_projection
from lib.extraction.native_claims.read_repository import read_sealed, seal_set
from lib.extraction.native_claims.set_repository import start_set


@contextmanager
def _transaction() -> Iterator[Any]:
    with db_connection(connect_timeout=5) as conn, conn.cursor() as cur:
        cur.execute("SET LOCAL lock_timeout='2s'")
        cur.execute("SET LOCAL statement_timeout='5s'")
        yield cur
        conn.commit()


class NativeClaimService:
    def start(
        self,
        processing: ProcessingBinding,
        *,
        configuration: NativeClaimConfiguration | None = None,
    ) -> NativeClaimBinding:
        with _transaction() as cur:
            return start_set(cur, processing, configuration or NativeClaimConfiguration())

    def checkpoint(self, binding: NativeClaimBinding, request: NativePageRequest) -> str:
        with _transaction() as cur:
            return persist_page(cur, binding, request)

    def seal(self, binding: NativeClaimBinding) -> dict[str, Any]:
        with _transaction() as cur:
            return seal_set(cur, binding)

    def rebuild(
        self, binding: NativeClaimBinding, *, credential: RequestCredential
    ) -> dict[str, Any]:
        # Retained history requires current reader authority, never a live producer.
        with _transaction() as cur:
            claims = read_sealed(cur, binding, credential)
        return diagnostic_projection(claims)

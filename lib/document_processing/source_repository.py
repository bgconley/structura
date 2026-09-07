"""Exact run-bound source metadata reads; no filesystem or model calls in transactions."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from lib.db.connection import db_connection
from lib.document_parsing.structure import Sha256, SourceMediaType
from lib.document_processing.authority_repository import fence_processing_attempt, lock_current_run
from lib.document_processing.errors import ProcessingError
from lib.document_processing.models import ParseConfiguration, ProcessingBinding


class RegisteredParseSource(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    original_asset_id: UUID
    original_sha256: Sha256
    uri: str = Field(min_length=1)
    mime_type: SourceMediaType
    byte_size: int = Field(gt=0, le=100 * 1024 * 1024)
    configuration: ParseConfiguration


def load_processing_source(binding: ProcessingBinding) -> RegisteredParseSource:
    """Read the registered original owned by this exact claimed run.

    Lock order is document → run → original asset → job ancestry/attempt.
    Returning from the context closes the transaction before source IO starts.
    The original content's hash/size are verified again by the source adapter.
    """
    with db_connection(connect_timeout=5) as conn, conn.cursor() as cur:
        cur.execute("SET LOCAL statement_timeout = '5s'")
        cur.execute("SET LOCAL lock_timeout = '2s'")
        run = lock_current_run(cur, binding)
        cur.execute(
            """SELECT id, sha256, uri, mime_type, byte_size FROM document_assets
            WHERE id = %s AND document_id = %s AND asset_role = 'original' AND sha256 = %s
            FOR KEY SHARE""",
            (run["original_asset_id"], binding.document_id, run["original_sha256"]),
        )
        asset = cur.fetchone()
        if asset is None:
            raise ProcessingError("Processing source does not match the registered original.")
        try:
            configuration = ParseConfiguration.model_validate(run["config_json"])
            result = RegisteredParseSource(
                original_asset_id=asset["id"],
                original_sha256=asset["sha256"],
                uri=asset["uri"],
                mime_type=asset["mime_type"],
                byte_size=asset["byte_size"],
                configuration=configuration,
            )
        except ValidationError:
            raise ProcessingError(
                "Registered processing source or configuration is invalid."
            ) from None
        if configuration.fingerprint != run["config_sha256"]:
            raise ProcessingError("Frozen parser configuration does not match its recorded hash.")
        fence_processing_attempt(cur, binding)
    return result

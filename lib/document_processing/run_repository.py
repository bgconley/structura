"""Transactional authorized run creation, idempotency and permanent revocation."""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

from psycopg.types.json import Jsonb

from lib.auth.models import AuthPrincipal
from lib.document_processing.errors import ProcessingError
from lib.document_processing.models import ParseConfiguration, ProcessingBinding, ProcessingRun
from lib.document_processing.request_authority_repository import admit_request
from lib.documents.access_policy import DocumentAccessContext
from lib.documents.access_repository import document_is_writable
from lib.jobs import create_job_with_cursor
from lib.jobs.ownership import current_job_attempt


def start_parse_run(
    cur: Any,
    *,
    document_id: UUID,
    principal: AuthPrincipal,
    original_asset_id: UUID,
    original_sha256: str,
    request_key: UUID,
    configuration: ParseConfiguration,
    queue_name: str,
) -> ProcessingRun:
    if current_job_attempt() is not None:
        raise ProcessingError("A worker cannot replace its inherited processing request.")
    origin = admit_request(cur, document_id, principal)
    cur.execute(
        """SELECT * FROM document_processing_runs
        WHERE document_id = %s AND request_key = %s""",
        (document_id, request_key),
    )
    existing = cur.fetchone()
    if existing:
        if (
            existing["original_asset_id"] != original_asset_id
            or existing["original_sha256"] != original_sha256
            or existing["config_sha256"] != configuration.fingerprint
            or existing["requested_by_user_id"] != origin.user_id
            or existing["origin_kind"] != origin.kind
            or existing["origin_session_id"] != origin.session_id
            or existing["origin_api_token_id"] != origin.api_token_id
        ):
            raise ProcessingError("Processing request key was reused with different intent.")
        return run_from_row(existing)
    cur.execute(
        """SELECT id FROM document_assets
        WHERE id = %s AND document_id = %s AND asset_role = 'original' AND sha256 = %s
        FOR KEY SHARE""",
        (original_asset_id, document_id, original_sha256),
    )
    if cur.fetchone() is None:
        raise ProcessingError("Processing source does not match the registered original.")
    cur.execute(
        "SELECT processing_generation, desired_processing_run_id FROM documents WHERE id = %s",
        (document_id,),
    )
    document = cur.fetchone()
    generation = int(document["processing_generation"]) + 1
    run_id, parse_id, job_id = uuid4(), uuid4(), uuid4()
    cur.execute(
        """UPDATE document_processing_runs
        SET status = 'superseded', revoked_at = clock_timestamp()
        WHERE id = %s AND revoked_at IS NULL""",
        (document["desired_processing_run_id"],),
    )
    cur.execute(
        """INSERT INTO document_processing_runs
        (id, document_id, household_id, generation, request_key, requested_by_user_id,
         original_asset_id, original_sha256, parse_generation_id, root_job_id,
         config_json, config_sha256, origin_kind, origin_session_id,
         origin_api_token_id, origin_scope_ceiling)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *""",
        (
            run_id,
            document_id,
            origin.household_id,
            generation,
            request_key,
            origin.user_id,
            original_asset_id,
            original_sha256,
            parse_id,
            job_id,
            Jsonb(configuration.model_dump(mode="json")),
            configuration.fingerprint,
            origin.kind,
            origin.session_id,
            origin.api_token_id,
            list(origin.scope_ceiling),
        ),
    )
    run = run_from_row(cur.fetchone())
    cur.execute(
        "INSERT INTO document_parse_generations (id, document_id, creator_run_id) "
        "VALUES (%s,%s,%s)",
        (parse_id, document_id, run_id),
    )
    cur.execute(
        """UPDATE documents SET processing_generation = %s, desired_processing_run_id = %s
        WHERE id = %s""",
        (generation, run_id, document_id),
    )
    _audit(cur, run, origin.user_id, "processing.requested")
    # No active worker listens to the candidate queue by default. Using the
    # existing ingest job enum avoids presenting this as legacy Docling work.
    create_job_with_cursor(
        cur,
        job_id=job_id,
        job_type="ingest",
        document_id=document_id,
        household_id=origin.household_id,
        queue_name=queue_name,
        processing_run_id=run_id,
        parse_generation_id=parse_id,
        payload={"processing_stage": "parse_candidate"},
    )
    return run


def cancel_parse_run(cur: Any, binding: ProcessingBinding, access: DocumentAccessContext) -> None:
    if current_job_attempt() is not None:
        raise ProcessingError("Processing cancellation is an authorized request operation.")
    if not document_is_writable(cur, binding.document_id, access):
        raise ProcessingError("Document is unavailable for processing.")
    cur.execute(
        """SELECT * FROM document_processing_runs
        WHERE id = %s AND document_id = %s AND parse_generation_id = %s FOR UPDATE""",
        (binding.processing_run_id, binding.document_id, binding.parse_generation_id),
    )
    row = cur.fetchone()
    if row is None:
        raise ProcessingError("Processing run is unavailable.")
    if row["revoked_at"] is not None:
        return
    cur.execute(
        """UPDATE document_processing_runs SET status = 'cancelled', revoked_at = clock_timestamp()
        WHERE id = %s""",
        (binding.processing_run_id,),
    )
    _audit(cur, run_from_row(row), access.user_id, "processing.cancelled")


def run_from_row(row: Any) -> ProcessingRun:
    return ProcessingRun(
        binding=ProcessingBinding(row["document_id"], row["id"], row["parse_generation_id"]),
        household_id=row["household_id"],
        generation=int(row["generation"]),
        root_job_id=row["root_job_id"],
        status=row["status"],
    )


def _audit(cur: Any, run: ProcessingRun, actor_id: UUID, event_name: str) -> None:
    cur.execute(
        """INSERT INTO audit_events (entity_type, entity_id, document_id, event_name,
                                      actor_label, payload_json)
        VALUES ('document_processing_run', %s, %s, %s, %s, %s)""",
        (
            run.binding.processing_run_id,
            run.binding.document_id,
            event_name,
            str(actor_id),
            Jsonb(
                {
                    "generation": run.generation,
                    "parseGenerationId": str(run.binding.parse_generation_id),
                }
            ),
        ),
    )

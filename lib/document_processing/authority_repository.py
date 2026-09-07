"""Document/run locks precede job-root locks in every candidate publication."""

from __future__ import annotations

from typing import Any, cast

from psycopg import sql

from lib.document_processing.errors import ProcessingAuthorityLost
from lib.document_processing.models import ProcessingBinding
from lib.document_processing.request_authority_repository import lock_processing_request
from lib.jobs.ownership import current_job_attempt, require_owned_job


def lock_current_run(
    cur: Any,
    binding: ProcessingBinding,
    *,
    include_artifacts: bool = True,
) -> dict[str, Any]:
    lock_processing_request(cur, binding)
    cur.execute(
        "SELECT id FROM document_processing_runs "
        "WHERE id = %s AND document_id = %s AND parse_generation_id = %s FOR UPDATE",
        (binding.processing_run_id, binding.document_id, binding.parse_generation_id),
    )
    if cur.fetchone() is None:
        raise ProcessingAuthorityLost("Processing run is unavailable.")
    # Fresh statement after waiting for document/run locks.
    artifacts = ", g.inventory_json, g.structure_json" if include_artifacts else ""
    cur.execute(
        sql.SQL("""SELECT r.*, g.state AS parse_state, g.inventory_sha256,
            g.structure_sha256 {artifacts}
        FROM document_processing_runs r
        JOIN documents d ON d.id = r.document_id
        JOIN document_parse_generations g ON g.id = r.parse_generation_id
        WHERE r.id = %s AND r.document_id = %s AND r.parse_generation_id = %s
          AND g.creator_run_id = r.id AND g.document_id = r.document_id
          AND d.deleted_at IS NULL AND d.desired_processing_run_id = r.id
          AND d.processing_generation = r.generation AND r.revoked_at IS NULL
          AND processing_request_is_authorized(r.id)""").format(artifacts=sql.SQL(artifacts)),
        (binding.processing_run_id, binding.document_id, binding.parse_generation_id),
    )
    row = cur.fetchone()
    if row is None:
        raise ProcessingAuthorityLost("Processing request no longer has publication authority.")
    return cast(dict[str, Any], row)


def fence_processing_attempt(cur: Any, binding: ProcessingBinding) -> None:
    """Publication requires the matching worker; caller already holds run locks."""
    attempt = current_job_attempt()
    if attempt is None:
        raise ProcessingAuthorityLost("Candidate publication requires a claimed processing job.")
    # Do not acquire a new domain lock after this ownership fence.
    require_owned_job(cur, attempt)
    cur.execute(
        """SELECT id FROM pipeline_jobs
        WHERE id = %s AND document_id = %s AND processing_run_id = %s
          AND parse_generation_id = %s""",
        (
            attempt.job_id,
            binding.document_id,
            binding.processing_run_id,
            binding.parse_generation_id,
        ),
    )
    if cur.fetchone() is None:
        raise ProcessingAuthorityLost("Job does not own this processing run and parse generation.")

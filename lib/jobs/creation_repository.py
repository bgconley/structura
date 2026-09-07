"""Job insertion and its fixed-scope foreign-key/ancestry lock boundary.

Current worker children remain in their parent's household/document/batch scope.
This makes repeated fanout reuse the same domain locks. Future multi-document
analysis fanout needs an explicit predeclared lock set before relaxing this rule.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, cast
from uuid import UUID

from psycopg import sql
from psycopg.types.json import Jsonb

from lib.jobs.errors import JobOwnershipLost, JobServiceError
from lib.jobs.ownership import current_job_attempt, require_owned_job
from lib.jobs.payload_policy import sanitize_job_payload


def insert_job(
    cur: Any,
    *,
    job_id: UUID,
    job_type: str,
    household_id: UUID | None,
    document_id: UUID | None,
    batch_id: UUID | None,
    payload: Mapping[str, Any] | None,
    priority: int,
    queue_name: str,
    max_attempts: int,
    processing_run_id: UUID | None = None,
    parse_generation_id: UUID | None = None,
) -> Mapping[str, Any]:
    safe_payload = sanitize_job_payload(payload or {})
    parent_id = None
    parent_generation = None
    parent = current_job_attempt()
    if parent is not None:
        cur.execute(
            "SELECT household_id, document_id, batch_id, processing_run_id, parse_generation_id "
            "FROM pipeline_jobs WHERE id = %s",
            (parent.job_id,),
        )
        scope = cur.fetchone()
        if scope is None:
            raise JobOwnershipLost("Parent job no longer exists.")
        household_id = _inherit_scope(household_id, scope["household_id"])
        document_id = _inherit_scope(document_id, scope["document_id"])
        batch_id = _inherit_scope(batch_id, scope["batch_id"])
        processing_run_id = _inherit_scope(processing_run_id, scope["processing_run_id"])
        parse_generation_id = _inherit_scope(parse_generation_id, scope["parse_generation_id"])
    # Job INSERT takes FK locks. Acquire its fixed domain reference set before
    # the root lock; otherwise sibling publication can hold document FOR UPDATE
    # while waiting on this tree. Repeated children have exactly the same scope.
    _lock_domain_references(cur, household_id, document_id, batch_id)
    _lock_processing_references(
        cur, processing_run_id, parse_generation_id, document_id, household_id
    )
    if parent is not None:
        require_owned_job(cur, parent)
        cur.execute(
            "SELECT execution_generation FROM pipeline_jobs WHERE id = %s", (parent.job_id,)
        )
        parent_id = parent.job_id
        parent_generation = cur.fetchone()["execution_generation"]
    cur.execute(
        """
        INSERT INTO pipeline_jobs
          (
            id,
            household_id,
            job_type,
            document_id,
            batch_id,
            parent_job_id,
            parent_execution_generation,
            payload_json,
            priority,
            queue_name,
            max_attempts,
            processing_run_id,
            parse_generation_id
          )
          VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s, %s, %s)
        RETURNING *
        """,
        (
            job_id,
            household_id,
            job_type,
            document_id,
            batch_id,
            parent_id,
            parent_generation,
            Jsonb(safe_payload),
            priority,
            queue_name,
            max_attempts,
            processing_run_id,
            parse_generation_id,
        ),
    )
    row = cur.fetchone()
    if not row:
        raise JobServiceError("Job was not created.")
    return cast(Mapping[str, Any], row)


def _inherit_scope(requested: UUID | None, parent: UUID | None) -> UUID | None:
    if requested is not None and requested != parent:
        raise JobServiceError(
            "Worker child jobs must retain their parent's domain and processing scope."
        )
    return parent


def _lock_domain_references(
    cur: Any, household_id: UUID | None, document_id: UUID | None, batch_id: UUID | None
) -> None:
    for table, identifier in (
        ("households", household_id),
        ("documents", document_id),
        ("ingest_batches", batch_id),
    ):
        if identifier is None:
            continue
        # Table names come exclusively from the literal tuple above.
        cur.execute(
            sql.SQL("SELECT id FROM {} WHERE id = %s FOR KEY SHARE").format(sql.Identifier(table)),
            (identifier,),
        )
        if cur.fetchone() is None:
            raise JobServiceError("Job document, household or batch reference does not exist.")


def _lock_processing_references(
    cur: Any,
    run_id: UUID | None,
    parse_id: UUID | None,
    document_id: UUID | None,
    household_id: UUID | None,
) -> None:
    if run_id is None and parse_id is None:
        return  # Transitional legacy queue work; never infer a current binding.
    if run_id is None or parse_id is None or document_id is None or household_id is None:
        raise JobServiceError("Processing jobs require a complete document/run/parse binding.")
    cur.execute(
        """SELECT r.id FROM document_processing_runs r
        JOIN document_parse_generations g ON g.id = r.parse_generation_id
        WHERE r.id = %s AND g.id = %s AND r.document_id = %s AND r.household_id = %s
          AND processing_job_is_current(r.id, g.id)
        FOR KEY SHARE OF r, g""",
        (run_id, parse_id, document_id, household_id),
    )
    if cur.fetchone() is None:
        raise JobOwnershipLost("Processing job source binding is invalid or no longer current.")

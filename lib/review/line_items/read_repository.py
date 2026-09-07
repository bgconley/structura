"""Coherent document-scoped current line, source and projection read envelopes."""

from typing import Any
from uuid import UUID

from lib.auth.request_authority import RequestCredential
from lib.auth.request_authority_repository import assert_request_authority, lock_request_authority
from lib.contracts.line_item_authority import (
    CanonicalLineResponse,
    LineCandidateRead,
    LineExtractionIdentity,
    VacantLineTarget,
)
from lib.fact_authority.models import ProjectionRevision
from lib.fact_authority.response_mapping import projection_response
from lib.review.errors import ReviewRepositoryError
from lib.review.line_items.read_budget import bounded_line_read
from lib.review.line_items.read_mapping import assignment_payload, canonical_payload, slot_decision
from lib.review.line_items.source_repository import LineSource, read_source
from lib.review.line_items.source_values import VALUE_COLUMNS, validation_summary


def lock_read(cur: Any, document_id: UUID, credential: RequestCredential) -> None:
    lock_request_authority(cur, credential, "documents:read")
    cur.execute("SELECT id FROM documents WHERE id=%s FOR SHARE", (document_id,))
    if cur.fetchone() is None:
        raise ReviewRepositoryError("Document not found.")
    assert_read(cur, document_id, credential)


def assert_read(cur: Any, document_id: UUID, credential: RequestCredential) -> None:
    assert_request_authority(cur, credential, "documents:read")
    cur.execute(
        "SELECT document_is_readable(id,%s,%s,NULL) AS allowed FROM documents WHERE "
        "id=%s AND deleted_at IS NULL",
        (credential.household_id, credential.user_id, document_id),
    )
    row = cur.fetchone()
    if row is None or not row["allowed"]:
        raise ReviewRepositoryError("Document not found.")


def read_projection(cur: Any, document_id: UUID):
    cur.execute(
        "SELECT document_id,state,accepted_fact_revision,projection_revision,accepted_facts_sha256,"
        "indexed_metadata_sha256,accepted_fact_basis_schema_version FROM "
        "document_fact_projection_state WHERE document_id=%s",
        (document_id,),
    )
    row = cur.fetchone()
    value = (
        ProjectionRevision(**row)
        if row
        else ProjectionRevision(
            document_id=document_id,
            state="unestablished",
            accepted_fact_revision=0,
            projection_revision=0,
            accepted_facts_sha256=None,
            indexed_metadata_sha256=None,
        )
    )
    return projection_response(value)


def canonical_lines(*, document_id: UUID, credential: RequestCredential) -> CanonicalLineResponse:
    with bounded_line_read() as cur:
        lock_read(cur, document_id, credential)
        cur.execute(
            "SELECT id,selected_candidate_id FROM selected_canonical_line_items WHERE "
            "document_id=%s",
            (document_id,),
        )
        selected = {(row["id"], row["selected_candidate_id"]) for row in cur.fetchall()}
        cur.execute(
            "SELECT * FROM canonical_line_items WHERE document_id=%s ORDER BY "
            "line_item_type,ordinal",
            (document_id,),
        )
        items = [
            canonical_payload(row, selected=(row["id"], row["selected_candidate_id"]) in selected)
            for row in cur.fetchall()
        ]
        cur.execute(
            "SELECT * FROM canonical_line_item_decisions WHERE document_id=%s ORDER BY "
            "line_item_type,ordinal",
            (document_id,),
        )
        decisions = [slot_decision(row) for row in cur.fetchall()]
        cur.execute(
            "SELECT * FROM canonical_line_item_source_bindings WHERE document_id=%s "
            "ORDER BY source_candidate_id",
            (document_id,),
        )
        assignments = [assignment_payload(row, selected) for row in cur.fetchall()]
        result = CanonicalLineResponse(
            authorityVersion="line_item_authority.v1",
            documentId=document_id,
            items=items,
            decisions=decisions,
            sourceAssignments=assignments,
            projection=read_projection(cur, document_id),
        )
        assert_read(cur, document_id, credential)
    return result


def candidate_lines(
    *,
    document_id: UUID,
    credential: RequestCredential,
    candidate_id: UUID | None = None,
    status: str | None = None,
) -> dict[str, Any]:
    with bounded_line_read() as cur:
        lock_read(cur, document_id, credential)
        cur.execute(
            "SELECT id FROM line_item_candidates WHERE document_id=%s AND (%s::uuid IS "
            "NULL OR id=%s)"
            "AND (%s::text IS NULL OR status=%s) ORDER BY "
            "line_item_type,ordinal,created_at DESC,id",
            (document_id, candidate_id, candidate_id, status, status),
        )
        ids = [row["id"] for row in cur.fetchall()]
        cur.execute(
            "SELECT id,selected_candidate_id FROM selected_canonical_line_items WHERE "
            "document_id=%s",
            (document_id,),
        )
        selected = {(row["id"], row["selected_candidate_id"]) for row in cur.fetchall()}
        cur.execute(
            "SELECT line_item_type,ordinal FROM canonical_line_items WHERE document_id=%s",
            (document_id,),
        )
        occupied = {(row["line_item_type"], row["ordinal"]) for row in cur.fetchall()}
        items = [
            _candidate_payload(read_source(cur, document_id, item_id), selected, occupied)
            for item_id in ids
        ]
        assert_read(cur, document_id, credential)
    return {
        "authorityVersion": "line_item_authority.v1",
        "documentId": document_id,
        "items": [item.model_dump(mode="json", by_alias=True) for item in items],
    }


def _candidate_payload(
    source: LineSource, selected: set[Any], occupied: set[tuple[str, int]]
) -> LineCandidateRead:
    row = source.row
    values = {key: row.get(key) for key in VALUE_COLUMNS if key != "currency_code"}
    suggested = None
    if source.eligibility.eligible and source.assignment is None:
        ordinal = 1
        while (row["line_item_type"], ordinal) in occupied:
            ordinal += 1
        suggested = VacantLineTarget(
            lineItemType=row["line_item_type"],
            ordinal=ordinal,
            canonicalLineItemId=None,
            expectedCanonicalUpdatedAt=None,
            expectedLineDecisionRevision=None,
        )
    return LineCandidateRead(
        **values,
        id=row["id"],
        documentId=row["document_id"],
        extractionId=row["extraction_id"],
        lineItemType=row["line_item_type"],
        ordinal=row["ordinal"],
        candidateGroup=row["candidate_group"],
        candidateVersion=row["decision_version"],
        sourceSnapshotSha256=source.sha256,
        candidateDecisionRevision=source.decision["revision"] if source.decision else None,
        sourceEngine=row["source_engine"],
        extraction=LineExtractionIdentity.model_validate(source.snapshot["extraction"])
        if source.snapshot["extraction"]
        else None,
        validation=validation_summary(row["validation_json"]),
        currency=row["currency_code"],
        evidence=source.evidence,
        status=row["status"],
        publicationEligibility=source.eligibility,
        sourceAssignment=assignment_payload(source.assignment, selected)
        if source.assignment
        else None,
        suggestedVacantTarget=suggested,
    )

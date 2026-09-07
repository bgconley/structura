"""Source locking, exact snapshots, and current publication eligibility."""

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from lib.contracts.line_item_authority import LineEvidenceRef, LinePublicationEligibility
from lib.review.errors import ReviewRepositoryError
from lib.review.line_items.errors import LineDecisionConflict
from lib.review.line_items.evidence_repository import evidence_is_bound
from lib.review.line_items.source_values import public_evidence, source_snapshot


@dataclass(frozen=True)
class LineSource:
    row: dict[str, Any]
    snapshot: dict[str, Any]
    sha256: str
    evidence: list[LineEvidenceRef]
    eligibility: LinePublicationEligibility
    decision: dict[str, Any] | None
    assignment: dict[str, Any] | None


def lock_selected_source(cur: Any, document_id: UUID, canonical_id: UUID) -> LineSource | None:
    # The caller holds the document lock; foreign legacy links are never followed.
    cur.execute(
        "SELECT c.selected_candidate_id FROM canonical_line_items c JOIN line_item_candidates s "
        "ON s.id=c.selected_candidate_id AND s.document_id=c.document_id "
        "WHERE c.id=%s AND c.document_id=%s",
        (canonical_id, document_id),
    )
    row = cur.fetchone()
    return lock_source(cur, document_id, row["selected_candidate_id"]) if row else None


def lock_source(cur: Any, document_id: UUID, candidate_id: UUID) -> LineSource:
    # Candidate identity/extraction binding is immutable. Observe the parent, lock
    # annotation then extraction, then candidate; re-read after all waits.
    cur.execute(
        "SELECT c.extraction_id,e.semantic_annotation_id FROM line_item_candidates c "
        "LEFT JOIN document_extractions e ON e.id=c.extraction_id AND e.document_id=c.document_id "
        "WHERE c.id=%s AND c.document_id=%s",
        (candidate_id, document_id),
    )
    parent = cur.fetchone()
    if parent is None:
        raise ReviewRepositoryError("Line-item candidate not found.")
    if parent["semantic_annotation_id"] is not None:
        cur.execute(
            "SELECT id FROM document_semantic_annotations WHERE id=%s AND document_id=%s FOR SHARE",
            (parent["semantic_annotation_id"], document_id),
        )
        cur.fetchone()
    if parent["extraction_id"] is not None:
        cur.execute(
            "SELECT id FROM document_extractions WHERE id=%s AND document_id=%s FOR SHARE",
            (parent["extraction_id"], document_id),
        )
        cur.fetchone()
    cur.execute("SELECT id FROM line_item_candidates WHERE id=%s FOR UPDATE", (candidate_id,))
    cur.fetchone()
    source = read_source(cur, document_id, candidate_id)
    extraction = source.snapshot["extraction"]
    annotation = extraction["semantic_annotation_id"] if extraction else None
    if annotation != (
        str(parent["semantic_annotation_id"]) if parent["semantic_annotation_id"] else None
    ):
        raise LineDecisionConflict()
    return source


def read_source(cur: Any, document_id: UUID, candidate_id: UUID) -> LineSource:
    cur.execute(
        "SELECT * FROM line_item_candidates WHERE id=%s AND document_id=%s",
        (candidate_id, document_id),
    )
    row = cur.fetchone()
    if row is None:
        raise ReviewRepositoryError("Line-item candidate not found.")
    cur.execute(
        "SELECT * FROM document_extractions WHERE id=%s AND document_id=%s",
        (row["extraction_id"], document_id),
    )
    extraction = cur.fetchone()
    cur.execute(
        "SELECT a.id,a.sha256 FROM document_assets a JOIN documents d ON d.id=a.document_id "
        "WHERE a.document_id=%s AND a.asset_role='original' AND a.sha256=d.original_sha256 "
        "ORDER BY a.created_at,a.id LIMIT 1",
        (document_id,),
    )
    original = cur.fetchone()
    cur.execute(
        "SELECT * FROM line_item_candidate_decisions WHERE document_id=%s AND "
        "source_candidate_id=%s",
        (document_id, candidate_id),
    )
    decision = cur.fetchone()
    cur.execute(
        "SELECT * FROM canonical_line_item_source_bindings WHERE document_id=%s AND "
        "source_candidate_id=%s",
        (document_id, candidate_id),
    )
    assignment = cur.fetchone()
    evidence, complete = public_evidence(row["evidence_json"])
    complete = (
        complete
        and original is not None
        and evidence_is_bound(cur, document_id, row["evidence_json"], evidence)
    )
    snapshot, sha256 = source_snapshot(row, extraction, original, evidence)
    eligibility = _eligibility(cur, row, extraction, assignment, complete)
    return LineSource(row, snapshot, sha256, evidence, eligibility, decision, assignment)


def _eligibility(
    cur: Any,
    row: dict[str, Any],
    extraction: dict[str, Any] | None,
    assignment: dict[str, Any] | None,
    evidence_complete: bool,
) -> LinePublicationEligibility:
    reason = "eligible"
    if assignment and assignment["binding_state"] == "legacy_conflict":
        reason = "legacy_assignment_conflict"
    elif extraction is None:
        reason = "source_binding_invalid" if row["extraction_id"] else "source_missing"
    elif extraction["document_id"] != row["document_id"]:
        reason = "source_binding_invalid"
    elif extraction["status"] != "completed":
        reason = "source_failed"
    elif not extraction["is_current"]:
        reason = "source_superseded"
    elif not _annotation_current(cur, extraction):
        reason = "source_superseded"
    elif not evidence_complete:
        reason = "evidence_incomplete"
    elif row["status"] not in {"proposed", "needs_review", "accepted", "rejected"}:
        reason = "unsupported_candidate_state"
    return LinePublicationEligibility.model_validate(
        {"eligible": reason == "eligible", "reason": reason}
    )


def _annotation_current(cur: Any, extraction: dict[str, Any]) -> bool:
    if extraction["extraction_scope"] not in {"semantic_region", "aggregate"}:
        return True
    cur.execute(
        "SELECT id FROM document_semantic_annotations WHERE id=%s AND document_id=%s "
        "AND status='succeeded' AND is_current",
        (extraction["semantic_annotation_id"], extraction["document_id"]),
    )
    if cur.fetchone() is None:
        return False
    if extraction["extraction_scope"] == "semantic_region":
        cur.execute(
            "SELECT id FROM semantic_region_annotations WHERE id=%s AND "
            "annotation_id=%s AND document_id=%s",
            (
                extraction["source_semantic_region_id"],
                extraction["semantic_annotation_id"],
                extraction["document_id"],
            ),
        )
        return cur.fetchone() is not None
    return True

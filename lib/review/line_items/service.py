"""One synchronous transaction for exact review, history, projection and enqueue."""

from typing import Any
from uuid import UUID

from lib.auth.request_authority import RequestCredential
from lib.contracts.line_item_authority import LineDecisionRequest, LineDecisionResponse
from lib.db.connection import db_connection
from lib.fact_authority.projection_repository import refresh_projection_and_enqueue
from lib.fact_authority.response_mapping import projection_response
from lib.review.audit_repository import update_document_review_status
from lib.review.line_items.access_repository import assert_line_review, lock_line_review
from lib.review.line_items.decision_repository import assign_source, decide_candidate, decide_slot
from lib.review.line_items.errors import LineDecisionConflict
from lib.review.line_items.history_repository import record_decision_history
from lib.review.line_items.read_mapping import candidate_decision, canonical_payload, slot_decision
from lib.review.line_items.source_repository import LineSource, lock_selected_source, lock_source
from lib.review.line_items.target_repository import (
    check_publication,
    check_source_version,
    lock_target,
    publish_canonical,
    reject_canonical,
    require_unselected_candidate,
)


def decide_line(
    *, document_id: UUID, credential: RequestCredential, request: LineDecisionRequest
) -> LineDecisionResponse:
    with db_connection() as conn, conn.cursor() as cur:
        lock_line_review(cur, document_id, credential)
        source = _source_for_request(cur, document_id, request)
        before = None
        after = None
        if request.operation != "reject_candidate":
            before = lock_target(cur, document_id, request.target)
            if request.operation == "reject_selected":
                if before is None:
                    raise LineDecisionConflict()
                after = reject_canonical(cur, before["id"], credential.user_id)
            else:
                if source is None:
                    raise LineDecisionConflict()
                check_publication(source, request.target)
                after = publish_canonical(
                    cur, document_id, credential.user_id, source, request.target
                )
                assign_source(cur, source, after)
        elif source is not None:
            require_unselected_candidate(cur, document_id, source.row["id"])
        event_id = record_decision_history(
            cur,
            document_id=document_id,
            actor_id=credential.user_id,
            operation=request.operation,
            before=before,
            after=after,
            source=source,
            comment=request.comment,
        )
        candidate = (
            decide_candidate(
                cur,
                source,
                credential.user_id,
                event_id,
                "accepted" if request.operation in {"create", "replace"} else "rejected",
            )
            if source
            else None
        )
        slot = (
            decide_slot(
                cur,
                after,
                credential.user_id,
                event_id,
                "rejected" if request.operation == "reject_selected" else "confirmed",
            )
            if after
            else None
        )
        update_document_review_status(cur, document_id)
        projection = refresh_projection_and_enqueue(
            cur, document_id=document_id, household_id=credential.household_id
        )
        # The last check follows job fences/FK waits as well as document/source
        # waits. Absolute expiry can pass while a credential row remains locked.
        assert_line_review(cur, document_id, credential)
        result = LineDecisionResponse(
            operation=request.operation,
            eventId=event_id,
            canonicalItem=canonical_payload(after, selected=request.operation != "reject_selected")
            if after
            else None,
            candidateDecision=candidate_decision(candidate) if candidate else None,
            lineDecision=slot_decision(slot) if slot else None,
            projection=projection_response(projection),
        )
        conn.commit()
    return result


def _source_for_request(
    cur: Any, document_id: UUID, request: LineDecisionRequest
) -> LineSource | None:
    if request.operation != "reject_selected":
        source = lock_source(cur, document_id, request.source.candidate_id)
        check_source_version(source, request.source)
        return source
    return lock_selected_source(cur, document_id, request.target.canonical_line_item_id)

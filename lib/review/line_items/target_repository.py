"""Exact physical canonical slot selection; no ordinal alignment or silent append."""

from typing import Any, cast
from uuid import UUID

from psycopg.types.json import Jsonb

from lib.contracts.line_item_authority import (
    ExistingLineTarget,
    LineSourceExpectation,
    VacantLineTarget,
)
from lib.review.line_items.errors import LineDecisionConflict, LineEvidenceError
from lib.review.line_items.source_repository import LineSource
from lib.review.line_items.source_values import VALUE_COLUMNS


def require_unselected_candidate(cur: Any, document_id: UUID, candidate_id: UUID) -> None:
    cur.execute(
        "SELECT id FROM selected_canonical_line_items "
        "WHERE document_id=%s AND selected_candidate_id=%s",
        (document_id, candidate_id),
    )
    if cur.fetchone() is not None:
        raise LineDecisionConflict()


def lock_target(
    cur: Any, document_id: UUID, target: ExistingLineTarget | VacantLineTarget
) -> dict[str, Any] | None:
    cur.execute(
        "SELECT * FROM canonical_line_items WHERE document_id=%s AND line_item_type=%s "
        "AND ordinal=%s FOR UPDATE",
        (document_id, target.line_item_type, target.ordinal),
    )
    row = cur.fetchone()
    cur.execute(
        "SELECT revision FROM canonical_line_item_decisions WHERE document_id=%s AND "
        "line_item_type=%s AND ordinal=%s FOR UPDATE",
        (document_id, target.line_item_type, target.ordinal),
    )
    decision = cur.fetchone()
    if isinstance(target, VacantLineTarget):
        if row is not None or decision is not None:
            raise LineDecisionConflict()
        return None
    if (
        row is None
        or row["id"] != target.canonical_line_item_id
        or row["updated_at"] != target.expected_canonical_updated_at
        or (decision["revision"] if decision else None) != target.expected_line_decision_revision
    ):
        raise LineDecisionConflict()
    return cast(dict[str, Any], row)


def check_source_version(source: LineSource, expected: LineSourceExpectation) -> None:
    if (
        source.row["id"] != expected.candidate_id
        or source.row["decision_version"] != expected.expected_candidate_version
        or source.sha256 != expected.expected_source_snapshot_sha256
        or (source.decision["revision"] if source.decision else None)
        != expected.expected_candidate_decision_revision
    ):
        raise LineDecisionConflict()


def check_publication(source: LineSource, target: ExistingLineTarget | VacantLineTarget) -> None:
    if not source.eligibility.eligible:
        if source.eligibility.reason == "evidence_incomplete":
            raise LineEvidenceError()
        raise LineDecisionConflict()
    if source.row["line_item_type"] != target.line_item_type:
        raise LineDecisionConflict()
    if source.assignment and (
        source.assignment["binding_state"] != "assigned"
        or source.assignment["canonical_line_item_id"] != target.canonical_line_item_id
        or source.assignment["line_item_type"] != target.line_item_type
        or source.assignment["ordinal"] != target.ordinal
    ):
        raise LineDecisionConflict()


def publish_canonical(
    cur: Any,
    document_id: UUID,
    actor_id: UUID,
    source: LineSource,
    target: ExistingLineTarget | VacantLineTarget,
) -> dict[str, Any]:
    values = tuple(source.row.get(key) for key in VALUE_COLUMNS)
    evidence = Jsonb(source.snapshot["evidence"])
    validation = Jsonb(
        {"reviewed": True, "sourceValidationSha256": source.snapshot["validationSha256"]}
    )
    if isinstance(target, VacantLineTarget):
        cur.execute(
            """INSERT INTO canonical_line_items
            (document_id,line_item_type,ordinal,selected_candidate_id,code,code_system,service_date,
             description,quantity,unit,unit_price,gross_amount,discount_amount,tax_amount,net_amount,
             allowed_amount,plan_paid_amount,currency_code,category_hint,evidence_json,validation_json,
             source_kind,review_status,accepted_by_user_id,accepted_at,updated_at)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
                    'candidate','user_confirmed',%s,clock_timestamp(),clock_timestamp())
                    RETURNING *""",
            (
                document_id,
                target.line_item_type,
                target.ordinal,
                source.row["id"],
                *values,
                evidence,
                validation,
                actor_id,
            ),
        )
    else:
        cur.execute(
            """UPDATE canonical_line_items SET selected_candidate_id=%s,code=%s,code_system=%s,
            service_date=%s,description=%s,quantity=%s,unit=%s,unit_price=%s,gross_amount=%s,
            discount_amount=%s,tax_amount=%s,net_amount=%s,allowed_amount=%s,plan_paid_amount=%s,
            currency_code=%s,category_hint=%s,evidence_json=%s,validation_json=%s,
            source_kind='candidate',review_status='user_confirmed',accepted_by_user_id=%s,
            accepted_at=clock_timestamp(),updated_at=GREATEST(clock_timestamp(),updated_at+interval
            '1 microsecond')
            WHERE id=%s AND document_id=%s RETURNING *""",
            (
                source.row["id"],
                *values,
                evidence,
                validation,
                actor_id,
                target.canonical_line_item_id,
                document_id,
            ),
        )
    return cast(dict[str, Any], cur.fetchone())


def reject_canonical(cur: Any, canonical_id: UUID, actor_id: UUID) -> dict[str, Any]:
    cur.execute(
        """UPDATE canonical_line_items SET review_status='rejected',accepted_by_user_id=%s,
        updated_at=GREATEST(clock_timestamp(),updated_at+interval '1 microsecond') WHERE
        id=%s RETURNING *""",
        (actor_id, canonical_id),
    )
    return cast(dict[str, Any], cur.fetchone())

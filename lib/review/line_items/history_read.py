"""ACL-scoped immutable history pagination, with explicitly partial legacy events."""

import base64
import binascii
import json
from datetime import datetime
from typing import Any
from uuid import UUID

from lib.auth.request_authority import RequestCredential
from lib.contracts.line_item_authority import (
    LineHistoryEntry,
    LineHistoryResponse,
    LineHistoryValue,
    LineLegacySummary,
    LineSourceSnapshotRead,
)
from lib.review.line_items.read_budget import bounded_line_read
from lib.review.line_items.read_repository import assert_read, lock_read


def line_history(
    *,
    document_id: UUID,
    credential: RequestCredential,
    canonical_line_item_id: UUID | None = None,
    source_candidate_id: UUID | None = None,
    cursor: str | None = None,
    limit: int = 50,
) -> LineHistoryResponse:
    if (canonical_line_item_id is None) == (source_candidate_id is None) or not 1 <= limit <= 100:
        raise ValueError("Exactly one line history selector is required.")
    selector = str(canonical_line_item_id or source_candidate_id)
    scope = f"{document_id}:{'canonical' if canonical_line_item_id else 'candidate'}:{selector}"
    before_time, before_id = _decode_cursor(cursor, scope)
    with bounded_line_read() as cur:
        lock_read(cur, document_id, credential)
        cur.execute(
            """WITH events AS (
              SELECT e.id,e.document_id,e.source_candidate_id,e.canonical_line_item_id,e.operation,
                e.before_json,e.after_json,e.source_snapshot_json,e.comment,e.occurred_at,
                COALESCE(u.display_name,'Deleted reviewer') AS actor_label,'complete' AS coverage
              FROM line_item_decision_events e LEFT JOIN users u ON u.id=e.actor_user_id
              WHERE e.document_id=%s AND ((%s::uuid IS NOT NULL AND e.canonical_line_item_id=%s)
                OR (%s::uuid IS NOT NULL AND e.source_candidate_id=%s))
              UNION ALL
              SELECT e.id,e.document_id,NULL::uuid,e.canonical_line_item_id,e.action,
                e.old_value_json,e.new_value_json,NULL::jsonb,e.reason,e.created_at,
                COALESCE(u.display_name,'Legacy reviewer (identity unestablished)'),
                'legacy_partial'
              FROM canonical_fact_history e LEFT JOIN users u ON u.id=e.actor_user_id
              WHERE e.document_id=%s AND %s::uuid IS NOT NULL AND e.canonical_line_item_id=%s
                AND e.action NOT LIKE 'line_item_%%'
              UNION ALL
              SELECT e.id,e.document_id,%s::uuid,NULL::uuid,e.action,
                e.old_value_json,e.new_value_json,
                NULL::jsonb,e.reason,e.created_at,
                'Legacy reviewer (identity unestablished)','legacy_partial'
              FROM review_events e WHERE e.document_id=%s AND %s::uuid IS NOT NULL
                AND e.action IN ('accept_line_item','reject_line_item')
                AND e.old_value_json->>'lineItemCandidateId'=%s
            ) SELECT * FROM events WHERE %s::timestamptz IS NULL
                OR (occurred_at,id)<(%s::timestamptz,%s::uuid)
              ORDER BY occurred_at DESC,id DESC LIMIT %s""",
            (
                document_id,
                canonical_line_item_id,
                canonical_line_item_id,
                source_candidate_id,
                source_candidate_id,
                document_id,
                canonical_line_item_id,
                canonical_line_item_id,
                source_candidate_id,
                document_id,
                source_candidate_id,
                str(source_candidate_id),
                before_time,
                before_time,
                before_id,
                limit + 1,
            ),
        )
        rows = cur.fetchall()
        page = rows[:limit]
        result = LineHistoryResponse(
            documentId=document_id,
            items=[_entry(row) for row in page],
            nextCursor=_encode_cursor(page[-1], scope) if len(rows) > limit else None,
        )
        assert_read(cur, document_id, credential)
    return result


def _entry(row: dict[str, Any]) -> LineHistoryEntry:
    complete = row["coverage"] == "complete"
    source = row["source_snapshot_json"]
    legacy = row["after_json"] if isinstance(row["after_json"], dict) else {}
    return LineHistoryEntry(
        id=row["id"],
        documentId=row["document_id"],
        sourceCandidateId=row["source_candidate_id"],
        canonicalLineItemId=row["canonical_line_item_id"],
        operation=row["operation"],
        coverage=row["coverage"],
        before=_value(row["before_json"]) if complete else None,
        after=_value(row["after_json"]) if complete else None,
        source=LineSourceSnapshotRead.model_validate(source) if complete and source else None,
        legacySummary=None
        if complete
        else LineLegacySummary.model_validate(
            {
                "description": legacy.get("description")
                if isinstance(legacy.get("description"), str)
                else None,
                "status": legacy.get("status") if isinstance(legacy.get("status"), str) else None,
                "netAmount": str(legacy["netAmount"])
                if isinstance(legacy.get("netAmount"), str | int | float)
                else None,
            }
        ),
        actorLabel=row["actor_label"],
        occurredAt=row["occurred_at"],
        comment=row["comment"],
    )


def _value(value: dict[str, Any] | None) -> LineHistoryValue | None:
    if value is None:
        return None
    source = value.get("source")
    recorded = isinstance(source, dict) and source.get("schemaVersion") == "line_item_source.v1"
    return LineHistoryValue(
        canonical=value["canonical"],
        source=LineSourceSnapshotRead.model_validate(source) if recorded else None,
        sourceCoverage="recorded" if recorded else "legacy_unestablished",
    )


def _decode_cursor(cursor: str | None, scope: str) -> tuple[datetime | None, UUID | None]:
    if cursor is None:
        return None, None
    try:
        if len(cursor) > 1024:
            raise ValueError()
        value = json.loads(base64.urlsafe_b64decode(cursor))
        if (
            not isinstance(value, list)
            or len(value) != 3
            or not all(isinstance(part, str) for part in value)
            or value[0] != scope
        ):
            raise ValueError()
        timestamp = datetime.fromisoformat(value[1])
        if timestamp.tzinfo is None:
            raise ValueError()
        return timestamp, UUID(value[2])
    except (ValueError, TypeError, binascii.Error, UnicodeError):
        raise ValueError("Invalid line history cursor.") from None


def _encode_cursor(row: dict[str, Any], scope: str) -> str:
    return base64.urlsafe_b64encode(
        json.dumps(
            [scope, row["occurred_at"].isoformat(), str(row["id"])],
            separators=(",", ":"),
        ).encode()
    ).decode()

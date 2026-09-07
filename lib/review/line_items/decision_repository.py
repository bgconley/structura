"""Durable candidate/slot decisions, lifetime assignments and exact task closure."""

from typing import Any, cast
from uuid import UUID

from psycopg.types.json import Jsonb

from lib.review.line_items.source_repository import LineSource


def assign_source(cur: Any, source: LineSource, canonical: dict[str, Any]) -> None:
    if source.assignment is not None:
        return  # The service already checked the immutable original target.
    cur.execute(
        """INSERT INTO canonical_line_item_source_bindings
        (document_id,source_candidate_id,candidate_id,binding_state,canonical_line_item_id,
         line_item_type,ordinal,source_snapshot_json,source_snapshot_sha256)
        VALUES(%s,%s,%s,'assigned',%s,%s,%s,%s,%s)""",
        (
            canonical["document_id"],
            source.row["id"],
            source.row["id"],
            canonical["id"],
            canonical["line_item_type"],
            canonical["ordinal"],
            Jsonb(source.snapshot),
            source.sha256,
        ),
    )


def decide_candidate(
    cur: Any, source: LineSource, actor_id: UUID, event_id: UUID, disposition: str
) -> dict[str, Any]:
    cur.execute(
        "UPDATE line_item_candidates SET status=%s WHERE id=%s AND document_id=%s",
        (disposition, source.row["id"], source.row["document_id"]),
    )
    cur.execute(
        """INSERT INTO line_item_candidate_decisions
        (document_id,source_candidate_id,candidate_id,disposition,origin,source_snapshot_json,
         source_snapshot_sha256,actor_user_id,review_event_id,decided_at)
        VALUES(%s,%s,%s,%s,'live_review',%s,%s,%s,%s,clock_timestamp())
        ON CONFLICT(document_id,source_candidate_id) DO UPDATE SET disposition=EXCLUDED.disposition,
          origin='live_review',source_snapshot_json=EXCLUDED.source_snapshot_json,
          source_snapshot_sha256=EXCLUDED.source_snapshot_sha256,actor_user_id=EXCLUDED.actor_user_id,
          review_event_id=EXCLUDED.review_event_id,decided_at=clock_timestamp(),revision=gen_random_uuid(),
          recorded_at=GREATEST(clock_timestamp(),line_item_candidate_decisions.recorded_at+interval
          '1 microsecond')
        RETURNING *""",
        (
            source.row["document_id"],
            source.row["id"],
            source.row["id"],
            disposition,
            Jsonb(source.snapshot),
            source.sha256,
            actor_id,
            event_id,
        ),
    )
    result = cur.fetchone()
    # Only exact, consistent candidate task references. Ambiguous legacy paths stay
    # visible; a similarly numbered region/aggregate proposal is a different task.
    cur.execute(
        """UPDATE review_tasks SET status='resolved',updated_at=now()
        WHERE document_id=%s AND status IN ('open','in_progress')
          AND metadata_json->>'lineItemCandidateId'=%s
          AND (NOT metadata_json ? 'lineItemType' OR metadata_json->>'lineItemType'=%s)
          AND (NOT metadata_json ? 'ordinal' OR metadata_json->>'ordinal'=%s)
          AND (NOT metadata_json ? 'fieldPath' OR metadata_json->>'fieldPath'=%s)""",
        (
            source.row["document_id"],
            str(source.row["id"]),
            source.row["line_item_type"],
            str(source.row["ordinal"]),
            f"line_items.{source.row['line_item_type']}.{source.row['ordinal']}",
        ),
    )
    return cast(dict[str, Any], result)


def decide_slot(
    cur: Any, canonical: dict[str, Any], actor_id: UUID, event_id: UUID, disposition: str
) -> dict[str, Any]:
    cur.execute(
        """INSERT INTO canonical_line_item_decisions
        (document_id,line_item_type,ordinal,canonical_line_item_id,disposition,origin,
         actor_user_id,review_event_id,decision_event_id,decided_at)
        VALUES(%s,%s,%s,%s,%s,'live_review',%s,%s,%s,clock_timestamp())
        ON CONFLICT(document_id,line_item_type,ordinal) DO UPDATE SET
        disposition=EXCLUDED.disposition,
          origin='live_review',actor_user_id=EXCLUDED.actor_user_id,review_event_id=EXCLUDED.review_event_id,
          decision_event_id=EXCLUDED.decision_event_id,
          decided_at=clock_timestamp(),revision=gen_random_uuid(),
          recorded_at=GREATEST(clock_timestamp(),canonical_line_item_decisions.recorded_at+interval
          '1 microsecond')
        RETURNING *""",
        (
            canonical["document_id"],
            canonical["line_item_type"],
            canonical["ordinal"],
            canonical["id"],
            disposition,
            actor_id,
            event_id,
            event_id,
        ),
    )
    return cast(dict[str, Any], cur.fetchone())

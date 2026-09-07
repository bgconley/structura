"""Immutable exact line decision history in the same publishing transaction."""

from typing import Any
from uuid import UUID

from psycopg.types.json import Jsonb

from lib.review.audit_repository import record_review_event
from lib.review.line_items.read_mapping import canonical_payload
from lib.review.line_items.source_repository import LineSource


def record_decision_history(
    cur: Any,
    *,
    document_id: UUID,
    actor_id: UUID,
    operation: str,
    before: dict[str, Any] | None,
    after: dict[str, Any] | None,
    source: LineSource | None,
    comment: str | None,
) -> UUID:
    before_json = _canonical_snapshot(cur, before) if before else None
    after_json = (
        _canonical_snapshot(cur, after, selected=operation != "reject_selected") if after else None
    )
    source_snapshot = source.snapshot if source else (before_json or {}).get("source")
    if source_snapshot and source_snapshot.get("schemaVersion") != "line_item_source.v1":
        source_snapshot = None
    canonical_id = after["id"] if after else None
    source_id = (
        source.row["id"]
        if source
        else (
            source_snapshot["candidate"]["id"]
            if source_snapshot and source_snapshot.get("schemaVersion") == "line_item_source.v1"
            else None
        )
    )
    field_path = f"line_items.{after['line_item_type']}.{after['ordinal']}" if after else None
    event_id = record_review_event(
        cur,
        document_id=document_id,
        review_task_id=None,
        field_path=field_path,
        action=f"line_item_{operation}",
        old_value=before_json,
        new_value={"canonical": after_json, "source": source_snapshot},
        actor_label=str(actor_id),
        reason=comment,
    )
    cur.execute(
        """INSERT INTO line_item_decision_events
        (id,document_id,source_candidate_id,canonical_line_item_id,operation,before_json,after_json,
         source_snapshot_json,actor_user_id,review_event_id,comment)
        VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
        (
            event_id,
            document_id,
            source_id,
            canonical_id,
            operation,
            Jsonb(before_json) if before_json is not None else None,
            Jsonb(after_json) if after_json is not None else None,
            Jsonb(source_snapshot) if source_snapshot is not None else None,
            actor_id,
            event_id,
            comment,
        ),
    )
    if canonical_id is not None:
        cur.execute(
            """INSERT INTO canonical_fact_history
            (document_id,canonical_line_item_id,field_path,action,old_value_json,new_value_json,actor_user_id,reason)
            VALUES(%s,%s,%s,%s,%s,%s,%s,%s)""",
            (
                document_id,
                canonical_id,
                field_path,
                f"line_item_{operation}",
                Jsonb(before_json),
                Jsonb(after_json),
                actor_id,
                comment,
            ),
        )
    return event_id


def _canonical_snapshot(
    cur: Any, row: dict[str, Any], *, selected: bool | None = None
) -> dict[str, Any]:
    if selected is None:
        cur.execute(
            "SELECT disposition FROM canonical_line_item_decisions WHERE "
            "document_id=%s AND line_item_type=%s AND ordinal=%s",
            (row["document_id"], row["line_item_type"], row["ordinal"]),
        )
        decision = cur.fetchone()
        selected = row["review_status"] in {
            "auto_accepted",
            "user_confirmed",
            "user_corrected",
        } and (decision is None or decision["disposition"] in {"confirmed", "corrected"})
    value = canonical_payload(row, selected=selected)
    cur.execute(
        "SELECT source_snapshot_json FROM canonical_line_item_source_bindings "
        "WHERE document_id=%s AND source_candidate_id=%s AND canonical_line_item_id=%s",
        (row["document_id"], row["selected_candidate_id"], row["id"]),
    )
    binding = cur.fetchone()
    if binding is None and row["selected_candidate_id"] is None:
        # The live candidate FK may have been cleared. The exact latest decision
        # identifies its retained full event; never guess from several previous
        # source assignments to this slot.
        cur.execute(
            "SELECT e.after_json->'source' AS source_snapshot_json "
            "FROM canonical_line_item_decisions d JOIN line_item_decision_events e "
            "ON e.id=d.decision_event_id AND e.document_id=d.document_id "
            "AND e.canonical_line_item_id=d.canonical_line_item_id "
            "WHERE d.document_id=%s AND d.canonical_line_item_id=%s",
            (row["document_id"], row["id"]),
        )
        binding = cur.fetchone()
    return {
        "canonical": value.model_dump(mode="json", by_alias=True),
        "source": binding["source_snapshot_json"] if binding else None,
    }

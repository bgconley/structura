"""Refresh filing metadata in the caller transaction without establishing facts."""

from typing import Any
from uuid import UUID

from lib.fact_authority.projection_values import snapshot_digest
from lib.jobs.ownership import fence_current_job
from lib.search.jobs import enqueue_embed_document_job


def metadata_fingerprint(
    indexed_metadata: object, decisions: dict[str, Any], rollups: object
) -> str:
    """Shared encoding with fact promotion; this helper makes no ownership decision."""
    return snapshot_digest(
        {
            "schemaVersion": "indexed_metadata.v1",
            "metadata": indexed_metadata,
            "decisions": decisions,
            "rollups": rollups,
        }
    )


def refresh_metadata_and_enqueue(cur: Any, *, document_id: UUID, household_id: UUID) -> None:
    # The SQL snapshot changes lexical inputs only. Do not call the accepted-fact
    # coordinator: that reconciles scalar ownership and establishes fact basis.
    cur.execute("SELECT refresh_document_chunk_projection_snapshot(%s) AS metadata", (document_id,))
    indexed_metadata = cur.fetchone()["metadata"]
    cur.execute(
        "SELECT state,rollup_json,indexed_metadata_sha256 FROM document_fact_projection_state "
        "WHERE document_id=%s FOR UPDATE",
        (document_id,),
    )
    previous = cur.fetchone()
    if previous and previous["state"] == "current":
        cur.execute(
            "SELECT property,value_json,revision FROM document_metadata_decisions "
            "WHERE document_id=%s ORDER BY property",
            (document_id,),
        )
        decisions = {row["property"]: row for row in cur.fetchall()}
        fingerprint = metadata_fingerprint(indexed_metadata, decisions, previous["rollup_json"])
        if previous["indexed_metadata_sha256"] != fingerprint:
            cur.execute(
                "UPDATE document_fact_projection_state SET indexed_metadata_sha256=%s,"
                "projection_revision=projection_revision+1,"
                "recorded_at=GREATEST(clock_timestamp(),recorded_at+interval '1 microsecond') "
                "WHERE document_id=%s",
                (fingerprint, document_id),
            )
    # Missing/unestablished rows stay exactly that way, including their null
    # fingerprints and zero revisions. Lexical maintenance is not fact acceptance.
    fence_current_job(cur)
    enqueue_embed_document_job(cur, document_id=document_id, household_id=household_id)

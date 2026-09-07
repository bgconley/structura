"""Accepted field snapshots, owned rollups and lexical revision in one caller transaction."""

from typing import Any
from uuid import UUID

from psycopg.types.json import Jsonb

from lib.fact_authority.line_projection import BASIS_VERSION, selected_facts_digest
from lib.fact_authority.models import ProjectionRevision
from lib.fact_authority.projection_values import (
    COUNTERPARTY_PATHS,
    DATE_PATHS,
    owned_scalar,
    scalar_selection,
    selected_total,
    snapshot_digest,
)
from lib.jobs.ownership import fence_current_job
from lib.search.jobs import enqueue_embed_document_job


def refresh_accepted_projection(cur: Any, document_id: UUID) -> ProjectionRevision:
    cur.execute("SELECT * FROM documents WHERE id=%s FOR UPDATE", (document_id,))
    document = cur.fetchone()
    if document is None:
        raise RuntimeError("Projection document is unavailable.")
    cur.execute(
        """SELECT cf.*,fd.revision AS decision_revision FROM selected_canonical_fields cf
        LEFT JOIN canonical_field_decisions fd ON fd.document_id=cf.document_id
          AND fd.field_path=cf.field_path AND fd.ordinal=cf.ordinal
        WHERE cf.document_id=%s ORDER BY cf.field_path,cf.ordinal""",
        (document_id,),
    )
    fields = cur.fetchall()
    cur.execute(
        "SELECT property,value_json,revision FROM document_metadata_decisions "
        "WHERE document_id=%s ORDER BY property",
        (document_id,),
    )
    metadata = {row["property"]: row for row in cur.fetchall()}
    cur.execute(
        """INSERT INTO document_fact_projection_state(document_id,legacy_metadata_json)
        VALUES (%s,%s) ON CONFLICT (document_id) DO NOTHING""",
        (
            document_id,
            Jsonb(
                {
                    "schemaVersion": "legacy_metadata.v1",
                    "classification": {
                        "family": document["document_family"],
                        "subtype": document["document_subtype"],
                    },
                    "documentDate": document["document_date"].isoformat()
                    if document["document_date"]
                    else None,
                    "counterpartyDisplay": document["counterparty_display"],
                }
            ),
        ),
    )
    cur.execute(
        "SELECT * FROM document_fact_projection_state WHERE document_id=%s FOR UPDATE",
        (document_id,),
    )
    previous = cur.fetchone()
    old_rollups = previous["rollup_json"] or {}
    date_decision = metadata.get("document_date")
    rollups: dict[str, Any] = {
        "schemaVersion": "accepted_field_rollups.v1",
        "counterparty": owned_scalar(
            current=document["counterparty_display"],
            proposed=scalar_selection(fields, COUNTERPARTY_PATHS, "text_value"),
            previous=old_rollups.get("counterparty"),
        ),
        "documentDate": owned_scalar(
            current=document["document_date"],
            proposed=scalar_selection(fields, DATE_PATHS, "date_value"),
            previous=old_rollups.get("documentDate"),
            manual_present=date_decision is not None,
            manual_value=date_decision["value_json"] if date_decision else None,
        ),
    }
    cur.execute(
        "UPDATE documents SET counterparty_display=%s,document_date=%s WHERE id=%s",
        (rollups["counterparty"]["value"], rollups["documentDate"]["value"], document_id),
    )
    _reconcile_owned_total(cur, document_id, selected_total(fields))
    cur.execute("SELECT refresh_document_chunk_projection_snapshot(%s) AS metadata", (document_id,))
    indexed_metadata = cur.fetchone()["metadata"]
    cur.execute(
        "SELECT c.*,d.revision AS decision_revision FROM selected_canonical_line_items c "
        "LEFT JOIN canonical_line_item_decisions d ON d.canonical_line_item_id=c.id "
        "WHERE c.document_id=%s ORDER BY c.line_item_type,c.ordinal",
        (document_id,),
    )
    fact_hash = selected_facts_digest(fields, cur.fetchall())
    metadata_hash = snapshot_digest(
        {
            "schemaVersion": "indexed_metadata.v1",
            "metadata": indexed_metadata,
            "decisions": metadata,
            "rollups": rollups,
        }
    )
    cur.execute(
        """UPDATE document_fact_projection_state SET state='current',
          accepted_fact_revision=accepted_fact_revision +
            CASE WHEN accepted_facts_sha256 IS DISTINCT FROM %s THEN 1 ELSE 0 END,
          projection_revision=projection_revision+1,accepted_facts_sha256=%s,
          indexed_metadata_sha256=%s,rollup_json=%s,accepted_fact_basis_schema_version=%s,
          recorded_at=GREATEST(clock_timestamp(),recorded_at+interval '1 microsecond')
        WHERE document_id=%s RETURNING document_id,state,accepted_fact_revision,
          projection_revision,accepted_facts_sha256,indexed_metadata_sha256,accepted_fact_basis_schema_version""",
        (fact_hash, fact_hash, metadata_hash, Jsonb(rollups), BASIS_VERSION, document_id),
    )
    return ProjectionRevision(**cur.fetchone())


def refresh_projection_and_enqueue(
    cur: Any,
    *,
    document_id: UUID,
    household_id: UUID,
) -> ProjectionRevision:
    revision = refresh_accepted_projection(cur, document_id)
    fence_current_job(cur)
    enqueue_embed_document_job(cur, document_id=document_id, household_id=household_id)
    return revision


def _reconcile_owned_total(
    cur: Any, document_id: UUID, total: tuple[object, str | None] | None
) -> None:
    cur.execute(
        """DELETE FROM document_amounts WHERE document_id=%s AND amount_role='total'
        AND (metadata_json @> '{"phase":"phase4","source":"canonical_fields"}'::jsonb
          OR metadata_json @> '{"source":"accepted_field_projection.v1"}'::jsonb)""",
        (document_id,),
    )
    if total is not None:
        cur.execute(
            """INSERT INTO document_amounts
            (document_id,amount_role,amount,currency_code,metadata_json)
            VALUES (%s,'total',%s,%s,'{"source":"accepted_field_projection.v1"}'::jsonb)""",
            (document_id, *total),
        )

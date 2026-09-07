"""SQL projections shared by document browse membership and scoped counts.

Only currently published records contribute. Candidate parse generations are not
searchable or extracted document state. Every duplicate counterpart is authorized
independently of the visible document.
"""

from psycopg import sql

from lib.documents.browse_query import DocumentSort, InboxState


def classification_state_sql() -> sql.SQL:
    """Keep legacy decision recognition isolated for the authority-marker migration.

    Generic is a valid classified family. Document review_status is not evidence
    of a human classification decision, and metadata has no reliable decision time.
    An explicit reclassification event therefore remains a human decision even if
    a legacy worker subsequently wrote classification output.
    """
    return sql.SQL("""
      CROSS JOIN LATERAL (
        SELECT
          EXISTS (
            SELECT 1 FROM review_events classification_event
            WHERE classification_event.document_id = d.id
              AND classification_event.action = 'reclassify_document'
              AND classification_event.field_path = 'classification.document_family'
          ) AS human_decision,
          (
            EXISTS (
              SELECT 1 FROM document_extractions classification_extraction
              WHERE classification_extraction.document_id = d.id
                AND classification_extraction.schema_name = 'document_classification'
                AND classification_extraction.is_current
                AND classification_extraction.status IN ('completed', 'accepted')
            )
            OR (
              d.metadata_json #>> '{phase8_5,semantic_classification,version}'
                = 'phase8_5_semantic_family_reconciliation_v1'
              AND jsonb_typeof(d.metadata_json #>
                '{phase8_5,semantic_classification,family}') = 'string'
              AND jsonb_typeof(d.metadata_json #>
                '{phase8_5,semantic_classification,should_update}') = 'boolean'
            )
          ) IS TRUE AS model_decision
      ) classification
    """)


def browse_state_sql() -> sql.Composed:
    return sql.SQL("""
      {classification_sql}
      CROSS JOIN LATERAL (
        SELECT
          TRUE AS all,
          (d.review_status = 'needs_review' OR EXISTS (
            SELECT 1 FROM review_tasks task
            WHERE task.document_id = d.id AND task.status IN ('open', 'in_progress')
          )) AS needs_review,
          NOT EXISTS (
            SELECT 1 FROM document_folder_memberships membership
            JOIN folders folder ON folder.id = membership.folder_id
            WHERE membership.document_id = d.id AND folder.folder_kind = 'manual'
          ) AS unfiled,
          (NOT classification.human_decision AND NOT classification.model_decision
            AND d.document_family = 'generic') AS awaiting_classification,
          EXISTS (
            SELECT 1 FROM documents counterpart
            WHERE counterpart.id <> d.id AND counterpart.deleted_at IS NULL
              AND counterpart.id IN (
                SELECT d.duplicate_of_document_id
                UNION
                SELECT duplicate.id FROM documents duplicate
                WHERE duplicate.duplicate_of_document_id = d.id
                UNION
                SELECT CASE WHEN relation.from_document_id = d.id
                  THEN relation.to_document_id ELSE relation.from_document_id END
                FROM document_relationships relation
                WHERE d.id IN (relation.from_document_id, relation.to_document_id)
                  AND relation.relationship_type = 'duplicate_of'
                  AND relation.status IN ('suggested', 'confirmed')
              )
              AND document_is_readable(counterpart.id, %s, %s, %s)
          ) AS duplicates,
          (classification.model_decision AND NOT classification.human_decision
            AND d.family_confidence < 0.7) IS TRUE AS low_confidence,
          EXISTS (
            SELECT 1 FROM document_extractions extraction
            WHERE extraction.document_id = d.id AND extraction.is_current
              AND extraction.schema_name <> 'document_classification'
              AND extraction.status IN ('completed', 'accepted')
              AND extraction.normalized_json <> '{{}}'::jsonb
          ) AS has_extraction,
          EXISTS (
            SELECT 1 FROM document_chunks chunk
            WHERE chunk.document_id = d.id AND btrim(chunk.bm25_text) <> ''
          ) AS text_searchable,
          EXISTS (
            SELECT 1 FROM document_assets preview
            WHERE preview.document_id = d.id AND preview.is_current
              AND preview.asset_role = 'thumbnail'
          ) AS preview_ready,
          (d.review_status IN ('user_confirmed', 'user_corrected')) AS human_reviewed
      ) browse
    """).format(classification_sql=classification_state_sql())


def browse_count_columns_sql() -> sql.Composed:
    states = [state.value for state in InboxState] + ["preview_ready", "human_reviewed"]
    return sql.SQL(",\n").join(
        sql.SQL("count(*) FILTER (WHERE browse.{field}) AS {field}").format(
            field=sql.Identifier(state)
        )
        for state in states
    )


def browse_membership_sql(state: InboxState) -> sql.Composed:
    return sql.SQL("browse.{}").format(sql.Identifier(InboxState(state).value))


def browse_order_sql(order: DocumentSort) -> sql.SQL:
    # No request-provided SQL fragments or column names are interpolated. C
    # collation makes title ordering deterministic across database locales.
    choices = {
        DocumentSort.UPLOADED_DESC: sql.SQL("d.created_at DESC NULLS LAST, d.id DESC"),
        DocumentSort.UPLOADED_ASC: sql.SQL("d.created_at ASC NULLS LAST, d.id ASC"),
        DocumentSort.DOCUMENT_DATE_DESC: sql.SQL("d.document_date DESC NULLS LAST, d.id DESC"),
        DocumentSort.DOCUMENT_DATE_ASC: sql.SQL("d.document_date ASC NULLS LAST, d.id ASC"),
        DocumentSort.TITLE_ASC: sql.SQL('lower(d.title COLLATE "C") ASC NULLS LAST, d.id ASC'),
        DocumentSort.TITLE_DESC: sql.SQL('lower(d.title COLLATE "C") DESC NULLS LAST, d.id DESC'),
    }
    return choices[DocumentSort(order)]

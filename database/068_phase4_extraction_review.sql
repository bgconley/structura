SET search_path TO structura, public;

CREATE OR REPLACE FUNCTION refresh_document_chunk_projection(target_document_id uuid)
RETURNS void
LANGUAGE SQL
AS $$
  UPDATE document_chunks c
  SET household_id = d.household_id,
      document_family_snapshot = d.document_family,
      document_subtype_snapshot = d.document_subtype,
      document_date_snapshot = d.document_date,
      sensitivity_snapshot = d.sensitivity,
      counterparty_snapshot = d.counterparty_display,
      primary_folder_id = d.primary_folder_id,
      bm25_text = concat_ws(
        E'\n',
        c.text_content,
        d.title,
        d.original_filename,
        d.counterparty_display,
        (
          SELECT string_agg(
            concat(cf.field_path, ': ', COALESCE(cf.text_value, cf.numeric_value::text, cf.date_value::text)),
            E'\n'
            ORDER BY cf.field_path, cf.ordinal
          )
          FROM canonical_fields cf
          WHERE cf.document_id = d.id
            AND cf.review_status IN ('auto_accepted', 'user_confirmed', 'user_corrected')
        )
      ),
      updated_at = now()
  FROM documents d
  WHERE c.document_id = d.id
    AND d.id = target_document_id;
$$;

CREATE INDEX IF NOT EXISTS review_tasks_document_status_idx
  ON review_tasks (document_id, status, priority DESC, created_at);

CREATE INDEX IF NOT EXISTS canonical_fact_history_document_created_idx
  ON canonical_fact_history (document_id, created_at DESC);

CREATE INDEX IF NOT EXISTS document_amounts_document_role_created_idx
  ON document_amounts (document_id, amount_role, created_at DESC);

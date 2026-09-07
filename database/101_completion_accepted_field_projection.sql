-- Human field decisions govern accepted selection independently from stale row status.
-- Canonical line-item selection deliberately retains its existing policy.
-- acceptedFactRevision hashes accepted_fields.v1 only; native fact_basis stays
-- not_collected until its complete field/line-item/metadata inputs are coordinated.
SET search_path TO structura, public;

CREATE VIEW selected_canonical_fields AS
SELECT cf.*
FROM canonical_fields cf
LEFT JOIN canonical_field_decisions fd
  ON fd.document_id=cf.document_id AND fd.field_path=cf.field_path AND fd.ordinal=cf.ordinal
LEFT JOIN canonical_field_path_guards pg
  ON pg.document_id=cf.document_id AND pg.field_path=cf.field_path AND pg.status='active'
WHERE cf.review_status IN ('auto_accepted','user_confirmed','user_corrected')
  AND (
    (fd.id IS NOT NULL AND fd.disposition IN ('confirmed','corrected') AND fd.canonical_field_id=cf.id)
    OR (fd.id IS NULL AND pg.id IS NULL)
  );

CREATE FUNCTION refresh_document_chunk_projection_snapshot(target_document_id uuid)
RETURNS jsonb
LANGUAGE plpgsql
AS $$
DECLARE indexed_metadata jsonb;
BEGIN
  -- Serialize every legacy lexical caller with canonical decisions and rollups.
  PERFORM 1 FROM documents WHERE id=target_document_id FOR UPDATE;
  -- Materialize metadata once: concurrent tag/folder label changes cannot make
  -- the returned fingerprint describe different inputs from the lexical write.
  WITH source AS MATERIALIZED (
    SELECT d.*,
      COALESCE((SELECT jsonb_agg(jsonb_build_object('id',t.id,'name',t.name) ORDER BY t.id)
        FROM document_tags dt JOIN tags t ON t.id=dt.tag_id
        WHERE dt.document_id=d.id),'[]'::jsonb) AS tags,
      (SELECT string_agg(t.name::text, E'\n' ORDER BY lower(t.name::text), t.id)
        FROM document_tags dt JOIN tags t ON t.id=dt.tag_id
        WHERE dt.document_id=d.id) AS tag_text,
      COALESCE((SELECT jsonb_agg(jsonb_build_object('id',f.id,'name',f.name,'path',f.path_cache,
        'primary',fm.is_primary) ORDER BY f.id)
        FROM document_folder_memberships fm JOIN folders f ON f.id=fm.folder_id
        WHERE fm.document_id=d.id),'[]'::jsonb) AS folders,
      (SELECT string_agg(COALESCE(f.path_cache, '/' || f.name), E'\n'
        ORDER BY fm.is_primary DESC,f.name,f.id)
        FROM document_folder_memberships fm JOIN folders f ON f.id=fm.folder_id
        WHERE fm.document_id=d.id) AS folder_text,
      COALESCE((SELECT jsonb_agg(jsonb_build_object('role',a.amount_role,'amount',a.amount::text,
        'currency',a.currency_code,'source',a.metadata_json)
        ORDER BY a.amount_role,a.amount,a.currency_code,a.metadata_json::text)
        FROM document_amounts a WHERE a.document_id=d.id),'[]'::jsonb) AS amounts
    FROM documents d WHERE d.id=target_document_id
  ), refreshed AS (
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
        c.markdown_content,
        d.title,
        d.original_filename,
        d.counterparty_display,
        d.filing_notes,
        d.tag_text,
        d.folder_text,
        (
          SELECT string_agg(
            concat(cf.field_path, ': ', COALESCE(cf.text_value, cf.integer_value::text, cf.numeric_value::text, cf.boolean_value::text, cf.date_value::text, cf.timestamp_value::text, cf.json_value::text)),
            E'\n'
            ORDER BY cf.field_path, cf.ordinal
          )
          FROM selected_canonical_fields cf
          WHERE cf.document_id = d.id
            AND cf.review_status IN ('auto_accepted', 'user_confirmed', 'user_corrected')
        ),
        (
          SELECT string_agg(
            concat_ws(' ', cli.line_item_type::text, cli.description, cli.net_amount::text, cli.currency_code),
            E'\n'
            ORDER BY cli.line_item_type, cli.ordinal
          )
          FROM canonical_line_items cli
          WHERE cli.document_id = d.id
            AND cli.review_status IN ('auto_accepted', 'user_confirmed', 'user_corrected')
        )
      ),
      updated_at = now()
  FROM source d
  WHERE c.document_id = d.id
  RETURNING c.id
  )
  SELECT jsonb_build_object(
    'title',d.title,'original_filename',d.original_filename,'filing_notes',d.filing_notes,
    'document_family',d.document_family,'document_subtype',d.document_subtype,
    'document_date',d.document_date,'counterparty_display',d.counterparty_display,
    'sensitivity',d.sensitivity,'primary_folder_id',d.primary_folder_id,
    'tags',d.tags,'folders',d.folders,'amounts',d.amounts
  ) INTO indexed_metadata FROM source d;
  RETURN indexed_metadata;
END;
$$;

-- Retain the existing entry point and return type for historical callers.
CREATE OR REPLACE FUNCTION refresh_document_chunk_projection(target_document_id uuid)
RETURNS void LANGUAGE plpgsql AS $$
BEGIN
  PERFORM refresh_document_chunk_projection_snapshot(target_document_id);
END;
$$;

SET search_path TO structura, public;

CREATE OR REPLACE FUNCTION _safe_snippet(source_text text, query_text text)
RETURNS text
LANGUAGE SQL
IMMUTABLE
AS $$
  SELECT CASE
    WHEN source_text IS NULL OR length(source_text) = 0 THEN NULL
    WHEN query_text IS NULL OR length(query_text) = 0 THEN left(source_text, 240)
    ELSE left(source_text, 240)
  END;
$$;

CREATE OR REPLACE FUNCTION _folder_paths(target_document_id uuid)
RETURNS text[]
LANGUAGE SQL
STABLE
AS $$
  SELECT COALESCE(
    (
      SELECT array_agg(
        COALESCE(f.path_cache, '/' || f.name)
        ORDER BY dfm.is_primary DESC, COALESCE(f.path_cache, '/' || f.name), f.name
      )
      FROM document_folder_memberships dfm
      JOIN folders f ON f.id = dfm.folder_id
      WHERE dfm.document_id = target_document_id
    ),
    ARRAY[]::text[]
  );
$$;

CREATE OR REPLACE FUNCTION _tag_names(target_document_id uuid)
RETURNS text[]
LANGUAGE SQL
STABLE
AS $$
  SELECT COALESCE(
    (
      SELECT array_agg(t.name::text ORDER BY lower(t.name::text), t.id)
      FROM document_tags dt
      JOIN tags t ON t.id = dt.tag_id
      WHERE dt.document_id = target_document_id
    ),
    ARRAY[]::text[]
  );
$$;

CREATE OR REPLACE FUNCTION document_matches_saved_query(
  target_document_id uuid,
  saved_query jsonb
)
RETURNS boolean
LANGUAGE SQL
STABLE
AS $$
  SELECT EXISTS (
    SELECT 1
    FROM documents d
    WHERE d.id = target_document_id
      AND (
        NOT (saved_query ? 'review_status')
        OR d.review_status::text IN (
          SELECT jsonb_array_elements_text(saved_query -> 'review_status')
        )
      )
      AND (
        NOT (saved_query ? 'document_family')
        OR d.document_family::text IN (
          SELECT jsonb_array_elements_text(saved_query -> 'document_family')
        )
      )
      AND (
        NOT (saved_query ? 'families')
        OR d.document_family::text IN (
          SELECT jsonb_array_elements_text(saved_query -> 'families')
        )
      )
      AND (
        NOT (saved_query ? 'tag_names')
        OR EXISTS (
          SELECT 1
          FROM document_tags dt
          JOIN tags t ON t.id = dt.tag_id
          WHERE dt.document_id = d.id
            AND lower(t.name::text) IN (
              SELECT lower(tag_name.value)
              FROM jsonb_array_elements_text(saved_query -> 'tag_names') AS tag_name(value)
            )
        )
      )
      AND (
        COALESCE((saved_query ->> 'open_review_tasks')::boolean, false) = false
        OR EXISTS (
          SELECT 1
          FROM review_tasks rt
          WHERE rt.document_id = d.id
            AND rt.status IN ('open', 'in_progress')
        )
      )
  );
$$;

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
        c.markdown_content,
        d.title,
        d.original_filename,
        d.counterparty_display,
        d.filing_notes,
        (
          SELECT string_agg(t.name::text, E'\n' ORDER BY lower(t.name::text), t.id)
          FROM document_tags dt
          JOIN tags t ON t.id = dt.tag_id
          WHERE dt.document_id = d.id
        ),
        (
          SELECT string_agg(COALESCE(f.path_cache, '/' || f.name), E'\n' ORDER BY dfm.is_primary DESC, f.name)
          FROM document_folder_memberships dfm
          JOIN folders f ON f.id = dfm.folder_id
          WHERE dfm.document_id = d.id
        ),
        (
          SELECT string_agg(
            concat(cf.field_path, ': ', COALESCE(cf.text_value, cf.numeric_value::text, cf.date_value::text, cf.timestamp_value::text, cf.json_value::text)),
            E'\n'
            ORDER BY cf.field_path, cf.ordinal
          )
          FROM canonical_fields cf
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
  FROM documents d
  WHERE c.document_id = d.id
    AND d.id = target_document_id;
$$;

DROP INDEX IF EXISTS document_chunks_bm25_idx;
CREATE INDEX IF NOT EXISTS document_chunks_bm25_idx
  ON document_chunks
  USING bm25 (
    id,
    heading_path,
    text_content,
    markdown_content,
    bm25_text,
    page_start,
    page_end,
    metadata_json
  )
  WITH (key_field='id');

CREATE INDEX IF NOT EXISTS document_chunks_phase5_filter_idx
  ON document_chunks (
    household_id,
    document_family_snapshot,
    document_date_snapshot,
    sensitivity_snapshot,
    primary_folder_id,
    document_id
  );

CREATE INDEX IF NOT EXISTS document_chunks_counterparty_snapshot_idx
  ON document_chunks (household_id, lower(counterparty_snapshot));

CREATE UNIQUE INDEX IF NOT EXISTS embeddings_active_text_owner_profile_uniq
  ON embeddings (
    owner_type,
    owner_id,
    modality,
    model_name,
    COALESCE(model_version, ''),
    embedding_dimensions
  )
  WHERE is_active;

ALTER TABLE saved_searches
  ADD COLUMN IF NOT EXISTS household_id uuid REFERENCES households(id) ON DELETE CASCADE,
  ADD COLUMN IF NOT EXISTS owner_user_id uuid REFERENCES users(id) ON DELETE SET NULL,
  ADD COLUMN IF NOT EXISTS description text,
  ADD COLUMN IF NOT EXISTS is_active boolean NOT NULL DEFAULT true;

CREATE UNIQUE INDEX IF NOT EXISTS saved_searches_household_name_uniq
  ON saved_searches (household_id, lower(name))
  WHERE household_id IS NOT NULL AND is_active;

CREATE INDEX IF NOT EXISTS saved_searches_household_created_idx
  ON saved_searches (household_id, created_at DESC)
  WHERE household_id IS NOT NULL AND is_active;

SELECT refresh_document_chunk_projection(d.id)
FROM documents d
WHERE d.deleted_at IS NULL;

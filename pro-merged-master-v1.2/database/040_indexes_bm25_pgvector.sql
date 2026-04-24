SET search_path TO structura, public;

-- Core relational indexes
CREATE INDEX documents_family_idx ON documents (document_family);
CREATE INDEX documents_state_idx ON documents (lifecycle_state, review_status);
CREATE INDEX documents_document_date_idx ON documents (document_date DESC NULLS LAST);
CREATE INDEX documents_created_at_idx ON documents (created_at DESC);
CREATE INDEX documents_duplicate_of_idx ON documents (duplicate_of_document_id);

CREATE INDEX document_assets_document_role_idx ON document_assets (document_id, asset_role, page_number);
CREATE UNIQUE INDEX document_assets_one_current_idx
  ON document_assets (document_id, asset_role, COALESCE(page_number, 0))
  WHERE is_current;

CREATE INDEX document_pages_document_page_idx ON document_pages (document_id, page_number);
CREATE INDEX document_elements_page_type_idx ON document_elements (page_id, element_type);
CREATE INDEX document_tables_document_page_idx ON document_tables (document_id, page_id, table_index);
CREATE INDEX document_chunks_document_idx ON document_chunks (document_id, chunk_index);

CREATE UNIQUE INDEX document_extractions_one_current_idx
  ON document_extractions (document_id, schema_name)
  WHERE is_current;

CREATE INDEX document_extractions_schema_idx ON document_extractions (schema_name, schema_version);
CREATE INDEX document_fields_document_field_idx ON document_fields (document_id, field_path);
CREATE INDEX document_amounts_document_role_idx ON document_amounts (document_id, amount_role, amount);
CREATE INDEX document_deadlines_document_due_idx ON document_deadlines (document_id, due_on);
CREATE INDEX document_line_items_document_idx ON document_line_items (document_id, line_item_type, ordinal);

CREATE INDEX document_party_mentions_document_role_idx ON document_party_mentions (document_id, role_name);
CREATE INDEX document_relationships_from_idx ON document_relationships (from_document_id, relationship_type);
CREATE INDEX document_relationships_to_idx ON document_relationships (to_document_id, relationship_type);

CREATE UNIQUE INDEX folders_parent_name_uniq
  ON folders (COALESCE(parent_id, '00000000-0000-0000-0000-000000000000'::uuid), lower(name));

CREATE INDEX document_folder_memberships_folder_idx ON document_folder_memberships (folder_id, document_id);
CREATE INDEX document_tags_tag_idx ON document_tags (tag_id, document_id);

CREATE INDEX review_tasks_status_priority_idx ON review_tasks (status, priority DESC, created_at);
CREATE INDEX review_events_document_idx ON review_events (document_id, created_at DESC);

CREATE INDEX embeddings_owner_idx ON embeddings (owner_type, owner_id);
CREATE INDEX embeddings_document_idx ON embeddings (document_id, modality, model_name);
CREATE INDEX pipeline_jobs_status_type_idx ON pipeline_jobs (status, job_type, scheduled_at);
CREATE INDEX audit_events_document_idx ON audit_events (document_id, created_at DESC);
CREATE INDEX household_memberships_user_idx ON household_memberships (user_id, household_id);
CREATE INDEX sessions_user_expires_idx ON sessions (user_id, revoked_at, expires_at DESC);
CREATE INDEX sessions_household_expires_idx ON sessions (household_id, revoked_at, expires_at DESC);
CREATE INDEX magic_links_user_purpose_idx ON magic_links (user_id, purpose, expires_at DESC);
CREATE INDEX api_tokens_user_expires_idx ON api_tokens (user_id, revoked_at, expires_at DESC);

-- JSONB support
CREATE INDEX documents_metadata_gin_idx ON documents USING gin (metadata_json);
CREATE INDEX document_extractions_normalized_gin_idx ON document_extractions USING gin (normalized_json);
CREATE INDEX document_extractions_validation_gin_idx ON document_extractions USING gin (validation_json);
CREATE INDEX parties_address_gin_idx ON parties USING gin (address_json);

-- Trigram / fuzzy support for names
CREATE INDEX parties_display_name_trgm_idx ON parties USING gin (display_name gin_trgm_ops);
CREATE INDEX parties_normalized_name_trgm_idx ON parties USING gin ((normalized_name::text) gin_trgm_ops);

-- ParadeDB BM25 indexes
-- Only one BM25 index may exist per table. These definitions intentionally include
-- commonly queried, filtered, or sorted columns.
CREATE INDEX documents_bm25_idx
ON documents
USING bm25 (
  id,
  title,
  counterparty_display,
  description,
  filing_notes,
  metadata_json,
  document_date,
  created_at
)
WITH (key_field = 'id')
WHERE deleted_at IS NULL;

CREATE INDEX document_chunks_bm25_idx
ON document_chunks
USING bm25 (
  id,
  heading_path,
  text_content,
  markdown_content,
  page_start,
  page_end,
  metadata_json
)
WITH (key_field = 'id');

CREATE INDEX parties_bm25_idx
ON parties
USING bm25 (
  id,
  display_name,
  normalized_name,
  address_json,
  created_at
)
WITH (key_field = 'id');

-- pgvector HNSW indexes
-- These are partial expression indexes so that multiple embedding dimensions can coexist.
-- Adjust the chosen dimensions if production-serving decisions differ.
CREATE INDEX embeddings_text_1536_hnsw_idx
ON embeddings
USING hnsw ((embedding::vector(1536)) vector_cosine_ops)
WHERE is_active
  AND modality = 'text'
  AND embedding_dimensions = 1536;

CREATE INDEX embeddings_visual_1024_hnsw_idx
ON embeddings
USING hnsw ((embedding::vector(1024)) vector_cosine_ops)
WHERE is_active
  AND modality = 'visual'
  AND embedding_dimensions = 1024;

CREATE INDEX embeddings_mixed_1536_hnsw_idx
ON embeddings
USING hnsw ((embedding::vector(1536)) vector_cosine_ops)
WHERE is_active
  AND modality = 'mixed'
  AND embedding_dimensions = 1536;

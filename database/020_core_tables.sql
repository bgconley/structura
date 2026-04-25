SET search_path TO structura, public;

CREATE TABLE ingest_batches (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  label text,
  source ingestion_source_enum NOT NULL,
  status text NOT NULL DEFAULT 'open',
  file_count_expected integer,
  file_count_received integer NOT NULL DEFAULT 0,
  metadata_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  completed_at timestamptz
);

CREATE TABLE documents (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  batch_id uuid REFERENCES ingest_batches(id) ON DELETE SET NULL,
  stable_slug text UNIQUE,
  title text NOT NULL DEFAULT 'Untitled document',
  original_filename text,
  document_family document_family_enum NOT NULL DEFAULT 'generic',
  document_subtype text,
  family_confidence numeric(5,4),
  lifecycle_state lifecycle_state_enum NOT NULL DEFAULT 'inbox',
  review_status review_status_enum NOT NULL DEFAULT 'unreviewed',
  ingestion_source ingestion_source_enum NOT NULL,
  sensitivity sensitivity_enum NOT NULL DEFAULT 'normal',
  language_code text,
  page_count integer,
  is_digital_native boolean,
  has_handwriting boolean,
  contains_signature boolean,
  original_sha256 char(64),
  canonical_asset_id uuid,
  duplicate_of_document_id uuid REFERENCES documents(id) ON DELETE SET NULL,
  document_date date,
  received_at timestamptz,
  filed_at timestamptz,
  archived_at timestamptz,
  counterparty_display text,
  description text,
  filing_notes text,
  metadata_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  deleted_at timestamptz,
  CHECK (family_confidence IS NULL OR (family_confidence >= 0 AND family_confidence <= 1))
);

CREATE TABLE document_assets (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  document_id uuid NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  asset_role asset_role_enum NOT NULL,
  version_no integer NOT NULL DEFAULT 1,
  page_number integer,
  storage_backend storage_backend_enum NOT NULL DEFAULT 'filesystem',
  uri text NOT NULL,
  mime_type text,
  byte_size bigint,
  sha256 char(64),
  model_name text,
  model_version text,
  is_current boolean NOT NULL DEFAULT true,
  metadata_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CHECK (page_number IS NULL OR page_number > 0)
);

ALTER TABLE documents
  ADD CONSTRAINT documents_canonical_asset_fk
  FOREIGN KEY (canonical_asset_id)
  REFERENCES document_assets(id)
  ON DELETE SET NULL;

CREATE TABLE document_pages (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  document_id uuid NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  page_number integer NOT NULL,
  width_points numeric(12,4),
  height_points numeric(12,4),
  rotation_degrees integer NOT NULL DEFAULT 0,
  has_text_layer boolean,
  text_content text,
  ocr_confidence numeric(5,4),
  image_asset_id uuid REFERENCES document_assets(id) ON DELETE SET NULL,
  thumbnail_asset_id uuid REFERENCES document_assets(id) ON DELETE SET NULL,
  metadata_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (document_id, page_number),
  CHECK (page_number > 0),
  CHECK (ocr_confidence IS NULL OR (ocr_confidence >= 0 AND ocr_confidence <= 1))
);

CREATE TABLE document_elements (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  document_id uuid NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  page_id uuid NOT NULL REFERENCES document_pages(id) ON DELETE CASCADE,
  parent_element_id uuid REFERENCES document_elements(id) ON DELETE SET NULL,
  element_type element_type_enum NOT NULL DEFAULT 'other',
  ordinal integer NOT NULL DEFAULT 1,
  heading_level integer,
  bbox_json jsonb,
  text_content text,
  html_fragment text,
  confidence numeric(5,4),
  source_engine model_source_enum NOT NULL DEFAULT 'docling',
  source_ref text,
  metadata_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CHECK (confidence IS NULL OR (confidence >= 0 AND confidence <= 1))
);

CREATE TABLE document_tables (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  document_id uuid NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  page_id uuid NOT NULL REFERENCES document_pages(id) ON DELETE CASCADE,
  element_id uuid REFERENCES document_elements(id) ON DELETE SET NULL,
  table_index integer NOT NULL DEFAULT 1,
  row_count integer,
  column_count integer,
  table_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  table_html text,
  table_markdown text,
  table_otsl text,
  confidence numeric(5,4),
  source_engine model_source_enum NOT NULL DEFAULT 'docling',
  metadata_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (document_id, page_id, table_index),
  CHECK (confidence IS NULL OR (confidence >= 0 AND confidence <= 1))
);

CREATE TABLE document_chunks (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  document_id uuid NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  chunk_index integer NOT NULL,
  chunk_kind text NOT NULL DEFAULT 'section',
  page_start integer,
  page_end integer,
  heading_path text,
  text_content text NOT NULL,
  markdown_content text,
  token_count integer,
  char_count integer,
  metadata_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (document_id, chunk_index)
);

CREATE TABLE document_extractions (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  document_id uuid NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  schema_name text NOT NULL,
  schema_version text NOT NULL,
  status extraction_status_enum NOT NULL DEFAULT 'pending',
  is_current boolean NOT NULL DEFAULT true,
  source_engine model_source_enum NOT NULL,
  model_name text,
  model_version text,
  prompt_version text,
  raw_output_asset_id uuid REFERENCES document_assets(id) ON DELETE SET NULL,
  normalized_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  validation_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  confidence numeric(5,4),
  review_status review_status_enum NOT NULL DEFAULT 'unreviewed',
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CHECK (confidence IS NULL OR (confidence >= 0 AND confidence <= 1))
);

CREATE TABLE document_fields (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  document_id uuid NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  extraction_id uuid NOT NULL REFERENCES document_extractions(id) ON DELETE CASCADE,
  field_path text NOT NULL,
  field_label text,
  ordinal integer NOT NULL DEFAULT 1,
  value_type field_value_type_enum NOT NULL,
  text_value text,
  integer_value bigint,
  numeric_value numeric(18,4),
  boolean_value boolean,
  date_value date,
  timestamp_value timestamptz,
  json_value jsonb,
  currency_code char(3),
  confidence numeric(5,4),
  evidence_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  metadata_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CHECK (ordinal > 0),
  CHECK (confidence IS NULL OR (confidence >= 0 AND confidence <= 1))
);

CREATE TABLE document_amounts (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  document_id uuid NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  extraction_id uuid REFERENCES document_extractions(id) ON DELETE CASCADE,
  amount_role text NOT NULL,
  amount numeric(18,4) NOT NULL,
  currency_code char(3),
  confidence numeric(5,4),
  evidence_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  metadata_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CHECK (confidence IS NULL OR (confidence >= 0 AND confidence <= 1))
);

CREATE TABLE document_deadlines (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  document_id uuid NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  extraction_id uuid REFERENCES document_extractions(id) ON DELETE CASCADE,
  deadline_type deadline_type_enum NOT NULL,
  due_on date NOT NULL,
  remind_from date,
  status text NOT NULL DEFAULT 'open',
  confidence numeric(5,4),
  evidence_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  metadata_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CHECK (confidence IS NULL OR (confidence >= 0 AND confidence <= 1))
);

CREATE TABLE document_line_items (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  document_id uuid NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  extraction_id uuid REFERENCES document_extractions(id) ON DELETE CASCADE,
  line_item_type line_item_type_enum NOT NULL DEFAULT 'generic',
  ordinal integer NOT NULL DEFAULT 1,
  code text,
  code_system text,
  service_date date,
  description text,
  quantity numeric(18,4),
  unit text,
  unit_price numeric(18,4),
  gross_amount numeric(18,4),
  discount_amount numeric(18,4),
  tax_amount numeric(18,4),
  net_amount numeric(18,4),
  currency_code char(3),
  category_hint text,
  confidence numeric(5,4),
  evidence_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  metadata_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CHECK (ordinal > 0),
  CHECK (confidence IS NULL OR (confidence >= 0 AND confidence <= 1))
);

CREATE TABLE parties (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  party_type party_type_enum NOT NULL DEFAULT 'organization',
  display_name text NOT NULL,
  normalized_name citext,
  primary_email citext,
  primary_phone text,
  tax_id text,
  member_id text,
  address_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  metadata_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE document_party_mentions (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  document_id uuid NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  extraction_id uuid REFERENCES document_extractions(id) ON DELETE CASCADE,
  party_id uuid REFERENCES parties(id) ON DELETE SET NULL,
  party_type party_type_enum,
  role_name text NOT NULL,
  display_name text,
  identifiers_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  evidence_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  confidence numeric(5,4),
  metadata_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CHECK (confidence IS NULL OR (confidence >= 0 AND confidence <= 1))
);

CREATE TABLE document_relationships (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  from_document_id uuid NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  to_document_id uuid NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  relationship_type relationship_type_enum NOT NULL,
  source_engine model_source_enum NOT NULL DEFAULT 'system',
  confidence numeric(5,4),
  evidence_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  metadata_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CHECK (from_document_id <> to_document_id),
  CHECK (confidence IS NULL OR (confidence >= 0 AND confidence <= 1))
);

CREATE TABLE folders (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  parent_id uuid REFERENCES folders(id) ON DELETE CASCADE,
  folder_kind folder_kind_enum NOT NULL DEFAULT 'manual',
  name text NOT NULL,
  description text,
  path_cache text,
  saved_query_json jsonb,
  sort_order integer NOT NULL DEFAULT 100,
  is_system boolean NOT NULL DEFAULT false,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE document_folder_memberships (
  document_id uuid NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  folder_id uuid NOT NULL REFERENCES folders(id) ON DELETE CASCADE,
  is_primary boolean NOT NULL DEFAULT false,
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (document_id, folder_id)
);

CREATE TABLE tags (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  name citext NOT NULL,
  color_hex text,
  description text,
  is_system boolean NOT NULL DEFAULT false,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (name)
);

CREATE TABLE document_tags (
  document_id uuid NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  tag_id uuid NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (document_id, tag_id)
);

CREATE TABLE saved_searches (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  name text NOT NULL,
  query_text text,
  filters_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  sort_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  is_system boolean NOT NULL DEFAULT false,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE analysis_notes (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  note_type analysis_note_type_enum NOT NULL,
  title text NOT NULL,
  user_prompt text,
  model_name text,
  model_version text,
  prompt_version text,
  answer_markdown text,
  answer_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  citations_json jsonb NOT NULL DEFAULT '[]'::jsonb,
  document_scope_json jsonb NOT NULL DEFAULT '[]'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE review_tasks (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  document_id uuid NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  extraction_id uuid REFERENCES document_extractions(id) ON DELETE CASCADE,
  task_type text NOT NULL,
  status review_task_status_enum NOT NULL DEFAULT 'open',
  priority smallint NOT NULL DEFAULT 50,
  reason text,
  assigned_to text,
  due_at timestamptz,
  metadata_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CHECK (priority >= 0 AND priority <= 100)
);

CREATE TABLE review_events (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  review_task_id uuid REFERENCES review_tasks(id) ON DELETE SET NULL,
  document_id uuid NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  extraction_id uuid REFERENCES document_extractions(id) ON DELETE SET NULL,
  field_path text,
  action text NOT NULL,
  old_value_json jsonb,
  new_value_json jsonb,
  reason text,
  actor_label text,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE embeddings (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  owner_type embedding_owner_type_enum NOT NULL,
  owner_id uuid NOT NULL,
  document_id uuid REFERENCES documents(id) ON DELETE CASCADE,
  model_name text NOT NULL,
  model_version text,
  modality modality_enum NOT NULL,
  embedding_dimensions integer NOT NULL,
  embedding vector NOT NULL,
  is_active boolean NOT NULL DEFAULT true,
  metadata_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CHECK (embedding_dimensions > 0)
);

CREATE TABLE pipeline_jobs (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  job_type job_type_enum NOT NULL,
  status job_status_enum NOT NULL DEFAULT 'queued',
  document_id uuid REFERENCES documents(id) ON DELETE CASCADE,
  batch_id uuid REFERENCES ingest_batches(id) ON DELETE SET NULL,
  parent_job_id uuid REFERENCES pipeline_jobs(id) ON DELETE SET NULL,
  priority smallint NOT NULL DEFAULT 50,
  queue_name text NOT NULL DEFAULT 'default',
  worker_name text,
  lease_expires_at timestamptz,
  scheduled_at timestamptz NOT NULL DEFAULT now(),
  started_at timestamptz,
  finished_at timestamptz,
  attempt_count integer NOT NULL DEFAULT 0,
  max_attempts integer NOT NULL DEFAULT 5,
  payload_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  result_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  error_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CHECK (priority >= 0 AND priority <= 100),
  CHECK (attempt_count >= 0),
  CHECK (max_attempts > 0)
);

CREATE TABLE audit_events (
  id bigserial PRIMARY KEY,
  entity_type text NOT NULL,
  entity_id uuid,
  document_id uuid REFERENCES documents(id) ON DELETE SET NULL,
  event_name text NOT NULL,
  actor_label text,
  payload_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);

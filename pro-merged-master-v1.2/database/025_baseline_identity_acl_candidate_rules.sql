-- 025_baseline_identity_acl_candidate_rules.sql
-- Normative v1.3 baseline extension.
--
-- Purpose:
--   1. Add household/auth/ACL foundations.
--   2. Add candidate-vs-canonical extraction tables.
--   3. Add contacts, filing rules, watched folders, status, and evaluation tables.
--   4. Add search projection columns for filter-aware retrieval.
--
-- This file is part of the v1.3 baseline apply order and should be run after
-- 020_core_tables.sql and before constraints, triggers, and indexes.

SET search_path TO structura, public;

-- Optional extensions. Enable only if available in the selected Postgres image.
-- CREATE EXTENSION IF NOT EXISTS pgmq;
-- CREATE EXTENSION IF NOT EXISTS pg_cron;
CREATE EXTENSION IF NOT EXISTS ltree;

-- ---------------------------------------------------------------------------
-- 1. Household, users, password credentials, passkeys, sessions, API tokens
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS households (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  name text NOT NULL,
  slug text UNIQUE,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS users (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  email citext UNIQUE NOT NULL,
  display_name text NOT NULL,
  is_disabled boolean NOT NULL DEFAULT false,
  is_system boolean NOT NULL DEFAULT false,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  last_seen_at timestamptz
);

CREATE TABLE IF NOT EXISTS household_memberships (
  household_id uuid NOT NULL REFERENCES households(id) ON DELETE CASCADE,
  user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  role text NOT NULL DEFAULT 'member',
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (household_id, user_id),
  CHECK (role IN ('owner', 'admin', 'member', 'viewer'))
);

CREATE TABLE IF NOT EXISTS webauthn_credentials (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  credential_id bytea NOT NULL UNIQUE,
  public_key bytea NOT NULL,
  sign_count bigint NOT NULL DEFAULT 0,
  transports text[],
  label text,
  last_used_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS user_password_credentials (
  user_id uuid PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
  password_hash text NOT NULL,
  hash_algorithm text NOT NULL DEFAULT 'argon2id',
  params_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  must_rotate boolean NOT NULL DEFAULT false,
  last_used_at timestamptz,
  disabled_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CHECK (hash_algorithm IN ('argon2id'))
);

CREATE TABLE IF NOT EXISTS sessions (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  household_id uuid REFERENCES households(id) ON DELETE SET NULL,
  auth_method auth_method_enum NOT NULL,
  token_hash text NOT NULL UNIQUE,
  user_agent text,
  ip_hint inet,
  expires_at timestamptz NOT NULL,
  revoked_at timestamptz,
  last_used_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS magic_links (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id uuid REFERENCES users(id) ON DELETE CASCADE,
  household_id uuid REFERENCES households(id) ON DELETE CASCADE,
  purpose text NOT NULL,
  token_hash text NOT NULL UNIQUE,
  used_at timestamptz,
  expires_at timestamptz NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  CHECK (purpose IN ('invite', 'recovery', 'bootstrap'))
);

CREATE TABLE IF NOT EXISTS api_tokens (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  household_id uuid REFERENCES households(id) ON DELETE CASCADE,
  label text NOT NULL,
  token_hash text NOT NULL UNIQUE,
  scopes text[] NOT NULL DEFAULT ARRAY[]::text[],
  last_used_at timestamptz,
  expires_at timestamptz,
  revoked_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE documents ADD COLUMN IF NOT EXISTS household_id uuid REFERENCES households(id) ON DELETE RESTRICT;
ALTER TABLE documents ADD COLUMN IF NOT EXISTS owner_user_id uuid REFERENCES users(id) ON DELETE SET NULL;
ALTER TABLE documents ADD COLUMN IF NOT EXISTS primary_folder_id uuid REFERENCES folders(id) ON DELETE SET NULL;
ALTER TABLE documents ADD COLUMN IF NOT EXISTS acl_mode text NOT NULL DEFAULT 'household';
ALTER TABLE documents ADD CONSTRAINT documents_acl_mode_check CHECK (acl_mode IN ('private', 'household', 'custom')) NOT VALID;
ALTER TABLE documents ADD CONSTRAINT documents_active_household_check CHECK (deleted_at IS NOT NULL OR household_id IS NOT NULL) NOT VALID;

ALTER TABLE folders ADD COLUMN IF NOT EXISTS household_id uuid REFERENCES households(id) ON DELETE CASCADE;
ALTER TABLE folders ADD COLUMN IF NOT EXISTS owner_user_id uuid REFERENCES users(id) ON DELETE SET NULL;
ALTER TABLE folders ADD COLUMN IF NOT EXISTS acl_mode text NOT NULL DEFAULT 'household';
ALTER TABLE folders ADD COLUMN IF NOT EXISTS path_ltree ltree;
ALTER TABLE folders ADD CONSTRAINT folders_acl_mode_check CHECK (acl_mode IN ('private', 'household', 'custom')) NOT VALID;

CREATE TABLE IF NOT EXISTS folder_acl (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  folder_id uuid NOT NULL REFERENCES folders(id) ON DELETE CASCADE,
  principal_type text NOT NULL,
  principal_id uuid NOT NULL,
  permission text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (folder_id, principal_type, principal_id, permission),
  CHECK (principal_type IN ('user', 'household', 'role')),
  CHECK (permission IN ('read', 'write', 'admin'))
);

-- ---------------------------------------------------------------------------
-- 2. Candidate-vs-canonical extraction model
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS field_candidates (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  document_id uuid NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  extraction_id uuid REFERENCES document_extractions(id) ON DELETE CASCADE,
  field_path text NOT NULL,
  ordinal integer NOT NULL DEFAULT 1,
  source_engine model_source_enum NOT NULL,
  source_ref text,
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
  authority_weight numeric(6,3) NOT NULL DEFAULT 0,
  evidence_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  validation_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  status text NOT NULL DEFAULT 'proposed',
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CHECK (ordinal > 0),
  CHECK (confidence IS NULL OR (confidence >= 0 AND confidence <= 1)),
  CHECK (status IN ('proposed', 'promoted', 'rejected', 'superseded', 'needs_review'))
);

CREATE TABLE IF NOT EXISTS canonical_fields (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  document_id uuid NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  selected_candidate_id uuid REFERENCES field_candidates(id) ON DELETE SET NULL,
  field_path text NOT NULL,
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
  source_kind text NOT NULL DEFAULT 'system',
  review_status review_status_enum NOT NULL DEFAULT 'auto_accepted',
  evidence_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  validation_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  accepted_by_user_id uuid REFERENCES users(id) ON DELETE SET NULL,
  accepted_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (document_id, field_path, ordinal),
  CHECK (ordinal > 0),
  CHECK (source_kind IN ('candidate', 'validator', 'human', 'system'))
);

CREATE TABLE IF NOT EXISTS line_item_candidates (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  document_id uuid NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  extraction_id uuid REFERENCES document_extractions(id) ON DELETE CASCADE,
  source_engine model_source_enum NOT NULL,
  line_item_type line_item_type_enum NOT NULL DEFAULT 'generic',
  candidate_group text,
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
  authority_weight numeric(6,3) NOT NULL DEFAULT 0,
  evidence_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  validation_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  status text NOT NULL DEFAULT 'proposed',
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CHECK (ordinal > 0),
  CHECK (confidence IS NULL OR (confidence >= 0 AND confidence <= 1))
);

CREATE TABLE IF NOT EXISTS canonical_line_items (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  document_id uuid NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  selected_candidate_id uuid REFERENCES line_item_candidates(id) ON DELETE SET NULL,
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
  source_kind text NOT NULL DEFAULT 'system',
  review_status review_status_enum NOT NULL DEFAULT 'auto_accepted',
  evidence_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  validation_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  accepted_by_user_id uuid REFERENCES users(id) ON DELETE SET NULL,
  accepted_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (document_id, line_item_type, ordinal),
  CHECK (ordinal > 0),
  CHECK (source_kind IN ('candidate', 'validator', 'human', 'system'))
);

CREATE TABLE IF NOT EXISTS canonical_fact_history (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  document_id uuid NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  field_path text,
  canonical_field_id uuid REFERENCES canonical_fields(id) ON DELETE SET NULL,
  canonical_line_item_id uuid REFERENCES canonical_line_items(id) ON DELETE SET NULL,
  action text NOT NULL,
  old_value_json jsonb,
  new_value_json jsonb,
  actor_user_id uuid REFERENCES users(id) ON DELETE SET NULL,
  reason text,
  created_at timestamptz NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------------------
-- 3. Contacts, rules, and watched folders
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS contacts (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  household_id uuid REFERENCES households(id) ON DELETE CASCADE,
  contact_type text NOT NULL DEFAULT 'organization',
  display_name text NOT NULL,
  normalized_name citext,
  primary_email citext,
  primary_phone text,
  address_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  identifiers_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  metadata_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CHECK (contact_type IN ('person', 'organization', 'merchant', 'provider', 'payer', 'insurer', 'law_firm', 'government', 'utility', 'vendor', 'other'))
);

CREATE TABLE IF NOT EXISTS contact_aliases (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  contact_id uuid NOT NULL REFERENCES contacts(id) ON DELETE CASCADE,
  alias citext NOT NULL,
  source text,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (contact_id, alias)
);

CREATE TABLE IF NOT EXISTS document_contacts (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  document_id uuid NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  contact_id uuid NOT NULL REFERENCES contacts(id) ON DELETE CASCADE,
  role_name text NOT NULL,
  evidence_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  confidence numeric(5,4),
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (document_id, contact_id, role_name),
  CHECK (confidence IS NULL OR (confidence >= 0 AND confidence <= 1))
);

CREATE TABLE IF NOT EXISTS filing_rules (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  household_id uuid REFERENCES households(id) ON DELETE CASCADE,
  name text NOT NULL,
  description text,
  enabled boolean NOT NULL DEFAULT true,
  priority smallint NOT NULL DEFAULT 50,
  conditions_json jsonb NOT NULL DEFAULT '[]'::jsonb,
  actions_json jsonb NOT NULL DEFAULT '[]'::jsonb,
  review_required boolean NOT NULL DEFAULT true,
  created_by_user_id uuid REFERENCES users(id) ON DELETE SET NULL,
  last_run_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CHECK (priority >= 0 AND priority <= 100)
);

CREATE TABLE IF NOT EXISTS filing_rule_runs (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  rule_id uuid NOT NULL REFERENCES filing_rules(id) ON DELETE CASCADE,
  document_id uuid REFERENCES documents(id) ON DELETE CASCADE,
  mode text NOT NULL DEFAULT 'dry_run',
  matched boolean NOT NULL DEFAULT false,
  proposed_actions_json jsonb NOT NULL DEFAULT '[]'::jsonb,
  applied_actions_json jsonb NOT NULL DEFAULT '[]'::jsonb,
  explanation_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  CHECK (mode IN ('dry_run', 'suggest', 'apply'))
);

CREATE TABLE IF NOT EXISTS watched_folders (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  household_id uuid REFERENCES households(id) ON DELETE CASCADE,
  path text NOT NULL,
  enabled boolean NOT NULL DEFAULT true,
  policy_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  last_scan_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (household_id, path)
);

-- ---------------------------------------------------------------------------
-- 4. Search projection enhancements
-- ---------------------------------------------------------------------------

ALTER TABLE document_chunks ADD COLUMN IF NOT EXISTS household_id uuid REFERENCES households(id) ON DELETE CASCADE;
ALTER TABLE document_chunks ADD COLUMN IF NOT EXISTS document_family_snapshot document_family_enum;
ALTER TABLE document_chunks ADD COLUMN IF NOT EXISTS document_subtype_snapshot text;
ALTER TABLE document_chunks ADD COLUMN IF NOT EXISTS document_date_snapshot date;
ALTER TABLE document_chunks ADD COLUMN IF NOT EXISTS sensitivity_snapshot sensitivity_enum;
ALTER TABLE document_chunks ADD COLUMN IF NOT EXISTS counterparty_snapshot text;
ALTER TABLE document_chunks ADD COLUMN IF NOT EXISTS primary_folder_id uuid REFERENCES folders(id) ON DELETE SET NULL;
ALTER TABLE document_chunks ADD COLUMN IF NOT EXISTS bm25_text text;

-- ---------------------------------------------------------------------------
-- 5. Service health and evaluation
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS service_health_snapshots (
  id bigserial PRIMARY KEY,
  service_name text NOT NULL,
  status text NOT NULL,
  metrics_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  checked_at timestamptz NOT NULL DEFAULT now(),
  CHECK (status IN ('ok', 'degraded', 'down', 'unknown'))
);

CREATE TABLE IF NOT EXISTS evaluation_runs (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  label text NOT NULL,
  corpus_name text NOT NULL,
  corpus_version text,
  run_type text NOT NULL,
  status text NOT NULL DEFAULT 'queued',
  metrics_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  failures_json jsonb NOT NULL DEFAULT '[]'::jsonb,
  started_at timestamptz,
  finished_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  CHECK (run_type IN ('extraction', 'search', 'pipeline', 'end_to_end')),
  CHECK (status IN ('queued', 'running', 'completed', 'failed'))
);

-- ---------------------------------------------------------------------------
-- 6. Indexes
-- ---------------------------------------------------------------------------

CREATE INDEX IF NOT EXISTS documents_household_idx ON documents (household_id, lifecycle_state, review_status);
CREATE INDEX IF NOT EXISTS documents_owner_idx ON documents (owner_user_id);
CREATE INDEX IF NOT EXISTS folders_household_idx ON folders (household_id, parent_id);
CREATE INDEX IF NOT EXISTS folders_path_ltree_idx ON folders USING gist (path_ltree);
CREATE INDEX IF NOT EXISTS folder_acl_principal_idx ON folder_acl (principal_type, principal_id, permission);

CREATE INDEX IF NOT EXISTS field_candidates_document_field_idx ON field_candidates (document_id, field_path, status);
CREATE INDEX IF NOT EXISTS field_candidates_extraction_idx ON field_candidates (extraction_id);
CREATE INDEX IF NOT EXISTS canonical_fields_document_field_idx ON canonical_fields (document_id, field_path);
CREATE INDEX IF NOT EXISTS line_item_candidates_document_idx ON line_item_candidates (document_id, line_item_type, status);
CREATE INDEX IF NOT EXISTS canonical_line_items_document_idx ON canonical_line_items (document_id, line_item_type, ordinal);

CREATE INDEX IF NOT EXISTS contacts_household_name_idx ON contacts (household_id, normalized_name);
CREATE INDEX IF NOT EXISTS contacts_display_name_trgm_idx ON contacts USING gin (display_name gin_trgm_ops);
CREATE INDEX IF NOT EXISTS document_contacts_document_idx ON document_contacts (document_id, role_name);
CREATE INDEX IF NOT EXISTS filing_rules_household_enabled_idx ON filing_rules (household_id, enabled, priority DESC);
CREATE INDEX IF NOT EXISTS watched_folders_household_idx ON watched_folders (household_id, enabled);
CREATE INDEX IF NOT EXISTS document_chunks_filter_projection_idx
  ON document_chunks (household_id, document_family_snapshot, document_date_snapshot, sensitivity_snapshot);

-- ---------------------------------------------------------------------------
-- 7. Optional PGMQ bootstrap for the default transport profile
-- ---------------------------------------------------------------------------

-- If the selected database image includes PGMQ, create queues in a separate
-- migration or bootstrap script:
--
--   CREATE EXTENSION IF NOT EXISTS pgmq;
--   SELECT pgmq.create('structura_pipeline');
--   SELECT pgmq.create('structura_deadletter');
--
-- Keep `pipeline_jobs` as the application ledger even when PGMQ is enabled.

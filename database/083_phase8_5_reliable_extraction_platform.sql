SET search_path TO structura, public;

CREATE TABLE IF NOT EXISTS semantic_extraction_plans (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  document_id uuid NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  semantic_annotation_id uuid NOT NULL REFERENCES document_semantic_annotations(id) ON DELETE CASCADE,
  planner_version text NOT NULL,
  prompt_version text,
  model_profile text,
  run_id text,
  status text NOT NULL,
  selected_task_count integer NOT NULL DEFAULT 0,
  skipped_task_count integer NOT NULL DEFAULT 0,
  abstention_count integer NOT NULL DEFAULT 0,
  missing_contract_count integer NOT NULL DEFAULT 0,
  missing_grounding_count integer NOT NULL DEFAULT 0,
  incompatible_schema_count integer NOT NULL DEFAULT 0,
  duplicate_suppressed_count integer NOT NULL DEFAULT 0,
  report_json jsonb NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  CHECK (jsonb_typeof(report_json) = 'object')
);

CREATE INDEX IF NOT EXISTS semantic_extraction_plans_document_idx
  ON semantic_extraction_plans(document_id, created_at DESC);

CREATE INDEX IF NOT EXISTS semantic_extraction_plans_annotation_idx
  ON semantic_extraction_plans(semantic_annotation_id, created_at DESC);

CREATE INDEX IF NOT EXISTS semantic_extraction_plans_run_idx
  ON semantic_extraction_plans(run_id, created_at DESC);

CREATE TABLE IF NOT EXISTS semantic_extraction_plan_tasks (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  plan_id uuid NOT NULL REFERENCES semantic_extraction_plans(id) ON DELETE CASCADE,
  document_id uuid NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  semantic_region_id uuid REFERENCES semantic_region_annotations(id) ON DELETE SET NULL,
  semantic_type text NOT NULL,
  granite_task text,
  extractor_backend text,
  resolved_document_type text,
  target_schema text,
  canonical_target_schema text,
  model_output_schema_name text,
  contract_resolution_reason text,
  compatibility_mode text,
  grounding_kind text,
  page_number integer,
  page_id uuid,
  element_id uuid,
  table_id uuid,
  status text NOT NULL,
  skip_reason text,
  review_required boolean NOT NULL DEFAULT true,
  task_json jsonb NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  CHECK (jsonb_typeof(task_json) = 'object')
);

CREATE INDEX IF NOT EXISTS semantic_extraction_plan_tasks_plan_idx
  ON semantic_extraction_plan_tasks(plan_id);

CREATE INDEX IF NOT EXISTS semantic_extraction_plan_tasks_document_idx
  ON semantic_extraction_plan_tasks(document_id, created_at DESC);

CREATE INDEX IF NOT EXISTS semantic_extraction_plan_tasks_status_idx
  ON semantic_extraction_plan_tasks(status, created_at DESC);

CREATE TABLE IF NOT EXISTS candidate_admission_events (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  document_id uuid NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  extraction_id uuid REFERENCES document_extractions(id) ON DELETE SET NULL,
  plan_id uuid REFERENCES semantic_extraction_plans(id) ON DELETE SET NULL,
  plan_task_id uuid REFERENCES semantic_extraction_plan_tasks(id) ON DELETE SET NULL,
  semantic_annotation_id uuid REFERENCES document_semantic_annotations(id) ON DELETE SET NULL,
  semantic_region_id uuid REFERENCES semantic_region_annotations(id) ON DELETE SET NULL,
  run_id text,
  planner_version text,
  candidate_gate_version text,
  contract_registry_version text,
  region_envelope_version text,
  candidate_kind text NOT NULL,
  candidate_fingerprint text,
  decision text NOT NULL,
  reasons text[] NOT NULL DEFAULT '{}',
  field_path text,
  semantic_type text,
  model_output_schema_name text,
  source_engine text,
  evidence_concrete boolean,
  payload_json jsonb NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  CHECK (jsonb_typeof(payload_json) = 'object')
);

CREATE INDEX IF NOT EXISTS candidate_admission_events_document_idx
  ON candidate_admission_events(document_id, created_at DESC);

CREATE INDEX IF NOT EXISTS candidate_admission_events_decision_idx
  ON candidate_admission_events(decision, created_at DESC);

CREATE INDEX IF NOT EXISTS candidate_admission_events_schema_idx
  ON candidate_admission_events(model_output_schema_name, created_at DESC);

CREATE INDEX IF NOT EXISTS candidate_admission_events_run_idx
  ON candidate_admission_events(run_id, created_at DESC);

CREATE INDEX IF NOT EXISTS candidate_admission_events_plan_task_idx
  ON candidate_admission_events(plan_task_id, created_at DESC)
  WHERE plan_task_id IS NOT NULL;

ALTER TABLE document_extractions
  ADD COLUMN IF NOT EXISTS plan_id uuid REFERENCES semantic_extraction_plans(id) ON DELETE SET NULL,
  ADD COLUMN IF NOT EXISTS plan_task_id uuid REFERENCES semantic_extraction_plan_tasks(id) ON DELETE SET NULL,
  ADD COLUMN IF NOT EXISTS canonical_target_schema text,
  ADD COLUMN IF NOT EXISTS compatibility_mode text,
  ADD COLUMN IF NOT EXISTS contract_resolution_reason text,
  ADD COLUMN IF NOT EXISTS region_envelope_version text;

CREATE INDEX IF NOT EXISTS document_extractions_plan_task_idx
  ON document_extractions(plan_task_id, created_at DESC)
  WHERE plan_task_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS document_extractions_canonical_target_idx
  ON document_extractions(canonical_target_schema, created_at DESC)
  WHERE canonical_target_schema IS NOT NULL;

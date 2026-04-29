SET search_path TO structura, public;

ALTER TYPE model_source_enum ADD VALUE IF NOT EXISTS 'qwen3_vl_2b';
ALTER TYPE job_type_enum ADD VALUE IF NOT EXISTS 'semantic_annotate';

CREATE TABLE IF NOT EXISTS document_semantic_annotations (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  document_id uuid NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  household_id uuid NOT NULL REFERENCES households(id) ON DELETE CASCADE,
  quality_mode text NOT NULL DEFAULT 'smart',
  status text NOT NULL DEFAULT 'pending',
  is_current boolean NOT NULL DEFAULT true,
  profile_name text NOT NULL,
  source_engine model_source_enum NOT NULL DEFAULT 'system',
  model_name text NOT NULL,
  model_version text NOT NULL,
  prompt_version text NOT NULL,
  docling_parse_asset_id uuid REFERENCES document_assets(id) ON DELETE SET NULL,
  docling_parse_sha256 char(64),
  input_page_hashes_json jsonb NOT NULL DEFAULT '[]'::jsonb,
  manifest_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  confidence_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  review_required boolean NOT NULL DEFAULT false,
  escalation_reason text,
  error_class text,
  error_message text,
  created_by text NOT NULL DEFAULT 'system',
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  superseded_at timestamptz,
  CHECK (quality_mode IN ('smart', 'high_quality', 'rescue')),
  CHECK (status IN ('pending', 'succeeded', 'failed', 'superseded')),
  CHECK (jsonb_typeof(input_page_hashes_json) = 'array'),
  CHECK (jsonb_typeof(manifest_json) = 'object'),
  CHECK (jsonb_typeof(confidence_json) = 'object')
);

CREATE TABLE IF NOT EXISTS page_semantic_annotations (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  annotation_id uuid NOT NULL REFERENCES document_semantic_annotations(id) ON DELETE CASCADE,
  document_id uuid NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  page_id uuid NOT NULL REFERENCES document_pages(id) ON DELETE CASCADE,
  page_number integer NOT NULL,
  page_role text NOT NULL,
  document_type_hint text,
  extraction_usefulness text NOT NULL DEFAULT 'unknown',
  is_boilerplate boolean NOT NULL DEFAULT false,
  has_structured_targets boolean NOT NULL DEFAULT false,
  ambiguous boolean NOT NULL DEFAULT false,
  escalation_required boolean NOT NULL DEFAULT false,
  reason text,
  confidence numeric(5,4),
  metadata_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CHECK (page_number > 0),
  CHECK (extraction_usefulness IN ('none', 'low', 'medium', 'high', 'unknown')),
  CHECK (confidence IS NULL OR (confidence >= 0 AND confidence <= 1)),
  CHECK (jsonb_typeof(metadata_json) = 'object')
);

CREATE TABLE IF NOT EXISTS semantic_region_annotations (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  annotation_id uuid NOT NULL REFERENCES document_semantic_annotations(id) ON DELETE CASCADE,
  page_annotation_id uuid REFERENCES page_semantic_annotations(id) ON DELETE CASCADE,
  document_id uuid NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  page_id uuid REFERENCES document_pages(id) ON DELETE CASCADE,
  element_id uuid REFERENCES document_elements(id) ON DELETE SET NULL,
  table_id uuid REFERENCES document_tables(id) ON DELETE SET NULL,
  semantic_type text NOT NULL,
  priority text NOT NULL DEFAULT 'medium',
  granite_task text,
  target_schema text,
  expected_fields_json jsonb NOT NULL DEFAULT '[]'::jsonb,
  grounding_kind text NOT NULL,
  unmatched_region boolean NOT NULL DEFAULT false,
  review_required boolean NOT NULL DEFAULT false,
  reason text,
  confidence numeric(5,4),
  metadata_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CHECK (priority IN ('low', 'medium', 'high', 'critical')),
  CHECK (
    granite_task IS NULL OR granite_task IN (
      'kvp',
      'tables_json',
      'tables_html',
      'tables_otsl',
      'chart2csv',
      'chart2summary',
      'chart2code',
      'ignore'
    )
  ),
  CHECK (
    semantic_type IN (
      'document_header',
      'billing_summary',
      'payment_summary',
      'patient_responsibility_summary',
      'covered_services_line_item_table',
      'invoice_line_item_table',
      'receipt_line_item_table',
      'retail_order_line_item_table',
      'tax_summary',
      'service_record_line_item_table',
      'receipt_payment_summary',
      'denial_or_coverage_decision',
      'appeal_or_next_steps',
      'legal_clause',
      'contact_block',
      'vehicle_or_asset_block',
      'signature_block',
      'seller_information_block',
      'escrow_summary',
      'mortgage_payment_summary',
      'dispute_transaction_table',
      'dispute_reason_block',
      'generic_form_kvp',
      'no_extraction_target',
      'unsupported_document_region',
      'boilerplate',
      'unmatched_region',
      'unknown'
    )
  ),
  CHECK (grounding_kind IN ('page', 'element', 'table', 'unmatched_region')),
  CHECK (expected_fields_json IS NULL OR jsonb_typeof(expected_fields_json) = 'array'),
  CHECK (jsonb_typeof(metadata_json) = 'object'),
  CHECK (confidence IS NULL OR (confidence >= 0 AND confidence <= 1)),
  CHECK (
    unmatched_region = false
    OR (semantic_type = 'unmatched_region' AND grounding_kind = 'unmatched_region' AND review_required = true)
  ),
  CHECK (
    grounding_kind = 'unmatched_region'
    OR page_id IS NOT NULL
    OR element_id IS NOT NULL
    OR table_id IS NOT NULL
  )
);

CREATE UNIQUE INDEX IF NOT EXISTS document_semantic_annotations_current_uniq
  ON document_semantic_annotations (document_id, profile_name, quality_mode)
  WHERE is_current;

CREATE INDEX IF NOT EXISTS document_semantic_annotations_document_status_idx
  ON document_semantic_annotations (document_id, status, created_at DESC);

CREATE INDEX IF NOT EXISTS document_semantic_annotations_household_status_idx
  ON document_semantic_annotations (household_id, status, created_at DESC);

CREATE INDEX IF NOT EXISTS page_semantic_annotations_annotation_page_idx
  ON page_semantic_annotations (annotation_id, page_number);

CREATE INDEX IF NOT EXISTS semantic_region_annotations_annotation_priority_idx
  ON semantic_region_annotations (annotation_id, priority, semantic_type);

CREATE INDEX IF NOT EXISTS semantic_region_annotations_document_task_idx
  ON semantic_region_annotations (document_id, granite_task, priority)
  WHERE granite_task IS NOT NULL;

CREATE TRIGGER trg_document_semantic_annotations_updated_at
BEFORE UPDATE ON document_semantic_annotations
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER trg_page_semantic_annotations_updated_at
BEFORE UPDATE ON page_semantic_annotations
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER trg_semantic_region_annotations_updated_at
BEFORE UPDATE ON semantic_region_annotations
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

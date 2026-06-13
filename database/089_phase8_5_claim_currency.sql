-- Phase 8.5 / HC-R5: persist Claims as the durable extraction currency.
-- Candidates, canonical payloads, and review tasks remain compatibility
-- projections during the E5 transition; this table lets those projections be
-- rebuilt without reading raw model output or normalized generative payloads.
SET search_path TO structura, public;

CREATE TABLE IF NOT EXISTS extraction_claims (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  extraction_id uuid NOT NULL REFERENCES document_extractions(id) ON DELETE CASCADE,
  document_id uuid NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  claim_id text NOT NULL,
  semantic_annotation_id uuid REFERENCES document_semantic_annotations(id) ON DELETE SET NULL,
  source_semantic_region_id uuid REFERENCES semantic_region_annotations(id) ON DELETE SET NULL,
  semantic_type text,
  granite_task text,
  method text NOT NULL,
  region_envelope_version text,
  source_engine text NOT NULL,
  canonical_key text NOT NULL,
  raw_value text NOT NULL DEFAULT '',
  typed_value_json jsonb NOT NULL,
  value_type text NOT NULL,
  confidence numeric(5,4),
  group_id text,
  anchor_json jsonb NOT NULL,
  evidence_json jsonb NOT NULL DEFAULT '[]'::jsonb,
  metadata_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (extraction_id, claim_id),
  CHECK (claim_id <> ''),
  CHECK (canonical_key <> ''),
  CHECK (method <> ''),
  CHECK (source_engine <> ''),
  CHECK (value_type IN (
    'money',
    'date',
    'quantity',
    'identifier',
    'party',
    'enum',
    'text',
    'number',
    'boolean',
    'object'
  )),
  CHECK (confidence IS NULL OR (confidence >= 0 AND confidence <= 1)),
  CHECK (jsonb_typeof(anchor_json) = 'object'),
  CHECK (jsonb_typeof(evidence_json) = 'array'),
  CHECK (jsonb_typeof(metadata_json) = 'object')
);

CREATE INDEX IF NOT EXISTS extraction_claims_document_key_idx
  ON extraction_claims (document_id, canonical_key, created_at DESC);

CREATE INDEX IF NOT EXISTS extraction_claims_extraction_idx
  ON extraction_claims (extraction_id, canonical_key, group_id);

CREATE INDEX IF NOT EXISTS extraction_claims_semantic_region_idx
  ON extraction_claims (source_semantic_region_id, canonical_key)
  WHERE source_semantic_region_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS extraction_claims_typed_value_gin_idx
  ON extraction_claims USING gin (typed_value_json);

CREATE TRIGGER trg_extraction_claims_updated_at
BEFORE UPDATE ON extraction_claims
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

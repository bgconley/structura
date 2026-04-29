SET search_path TO structura, public;

CREATE TABLE IF NOT EXISTS extraction_observations (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  document_id uuid NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  extraction_id uuid NOT NULL REFERENCES document_extractions(id) ON DELETE CASCADE,
  semantic_annotation_id uuid REFERENCES document_semantic_annotations(id) ON DELETE SET NULL,
  source_semantic_region_id uuid REFERENCES semantic_region_annotations(id) ON DELETE SET NULL,
  semantic_type text,
  source_engine model_source_enum NOT NULL,
  model_output_schema_name text,
  observation_family text,
  field_name text NOT NULL,
  value_type text NOT NULL,
  value_json jsonb,
  confidence numeric(5,4),
  evidence_json jsonb NOT NULL DEFAULT '[]'::jsonb,
  validation_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  status text NOT NULL DEFAULT 'needs_review',
  metadata_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CHECK (field_name <> ''),
  CHECK (value_type IN ('string', 'number', 'boolean', 'json', 'null')),
  CHECK (confidence IS NULL OR (confidence >= 0 AND confidence <= 1)),
  CHECK (jsonb_typeof(evidence_json) = 'array'),
  CHECK (jsonb_typeof(validation_json) = 'object'),
  CHECK (jsonb_typeof(metadata_json) = 'object'),
  CHECK (status IN ('needs_review', 'promoted', 'rejected', 'superseded'))
);

CREATE INDEX IF NOT EXISTS extraction_observations_document_family_idx
  ON extraction_observations (document_id, observation_family, field_name, status);

CREATE INDEX IF NOT EXISTS extraction_observations_extraction_idx
  ON extraction_observations (extraction_id);

CREATE INDEX IF NOT EXISTS extraction_observations_semantic_region_idx
  ON extraction_observations (source_semantic_region_id, field_name)
  WHERE source_semantic_region_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS extraction_observations_model_output_schema_idx
  ON extraction_observations (model_output_schema_name, field_name)
  WHERE model_output_schema_name IS NOT NULL;

CREATE TRIGGER trg_extraction_observations_updated_at
BEFORE UPDATE ON extraction_observations
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

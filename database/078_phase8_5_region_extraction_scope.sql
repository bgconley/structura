SET search_path TO structura, public;

ALTER TABLE document_extractions
  ADD COLUMN IF NOT EXISTS extraction_scope text NOT NULL DEFAULT 'document',
  ADD COLUMN IF NOT EXISTS semantic_annotation_id uuid REFERENCES document_semantic_annotations(id) ON DELETE SET NULL,
  ADD COLUMN IF NOT EXISTS source_semantic_region_id uuid REFERENCES semantic_region_annotations(id) ON DELETE SET NULL,
  ADD COLUMN IF NOT EXISTS semantic_type text,
  ADD COLUMN IF NOT EXISTS granite_task text,
  ADD COLUMN IF NOT EXISTS model_output_schema_name text,
  ADD COLUMN IF NOT EXISTS model_output_schema_version text,
  ADD COLUMN IF NOT EXISTS normalization_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  ADD COLUMN IF NOT EXISTS metadata_json jsonb NOT NULL DEFAULT '{}'::jsonb;

ALTER TABLE document_extractions
  DROP CONSTRAINT IF EXISTS document_extractions_extraction_scope_check,
  ADD CONSTRAINT document_extractions_extraction_scope_check
  CHECK (extraction_scope IN ('document', 'semantic_region', 'aggregate'));

ALTER TABLE document_extractions
  DROP CONSTRAINT IF EXISTS document_extractions_region_scope_check,
  ADD CONSTRAINT document_extractions_region_scope_check
  CHECK (
    extraction_scope <> 'semantic_region'
    OR source_semantic_region_id IS NOT NULL
  );

ALTER TABLE document_extractions
  DROP CONSTRAINT IF EXISTS document_extractions_normalization_object_check,
  ADD CONSTRAINT document_extractions_normalization_object_check
  CHECK (jsonb_typeof(normalization_json) = 'object');

ALTER TABLE document_extractions
  DROP CONSTRAINT IF EXISTS document_extractions_metadata_object_check,
  ADD CONSTRAINT document_extractions_metadata_object_check
  CHECK (jsonb_typeof(metadata_json) = 'object');

DROP INDEX IF EXISTS document_extractions_one_current_idx;

CREATE UNIQUE INDEX IF NOT EXISTS document_extractions_current_document_scope_idx
  ON document_extractions (document_id, schema_name, extraction_scope)
  WHERE is_current AND extraction_scope IN ('document', 'aggregate');

CREATE UNIQUE INDEX IF NOT EXISTS document_extractions_current_region_scope_idx
  ON document_extractions (document_id, schema_name, source_semantic_region_id)
  WHERE is_current AND extraction_scope = 'semantic_region';

CREATE INDEX IF NOT EXISTS document_extractions_scope_schema_idx
  ON document_extractions (document_id, schema_name, extraction_scope, created_at DESC);

CREATE INDEX IF NOT EXISTS document_extractions_semantic_annotation_idx
  ON document_extractions (semantic_annotation_id, schema_name, extraction_scope)
  WHERE semantic_annotation_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS document_extractions_semantic_region_idx
  ON document_extractions (source_semantic_region_id, schema_name)
  WHERE source_semantic_region_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS document_extractions_model_output_schema_idx
  ON document_extractions (model_output_schema_name, model_output_schema_version)
  WHERE model_output_schema_name IS NOT NULL;

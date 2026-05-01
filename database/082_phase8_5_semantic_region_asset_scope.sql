SET search_path TO structura, public;

DROP INDEX IF EXISTS document_assets_one_current_idx;
DROP INDEX IF EXISTS document_assets_current_document_extraction_idx;
DROP INDEX IF EXISTS document_assets_current_region_extraction_idx;

CREATE UNIQUE INDEX IF NOT EXISTS document_assets_one_current_idx
  ON document_assets (document_id, asset_role, COALESCE(page_number, 0))
  WHERE is_current
    AND asset_role NOT IN ('raw_model_output', 'normalized_extraction_json');

CREATE UNIQUE INDEX IF NOT EXISTS document_assets_current_document_extraction_idx
  ON document_assets (document_id, asset_role, COALESCE(page_number, 0))
  WHERE is_current
    AND asset_role IN ('raw_model_output', 'normalized_extraction_json')
    AND COALESCE(metadata_json ->> 'extractionScope', 'document') <> 'semantic_region';

CREATE UNIQUE INDEX IF NOT EXISTS document_assets_current_region_extraction_idx
  ON document_assets (
    document_id,
    asset_role,
    COALESCE(metadata_json ->> 'sourceSemanticRegionId', ''),
    COALESCE(page_number, 0)
  )
  WHERE is_current
    AND asset_role IN ('raw_model_output', 'normalized_extraction_json')
    AND metadata_json ->> 'extractionScope' = 'semantic_region';

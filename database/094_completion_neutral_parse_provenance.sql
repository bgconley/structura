-- Additive vocabulary only. Do not relabel historical Docling/model evidence.
-- Later migrations in this transaction must not use new enum values in DML.
SET search_path TO structura, public;

ALTER TYPE model_source_enum ADD VALUE IF NOT EXISTS 'qwen3_8_27b';
ALTER TYPE model_source_enum ADD VALUE IF NOT EXISTS 'pdf_native';
ALTER TYPE asset_role_enum ADD VALUE IF NOT EXISTS 'document_structure_json';
ALTER TYPE asset_role_enum ADD VALUE IF NOT EXISTS 'document_structure_md';
ALTER TYPE asset_role_enum ADD VALUE IF NOT EXISTS 'document_structure_html';

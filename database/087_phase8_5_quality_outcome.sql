-- Phase 8.5 / ADR 0005 D8: quality outcomes are first-class persisted decisions.
-- Adds a quality_outcome column on document_extractions sourced from the
-- aggregate payload metadata written by claim reconciliation, and expands the
-- extraction_observations status vocabulary so review accept decisions can be
-- recorded without implying canonical promotion.
SET search_path TO structura, public;

ALTER TABLE document_extractions
  ADD COLUMN IF NOT EXISTS quality_outcome text;

ALTER TABLE document_extractions
  DROP CONSTRAINT IF EXISTS document_extractions_quality_outcome_check;

ALTER TABLE document_extractions
  ADD CONSTRAINT document_extractions_quality_outcome_check
  CHECK (
    quality_outcome IS NULL
    OR quality_outcome IN (
      'extracted_cleanly',
      'needs_human_review',
      'insufficient_signal',
      'no_extraction_target',
      'pipeline_failed'
    )
  );

CREATE INDEX IF NOT EXISTS document_extractions_quality_outcome_idx
  ON document_extractions (document_id, quality_outcome)
  WHERE is_current AND quality_outcome IS NOT NULL;

-- Review accept decisions mark observation candidates 'accepted' without a
-- canonical promotion path; 'promoted' remains reserved for canonical writes.
ALTER TABLE extraction_observations
  DROP CONSTRAINT IF EXISTS extraction_observations_status_check;

ALTER TABLE extraction_observations
  ADD CONSTRAINT extraction_observations_status_check
  CHECK (status IN ('needs_review', 'accepted', 'promoted', 'rejected', 'superseded'));

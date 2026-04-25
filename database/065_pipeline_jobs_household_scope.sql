SET search_path TO structura, public;

ALTER TABLE pipeline_jobs
  ADD COLUMN IF NOT EXISTS household_id uuid REFERENCES households(id) ON DELETE CASCADE;

UPDATE pipeline_jobs pj
SET household_id = d.household_id
FROM documents d
WHERE pj.document_id = d.id
  AND pj.household_id IS NULL;

CREATE INDEX IF NOT EXISTS pipeline_jobs_household_status_idx
  ON pipeline_jobs (household_id, status, created_at DESC);

-- Apply with token-aware workers drained. Legacy root jobs remain roots;
-- existing explicit parent links are preserved, never inferred from timestamps.
SET search_path TO structura, public;

ALTER TABLE pipeline_jobs
  ADD COLUMN execution_generation bigint NOT NULL DEFAULT 0,
  ADD COLUMN parent_execution_generation bigint,
  ADD COLUMN lineage_revoked_at timestamptz;

UPDATE pipeline_jobs SET execution_generation = attempt_count;
UPDATE pipeline_jobs child
SET parent_execution_generation = parent.execution_generation
FROM pipeline_jobs parent WHERE child.parent_job_id = parent.id;

ALTER TABLE pipeline_jobs
  ADD CONSTRAINT pipeline_jobs_execution_generation_check CHECK (execution_generation >= 0),
  ADD CONSTRAINT pipeline_jobs_parent_generation_check CHECK (
    (parent_job_id IS NULL AND parent_execution_generation IS NULL)
    OR (parent_job_id IS NOT NULL AND parent_execution_generation IS NOT NULL
        AND parent_execution_generation >= 0)
  ),
  ADD CONSTRAINT pipeline_jobs_not_own_parent CHECK (parent_job_id IS DISTINCT FROM id),
  DROP CONSTRAINT pipeline_jobs_parent_job_id_fkey,
  ADD CONSTRAINT pipeline_jobs_parent_job_id_fkey FOREIGN KEY (parent_job_id)
    REFERENCES pipeline_jobs(id) DEFERRABLE INITIALLY DEFERRED;

CREATE INDEX pipeline_jobs_parent_idx ON pipeline_jobs(parent_job_id)
  WHERE parent_job_id IS NOT NULL;

CREATE FUNCTION preserve_pipeline_job_lineage() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF NEW.parent_job_id IS DISTINCT FROM OLD.parent_job_id
     OR NEW.parent_execution_generation IS DISTINCT FROM OLD.parent_execution_generation THEN
    RAISE EXCEPTION 'Job parent lineage is immutable';
  END IF;
  IF NEW.household_id IS DISTINCT FROM OLD.household_id
     OR NEW.document_id IS DISTINCT FROM OLD.document_id
     OR NEW.batch_id IS DISTINCT FROM OLD.batch_id THEN
    RAISE EXCEPTION 'Job document, household and batch scope is immutable';
  END IF;
  IF NEW.execution_generation < OLD.execution_generation THEN
    RAISE EXCEPTION 'Job execution generation cannot decrease';
  END IF;
  IF OLD.lineage_revoked_at IS NOT NULL AND NEW.lineage_revoked_at IS NULL THEN
    RAISE EXCEPTION 'Revoked descendant lineage cannot be restored';
  END IF;
  RETURN NEW;
END;
$$;

CREATE TRIGGER preserve_pipeline_job_lineage_before_update
BEFORE UPDATE ON pipeline_jobs FOR EACH ROW EXECUTE FUNCTION preserve_pipeline_job_lineage();

COMMENT ON COLUMN pipeline_jobs.execution_generation IS
  'Durable attempt sequence, incremented on claim and never reset by operator retry.';
COMMENT ON COLUMN pipeline_jobs.lineage_revoked_at IS
  'Permanent descendant invalidation; explicit retry cannot revive obsolete ancestry.';

-- Additive candidate storage only. Existing structural tables/current pointers
-- and document-global uniqueness remain unchanged until consumer cutover.
SET search_path TO structura, public;

ALTER TABLE documents
  ADD COLUMN processing_generation bigint NOT NULL DEFAULT 0,
  ADD COLUMN desired_processing_run_id uuid,
  ADD CONSTRAINT documents_processing_generation_nonnegative CHECK (processing_generation >= 0);

CREATE TABLE document_processing_runs (
  id uuid PRIMARY KEY,
  document_id uuid NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  household_id uuid NOT NULL REFERENCES households(id) ON DELETE CASCADE,
  generation bigint NOT NULL CHECK (generation > 0),
  request_key uuid NOT NULL,
  requested_by_user_id uuid NOT NULL REFERENCES users(id),
  original_asset_id uuid NOT NULL REFERENCES document_assets(id),
  original_sha256 text NOT NULL CHECK (original_sha256 ~ '^[a-f0-9]{64}$'),
  parse_generation_id uuid NOT NULL,
  root_job_id uuid NOT NULL UNIQUE,
  config_json jsonb NOT NULL CHECK (jsonb_typeof(config_json) = 'object'),
  config_sha256 text NOT NULL CHECK (config_sha256 ~ '^[a-f0-9]{64}$'),
  status text NOT NULL DEFAULT 'requested'
    CHECK (status IN ('requested', 'sealed', 'superseded', 'cancelled')),
  revoked_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  UNIQUE (document_id, generation),
  UNIQUE (document_id, request_key),
  UNIQUE (id, document_id),
  UNIQUE (id, document_id, household_id, parse_generation_id),
  CHECK ((status IN ('superseded', 'cancelled')) = (revoked_at IS NOT NULL))
);

CREATE TABLE document_parse_generations (
  id uuid PRIMARY KEY,
  document_id uuid NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  creator_run_id uuid NOT NULL UNIQUE,
  state text NOT NULL DEFAULT 'building' CHECK (state IN ('building', 'sealed')),
  inventory_json jsonb CHECK (inventory_json IS NULL OR jsonb_typeof(inventory_json) = 'object'),
  inventory_sha256 text CHECK (inventory_sha256 IS NULL OR inventory_sha256 ~ '^[a-f0-9]{64}$'),
  structure_json jsonb CHECK (structure_json IS NULL OR jsonb_typeof(structure_json) = 'object'),
  structure_sha256 text CHECK (structure_sha256 IS NULL OR structure_sha256 ~ '^[a-f0-9]{64}$'),
  sealed_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  UNIQUE (id, document_id),
  CHECK ((inventory_json IS NULL) = (inventory_sha256 IS NULL)),
  CHECK ((state = 'sealed') = (sealed_at IS NOT NULL)),
  CHECK ((state = 'sealed') = (structure_json IS NOT NULL)),
  CHECK ((structure_json IS NULL) = (structure_sha256 IS NULL)),
  CHECK (state <> 'sealed' OR inventory_json IS NOT NULL),
  FOREIGN KEY (creator_run_id, document_id)
    REFERENCES document_processing_runs(id, document_id) DEFERRABLE INITIALLY DEFERRED
);

ALTER TABLE document_processing_runs ADD CONSTRAINT processing_runs_parse_generation_fk
  FOREIGN KEY (parse_generation_id, document_id)
  REFERENCES document_parse_generations(id, document_id) DEFERRABLE INITIALLY DEFERRED;
ALTER TABLE documents ADD CONSTRAINT documents_desired_processing_run_fk
  FOREIGN KEY (desired_processing_run_id, id)
  REFERENCES document_processing_runs(id, document_id) DEFERRABLE INITIALLY DEFERRED;

CREATE TABLE document_parse_page_checkpoints (
  parse_generation_id uuid NOT NULL REFERENCES document_parse_generations(id) ON DELETE CASCADE,
  page_number integer NOT NULL CHECK (page_number > 0),
  page_id uuid NOT NULL UNIQUE,
  page_json jsonb NOT NULL CHECK (jsonb_typeof(page_json) = 'object'),
  invocation_json jsonb NOT NULL CHECK (jsonb_typeof(invocation_json) = 'object'),
  raw_output text NOT NULL,
  content_sha256 text NOT NULL CHECK (content_sha256 ~ '^[a-f0-9]{64}$'),
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  PRIMARY KEY (parse_generation_id, page_number)
);

ALTER TABLE pipeline_jobs
  ADD COLUMN processing_run_id uuid,
  ADD COLUMN parse_generation_id uuid,
  ADD CONSTRAINT pipeline_jobs_processing_binding_complete CHECK (
    (processing_run_id IS NULL AND parse_generation_id IS NULL)
    OR (processing_run_id IS NOT NULL AND parse_generation_id IS NOT NULL
        AND document_id IS NOT NULL AND household_id IS NOT NULL)
  ),
  ADD CONSTRAINT pipeline_jobs_processing_scope_fk
    FOREIGN KEY (processing_run_id, document_id, household_id, parse_generation_id)
    REFERENCES document_processing_runs(id, document_id, household_id, parse_generation_id)
    DEFERRABLE INITIALLY DEFERRED,
  ADD CONSTRAINT pipeline_jobs_processing_root_key
    UNIQUE (id, processing_run_id, parse_generation_id);
ALTER TABLE document_processing_runs ADD CONSTRAINT processing_runs_root_job_fk
  FOREIGN KEY (root_job_id, id, parse_generation_id)
  REFERENCES pipeline_jobs(id, processing_run_id, parse_generation_id)
  DEFERRABLE INITIALLY DEFERRED;
CREATE INDEX pipeline_jobs_processing_run_idx ON pipeline_jobs(processing_run_id)
  WHERE processing_run_id IS NOT NULL;

-- This is a snapshot check, deliberately taking no domain locks after job-root
-- locks. Locked run publication remains a separate same-transaction obligation.
CREATE FUNCTION processing_job_is_current(run_id uuid, parse_id uuid)
RETURNS boolean LANGUAGE sql STABLE AS $$
  SELECT CASE WHEN run_id IS NULL THEN parse_id IS NULL ELSE EXISTS (
    SELECT 1 FROM document_processing_runs r
    JOIN documents d ON d.id = r.document_id
    WHERE r.id = run_id AND r.parse_generation_id = parse_id
      AND r.revoked_at IS NULL AND d.deleted_at IS NULL
      AND d.desired_processing_run_id = r.id AND d.processing_generation = r.generation
  ) END;
$$;

CREATE FUNCTION preserve_processing_job_binding() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE parent_run uuid; parent_parse uuid;
BEGIN
  IF TG_OP = 'UPDATE' AND ROW(NEW.processing_run_id, NEW.parse_generation_id)
       IS DISTINCT FROM ROW(OLD.processing_run_id, OLD.parse_generation_id) THEN
    RAISE EXCEPTION 'Job processing binding is immutable';
  END IF;
  IF TG_OP = 'INSERT' AND NEW.parent_job_id IS NOT NULL THEN
    SELECT processing_run_id, parse_generation_id INTO parent_run, parent_parse
      FROM pipeline_jobs WHERE id = NEW.parent_job_id;
    IF ROW(NEW.processing_run_id, NEW.parse_generation_id)
       IS DISTINCT FROM ROW(parent_run, parent_parse) THEN
      RAISE EXCEPTION 'Child processing binding must match parent';
    END IF;
  END IF;
  RETURN NEW;
END;
$$;
CREATE TRIGGER pipeline_jobs_preserve_processing_binding BEFORE INSERT OR UPDATE ON pipeline_jobs
  FOR EACH ROW EXECUTE FUNCTION preserve_processing_job_binding();

CREATE FUNCTION preserve_processing_run_identity() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF ROW(NEW.id, NEW.document_id, NEW.household_id, NEW.generation, NEW.request_key,
         NEW.requested_by_user_id, NEW.original_asset_id, NEW.original_sha256,
         NEW.parse_generation_id, NEW.root_job_id, NEW.config_json, NEW.config_sha256, NEW.created_at)
     IS DISTINCT FROM ROW(OLD.id, OLD.document_id, OLD.household_id, OLD.generation, OLD.request_key,
         OLD.requested_by_user_id, OLD.original_asset_id, OLD.original_sha256,
         OLD.parse_generation_id, OLD.root_job_id, OLD.config_json, OLD.config_sha256, OLD.created_at)
     OR (OLD.revoked_at IS NOT NULL AND ROW(NEW.revoked_at, NEW.status)
         IS DISTINCT FROM ROW(OLD.revoked_at, OLD.status))
     OR (OLD.status = 'sealed' AND NEW.status = 'requested') THEN
    RAISE EXCEPTION 'Processing run identity and revocation are immutable';
  END IF;
  RETURN NEW;
END;
$$;
CREATE TRIGGER document_processing_runs_preserve_identity BEFORE UPDATE ON document_processing_runs
  FOR EACH ROW EXECUTE FUNCTION preserve_processing_run_identity();

CREATE FUNCTION preserve_parse_generation() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF ROW(NEW.id, NEW.document_id, NEW.creator_run_id, NEW.created_at)
       IS DISTINCT FROM ROW(OLD.id, OLD.document_id, OLD.creator_run_id, OLD.created_at)
     OR (OLD.inventory_json IS NOT NULL AND ROW(NEW.inventory_json, NEW.inventory_sha256)
         IS DISTINCT FROM ROW(OLD.inventory_json, OLD.inventory_sha256))
     OR (OLD.state = 'sealed' AND NEW IS DISTINCT FROM OLD) THEN
    RAISE EXCEPTION 'Parse generation content is immutable once assigned';
  END IF;
  RETURN NEW;
END;
$$;
CREATE TRIGGER document_parse_generations_preserve_content BEFORE UPDATE ON document_parse_generations
  FOR EACH ROW EXECUTE FUNCTION preserve_parse_generation();

CREATE FUNCTION preserve_parse_checkpoint() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION 'Parse checkpoints are immutable';
END;
$$;
CREATE TRIGGER document_parse_checkpoints_no_update BEFORE UPDATE ON document_parse_page_checkpoints
  FOR EACH ROW EXECUTE FUNCTION preserve_parse_checkpoint();

-- Whole-document removal may cascade; deleting retained processing evidence
-- independently while its document still exists is not a retention policy.
CREATE FUNCTION retain_processing_history() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE owner_document uuid;
BEGIN
  IF TG_TABLE_NAME = 'document_parse_page_checkpoints' THEN
    SELECT document_id INTO owner_document FROM document_parse_generations
      WHERE id = OLD.parse_generation_id;
  ELSE
    owner_document := OLD.document_id;
  END IF;
  IF EXISTS (SELECT 1 FROM documents WHERE id = owner_document) THEN
    RAISE EXCEPTION 'Processing history is retained with its document';
  END IF;
  RETURN OLD;
END;
$$;
CREATE TRIGGER document_processing_runs_retain_history BEFORE DELETE ON document_processing_runs
  FOR EACH ROW EXECUTE FUNCTION retain_processing_history();
CREATE TRIGGER document_parse_generations_retain_history BEFORE DELETE ON document_parse_generations
  FOR EACH ROW EXECUTE FUNCTION retain_processing_history();
CREATE TRIGGER document_parse_checkpoints_retain_history BEFORE DELETE ON document_parse_page_checkpoints
  FOR EACH ROW EXECUTE FUNCTION retain_processing_history();

CREATE FUNCTION preserve_processing_counter() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF NEW.processing_generation < OLD.processing_generation
     OR (NEW.desired_processing_run_id IS DISTINCT FROM OLD.desired_processing_run_id
         AND NEW.processing_generation <= OLD.processing_generation) THEN
    RAISE EXCEPTION 'Processing authority must advance monotonically';
  END IF;
  RETURN NEW;
END;
$$;
CREATE TRIGGER documents_preserve_processing_counter BEFORE UPDATE ON documents
  FOR EACH ROW EXECUTE FUNCTION preserve_processing_counter();

-- Parse-owned retained source pages; no ordinary current publication changes.
SET search_path TO structura, public;

ALTER TABLE document_parse_page_checkpoints
  ADD CONSTRAINT parse_checkpoint_exact_page_identity
  UNIQUE (parse_generation_id, page_number, page_id);

CREATE TABLE document_parse_render_sets (
  id uuid PRIMARY KEY,
  document_id uuid NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  household_id uuid NOT NULL,
  processing_run_id uuid NOT NULL,
  parse_generation_id uuid NOT NULL UNIQUE,
  producer_job_id uuid NOT NULL,
  original_asset_id uuid NOT NULL REFERENCES document_assets(id) DEFERRABLE INITIALLY DEFERRED,
  original_sha256 text NOT NULL CHECK (original_sha256 ~ '^[a-f0-9]{64}$'),
  expected_json jsonb NOT NULL CHECK (jsonb_typeof(expected_json)='object'),
  expected_sha256 text NOT NULL CHECK (expected_sha256 ~ '^[a-f0-9]{64}$'),
  state text NOT NULL DEFAULT 'building' CHECK (state IN ('building','sealed')),
  completion_json jsonb,
  completion_sha256 text CHECK (completion_sha256 ~ '^[a-f0-9]{64}$'),
  sealed_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  UNIQUE (id,document_id,parse_generation_id),
  FOREIGN KEY (processing_run_id,document_id,household_id,parse_generation_id)
    REFERENCES document_processing_runs(id,document_id,household_id,parse_generation_id)
    DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY (parse_generation_id,document_id)
    REFERENCES document_parse_generations(id,document_id) DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY (producer_job_id,processing_run_id,parse_generation_id)
    REFERENCES pipeline_jobs(id,processing_run_id,parse_generation_id)
    DEFERRABLE INITIALLY DEFERRED,
  CHECK ((state='sealed')=(completion_json IS NOT NULL)),
  CHECK ((completion_json IS NULL)=(completion_sha256 IS NULL)),
  CHECK ((state='sealed')=(sealed_at IS NOT NULL))
);

CREATE TABLE document_parse_page_render_assets (
  id uuid PRIMARY KEY,
  render_set_id uuid NOT NULL,
  document_id uuid NOT NULL,
  parse_generation_id uuid NOT NULL,
  page_number integer NOT NULL CHECK (page_number BETWEEN 1 AND 500),
  page_id uuid NOT NULL,
  asset_json jsonb NOT NULL CHECK (jsonb_typeof(asset_json)='object'),
  content_sha256 text NOT NULL CHECK (content_sha256 ~ '^[a-f0-9]{64}$'),
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  UNIQUE (parse_generation_id,page_number),
  UNIQUE (parse_generation_id,page_id),
  FOREIGN KEY (render_set_id,document_id,parse_generation_id)
    REFERENCES document_parse_render_sets(id,document_id,parse_generation_id) ON DELETE CASCADE,
  FOREIGN KEY (parse_generation_id,page_number,page_id)
    REFERENCES document_parse_page_checkpoints(parse_generation_id,page_number,page_id)
    DEFERRABLE INITIALLY DEFERRED
);
CREATE INDEX retained_page_render_uri ON document_parse_page_render_assets((asset_json->>'uri'));
CREATE INDEX retained_page_render_hash
  ON document_parse_page_render_assets((asset_json->'render'->>'image_sha256'));

CREATE FUNCTION preserve_retained_render_set() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF TG_OP='INSERT' THEN
    IF NEW.state<>'building' OR NOT EXISTS (
      SELECT 1 FROM document_processing_runs r JOIN document_parse_generations g
        ON g.id=r.parse_generation_id AND g.creator_run_id=r.id AND g.document_id=r.document_id
      WHERE r.id=NEW.processing_run_id AND r.document_id=NEW.document_id
        AND r.household_id=NEW.household_id AND r.parse_generation_id=NEW.parse_generation_id
        AND r.original_asset_id=NEW.original_asset_id AND r.original_sha256=NEW.original_sha256
        AND g.state='sealed'
        AND NEW.expected_json->>'document_id'=r.document_id::text
        AND NEW.expected_json->>'processing_run_id'=r.id::text
        AND NEW.expected_json->>'parse_generation_id'=g.id::text
        AND NEW.expected_json->>'original_asset_id'=r.original_asset_id::text
        AND NEW.expected_json->>'original_sha256'=r.original_sha256
        AND NEW.expected_json->>'inventory_sha256'=g.inventory_sha256
        AND NEW.expected_json->>'structure_sha256'=g.structure_sha256
        AND NEW.expected_json->>'parse_configuration_sha256'=r.config_sha256
        AND jsonb_typeof(NEW.expected_json->'pages')='array'
        AND jsonb_array_length(NEW.expected_json->'pages')=jsonb_array_length(g.inventory_json->'pages')
    ) THEN RAISE EXCEPTION 'Retained render set requires its exact sealed parse'; END IF;
    RETURN NEW;
  END IF;
  IF ROW(NEW.id,NEW.document_id,NEW.household_id,NEW.processing_run_id,NEW.parse_generation_id,
         NEW.producer_job_id,NEW.original_asset_id,NEW.original_sha256,NEW.expected_json,
         NEW.expected_sha256,NEW.created_at)
    IS DISTINCT FROM ROW(OLD.id,OLD.document_id,OLD.household_id,OLD.processing_run_id,OLD.parse_generation_id,
         OLD.producer_job_id,OLD.original_asset_id,OLD.original_sha256,OLD.expected_json,
         OLD.expected_sha256,OLD.created_at)
    OR (OLD.state='sealed' AND NEW IS DISTINCT FROM OLD) THEN
    RAISE EXCEPTION 'Retained render identity and sealed content are immutable';
  END IF;
  IF NEW.state='sealed' AND (
    SELECT count(*) FROM document_parse_page_render_assets WHERE render_set_id=NEW.id
  ) <> jsonb_array_length(NEW.expected_json->'pages') THEN
    RAISE EXCEPTION 'Retained render set is incomplete';
  END IF;
  RETURN NEW;
END;
$$;
CREATE TRIGGER retained_render_set_identity BEFORE INSERT OR UPDATE ON document_parse_render_sets
  FOR EACH ROW EXECUTE FUNCTION preserve_retained_render_set();

CREATE FUNCTION preserve_retained_page_asset() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE expected jsonb; set_state text;
BEGIN
  IF TG_OP='UPDATE' THEN RAISE EXCEPTION 'Retained page assets are immutable'; END IF;
  SELECT expected_json->'pages'->(NEW.page_number-1),state INTO expected,set_state
    FROM document_parse_render_sets WHERE id=NEW.render_set_id FOR UPDATE;
  IF set_state IS DISTINCT FROM 'building' OR expected IS NULL
    OR (expected->>'page_id') IS DISTINCT FROM NEW.page_id::text
    OR (expected->>'page_number') IS DISTINCT FROM NEW.page_number::text
    OR (NEW.asset_json->>'id') IS DISTINCT FROM NEW.id::text
    OR (NEW.asset_json->>'page_id') IS DISTINCT FROM NEW.page_id::text
    OR (NEW.asset_json->>'page_number') IS DISTINCT FROM NEW.page_number::text
    OR (NEW.asset_json->>'checkpoint_sha256') IS DISTINCT FROM (expected->>'checkpoint_sha256')
    OR (NEW.asset_json->>'source_render_sha256') IS DISTINCT FROM (expected->>'source_render_sha256')
    OR (NEW.asset_json->'render') IS DISTINCT FROM (expected->'render') THEN
    RAISE EXCEPTION 'Retained page does not match its frozen source';
  END IF;
  RETURN NEW;
END;
$$;
CREATE TRIGGER retained_page_asset_identity BEFORE INSERT OR UPDATE ON document_parse_page_render_assets
  FOR EACH ROW EXECUTE FUNCTION preserve_retained_page_asset();

CREATE FUNCTION retain_page_evidence_history() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF EXISTS (SELECT 1 FROM documents WHERE id=OLD.document_id) THEN
    RAISE EXCEPTION 'Page evidence remains retained with its document';
  END IF;
  RETURN OLD;
END;
$$;
CREATE TRIGGER retained_render_set_history BEFORE DELETE ON document_parse_render_sets
  FOR EACH ROW EXECUTE FUNCTION retain_page_evidence_history();
CREATE TRIGGER retained_page_asset_history BEFORE DELETE ON document_parse_page_render_assets
  FOR EACH ROW EXECUTE FUNCTION retain_page_evidence_history();

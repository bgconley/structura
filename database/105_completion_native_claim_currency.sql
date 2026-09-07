-- Hidden immutable structure-derived claims. No current/canonical/index activation.
SET search_path TO structura, public;

CREATE TABLE native_claim_sets (
  id uuid PRIMARY KEY,
  document_id uuid NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  household_id uuid NOT NULL,
  processing_run_id uuid NOT NULL,
  parse_generation_id uuid NOT NULL,
  producer_job_id uuid NOT NULL,
  configuration_json jsonb NOT NULL CHECK(jsonb_typeof(configuration_json)='object'),
  configuration_sha256 text NOT NULL CHECK(configuration_sha256 ~ '^[a-f0-9]{64}$'),
  source_manifest_json jsonb NOT NULL CHECK(jsonb_typeof(source_manifest_json)='object'),
  source_manifest_sha256 text NOT NULL CHECK(source_manifest_sha256 ~ '^[a-f0-9]{64}$'),
  expected_pages integer NOT NULL CHECK(expected_pages BETWEEN 1 AND 500),
  state text NOT NULL DEFAULT 'building' CHECK(state IN ('building','sealed')),
  completion_json jsonb,
  completion_sha256 text CHECK(completion_sha256 ~ '^[a-f0-9]{64}$'),
  sealed_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  UNIQUE(parse_generation_id,configuration_sha256),
  UNIQUE(id,document_id),
  UNIQUE(id,document_id,parse_generation_id),
  FOREIGN KEY(processing_run_id,document_id,household_id,parse_generation_id)
    REFERENCES document_processing_runs(id,document_id,household_id,parse_generation_id)
    DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY(producer_job_id,processing_run_id,parse_generation_id)
    REFERENCES pipeline_jobs(id,processing_run_id,parse_generation_id)
    DEFERRABLE INITIALLY DEFERRED,
  CHECK((state='sealed')=(completion_json IS NOT NULL)),
  CHECK((completion_json IS NULL)=(completion_sha256 IS NULL)),
  CHECK((state='sealed')=(sealed_at IS NOT NULL))
);

CREATE TABLE native_claim_page_checkpoints (
  claim_set_id uuid NOT NULL,
  document_id uuid NOT NULL,
  parse_generation_id uuid NOT NULL,
  page_number integer NOT NULL CHECK(page_number BETWEEN 1 AND 500),
  page_id uuid NOT NULL,
  request_json jsonb NOT NULL CHECK(jsonb_typeof(request_json)='object'),
  content_sha256 text NOT NULL CHECK(content_sha256 ~ '^[a-f0-9]{64}$'),
  claim_count integer NOT NULL CHECK(claim_count BETWEEN 0 AND 1000),
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  PRIMARY KEY(claim_set_id,page_number),
  UNIQUE(claim_set_id,document_id,page_number),
  FOREIGN KEY(claim_set_id,document_id,parse_generation_id)
    REFERENCES native_claim_sets(id,document_id,parse_generation_id) ON DELETE CASCADE,
  FOREIGN KEY(parse_generation_id,page_number,page_id)
    REFERENCES document_parse_page_checkpoints(parse_generation_id,page_number,page_id)
    DEFERRABLE INITIALLY DEFERRED
);

ALTER TABLE extraction_claims
  ALTER COLUMN extraction_id DROP NOT NULL,
  ADD COLUMN origin_kind text NOT NULL DEFAULT 'legacy_extraction',
  ADD COLUMN native_claim_set_id uuid,
  ADD COLUMN native_page_number integer,
  ADD COLUMN native_payload_json jsonb,
  ADD COLUMN native_content_sha256 text,
  ADD CONSTRAINT extraction_claim_native_scope
    FOREIGN KEY(native_claim_set_id,document_id,native_page_number)
    REFERENCES native_claim_page_checkpoints(claim_set_id,document_id,page_number)
    DEFERRABLE INITIALLY DEFERRED,
  ADD CONSTRAINT extraction_claim_native_identity UNIQUE(native_claim_set_id,claim_id),
  ADD CONSTRAINT extraction_claim_origin_branch CHECK (
    (origin_kind='legacy_extraction' AND extraction_id IS NOT NULL
      AND native_claim_set_id IS NULL AND native_page_number IS NULL
      AND native_payload_json IS NULL AND native_content_sha256 IS NULL)
    OR
    (origin_kind='native_structure' AND extraction_id IS NULL
      AND native_claim_set_id IS NOT NULL AND native_page_number IS NOT NULL
      AND native_page_number BETWEEN 1 AND 500 AND native_payload_json IS NOT NULL
      AND jsonb_typeof(native_payload_json)='object' AND native_content_sha256 IS NOT NULL
      AND native_content_sha256 ~ '^[a-f0-9]{64}$'
      AND source_engine='qwen3_8_27b' AND method='structure_normalization:v1'
      AND semantic_annotation_id IS NULL AND source_semantic_region_id IS NULL
      AND confidence IS NULL
      AND native_payload_json->>'schema_version' IS NOT DISTINCT FROM 'native_claim.v2'
      AND native_payload_json->>'derivation' IS NOT DISTINCT FROM 'structure_normalization'
      AND native_payload_json->>'claim_id' IS NOT DISTINCT FROM claim_id
      AND native_payload_json->>'document_id' IS NOT DISTINCT FROM document_id::text
      AND native_payload_json->>'claim_set_id' IS NOT DISTINCT FROM native_claim_set_id::text
      AND native_payload_json->>'raw_value' IS NOT DISTINCT FROM raw_value
      AND native_payload_json->>'canonical_key' IS NOT DISTINCT FROM canonical_key
      AND native_payload_json->>'value_type' IS NOT DISTINCT FROM value_type
      AND native_payload_json->'typed_value' IS NOT DISTINCT FROM typed_value_json
      AND native_payload_json->'anchor' IS NOT DISTINCT FROM anchor_json
      AND native_payload_json->'requires_review' IS NOT DISTINCT FROM 'true'::jsonb
      AND native_payload_json->>'source_pixel_support' IS NOT DISTINCT FROM 'not_evaluated')
  );
CREATE INDEX extraction_claim_native_page ON extraction_claims(native_claim_set_id,native_page_number)
  WHERE native_claim_set_id IS NOT NULL;

CREATE FUNCTION guard_native_claim_set() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF TG_OP='INSERT' THEN
    IF NEW.state<>'building' OR NOT EXISTS (
      SELECT 1 FROM document_parse_generations g JOIN document_processing_runs r ON r.id=g.creator_run_id
      WHERE g.id=NEW.parse_generation_id AND g.document_id=NEW.document_id AND g.state='sealed'
        AND r.id=NEW.processing_run_id AND r.household_id=NEW.household_id
        AND NEW.source_manifest_json->>'structure_sha256'=g.structure_sha256
        AND NEW.source_manifest_json->>'inventory_sha256'=g.inventory_sha256
        AND NEW.source_manifest_json->>'parse_configuration_sha256'=r.config_sha256
        AND NEW.source_manifest_json->>'original_asset_id'=r.original_asset_id::text
        AND NEW.source_manifest_json->>'original_sha256'=r.original_sha256
        AND NEW.expected_pages=jsonb_array_length(g.inventory_json->'pages')
    ) THEN RAISE EXCEPTION 'Native claims require an exact sealed parse source'; END IF;
    RETURN NEW;
  END IF;
  IF ROW(NEW.id,NEW.document_id,NEW.household_id,NEW.processing_run_id,NEW.parse_generation_id,
         NEW.producer_job_id,NEW.configuration_json,NEW.configuration_sha256,
         NEW.source_manifest_json,NEW.source_manifest_sha256,NEW.expected_pages,NEW.created_at)
    IS DISTINCT FROM ROW(OLD.id,OLD.document_id,OLD.household_id,OLD.processing_run_id,OLD.parse_generation_id,
         OLD.producer_job_id,OLD.configuration_json,OLD.configuration_sha256,
         OLD.source_manifest_json,OLD.source_manifest_sha256,OLD.expected_pages,OLD.created_at)
    OR (OLD.state='sealed' AND NEW IS DISTINCT FROM OLD) THEN
    RAISE EXCEPTION 'Native claim set identity and sealed content are immutable';
  END IF;
  IF NEW.state='sealed' AND (SELECT count(*) FROM native_claim_page_checkpoints
    WHERE claim_set_id=NEW.id)<>NEW.expected_pages THEN
    RAISE EXCEPTION 'Native claim page inventory is incomplete';
  END IF;
  RETURN NEW;
END;
$$;
CREATE TRIGGER native_claim_set_guard BEFORE INSERT OR UPDATE ON native_claim_sets
  FOR EACH ROW EXECUTE FUNCTION guard_native_claim_set();

CREATE FUNCTION guard_native_claim_content() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE target_set uuid; header_state text;
BEGIN
  IF TG_TABLE_NAME='extraction_claims' THEN
    IF TG_OP='UPDATE' AND OLD.origin_kind='native_structure' THEN
      RAISE EXCEPTION 'Native claims are immutable';
    END IF;
    IF NEW.origin_kind<>'native_structure' THEN RETURN NEW; END IF;
    IF TG_OP='UPDATE' THEN RAISE EXCEPTION 'Legacy claims cannot change origin'; END IF;
    target_set:=NEW.native_claim_set_id;
  ELSE
    IF TG_OP='UPDATE' THEN RAISE EXCEPTION 'Native claim checkpoints are immutable'; END IF;
    target_set:=NEW.claim_set_id;
  END IF;
  SELECT state INTO header_state FROM native_claim_sets WHERE id=target_set FOR UPDATE;
  IF header_state IS DISTINCT FROM 'building' THEN
    RAISE EXCEPTION 'Native claim checkpoint stage is unavailable';
  END IF;
  RETURN NEW;
END;
$$;
CREATE TRIGGER native_claim_page_guard BEFORE INSERT OR UPDATE ON native_claim_page_checkpoints
  FOR EACH ROW EXECUTE FUNCTION guard_native_claim_content();
CREATE TRIGGER extraction_claim_native_guard BEFORE INSERT OR UPDATE ON extraction_claims
  FOR EACH ROW EXECUTE FUNCTION guard_native_claim_content();

CREATE FUNCTION retain_native_claim_history() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF TG_TABLE_NAME='extraction_claims' THEN
    IF OLD.origin_kind<>'native_structure' THEN RETURN OLD; END IF;
  END IF;
  IF EXISTS(SELECT 1 FROM documents WHERE id=OLD.document_id) THEN
    RAISE EXCEPTION 'Native claim history is retained with its document';
  END IF;
  RETURN OLD;
END;
$$;
CREATE TRIGGER native_claim_set_retention BEFORE DELETE ON native_claim_sets
  FOR EACH ROW EXECUTE FUNCTION retain_native_claim_history();
CREATE TRIGGER native_claim_page_retention BEFORE DELETE ON native_claim_page_checkpoints
  FOR EACH ROW EXECUTE FUNCTION retain_native_claim_history();
CREATE TRIGGER extraction_claim_native_retention BEFORE DELETE ON extraction_claims
  FOR EACH ROW EXECUTE FUNCTION retain_native_claim_history();

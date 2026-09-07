-- Hidden candidates only: no legacy structure/vector rows or current pointers change.
SET search_path TO structura, public;

CREATE TABLE document_index_generations (
  id uuid PRIMARY KEY,
  document_id uuid NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  household_id uuid NOT NULL,
  processing_run_id uuid NOT NULL,
  parse_generation_id uuid NOT NULL,
  producer_job_id uuid NOT NULL,
  slot text NOT NULL DEFAULT 'native-parse-candidate-v1'
    CHECK (slot = 'native-parse-candidate-v1'),
  generation bigint NOT NULL CHECK (generation > 0),
  request_key uuid NOT NULL,
  structure_sha256 text NOT NULL CHECK (structure_sha256 ~ '^[a-f0-9]{64}$'),
  inventory_sha256 text NOT NULL CHECK (inventory_sha256 ~ '^[a-f0-9]{64}$'),
  parse_config_sha256 text NOT NULL CHECK (parse_config_sha256 ~ '^[a-f0-9]{64}$'),
  config_json jsonb NOT NULL CHECK (jsonb_typeof(config_json) = 'object'),
  config_sha256 text NOT NULL CHECK (config_sha256 ~ '^[a-f0-9]{64}$'),
  state text NOT NULL DEFAULT 'preparing' CHECK (state IN ('preparing','embedding','sealed')),
  manifest_json jsonb,
  manifest_sha256 text CHECK (manifest_sha256 IS NULL OR manifest_sha256 ~ '^[a-f0-9]{64}$'),
  completion_json jsonb,
  completion_sha256 text CHECK (completion_sha256 IS NULL OR completion_sha256 ~ '^[a-f0-9]{64}$'),
  revoked_at timestamptz,
  sealed_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  UNIQUE (document_id, slot, generation),
  UNIQUE (processing_run_id, request_key),
  UNIQUE (id, document_id, parse_generation_id),
  FOREIGN KEY (processing_run_id, document_id, household_id, parse_generation_id)
    REFERENCES document_processing_runs(id, document_id, household_id, parse_generation_id),
  FOREIGN KEY (producer_job_id, processing_run_id, parse_generation_id)
    REFERENCES pipeline_jobs(id, processing_run_id, parse_generation_id),
  CHECK ((state <> 'preparing') = (manifest_json IS NOT NULL)),
  CHECK ((manifest_json IS NULL) = (manifest_sha256 IS NULL)),
  CHECK ((state = 'sealed') = (completion_json IS NOT NULL)),
  CHECK ((completion_json IS NULL) = (completion_sha256 IS NULL)),
  CHECK ((state = 'sealed') = (sealed_at IS NOT NULL))
);
CREATE UNIQUE INDEX document_index_candidates_one_authorized_slot
  ON document_index_generations(document_id, slot) WHERE revoked_at IS NULL;

CREATE TABLE document_generation_render_assets (
  id uuid PRIMARY KEY,
  index_generation_id uuid NOT NULL,
  document_id uuid NOT NULL,
  parse_generation_id uuid NOT NULL,
  original_asset_id uuid NOT NULL REFERENCES document_assets(id),
  page_number integer NOT NULL CHECK (page_number > 0),
  page_id uuid NOT NULL,
  asset_json jsonb NOT NULL CHECK (jsonb_typeof(asset_json) = 'object'),
  content_sha256 text NOT NULL CHECK (content_sha256 ~ '^[a-f0-9]{64}$'),
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  UNIQUE (index_generation_id, page_number),
  UNIQUE (id, index_generation_id),
  FOREIGN KEY (index_generation_id, document_id, parse_generation_id)
    REFERENCES document_index_generations(id, document_id, parse_generation_id) ON DELETE CASCADE,
  FOREIGN KEY (parse_generation_id, page_number)
    REFERENCES document_parse_page_checkpoints(parse_generation_id, page_number)
);

CREATE TABLE document_index_inputs (
  id uuid PRIMARY KEY,
  index_generation_id uuid NOT NULL REFERENCES document_index_generations(id) ON DELETE CASCADE,
  ordinal integer NOT NULL CHECK (ordinal >= 0),
  modality text NOT NULL CHECK (modality IN ('text','visual')),
  render_asset_id uuid,
  input_json jsonb NOT NULL CHECK (jsonb_typeof(input_json) = 'object'),
  content_sha256 text NOT NULL CHECK (content_sha256 ~ '^[a-f0-9]{64}$'),
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  UNIQUE (index_generation_id, ordinal),
  UNIQUE (id, index_generation_id, modality),
  FOREIGN KEY (render_asset_id, index_generation_id)
    REFERENCES document_generation_render_assets(id, index_generation_id),
  CHECK ((modality = 'visual') = (render_asset_id IS NOT NULL))
);

CREATE INDEX document_generation_render_uri
  ON document_generation_render_assets((asset_json->>'uri'));
CREATE INDEX document_generation_render_image_sha256
  ON document_generation_render_assets((asset_json->'source'->>'image_sha256'));

CREATE TABLE document_index_vector_checkpoints (
  input_id uuid PRIMARY KEY,
  index_generation_id uuid NOT NULL,
  modality text NOT NULL CHECK (modality IN ('text','visual')),
  dimensions integer NOT NULL,
  embedding vector NOT NULL,
  vector_sha256 text NOT NULL CHECK (vector_sha256 ~ '^[a-f0-9]{64}$'),
  observation_json jsonb NOT NULL CHECK (jsonb_typeof(observation_json) = 'object'),
  content_sha256 text NOT NULL CHECK (content_sha256 ~ '^[a-f0-9]{64}$'),
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  FOREIGN KEY (input_id, index_generation_id, modality)
    REFERENCES document_index_inputs(id, index_generation_id, modality) ON DELETE CASCADE,
  CHECK (vector_dims(embedding) = dimensions),
  CHECK ((modality = 'text' AND dimensions = 1536) OR (modality = 'visual' AND dimensions = 2048))
);

CREATE FUNCTION preserve_native_index_header() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF TG_OP = 'INSERT' THEN
    IF NEW.state <> 'preparing' OR NEW.revoked_at IS NOT NULL OR NOT EXISTS (
      SELECT 1 FROM document_parse_generations g JOIN document_processing_runs r ON r.id=g.creator_run_id
      WHERE g.id=NEW.parse_generation_id AND g.document_id=NEW.document_id AND g.state='sealed'
        AND g.structure_sha256=NEW.structure_sha256 AND g.inventory_sha256=NEW.inventory_sha256
        AND r.id=NEW.processing_run_id AND r.config_sha256=NEW.parse_config_sha256
    ) THEN RAISE EXCEPTION 'Native index requires exact sealed source identity'; END IF;
    RETURN NEW;
  END IF;
  IF ROW(NEW.id,NEW.document_id,NEW.household_id,NEW.processing_run_id,NEW.parse_generation_id,
         NEW.producer_job_id,NEW.slot,NEW.generation,NEW.request_key,NEW.structure_sha256,
         NEW.inventory_sha256,NEW.parse_config_sha256,NEW.config_json,NEW.config_sha256,NEW.created_at)
    IS DISTINCT FROM ROW(OLD.id,OLD.document_id,OLD.household_id,OLD.processing_run_id,OLD.parse_generation_id,
         OLD.producer_job_id,OLD.slot,OLD.generation,OLD.request_key,OLD.structure_sha256,
         OLD.inventory_sha256,OLD.parse_config_sha256,OLD.config_json,OLD.config_sha256,OLD.created_at)
    OR (OLD.revoked_at IS NOT NULL AND NEW IS DISTINCT FROM OLD)
    OR (OLD.manifest_json IS NOT NULL AND ROW(NEW.manifest_json,NEW.manifest_sha256)
        IS DISTINCT FROM ROW(OLD.manifest_json,OLD.manifest_sha256))
    OR (OLD.completion_json IS NOT NULL AND ROW(NEW.completion_json,NEW.completion_sha256,NEW.sealed_at)
        IS DISTINCT FROM ROW(OLD.completion_json,OLD.completion_sha256,OLD.sealed_at))
    OR (OLD.state='embedding' AND NEW.state='preparing')
    OR (OLD.state='sealed' AND NEW.state<>'sealed')
    OR (OLD.state='preparing' AND NEW.state='sealed') THEN
    RAISE EXCEPTION 'Native index identity and sealed content are immutable';
  END IF;
  RETURN NEW;
END;
$$;
CREATE TRIGGER document_index_header_identity BEFORE INSERT OR UPDATE ON document_index_generations
  FOR EACH ROW EXECUTE FUNCTION preserve_native_index_header();

CREATE FUNCTION guard_native_index_checkpoint() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE header_state text; revoked timestamptz;
BEGIN
  IF TG_OP='UPDATE' THEN RAISE EXCEPTION 'Native index checkpoints are immutable'; END IF;
  SELECT state,revoked_at INTO header_state,revoked FROM document_index_generations
    WHERE id=NEW.index_generation_id FOR UPDATE;
  IF revoked IS NOT NULL OR header_state IS NULL
    OR (TG_TABLE_NAME='document_index_vector_checkpoints' AND header_state<>'embedding')
    OR (TG_TABLE_NAME<>'document_index_vector_checkpoints' AND header_state<>'preparing') THEN
    RAISE EXCEPTION 'Native index checkpoint stage is unavailable';
  END IF;
  RETURN NEW;
END;
$$;
CREATE TRIGGER document_index_input_guard BEFORE INSERT OR UPDATE ON document_index_inputs
  FOR EACH ROW EXECUTE FUNCTION guard_native_index_checkpoint();
CREATE TRIGGER document_index_render_guard BEFORE INSERT OR UPDATE ON document_generation_render_assets
  FOR EACH ROW EXECUTE FUNCTION guard_native_index_checkpoint();
CREATE TRIGGER document_index_vector_guard BEFORE INSERT OR UPDATE ON document_index_vector_checkpoints
  FOR EACH ROW EXECUTE FUNCTION guard_native_index_checkpoint();

CREATE FUNCTION retain_native_index_history() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE owner_document uuid;
BEGIN
  IF TG_TABLE_NAME='document_index_generations' THEN owner_document:=OLD.document_id;
  ELSE SELECT document_id INTO owner_document FROM document_index_generations WHERE id=OLD.index_generation_id;
  END IF;
  IF EXISTS(SELECT 1 FROM documents WHERE id=owner_document) THEN
    RAISE EXCEPTION 'Native index history is retained with its document';
  END IF;
  RETURN OLD;
END;
$$;
CREATE TRIGGER document_index_header_retention BEFORE DELETE ON document_index_generations
  FOR EACH ROW EXECUTE FUNCTION retain_native_index_history();
CREATE TRIGGER document_index_input_retention BEFORE DELETE ON document_index_inputs
  FOR EACH ROW EXECUTE FUNCTION retain_native_index_history();
CREATE TRIGGER document_index_render_retention BEFORE DELETE ON document_generation_render_assets
  FOR EACH ROW EXECUTE FUNCTION retain_native_index_history();
CREATE TRIGGER document_index_vector_retention BEFORE DELETE ON document_index_vector_checkpoints
  FOR EACH ROW EXECUTE FUNCTION retain_native_index_history();

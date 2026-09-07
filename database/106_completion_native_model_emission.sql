-- Hidden raw-member-bound model claims. No current/canonical/index activation.
SET search_path TO structura, public;

ALTER TABLE native_claim_sets
  ADD COLUMN interpretation_kind text NOT NULL DEFAULT 'structure_normalization'
    CHECK (interpretation_kind IN ('structure_normalization','model_emission'));
ALTER TABLE document_parse_page_checkpoints ADD CONSTRAINT parse_checkpoint_content_identity
  UNIQUE(parse_generation_id,page_number,content_sha256);
ALTER TABLE native_claim_page_checkpoints
  ADD COLUMN source_checkpoint_sha256 text,
  ADD COLUMN source_members_json jsonb,
  ADD CONSTRAINT native_model_page_checkpoint_identity
    FOREIGN KEY(parse_generation_id,page_number,source_checkpoint_sha256)
    REFERENCES document_parse_page_checkpoints(parse_generation_id,page_number,content_sha256)
    DEFERRABLE INITIALLY DEFERRED,
  DROP CONSTRAINT native_claim_page_checkpoints_claim_count_check,
  ADD CONSTRAINT native_claim_page_count_bound CHECK(claim_count BETWEEN 0 AND 3000);
ALTER TABLE extraction_claims
  ADD COLUMN native_member_index integer,
  ADD COLUMN native_member_sha256 text,
  DROP CONSTRAINT extraction_claims_value_type_check,
  ADD CONSTRAINT extraction_claim_value_types CHECK (
    value_type IN ('money','date','quantity','identifier','party','enum','text','number','boolean','object')
    OR (origin_kind='native_model_emission' AND value_type IN ('time','identifiers'))),
  ADD CONSTRAINT extraction_claim_member_branch CHECK (
    (origin_kind<>'native_model_emission' AND native_member_index IS NULL AND native_member_sha256 IS NULL)
    OR (origin_kind='native_model_emission' AND native_member_index IS NOT NULL
      AND native_member_index BETWEEN 0 AND 2999 AND native_member_sha256 IS NOT NULL
      AND native_member_sha256 ~ '^[a-f0-9]{64}$')),
  DROP CONSTRAINT extraction_claim_origin_branch,
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
    OR
    (origin_kind='native_model_emission' AND extraction_id IS NULL
      AND native_claim_set_id IS NOT NULL AND native_page_number IS NOT NULL
      AND native_page_number BETWEEN 1 AND 500 AND native_payload_json IS NOT NULL
      AND jsonb_typeof(native_payload_json)='object' AND native_content_sha256 IS NOT NULL
      AND native_content_sha256 ~ '^[a-f0-9]{64}$'
      AND source_engine='qwen3_8_27b' AND method='model_emission:v1'
      AND semantic_annotation_id IS NULL AND source_semantic_region_id IS NULL AND confidence IS NULL
      AND native_payload_json->>'schema_version' IS NOT DISTINCT FROM 'native_model_claim.v1'
      AND native_payload_json->>'derivation' IS NOT DISTINCT FROM 'model_emission'
      AND native_payload_json->>'interpretation_origin' IS NOT DISTINCT FROM 'model_emission'
      AND native_payload_json->>'source_engine' IS NOT DISTINCT FROM source_engine
      AND native_payload_json->>'claim_id' IS NOT DISTINCT FROM claim_id
      AND native_payload_json->>'document_id' IS NOT DISTINCT FROM document_id::text
      AND native_payload_json->>'claim_set_id' IS NOT DISTINCT FROM native_claim_set_id::text
      AND native_payload_json->'proposed'->>'raw_value' IS NOT DISTINCT FROM raw_value
      AND native_payload_json->'proposed'->>'canonical_key' IS NOT DISTINCT FROM canonical_key
      AND native_payload_json->'proposed'->>'value_type' IS NOT DISTINCT FROM value_type
      AND native_payload_json->'proposed'->'typed_value' IS NOT DISTINCT FROM typed_value_json
      AND jsonb_typeof(native_payload_json->'raw_member_json') IS NOT DISTINCT FROM 'object'
      AND native_payload_json->'raw_member_json'->>'canonical_key' IS NOT DISTINCT FROM canonical_key
      AND native_payload_json->'raw_member_json'->>'value_type' IS NOT DISTINCT FROM value_type
      AND native_payload_json->'raw_member_json'->>'raw_value' IS NOT DISTINCT FROM raw_value
      AND native_payload_json->'raw_member_json'->'typed_value' IS NOT DISTINCT FROM typed_value_json
      AND native_payload_json->'anchor' IS NOT DISTINCT FROM anchor_json
      AND native_payload_json->>'group_id' IS NOT DISTINCT FROM group_id
      AND native_payload_json->'member'->>'index' IS NOT DISTINCT FROM native_member_index::text
      AND native_payload_json->'member'->>'pointer' IS NOT DISTINCT FROM '/extraction/claims/'||native_member_index::text
      AND native_payload_json->'member'->>'canonical_member_sha256' IS NOT DISTINCT FROM native_member_sha256
      AND native_payload_json->'member'->>'claim_id' IS NOT DISTINCT FROM claim_id
      AND native_payload_json->'requires_review' IS NOT DISTINCT FROM 'true'::jsonb
      AND native_payload_json->>'source_pixel_support' IS NOT DISTINCT FROM 'not_evaluated')
  );
CREATE UNIQUE INDEX native_model_claim_member_identity
  ON extraction_claims(native_claim_set_id,native_page_number,native_member_index)
  WHERE origin_kind='native_model_emission';

CREATE OR REPLACE FUNCTION guard_native_claim_set() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF (NEW.interpretation_kind='structure_normalization' AND (
        NEW.configuration_json->>'schema_version' IS DISTINCT FROM 'native_claim_configuration.v1'
        OR NEW.configuration_json->>'derivation' IS DISTINCT FROM 'structure_normalization'))
    OR (NEW.interpretation_kind='model_emission' AND (
        NEW.configuration_json->>'schema_version' IS DISTINCT FROM 'native_model_emission_configuration.v1'
        OR NEW.configuration_json->>'derivation' IS DISTINCT FROM 'model_emission')) THEN
    RAISE EXCEPTION 'Native claim interpretation branch is inconsistent';
  END IF;
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
        AND (NEW.interpretation_kind='structure_normalization' OR (
          r.config_json->>'output_schema_version'='structura.page_understanding.v2'
          AND NEW.configuration_json->'definitions'=r.config_json->'definitions'))
    ) THEN RAISE EXCEPTION 'Native claims require an exact sealed parse source'; END IF;
    RETURN NEW;
  END IF;
  IF ROW(NEW.id,NEW.document_id,NEW.household_id,NEW.processing_run_id,NEW.parse_generation_id,
         NEW.producer_job_id,NEW.configuration_json,NEW.configuration_sha256,
         NEW.source_manifest_json,NEW.source_manifest_sha256,NEW.expected_pages,NEW.created_at,
         NEW.interpretation_kind)
    IS DISTINCT FROM ROW(OLD.id,OLD.document_id,OLD.household_id,OLD.processing_run_id,OLD.parse_generation_id,
         OLD.producer_job_id,OLD.configuration_json,OLD.configuration_sha256,
         OLD.source_manifest_json,OLD.source_manifest_sha256,OLD.expected_pages,OLD.created_at,
         OLD.interpretation_kind)
    OR (OLD.state='sealed' AND NEW IS DISTINCT FROM OLD) THEN
    RAISE EXCEPTION 'Native claim set identity and sealed content are immutable';
  END IF;
  IF NEW.state='sealed' THEN
    IF (SELECT count(*) FROM native_claim_page_checkpoints WHERE claim_set_id=NEW.id)<>NEW.expected_pages
      OR EXISTS (SELECT 1 FROM native_claim_page_checkpoints p WHERE p.claim_set_id=NEW.id
        AND (p.page_number>NEW.expected_pages OR p.claim_count<>(
          SELECT count(*) FROM extraction_claims c WHERE c.native_claim_set_id=p.claim_set_id
            AND c.native_page_number=p.page_number))) THEN
      RAISE EXCEPTION 'Native claim page inventory is incomplete';
    END IF;
    IF NEW.interpretation_kind='model_emission' AND EXISTS (
      SELECT 1 FROM native_claim_page_checkpoints p,
        LATERAL jsonb_array_elements(p.request_json->'members') m
      WHERE p.claim_set_id=NEW.id AND NOT EXISTS (
        SELECT 1 FROM extraction_claims c WHERE c.native_claim_set_id=p.claim_set_id
          AND c.native_page_number=p.page_number AND c.origin_kind='native_model_emission'
          AND c.native_member_index::text=m->>'index' AND c.claim_id=m->>'claim_id'
          AND c.native_member_sha256=m->>'canonical_member_sha256')) THEN
      RAISE EXCEPTION 'Native model member inventory is inconsistent';
    END IF;
  END IF;
  RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION guard_native_claim_content() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE target_set uuid; header native_claim_sets%ROWTYPE; source_document jsonb;
BEGIN
  IF TG_TABLE_NAME='extraction_claims' THEN
    IF TG_OP='UPDATE' AND OLD.origin_kind IN ('native_structure','native_model_emission') THEN
      RAISE EXCEPTION 'Native claims are immutable';
    END IF;
    IF NEW.origin_kind NOT IN ('native_structure','native_model_emission') THEN RETURN NEW; END IF;
    IF TG_OP='UPDATE' THEN RAISE EXCEPTION 'Legacy claims cannot change origin'; END IF;
    target_set:=NEW.native_claim_set_id;
  ELSE
    IF TG_OP='UPDATE' THEN RAISE EXCEPTION 'Native claim checkpoints are immutable'; END IF;
    target_set:=NEW.claim_set_id;
  END IF;
  SELECT * INTO header FROM native_claim_sets WHERE id=target_set FOR UPDATE;
  IF header.state IS DISTINCT FROM 'building' THEN
    RAISE EXCEPTION 'Native claim checkpoint stage is unavailable';
  END IF;
  IF TG_TABLE_NAME='extraction_claims' THEN
    IF (NEW.origin_kind='native_structure')<>(header.interpretation_kind='structure_normalization')
      OR NEW.native_payload_json->>'configuration_sha256' IS DISTINCT FROM header.configuration_sha256 THEN
      RAISE EXCEPTION 'Native claim source branch or configuration is inconsistent';
    END IF;
    IF NEW.origin_kind='native_model_emission' AND NOT EXISTS (
      SELECT 1 FROM native_claim_page_checkpoints p
      JOIN document_parse_page_checkpoints s ON s.parse_generation_id=p.parse_generation_id
        AND s.page_number=p.page_number AND s.content_sha256=p.source_checkpoint_sha256
      WHERE p.claim_set_id=target_set
        AND p.page_number=NEW.native_page_number AND p.document_id=NEW.document_id
        AND NEW.native_payload_json->>'checkpoint_sha256'=p.source_checkpoint_sha256
        AND NEW.native_payload_json->>'raw_output_sha256'=p.request_json->>'raw_output_sha256'
        AND NEW.native_payload_json->'anchor'->>'page_id'=p.page_id::text
        AND NEW.native_payload_json->'anchor'->>'page_number'=p.page_number::text
        AND NEW.native_payload_json->'anchor'->>'parse_generation_id'=p.parse_generation_id::text
        AND NEW.native_payload_json->>'invocation_request_id'=s.invocation_json->>'request_id'
        AND NEW.native_payload_json->>'source_engine'=s.invocation_json->>'source_engine'
        AND NEW.native_payload_json->'anchor'->>'source_page_image_sha256'=s.page_json->'source'->>'image_sha256'
        AND NEW.native_payload_json->'raw_member_json'=
          p.source_members_json->NEW.native_member_index
    ) THEN RAISE EXCEPTION 'Native model claim checkpoint is inconsistent'; END IF;
  ELSIF header.interpretation_kind='structure_normalization' THEN
    IF NEW.claim_count>1000 OR NEW.source_checkpoint_sha256 IS NOT NULL
      OR NEW.source_members_json IS NOT NULL
      OR NEW.request_json->>'schema_version' IS DISTINCT FROM 'native_claim_page_request.v1' THEN
      RAISE EXCEPTION 'Recorded-text claim page contract is unchanged';
    END IF;
  ELSE
    IF NEW.source_checkpoint_sha256 IS NULL OR NEW.source_checkpoint_sha256 !~ '^[a-f0-9]{64}$'
      OR NEW.request_json->>'schema_version' IS DISTINCT FROM 'native_model_claim_page.v1'
      OR NEW.request_json->>'derivation' IS DISTINCT FROM 'model_emission'
      OR NEW.request_json->>'checkpoint_sha256' IS DISTINCT FROM NEW.source_checkpoint_sha256
      OR NEW.request_json->>'page_id' IS DISTINCT FROM NEW.page_id::text
      OR NEW.request_json->>'page_number' IS DISTINCT FROM NEW.page_number::text
      OR jsonb_typeof(NEW.request_json->'members') IS DISTINCT FROM 'array'
      OR jsonb_typeof(NEW.source_members_json) IS DISTINCT FROM 'array' THEN
      RAISE EXCEPTION 'Native model page source or accounting is inconsistent';
    END IF;
    IF jsonb_array_length(NEW.request_json->'members')<>NEW.claim_count
      OR EXISTS (SELECT 1 FROM jsonb_array_elements(NEW.request_json->'members') WITH ORDINALITY AS x(m,n)
        WHERE m->>'index' IS DISTINCT FROM (n-1)::text
          OR m->>'pointer' IS DISTINCT FROM '/extraction/claims/'||(n-1)::text) THEN
      RAISE EXCEPTION 'Native model page member accounting is incomplete';
    END IF;
    -- Parse the exact source envelope once at page admission. Each later claim
    -- references this immutable checked JSON cache instead of reparsing raw text.
    SELECT s.raw_output::jsonb INTO source_document FROM document_parse_page_checkpoints s
      WHERE s.parse_generation_id=NEW.parse_generation_id AND s.page_number=NEW.page_number
        AND s.content_sha256=NEW.source_checkpoint_sha256
        AND NEW.request_json->>'raw_output_sha256'=s.invocation_json->>'raw_output_sha256';
    IF source_document IS NULL
      OR NEW.request_json->'classification_json' IS DISTINCT FROM source_document->'classification'
      OR NEW.request_json->'coverage_json' IS DISTINCT FROM (source_document->'extraction')-'claims'
      OR NEW.source_members_json IS DISTINCT FROM source_document->'extraction'->'claims'
      OR NEW.claim_count<>jsonb_array_length(NEW.source_members_json) THEN
      RAISE EXCEPTION 'Native model page raw source is inconsistent';
    END IF;
  END IF;
  RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION retain_native_claim_history() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF TG_TABLE_NAME='extraction_claims' THEN
    IF OLD.origin_kind NOT IN ('native_structure','native_model_emission') THEN RETURN OLD; END IF;
  END IF;
  IF EXISTS(SELECT 1 FROM documents WHERE id=OLD.document_id) THEN
    RAISE EXCEPTION 'Native claim history is retained with its document';
  END IF;
  RETURN OLD;
END;
$$;

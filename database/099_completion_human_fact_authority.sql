-- Durable human authority foundation. Writer/response integration is separate.
-- Never synthesize an accepted fact for a rejection or restore historical metadata.
SET search_path TO structura, public;

ALTER TABLE canonical_fields ADD CONSTRAINT canonical_fields_authority_identity
  UNIQUE (id, document_id, field_path, ordinal);
ALTER TABLE review_events ADD CONSTRAINT review_events_authority_identity UNIQUE (id, document_id);
ALTER TABLE audit_events ADD CONSTRAINT audit_events_authority_identity UNIQUE (id, document_id);

CREATE TABLE canonical_field_decisions (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  document_id uuid NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  field_path text NOT NULL CHECK (length(btrim(field_path)) > 0),
  ordinal integer NOT NULL CHECK (ordinal > 0),
  revision uuid NOT NULL UNIQUE DEFAULT gen_random_uuid(),
  disposition text NOT NULL CHECK (disposition IN ('confirmed','corrected','rejected','protected_legacy')),
  origin text NOT NULL CHECK (origin IN ('live_review','legacy_current_field')),
  canonical_field_id uuid,
  review_event_id uuid,
  actor_user_id uuid REFERENCES users(id) ON DELETE SET NULL,
  decided_at timestamptz,
  recorded_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  UNIQUE (document_id, field_path, ordinal),
  FOREIGN KEY (canonical_field_id, document_id, field_path, ordinal)
    REFERENCES canonical_fields(id, document_id, field_path, ordinal)
    ON DELETE SET NULL (canonical_field_id) DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY (review_event_id, document_id) REFERENCES review_events(id, document_id)
    ON DELETE SET NULL (review_event_id) DEFERRABLE INITIALLY DEFERRED,
  CHECK (origin <> 'live_review' OR (disposition <> 'protected_legacy' AND decided_at IS NOT NULL))
);

CREATE TABLE canonical_field_path_guards (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  document_id uuid NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  field_path text NOT NULL CHECK (length(btrim(field_path)) > 0),
  revision uuid NOT NULL UNIQUE DEFAULT gen_random_uuid(),
  origin text NOT NULL DEFAULT 'legacy_path_rejection' CHECK (origin='legacy_path_rejection'),
  review_event_id uuid,
  status text NOT NULL DEFAULT 'active' CHECK (status IN ('active','resolved')),
  actor_user_id uuid REFERENCES users(id) ON DELETE SET NULL,
  recorded_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  UNIQUE (document_id, field_path),
  FOREIGN KEY (review_event_id, document_id) REFERENCES review_events(id, document_id)
    ON DELETE SET NULL (review_event_id) DEFERRABLE INITIALLY DEFERRED
);

CREATE FUNCTION valid_manual_metadata_value(property_name text, value jsonb)
RETURNS boolean LANGUAGE plpgsql STABLE AS $$
DECLARE parsed_date date;
BEGIN
  IF value IS NULL OR property_name IS NULL THEN RETURN false; END IF;
  IF property_name='classification' THEN
    IF jsonb_typeof(value)<>'object' THEN RETURN false; END IF;
    RETURN COALESCE(jsonb_typeof(value)='object'
      AND value ? 'family' AND value ? 'subtype'
      AND value - ARRAY['family','subtype'] = '{}'::jsonb
      AND jsonb_typeof(value->'family')='string'
      AND (value->>'family')::document_family_enum IS NOT NULL
      AND (jsonb_typeof(value->'subtype')='string' OR value->'subtype'='null'::jsonb),false);
  END IF;
  IF property_name='document_date' THEN
    IF value='null'::jsonb THEN RETURN true; END IF;
    IF jsonb_typeof(value)<>'string' OR (value #>> '{}') !~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$' THEN
      RETURN false;
    END IF;
    parsed_date := (value #>> '{}')::date;
    RETURN to_char(parsed_date,'YYYY-MM-DD') = (value #>> '{}');
  END IF;
  RETURN false;
EXCEPTION WHEN invalid_text_representation OR datetime_field_overflow OR invalid_datetime_format
  THEN RETURN false;
END;
$$;

CREATE TABLE document_metadata_decisions (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  document_id uuid NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  property text NOT NULL CHECK (property IN ('classification','document_date')),
  revision uuid NOT NULL UNIQUE DEFAULT gen_random_uuid(),
  value_schema_version text NOT NULL DEFAULT 'manual_metadata.v1'
    CHECK (value_schema_version='manual_metadata.v1'),
  value_json jsonb NOT NULL,
  origin text NOT NULL CHECK (origin IN ('live_review','legacy_matching_review','legacy_matching_filing')),
  review_event_id uuid,
  audit_event_id bigint,
  actor_user_id uuid REFERENCES users(id) ON DELETE SET NULL,
  decided_at timestamptz,
  recorded_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  UNIQUE (document_id, property),
  FOREIGN KEY (review_event_id, document_id) REFERENCES review_events(id, document_id)
    ON DELETE SET NULL (review_event_id) DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY (audit_event_id, document_id) REFERENCES audit_events(id, document_id)
    ON DELETE SET NULL (audit_event_id) DEFERRABLE INITIALLY DEFERRED,
  CHECK (valid_manual_metadata_value(property, value_json)),
  CHECK (origin <> 'live_review' OR decided_at IS NOT NULL),
  CHECK (property <> 'classification' OR audit_event_id IS NULL),
  CHECK (property <> 'document_date' OR review_event_id IS NULL)
);

CREATE TABLE document_fact_projection_state (
  document_id uuid PRIMARY KEY REFERENCES documents(id) ON DELETE CASCADE,
  schema_version text NOT NULL DEFAULT 'accepted_fact_projection.v1'
    CHECK (schema_version='accepted_fact_projection.v1'),
  accepted_fact_revision bigint NOT NULL DEFAULT 0 CHECK (accepted_fact_revision >= 0),
  projection_revision bigint NOT NULL DEFAULT 0 CHECK (projection_revision >= accepted_fact_revision),
  state text NOT NULL DEFAULT 'unestablished' CHECK (state IN ('unestablished','current')),
  accepted_facts_sha256 text CHECK (accepted_facts_sha256 ~ '^[a-f0-9]{64}$'),
  indexed_metadata_sha256 text CHECK (indexed_metadata_sha256 ~ '^[a-f0-9]{64}$'),
  rollup_json jsonb CHECK (jsonb_typeof(rollup_json)='object'),
  legacy_metadata_json jsonb NOT NULL CHECK (jsonb_typeof(legacy_metadata_json)='object'),
  recorded_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  CHECK ((state='current') = (accepted_facts_sha256 IS NOT NULL)),
  CHECK ((state='current') = (indexed_metadata_sha256 IS NOT NULL)),
  CHECK ((state='current') = (rollup_json IS NOT NULL)),
  CHECK (state <> 'current' OR accepted_fact_revision > 0),
  CHECK (state <> 'unestablished' OR (accepted_fact_revision=0 AND projection_revision=0))
);

-- Human markers establish authority independently of an actor FK. A rejected
-- status always wins; uncertain legacy status protects without declaring acceptance.
INSERT INTO canonical_field_decisions
  (document_id,field_path,ordinal,disposition,origin,canonical_field_id,actor_user_id,decided_at)
SELECT document_id,field_path,ordinal,
  CASE WHEN review_status='rejected' THEN 'rejected'
       WHEN review_status NOT IN ('auto_accepted','user_confirmed','user_corrected') THEN 'protected_legacy'
       WHEN source_kind='human' OR review_status='user_corrected' THEN 'corrected'
       ELSE 'confirmed' END,
  'legacy_current_field',id,accepted_by_user_id,accepted_at
FROM canonical_fields
WHERE source_kind='human' OR review_status IN ('user_confirmed','user_corrected')
   OR accepted_by_user_id IS NOT NULL;

-- Old rejection events did not reliably record an ordinal. Preserve an explicit
-- path-wide guard; do not invent a scalar canonical row or guess ordinal one.
INSERT INTO canonical_field_path_guards (document_id,field_path,review_event_id)
SELECT DISTINCT ON (document_id,field_path) document_id,field_path,id
FROM review_events
WHERE action='reject_field' AND field_path IS NOT NULL AND length(btrim(field_path))>0
ORDER BY document_id,field_path,created_at DESC,id DESC;

-- Reclassification has no historical monotonic event counter. Only unanimous
-- recorded human values that exactly match the current pair establish a binding.
WITH unambiguous AS (
  SELECT document_id FROM review_events WHERE action='reclassify_document'
  GROUP BY document_id HAVING count(DISTINCT new_value_json)=1
    AND bool_and(valid_manual_metadata_value('classification',new_value_json))
), source_event AS (
  SELECT DISTINCT ON (e.document_id) e.* FROM review_events e
  JOIN unambiguous u ON u.document_id=e.document_id
  WHERE e.action='reclassify_document'
  ORDER BY e.document_id,e.created_at DESC,e.id DESC
)
INSERT INTO document_metadata_decisions
  (document_id,property,value_json,origin,review_event_id,actor_user_id,decided_at)
SELECT d.id,'classification',e.new_value_json,'legacy_matching_review',e.id,u.id,e.created_at
FROM source_event e JOIN documents d ON d.id=e.document_id
LEFT JOIN users u ON u.id::text=e.actor_label
WHERE valid_manual_metadata_value('classification',e.new_value_json)
  AND e.new_value_json->>'family'=d.document_family::text
  AND (e.new_value_json->>'subtype') IS NOT DISTINCT FROM d.document_subtype;

-- Organization audit IDs are allocated while the document lock is held. Select
-- the last explicit date mutation, including a clear; never restore its value.
WITH source_event AS (
  SELECT DISTINCT ON (document_id) * FROM audit_events
  WHERE event_name='document.organization_updated' AND document_id IS NOT NULL
    AND payload_json->'changed_fields' @> '["documentDate"]'::jsonb
  ORDER BY document_id,id DESC
)
INSERT INTO document_metadata_decisions
  (document_id,property,value_json,origin,audit_event_id,actor_user_id,decided_at)
SELECT d.id,'document_date',e.payload_json #> '{after,documentDate}',
  'legacy_matching_filing',e.id,u.id,e.created_at
FROM source_event e JOIN documents d ON d.id=e.document_id
LEFT JOIN users u ON u.id::text=e.actor_label
WHERE valid_manual_metadata_value('document_date',e.payload_json #> '{after,documentDate}')
  AND e.payload_json #> '{after,documentDate}' = COALESCE(to_jsonb(d.document_date),'null'::jsonb);

-- Revision zero is an unestablished bookkeeping baseline, not a verified empty
-- fact set. Unknown metadata is preserved verbatim and never promoted by migration.
INSERT INTO document_fact_projection_state (document_id,legacy_metadata_json)
SELECT id,jsonb_build_object('schemaVersion','legacy_metadata.v1',
  'classification',jsonb_build_object('family',document_family,'subtype',document_subtype),
  'documentDate',document_date,'counterpartyDisplay',counterparty_display)
FROM documents;

CREATE FUNCTION preserve_human_authority_record() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE old_json jsonb; new_json jsonb; key_name text;
        reference_keys text[] := ARRAY['actor_user_id','canonical_field_id','review_event_id','audit_event_id'];
        reference_cleanup boolean := true;
BEGIN
  IF TG_OP='DELETE' THEN
    IF EXISTS(SELECT 1 FROM documents WHERE id=OLD.document_id) THEN
      RAISE EXCEPTION 'Human authority is retained with its document';
    END IF;
    RETURN OLD;
  END IF;
  old_json:=to_jsonb(OLD); new_json:=to_jsonb(NEW);
  FOREACH key_name IN ARRAY ARRAY['id','document_id','field_path','ordinal','property','created_at'] LOOP
    IF new_json->key_name IS DISTINCT FROM old_json->key_name THEN
      RAISE EXCEPTION 'Human authority identity is immutable';
    END IF;
  END LOOP;
  IF NEW IS NOT DISTINCT FROM OLD THEN RETURN NEW; END IF;
  -- FK cleanup must not erase authority or force a new reviewer decision.
  FOREACH key_name IN ARRAY reference_keys LOOP
    IF new_json->key_name IS DISTINCT FROM old_json->key_name
       AND new_json->key_name IS DISTINCT FROM 'null'::jsonb THEN reference_cleanup:=false; END IF;
  END LOOP;
  IF reference_cleanup AND new_json-reference_keys=old_json-reference_keys THEN RETURN NEW; END IF;
  IF NEW.revision=OLD.revision OR NEW.recorded_at<=OLD.recorded_at THEN
    RAISE EXCEPTION 'A human decision requires a fresh revision and timestamp';
  END IF;
  RETURN NEW;
END;
$$;
CREATE TRIGGER canonical_field_decision_identity BEFORE UPDATE OR DELETE ON canonical_field_decisions
  FOR EACH ROW EXECUTE FUNCTION preserve_human_authority_record();
CREATE TRIGGER canonical_field_path_guard_identity BEFORE UPDATE OR DELETE ON canonical_field_path_guards
  FOR EACH ROW EXECUTE FUNCTION preserve_human_authority_record();
CREATE TRIGGER document_metadata_decision_identity BEFORE UPDATE OR DELETE ON document_metadata_decisions
  FOR EACH ROW EXECUTE FUNCTION preserve_human_authority_record();

CREATE FUNCTION preserve_fact_projection_revision() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF TG_OP='DELETE' THEN
    IF EXISTS(SELECT 1 FROM documents WHERE id=OLD.document_id) THEN
      RAISE EXCEPTION 'Fact projection state is retained with its document';
    END IF;
    RETURN OLD;
  END IF;
  IF NEW.document_id<>OLD.document_id OR NEW.created_at<>OLD.created_at
    OR NEW.legacy_metadata_json IS DISTINCT FROM OLD.legacy_metadata_json THEN
    RAISE EXCEPTION 'Projection identity and legacy snapshot are immutable';
  END IF;
  IF NEW IS NOT DISTINCT FROM OLD THEN RETURN NEW; END IF;
  IF NEW.accepted_fact_revision NOT IN (OLD.accepted_fact_revision,OLD.accepted_fact_revision+1)
    OR NEW.projection_revision<>OLD.projection_revision+1 OR NEW.recorded_at<=OLD.recorded_at
    OR NEW.state<>'current'
    OR ((NEW.accepted_facts_sha256 IS DISTINCT FROM OLD.accepted_facts_sha256)
        <> (NEW.accepted_fact_revision=OLD.accepted_fact_revision+1)) THEN
    RAISE EXCEPTION 'Fact projections require a new monotonic revision';
  END IF;
  RETURN NEW;
END;
$$;
CREATE TRIGGER document_fact_projection_revision BEFORE UPDATE OR DELETE ON document_fact_projection_state
  FOR EACH ROW EXECUTE FUNCTION preserve_fact_projection_revision();

-- Explicit human line selection; no automatic publication or inferred legacy repair.
SET search_path TO structura, public;

ALTER TABLE canonical_line_items ADD COLUMN allowed_amount numeric(18,4),
  ADD COLUMN plan_paid_amount numeric(18,4),
  ADD CONSTRAINT canonical_line_authority_identity UNIQUE(id,document_id,line_item_type,ordinal);
ALTER TABLE line_item_candidates ADD COLUMN decision_version uuid NOT NULL DEFAULT gen_random_uuid(),
  ADD CONSTRAINT line_candidate_authority_identity UNIQUE(id,document_id);
ALTER TABLE document_extractions ADD CONSTRAINT extraction_line_authority_identity UNIQUE(id,document_id);
-- Historical cross-document bindings are debt, not provenance established by this migration.
ALTER TABLE line_item_candidates ADD CONSTRAINT line_candidate_extraction_document
  FOREIGN KEY(extraction_id,document_id) REFERENCES document_extractions(id,document_id)
  DEFERRABLE INITIALLY DEFERRED NOT VALID;
ALTER TABLE canonical_line_items ADD CONSTRAINT canonical_line_candidate_document
  FOREIGN KEY(selected_candidate_id,document_id) REFERENCES line_item_candidates(id,document_id)
  ON DELETE SET NULL(selected_candidate_id) DEFERRABLE INITIALLY DEFERRED NOT VALID;

CREATE TABLE line_item_candidate_decisions (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  document_id uuid NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  source_candidate_id uuid NOT NULL,
  candidate_id uuid,
  revision uuid NOT NULL UNIQUE DEFAULT gen_random_uuid(),
  disposition text NOT NULL CHECK(disposition IN ('accepted','rejected','protected_legacy')),
  origin text NOT NULL CHECK(origin IN ('live_review','legacy_current_line')),
  source_snapshot_json jsonb NOT NULL CHECK(jsonb_typeof(source_snapshot_json)='object'),
  source_snapshot_sha256 text NOT NULL CHECK(source_snapshot_sha256 ~ '^[a-f0-9]{64}$'),
  actor_user_id uuid REFERENCES users(id) ON DELETE SET NULL,
  review_event_id uuid,
  decided_at timestamptz,
  recorded_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  UNIQUE(document_id,source_candidate_id),
  FOREIGN KEY(candidate_id,document_id) REFERENCES line_item_candidates(id,document_id)
    ON DELETE SET NULL(candidate_id) DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY(review_event_id,document_id) REFERENCES review_events(id,document_id)
    ON DELETE SET NULL(review_event_id) DEFERRABLE INITIALLY DEFERRED,
  CHECK(candidate_id IS NULL OR candidate_id=source_candidate_id),
  CHECK(origin<>'live_review' OR (disposition<>'protected_legacy' AND decided_at IS NOT NULL))
);

CREATE TABLE canonical_line_item_decisions (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  document_id uuid NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  line_item_type line_item_type_enum NOT NULL,
  ordinal integer NOT NULL CHECK(ordinal>0),
  canonical_line_item_id uuid NOT NULL,
  revision uuid NOT NULL UNIQUE DEFAULT gen_random_uuid(),
  disposition text NOT NULL CHECK(disposition IN ('confirmed','corrected','rejected','protected_legacy')),
  origin text NOT NULL CHECK(origin IN ('live_review','legacy_current_line')),
  actor_user_id uuid REFERENCES users(id) ON DELETE SET NULL,
  review_event_id uuid,
  decision_event_id uuid,
  decided_at timestamptz,
  recorded_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  UNIQUE(document_id,line_item_type,ordinal),
  FOREIGN KEY(canonical_line_item_id,document_id,line_item_type,ordinal)
    REFERENCES canonical_line_items(id,document_id,line_item_type,ordinal)
    DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY(review_event_id,document_id) REFERENCES review_events(id,document_id)
    ON DELETE SET NULL(review_event_id) DEFERRABLE INITIALLY DEFERRED,
  CHECK(origin<>'live_review' OR (disposition IN ('confirmed','rejected') AND decided_at IS NOT NULL
    AND decision_event_id IS NOT NULL))
);

CREATE TABLE canonical_line_item_source_bindings (
  document_id uuid NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  source_candidate_id uuid NOT NULL,
  candidate_id uuid,
  binding_state text NOT NULL CHECK(binding_state IN ('assigned','legacy_conflict')),
  canonical_line_item_id uuid,
  line_item_type line_item_type_enum,
  ordinal integer,
  source_snapshot_json jsonb NOT NULL CHECK(jsonb_typeof(source_snapshot_json)='object'),
  source_snapshot_sha256 text NOT NULL CHECK(source_snapshot_sha256 ~ '^[a-f0-9]{64}$'),
  recorded_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  PRIMARY KEY(document_id,source_candidate_id),
  UNIQUE(document_id,source_candidate_id,canonical_line_item_id),
  FOREIGN KEY(candidate_id,document_id) REFERENCES line_item_candidates(id,document_id)
    ON DELETE SET NULL(candidate_id) DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY(canonical_line_item_id,document_id,line_item_type,ordinal)
    REFERENCES canonical_line_items(id,document_id,line_item_type,ordinal)
    DEFERRABLE INITIALLY DEFERRED,
  CHECK(candidate_id IS NULL OR candidate_id=source_candidate_id),
  CHECK((binding_state='assigned' AND canonical_line_item_id IS NOT NULL
    AND line_item_type IS NOT NULL AND ordinal IS NOT NULL AND ordinal>0)
    OR (binding_state='legacy_conflict' AND canonical_line_item_id IS NULL
      AND line_item_type IS NULL AND ordinal IS NULL))
);

-- A full, immutable event is distinct from the mutable current decision summary.
CREATE TABLE line_item_decision_events (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  document_id uuid NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  source_candidate_id uuid,
  canonical_line_item_id uuid,
  operation text NOT NULL CHECK(operation IN ('create','replace','reject_selected','reject_candidate')),
  before_json jsonb,
  after_json jsonb,
  source_snapshot_json jsonb,
  actor_user_id uuid REFERENCES users(id) ON DELETE SET NULL,
  review_event_id uuid,
  comment text,
  occurred_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  UNIQUE(id,document_id),
  CHECK(source_candidate_id IS NOT NULL OR canonical_line_item_id IS NOT NULL),
  CHECK((before_json IS NULL OR jsonb_typeof(before_json)='object')
    AND (after_json IS NULL OR jsonb_typeof(after_json)='object')
    AND (source_snapshot_json IS NULL OR jsonb_typeof(source_snapshot_json)='object')),
  CHECK(source_snapshot_json IS NULL OR COALESCE(
    source_snapshot_json->>'schemaVersion'='line_item_source.v1'
    AND source_snapshot_json #>> '{candidate,id}'=source_candidate_id::text
    AND source_snapshot_json #>> '{candidate,document_id}'=document_id::text,false)),
  CHECK(before_json IS NULL OR COALESCE(before_json #>> '{canonical,id}'=canonical_line_item_id::text
    AND before_json #>> '{canonical,documentId}'=document_id::text,false)),
  CHECK(after_json IS NULL OR COALESCE(after_json #>> '{canonical,id}'=canonical_line_item_id::text
    AND after_json #>> '{canonical,documentId}'=document_id::text,false)),
  CHECK((operation='create' AND before_json IS NULL AND after_json IS NOT NULL
      AND canonical_line_item_id IS NOT NULL AND source_snapshot_json IS NOT NULL)
    OR (operation='replace' AND before_json IS NOT NULL AND after_json IS NOT NULL
      AND canonical_line_item_id IS NOT NULL AND source_snapshot_json IS NOT NULL)
    OR (operation='reject_selected' AND before_json IS NOT NULL AND after_json IS NOT NULL
      AND canonical_line_item_id IS NOT NULL)
    OR (operation='reject_candidate' AND before_json IS NULL AND after_json IS NULL
      AND canonical_line_item_id IS NULL AND source_snapshot_json IS NOT NULL)),
  FOREIGN KEY(review_event_id,document_id) REFERENCES review_events(id,document_id)
    ON DELETE SET NULL(review_event_id) DEFERRABLE INITIALLY DEFERRED
);
ALTER TABLE canonical_line_item_decisions ADD CONSTRAINT line_decision_retained_event
 FOREIGN KEY(decision_event_id,document_id) REFERENCES line_item_decision_events(id,document_id)
 DEFERRABLE INITIALLY DEFERRED;
CREATE INDEX line_item_events_canonical ON line_item_decision_events
  (document_id,canonical_line_item_id,occurred_at DESC,id DESC);
CREATE INDEX line_item_events_source ON line_item_decision_events
  (document_id,source_candidate_id,occurred_at DESC,id DESC);

-- Preserve only a demonstrated current human binding. Never manufacture a row
-- from a historical candidate acceptance; protected legacy values are not selected.
INSERT INTO canonical_line_item_decisions
(document_id,line_item_type,ordinal,canonical_line_item_id,disposition,origin,actor_user_id,decided_at)
SELECT document_id,line_item_type,ordinal,id,
 CASE WHEN review_status='rejected' THEN 'rejected'
      WHEN review_status NOT IN ('auto_accepted','user_confirmed','user_corrected') THEN 'protected_legacy'
      WHEN review_status='user_corrected' OR source_kind='human' THEN 'corrected' ELSE 'confirmed' END,
 'legacy_current_line',accepted_by_user_id,accepted_at
FROM canonical_line_items WHERE source_kind='human'
 OR review_status IN ('user_confirmed','user_corrected') OR accepted_by_user_id IS NOT NULL;

-- A source used by several legacy targets remains explicitly unresolved. The
-- NOT VALID reverse FK below enforces new keys without certifying these old rows.
INSERT INTO canonical_line_item_source_bindings
(document_id,source_candidate_id,candidate_id,binding_state,canonical_line_item_id,
 line_item_type,ordinal,source_snapshot_json,source_snapshot_sha256)
SELECT c.document_id,c.selected_candidate_id,
 CASE WHEN bool_and(l.document_id=c.document_id) THEN c.selected_candidate_id ELSE NULL END,
 CASE WHEN count(*)=1 THEN 'assigned' ELSE 'legacy_conflict' END,
 CASE WHEN count(*)=1 THEN (array_agg(c.id))[1] ELSE NULL END,
 CASE WHEN count(*)=1 THEN (array_agg(c.line_item_type))[1] ELSE NULL END,
 CASE WHEN count(*)=1 THEN min(c.ordinal) ELSE NULL END,
 jsonb_build_object('schemaVersion','legacy_line_binding.v1','verifiedSource',false,
   'canonicalLineItemIds',jsonb_agg(c.id ORDER BY c.id)),
 encode(sha256(convert_to(jsonb_agg(c.id ORDER BY c.id)::text,'UTF8')),'hex')
FROM canonical_line_items c LEFT JOIN line_item_candidates l ON l.id=c.selected_candidate_id
WHERE c.selected_candidate_id IS NOT NULL GROUP BY c.document_id,c.selected_candidate_id;

ALTER TABLE canonical_line_items ADD CONSTRAINT canonical_line_selected_source_binding
 FOREIGN KEY(document_id,selected_candidate_id,id)
 REFERENCES canonical_line_item_source_bindings(document_id,source_candidate_id,canonical_line_item_id)
 DEFERRABLE INITIALLY DEFERRED NOT VALID;

CREATE VIEW selected_canonical_line_items AS
SELECT c.* FROM canonical_line_items c LEFT JOIN canonical_line_item_decisions d
 ON d.document_id=c.document_id AND d.line_item_type=c.line_item_type AND d.ordinal=c.ordinal
WHERE c.review_status IN ('auto_accepted','user_confirmed','user_corrected')
 AND (d.id IS NULL OR (d.canonical_line_item_id=c.id AND d.disposition IN ('confirmed','corrected')));

CREATE FUNCTION preserve_line_authority() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE old_json jsonb; new_json jsonb; key_name text;
  cleanup_keys text[]:=ARRAY['actor_user_id','review_event_id','candidate_id'];
  cleanup boolean:=true;
BEGIN
 IF TG_OP='DELETE' THEN
  IF EXISTS(SELECT 1 FROM documents WHERE id=OLD.document_id) THEN
   RAISE EXCEPTION 'Line authority is retained with its document';
  END IF;
  RETURN OLD;
 END IF;
 old_json:=to_jsonb(OLD); new_json:=to_jsonb(NEW);
 FOREACH key_name IN ARRAY ARRAY['id','document_id','source_candidate_id','line_item_type',
   'ordinal','canonical_line_item_id','created_at'] LOOP
  IF new_json->key_name IS DISTINCT FROM old_json->key_name THEN
   RAISE EXCEPTION 'Line authority identity is immutable';
  END IF;
 END LOOP;
 IF NEW IS NOT DISTINCT FROM OLD THEN RETURN NEW; END IF;
 FOREACH key_name IN ARRAY cleanup_keys LOOP
  IF new_json->key_name IS DISTINCT FROM old_json->key_name
    AND new_json->key_name IS DISTINCT FROM 'null'::jsonb THEN cleanup:=false; END IF;
 END LOOP;
 IF cleanup AND new_json-cleanup_keys=old_json-cleanup_keys THEN RETURN NEW; END IF;
 IF TG_TABLE_NAME IN ('canonical_line_item_source_bindings','line_item_decision_events') THEN
  RAISE EXCEPTION 'Line source bindings and history are immutable';
 END IF;
 IF NEW.revision=OLD.revision OR NEW.recorded_at<=OLD.recorded_at THEN
  RAISE EXCEPTION 'A line decision requires a fresh revision and timestamp';
 END IF;
 RETURN NEW;
END;
$$;
CREATE TRIGGER line_candidate_decision_retention BEFORE UPDATE OR DELETE ON line_item_candidate_decisions
 FOR EACH ROW EXECUTE FUNCTION preserve_line_authority();
CREATE TRIGGER canonical_line_decision_retention BEFORE UPDATE OR DELETE ON canonical_line_item_decisions
 FOR EACH ROW EXECUTE FUNCTION preserve_line_authority();
CREATE TRIGGER canonical_line_binding_retention BEFORE UPDATE OR DELETE ON canonical_line_item_source_bindings
 FOR EACH ROW EXECUTE FUNCTION preserve_line_authority();
CREATE TRIGGER line_history_retention BEFORE UPDATE OR DELETE ON line_item_decision_events
 FOR EACH ROW EXECUTE FUNCTION preserve_line_authority();

CREATE FUNCTION version_line_candidate() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF (NEW.id,NEW.document_id,NEW.extraction_id) IS DISTINCT FROM (OLD.id,OLD.document_id,OLD.extraction_id) THEN
  RAISE EXCEPTION 'Line candidate identity is immutable';
 END IF;
 IF to_jsonb(NEW)-ARRAY['updated_at','decision_version'] IS DISTINCT FROM
    to_jsonb(OLD)-ARRAY['updated_at','decision_version'] THEN
  IF EXISTS(SELECT 1 FROM canonical_line_item_source_bindings
     WHERE document_id=OLD.document_id AND source_candidate_id=OLD.id)
    AND to_jsonb(NEW)-ARRAY['updated_at','decision_version','status'] IS DISTINCT FROM
        to_jsonb(OLD)-ARRAY['updated_at','decision_version','status'] THEN
   RAISE EXCEPTION 'Published line source content is immutable';
  END IF;
  NEW.decision_version:=gen_random_uuid();
  NEW.updated_at:=GREATEST(clock_timestamp(),OLD.updated_at+interval '1 microsecond');
 ELSE NEW.decision_version:=OLD.decision_version;
 END IF;
 RETURN NEW;
END;
$$;
CREATE TRIGGER line_candidate_version BEFORE UPDATE ON line_item_candidates
 FOR EACH ROW EXECUTE FUNCTION version_line_candidate();

ALTER TABLE document_fact_projection_state ADD COLUMN accepted_fact_basis_schema_version text
 NOT NULL DEFAULT 'accepted_fields.v1'
 CHECK(accepted_fact_basis_schema_version IN ('accepted_fields.v1','accepted_fields_and_lines.v1'));

CREATE FUNCTION preserve_line_fact_basis() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF OLD.accepted_fact_basis_schema_version='accepted_fields_and_lines.v1'
   AND NEW.accepted_fact_basis_schema_version<>'accepted_fields_and_lines.v1' THEN
  RAISE EXCEPTION 'The accepted field and line basis cannot be downgraded';
 END IF;
 IF NEW.accepted_fact_basis_schema_version IS DISTINCT FROM OLD.accepted_fact_basis_schema_version
   AND (NEW.accepted_facts_sha256 IS NOT DISTINCT FROM OLD.accepted_facts_sha256
     OR NEW.accepted_fact_revision<>OLD.accepted_fact_revision+1) THEN
  RAISE EXCEPTION 'Changing the accepted fact basis requires a new digest and revision';
 END IF;
 RETURN NEW;
END;
$$;
CREATE TRIGGER line_fact_basis_revision BEFORE UPDATE ON document_fact_projection_state
 FOR EACH ROW EXECUTE FUNCTION preserve_line_fact_basis();

CREATE OR REPLACE FUNCTION refresh_document_chunk_projection_snapshot(target_document_id uuid)
RETURNS jsonb
LANGUAGE plpgsql
AS $$
DECLARE indexed_metadata jsonb;
BEGIN
  -- Serialize every legacy lexical caller with canonical decisions and rollups.
  PERFORM 1 FROM documents WHERE id=target_document_id FOR UPDATE;
  -- Materialize metadata once: concurrent tag/folder label changes cannot make
  -- the returned fingerprint describe different inputs from the lexical write.
  WITH source AS MATERIALIZED (
    SELECT d.*,
      COALESCE((SELECT jsonb_agg(jsonb_build_object('id',t.id,'name',t.name) ORDER BY t.id)
        FROM document_tags dt JOIN tags t ON t.id=dt.tag_id
        WHERE dt.document_id=d.id),'[]'::jsonb) AS tags,
      (SELECT string_agg(t.name::text, E'\n' ORDER BY lower(t.name::text), t.id)
        FROM document_tags dt JOIN tags t ON t.id=dt.tag_id
        WHERE dt.document_id=d.id) AS tag_text,
      COALESCE((SELECT jsonb_agg(jsonb_build_object('id',f.id,'name',f.name,'path',f.path_cache,
        'primary',fm.is_primary) ORDER BY f.id)
        FROM document_folder_memberships fm JOIN folders f ON f.id=fm.folder_id
        WHERE fm.document_id=d.id),'[]'::jsonb) AS folders,
      (SELECT string_agg(COALESCE(f.path_cache, '/' || f.name), E'\n'
        ORDER BY fm.is_primary DESC,f.name,f.id)
        FROM document_folder_memberships fm JOIN folders f ON f.id=fm.folder_id
        WHERE fm.document_id=d.id) AS folder_text,
      COALESCE((SELECT jsonb_agg(jsonb_build_object('role',a.amount_role,'amount',a.amount::text,
        'currency',a.currency_code,'source',a.metadata_json)
        ORDER BY a.amount_role,a.amount,a.currency_code,a.metadata_json::text)
        FROM document_amounts a WHERE a.document_id=d.id),'[]'::jsonb) AS amounts
    FROM documents d WHERE d.id=target_document_id
  ), refreshed AS (
  UPDATE document_chunks c
  SET household_id = d.household_id,
      document_family_snapshot = d.document_family,
      document_subtype_snapshot = d.document_subtype,
      document_date_snapshot = d.document_date,
      sensitivity_snapshot = d.sensitivity,
      counterparty_snapshot = d.counterparty_display,
      primary_folder_id = d.primary_folder_id,
      bm25_text = concat_ws(
        E'\n',
        c.text_content,
        c.markdown_content,
        d.title,
        d.original_filename,
        d.counterparty_display,
        d.filing_notes,
        d.tag_text,
        d.folder_text,
        (
          SELECT string_agg(
            concat(cf.field_path, ': ', COALESCE(cf.text_value, cf.integer_value::text, cf.numeric_value::text, cf.boolean_value::text, cf.date_value::text, cf.timestamp_value::text, cf.json_value::text)),
            E'\n'
            ORDER BY cf.field_path, cf.ordinal
          )
          FROM selected_canonical_fields cf
          WHERE cf.document_id = d.id
            AND cf.review_status IN ('auto_accepted', 'user_confirmed', 'user_corrected')
        ),
        (
          SELECT string_agg(
            concat_ws(' ', cli.line_item_type::text, cli.description, cli.net_amount::text, cli.currency_code),
            E'\n'
            ORDER BY cli.line_item_type, cli.ordinal
          )
          FROM selected_canonical_line_items cli
          WHERE cli.document_id = d.id
            AND cli.review_status IN ('auto_accepted', 'user_confirmed', 'user_corrected')
        )
      ),
      updated_at = now()
  FROM source d
  WHERE c.document_id = d.id
  RETURNING c.id
  )
  SELECT jsonb_build_object(
    'title',d.title,'original_filename',d.original_filename,'filing_notes',d.filing_notes,
    'document_family',d.document_family,'document_subtype',d.document_subtype,
    'document_date',d.document_date,'counterparty_display',d.counterparty_display,
    'sensitivity',d.sensitivity,'primary_folder_id',d.primary_folder_id,
    'tags',d.tags,'folders',d.folders,'amounts',d.amounts
  ) INTO indexed_metadata FROM source d;
  RETURN indexed_metadata;
END;
$$;

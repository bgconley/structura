SET search_path TO structura, public;

-- Unknown historical credentials are not an execution grant. Retain all history.
ALTER TABLE document_processing_runs
  ADD COLUMN origin_kind text NOT NULL DEFAULT 'legacy_unestablished',
  ADD COLUMN origin_session_id uuid,
  ADD COLUMN origin_api_token_id uuid,
  ADD COLUMN origin_scope_ceiling text[] NOT NULL DEFAULT ARRAY[]::text[],
  ADD COLUMN required_capability text NOT NULL DEFAULT 'documents:write',
  ADD CONSTRAINT processing_request_origin_shape CHECK (
    required_capability = 'documents:write' AND (
      (origin_kind = 'legacy_unestablished' AND origin_session_id IS NULL
        AND origin_api_token_id IS NULL AND cardinality(origin_scope_ceiling) = 0)
      OR (origin_kind = 'session' AND origin_session_id IS NOT NULL
        AND origin_api_token_id IS NULL AND cardinality(origin_scope_ceiling) = 0)
      OR (origin_kind = 'api_token' AND origin_session_id IS NULL
        AND origin_api_token_id IS NOT NULL)
    )
  );

-- Credential IDs are retained audit identity, not FK restrictions on future
-- credential retention. Missing API tokens deny execution. Browser sessions are
-- checked at admission only: durable ingestion survives logout/expiry/reset.
CREATE FUNCTION processing_request_is_authorized(run_id uuid)
RETURNS boolean LANGUAGE sql STABLE AS $$
  SELECT EXISTS (
    SELECT 1 FROM document_processing_runs r
    WHERE r.id = run_id AND r.required_capability = 'documents:write'
      AND document_is_writable(r.document_id, r.household_id, r.requested_by_user_id, NULL)
      AND (
        r.origin_kind = 'session'
        OR (r.origin_kind = 'api_token'
          AND r.origin_scope_ceiling && ARRAY['documents:write','admin','admin:*']::text[]
          AND EXISTS (
            SELECT 1 FROM api_tokens t
            WHERE t.id = r.origin_api_token_id AND t.user_id = r.requested_by_user_id
              AND t.household_id = r.household_id AND t.revoked_at IS NULL
              AND (t.expires_at IS NULL OR t.expires_at > clock_timestamp())
              AND t.scopes && ARRAY['documents:write','admin','admin:*']::text[]
          ))
      )
  );
$$;

-- A snapshot-only early rejection: never acquire domain locks under job roots.
CREATE OR REPLACE FUNCTION processing_job_is_current(run_id uuid, parse_id uuid)
RETURNS boolean LANGUAGE sql STABLE AS $$
  SELECT CASE WHEN run_id IS NULL THEN parse_id IS NULL ELSE EXISTS (
    SELECT 1 FROM document_processing_runs r
    JOIN documents d ON d.id = r.document_id
    WHERE r.id = run_id AND r.parse_generation_id = parse_id
      AND r.revoked_at IS NULL AND d.deleted_at IS NULL
      AND d.desired_processing_run_id = r.id AND d.processing_generation = r.generation
      AND processing_request_is_authorized(r.id)
  ) END;
$$;

CREATE OR REPLACE FUNCTION preserve_processing_run_identity() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF ROW(NEW.id, NEW.document_id, NEW.household_id, NEW.generation, NEW.request_key,
         NEW.requested_by_user_id, NEW.original_asset_id, NEW.original_sha256,
         NEW.parse_generation_id, NEW.root_job_id, NEW.config_json, NEW.config_sha256, NEW.created_at,
         NEW.origin_kind, NEW.origin_session_id, NEW.origin_api_token_id,
         NEW.origin_scope_ceiling, NEW.required_capability)
     IS DISTINCT FROM ROW(OLD.id, OLD.document_id, OLD.household_id, OLD.generation, OLD.request_key,
         OLD.requested_by_user_id, OLD.original_asset_id, OLD.original_sha256,
         OLD.parse_generation_id, OLD.root_job_id, OLD.config_json, OLD.config_sha256, OLD.created_at,
         OLD.origin_kind, OLD.origin_session_id, OLD.origin_api_token_id,
         OLD.origin_scope_ceiling, OLD.required_capability)
     OR (OLD.revoked_at IS NOT NULL AND ROW(NEW.revoked_at, NEW.status)
         IS DISTINCT FROM ROW(OLD.revoked_at, OLD.status))
     OR (OLD.status = 'sealed' AND NEW.status = 'requested') THEN
    RAISE EXCEPTION 'Processing run identity and revocation are immutable';
  END IF;
  RETURN NEW;
END;
$$;

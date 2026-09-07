SET search_path TO structura, public;

ALTER TABLE sessions ADD COLUMN csrf_token_hash text;

-- Existing random CSRF cookies have no server-side binding and cannot be
-- recovered from the stored session-token hash. Require a fresh sign-in.
UPDATE sessions SET revoked_at = COALESCE(revoked_at, clock_timestamp())
WHERE csrf_token_hash IS NULL;

ALTER TABLE sessions ADD CONSTRAINT sessions_bound_csrf_check CHECK (
  revoked_at IS NOT NULL OR (csrf_token_hash IS NOT NULL AND csrf_token_hash ~ '^[0-9a-f]{64}$')
);

COMMENT ON COLUMN sessions.csrf_token_hash IS
  'SHA-256 of the session-specific browser CSRF secret; never store the raw secret.';

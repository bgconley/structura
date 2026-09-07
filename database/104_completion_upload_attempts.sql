-- Durable upload admission. Additive; legacy POST /documents remains compatible.
-- Identity snapshots intentionally have no user/document cascading foreign keys:
-- deleting a source or actor must not free an operation key for replay publication.
SET search_path TO structura, public;

CREATE TABLE upload_attempts (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    household_id uuid NOT NULL,
    actor_user_id uuid NOT NULL,
    operation_id uuid NOT NULL,
    metadata_json jsonb NOT NULL CHECK (jsonb_typeof(metadata_json) = 'object'),
    revision uuid NOT NULL DEFAULT gen_random_uuid(),
    state text NOT NULL DEFAULT 'awaiting_content' CHECK (state IN (
        'awaiting_content','receiving','awaiting_duplicate_decision','accepted',
        'reused','rejected','cancelled','expired')),
    generation bigint NOT NULL DEFAULT 0 CHECK (generation >= 0),
    current_transfer_id uuid,
    content_sha256 text CHECK (content_sha256 ~ '^[0-9a-f]{64}$'),
    content_bytes bigint CHECK (content_bytes > 0 AND content_bytes <= 104857600),
    detected_mime_type text,
    receipt_json jsonb,
    error_code text CHECK (error_code IN ('upload_size_mismatch','upload_signature_unsupported',
        'upload_format_mismatch','upload_too_large')),
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    inactive_expires_at timestamptz NOT NULL DEFAULT clock_timestamp()+interval '30 minutes',
    UNIQUE(household_id, actor_user_id, operation_id),
    CHECK ((content_sha256 IS NULL AND content_bytes IS NULL AND detected_mime_type IS NULL)
        OR (content_sha256 IS NOT NULL AND content_bytes IS NOT NULL
            AND detected_mime_type IS NOT NULL AND detected_mime_type IN ('application/pdf','image/png','image/jpeg','image/tiff','image/webp'))),
    CHECK ((state IN ('accepted','reused')) = (receipt_json IS NOT NULL)),
    CHECK (receipt_json IS NULL OR jsonb_typeof(receipt_json) = 'object')
);

CREATE TABLE upload_transfers (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    upload_id uuid NOT NULL REFERENCES upload_attempts(id),
    generation bigint NOT NULL CHECK (generation > 0),
    owner_token uuid NOT NULL,
    kind text NOT NULL CHECK (kind IN ('receive','replay','decision')),
    credential_json jsonb NOT NULL CHECK (jsonb_typeof(credential_json) = 'object'),
    source_transfer_id uuid NOT NULL,
    reserved_bytes bigint NOT NULL CHECK (reserved_bytes BETWEEN 0 AND 104857600),
    lease_expires_at timestamptz NOT NULL,
    deadline_at timestamptz NOT NULL,
    held_until timestamptz,
    revoked_at timestamptz,
    io_stopped_at timestamptz,
    verified_at timestamptz,
    content_sha256 text CHECK (content_sha256 ~ '^[0-9a-f]{64}$'),
    content_bytes bigint CHECK (content_bytes > 0 AND content_bytes <= 104857600),
    detected_mime_type text,
    cleanup_token uuid,
    cleanup_expires_at timestamptz,
    cleanup_confirmed_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    UNIQUE(upload_id, generation),
    UNIQUE(upload_id, id),
    FOREIGN KEY(upload_id, source_transfer_id) REFERENCES upload_transfers(upload_id,id)
        DEFERRABLE INITIALLY DEFERRED,
    CHECK ((kind = 'decision' AND reserved_bytes = 0 AND source_transfer_id <> id)
        OR (kind IN ('receive','replay') AND reserved_bytes > 0 AND source_transfer_id = id)),
    CHECK ((verified_at IS NULL AND content_sha256 IS NULL AND content_bytes IS NULL
        AND detected_mime_type IS NULL) OR (verified_at IS NOT NULL AND io_stopped_at IS NOT NULL
        AND content_sha256 IS NOT NULL AND content_bytes IS NOT NULL
        AND detected_mime_type IS NOT NULL AND detected_mime_type IN ('application/pdf','image/png','image/jpeg','image/tiff','image/webp'))),
    CHECK (cleanup_confirmed_at IS NULL OR io_stopped_at IS NOT NULL),
    CHECK ((cleanup_token IS NULL) = (cleanup_expires_at IS NULL))
);
ALTER TABLE upload_attempts ADD CONSTRAINT upload_attempt_current_transfer_fk
    FOREIGN KEY(id,current_transfer_id) REFERENCES upload_transfers(upload_id,id)
    DEFERRABLE INITIALLY DEFERRED;
CREATE INDEX upload_attempt_inactive ON upload_attempts(inactive_expires_at,id)
    WHERE state='awaiting_content';
CREATE INDEX upload_transfer_capacity ON upload_transfers(upload_id)
    WHERE cleanup_confirmed_at IS NULL;
CREATE INDEX upload_transfer_cleanup ON upload_transfers(lease_expires_at,held_until)
    WHERE cleanup_confirmed_at IS NULL;

CREATE FUNCTION preserve_upload_attempt_identity() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'Upload operation tombstones must be retained';
    END IF;
    IF ROW(NEW.id,NEW.household_id,NEW.actor_user_id,NEW.operation_id,NEW.metadata_json,NEW.created_at)
        IS DISTINCT FROM ROW(OLD.id,OLD.household_id,OLD.actor_user_id,OLD.operation_id,
            OLD.metadata_json,OLD.created_at)
        OR NEW.generation < OLD.generation
        OR (OLD.receipt_json IS NOT NULL AND ROW(NEW.receipt_json,NEW.state)
            IS DISTINCT FROM ROW(OLD.receipt_json,OLD.state))
        OR (OLD.state IN ('cancelled','expired','rejected') AND NEW.state <> OLD.state)
        OR (OLD.content_sha256 IS NOT NULL AND ROW(NEW.content_sha256,NEW.content_bytes,
            NEW.detected_mime_type) IS DISTINCT FROM ROW(OLD.content_sha256,
            OLD.content_bytes,OLD.detected_mime_type)) THEN
        RAISE EXCEPTION 'Immutable upload operation identity or outcome';
    END IF;
    IF OLD.receipt_json IS NULL AND NEW.receipt_json IS NOT NULL THEN
        IF NEW.content_sha256 IS NULL OR NOT EXISTS (
            SELECT 1 FROM documents d JOIN document_assets a
            ON a.id=d.canonical_asset_id AND a.document_id=d.id AND a.asset_role='original'
            WHERE d.id=(NEW.receipt_json->>'document_id')::uuid
              AND d.household_id=NEW.household_id AND d.deleted_at IS NULL
              AND a.id=(NEW.receipt_json->>'asset_id')::uuid
              AND d.original_sha256=NEW.content_sha256 AND a.sha256=NEW.content_sha256
              AND a.byte_size=NEW.content_bytes
              AND NEW.receipt_json->>'outcome'=NEW.state
              AND NEW.receipt_json->>'sha256'=NEW.content_sha256
              AND (NEW.receipt_json->>'byte_size')::bigint=NEW.content_bytes
              AND NEW.receipt_json->>'recorded_at' IS NOT NULL
              AND ((NEW.state='reused' AND NEW.receipt_json->>'job_id' IS NULL
                    AND NEW.receipt_json->>'batch_id' IS NULL)
                OR (NEW.state='accepted' AND d.batch_id=(NEW.receipt_json->>'batch_id')::uuid
                    AND EXISTS (SELECT 1 FROM pipeline_jobs j
                        WHERE j.id=(NEW.receipt_json->>'job_id')::uuid
                          AND j.document_id=d.id AND j.batch_id=d.batch_id
                          AND j.job_type='ingest')))
        ) THEN RAISE EXCEPTION 'Upload receipt must bind its exact accepted original'; END IF;
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER upload_attempt_identity BEFORE UPDATE OR DELETE ON upload_attempts
    FOR EACH ROW EXECUTE FUNCTION preserve_upload_attempt_identity();

CREATE FUNCTION preserve_upload_transfer_identity() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'Upload transfer accounting must be retained';
    END IF;
    IF ROW(NEW.id,NEW.upload_id,NEW.generation,NEW.owner_token,NEW.kind,NEW.credential_json,
            NEW.source_transfer_id,NEW.reserved_bytes,NEW.deadline_at,NEW.created_at)
        IS DISTINCT FROM ROW(OLD.id,OLD.upload_id,OLD.generation,OLD.owner_token,OLD.kind,
            OLD.credential_json,OLD.source_transfer_id,OLD.reserved_bytes,OLD.deadline_at,OLD.created_at)
        OR (OLD.revoked_at IS NOT NULL AND NEW.revoked_at IS DISTINCT FROM OLD.revoked_at)
        OR (OLD.io_stopped_at IS NOT NULL AND NEW.io_stopped_at IS DISTINCT FROM OLD.io_stopped_at)
        OR (OLD.cleanup_confirmed_at IS NOT NULL AND NEW IS DISTINCT FROM OLD)
        OR (OLD.verified_at IS NOT NULL AND ROW(NEW.verified_at,NEW.content_sha256,NEW.content_bytes,
            NEW.detected_mime_type) IS DISTINCT FROM ROW(OLD.verified_at,OLD.content_sha256,
            OLD.content_bytes,OLD.detected_mime_type)) THEN
        RAISE EXCEPTION 'Immutable upload transfer identity or accounting';
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER upload_transfer_identity BEFORE UPDATE OR DELETE ON upload_transfers
    FOR EACH ROW EXECUTE FUNCTION preserve_upload_transfer_identity();


CREATE FUNCTION validate_upload_admission_identity() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF TG_TABLE_NAME='upload_attempts' THEN
        IF NEW.state<>'awaiting_content' OR NEW.generation<>0 OR NEW.current_transfer_id IS NOT NULL
           OR NEW.content_sha256 IS NOT NULL OR NEW.receipt_json IS NOT NULL THEN
            RAISE EXCEPTION 'Upload operation must begin without content or acceptance';
        END IF;
    ELSE
        IF NEW.revoked_at IS NOT NULL OR NEW.io_stopped_at IS NOT NULL
           OR NEW.verified_at IS NOT NULL OR NEW.cleanup_confirmed_at IS NOT NULL
           OR NEW.cleanup_token IS NOT NULL OR NEW.held_until IS NOT NULL
           OR NOT EXISTS (SELECT 1 FROM upload_attempts a WHERE a.id=NEW.upload_id
             AND NEW.credential_json->>'household_id'=a.household_id::text
             AND NEW.credential_json->>'user_id'=a.actor_user_id::text
             AND NEW.credential_json->>'kind' IN ('session','api_token')
             AND jsonb_typeof(NEW.credential_json->'scope_ceiling')='array'
             AND ((NEW.credential_json->>'kind'='session'
                 AND NEW.credential_json->>'session_id' IS NOT NULL
                 AND NEW.credential_json->>'api_token_id' IS NULL
                 AND NEW.credential_json->>'session_csrf_bound'='true')
               OR (NEW.credential_json->>'kind'='api_token'
                 AND NEW.credential_json->>'api_token_id' IS NOT NULL
                 AND NEW.credential_json->>'session_id' IS NULL
                 AND NEW.credential_json->>'session_csrf_bound'='false'))) THEN
            RAISE EXCEPTION 'Upload transfer must capture its originating actor credential';
        END IF;
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER upload_attempt_admission BEFORE INSERT ON upload_attempts
    FOR EACH ROW EXECUTE FUNCTION validate_upload_admission_identity();
CREATE TRIGGER upload_transfer_admission BEFORE INSERT ON upload_transfers
    FOR EACH ROW EXECUTE FUNCTION validate_upload_admission_identity();

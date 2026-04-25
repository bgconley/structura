from __future__ import annotations

import os

import pytest

pytest.importorskip("psycopg")
import psycopg

from lib.db.migrations import apply_baseline_migrations


@pytest.mark.skipif(
    not os.environ.get("STRUCTURA_TEST_DATABASE_URL"),
    reason="Set STRUCTURA_TEST_DATABASE_URL to run live database smoke tests.",
)
def test_baseline_migrations_are_idempotent() -> None:
    database_url = os.environ["STRUCTURA_TEST_DATABASE_URL"]

    apply_baseline_migrations(database_url, "database")
    assert apply_baseline_migrations(database_url, "database") == []


@pytest.mark.skipif(
    not os.environ.get("STRUCTURA_TEST_DATABASE_URL"),
    reason="Set STRUCTURA_TEST_DATABASE_URL to run live database smoke tests.",
)
def test_baseline_schema_accepts_core_phase_0_inserts() -> None:
    database_url = os.environ["STRUCTURA_TEST_DATABASE_URL"]
    with psycopg.connect(database_url) as conn:
        with conn.cursor() as cur:
            cur.execute("SET search_path TO structura, public")
            cur.execute(
                "INSERT INTO households (name, slug) VALUES (%s, %s) RETURNING id",
                ("Phase 0 Household", "phase-0-household"),
            )
            household_id = cur.fetchone()[0]

            cur.execute(
                "INSERT INTO users (email, display_name) VALUES (%s, %s) RETURNING id",
                ("phase0@example.test", "Phase 0 Admin"),
            )
            user_id = cur.fetchone()[0]

            cur.execute(
                "INSERT INTO household_memberships (household_id, user_id, role) "
                "VALUES (%s, %s, %s)",
                (household_id, user_id, "owner"),
            )
            cur.execute(
                "INSERT INTO user_password_credentials (user_id, password_hash) VALUES (%s, %s)",
                (user_id, "argon2id-test-hash"),
            )
            cur.execute(
                "INSERT INTO sessions "
                "(user_id, household_id, auth_method, token_hash, expires_at) "
                "VALUES (%s, %s, %s, %s, now() + interval '1 hour') RETURNING id",
                (user_id, household_id, "password", "phase0-token-hash"),
            )
            session_id = cur.fetchone()[0]

            cur.execute(
                "INSERT INTO ingest_batches (source, label) VALUES (%s, %s) RETURNING id",
                ("web_upload", "phase-0"),
            )
            batch_id = cur.fetchone()[0]

            cur.execute(
                "INSERT INTO documents "
                "(batch_id, household_id, owner_user_id, title, ingestion_source, original_sha256) "
                "VALUES (%s, %s, %s, %s, %s, %s) RETURNING id",
                (
                    batch_id,
                    household_id,
                    user_id,
                    "Phase 0 document",
                    "web_upload",
                    "a" * 64,
                ),
            )
            document_id = cur.fetchone()[0]

            cur.execute(
                "INSERT INTO document_assets "
                "(document_id, asset_role, uri, mime_type, sha256) "
                "VALUES (%s, %s, %s, %s, %s) RETURNING id",
                (
                    document_id,
                    "original",
                    "filesystem://canonical/sha256/aa/aa/" + ("a" * 64),
                    "application/pdf",
                    "a" * 64,
                ),
            )
            asset_id = cur.fetchone()[0]

            cur.execute(
                "INSERT INTO pipeline_jobs (job_type, status, document_id, payload_json) "
                "VALUES (%s, %s, %s, %s) RETURNING id",
                ("ingest", "queued", document_id, "{}"),
            )
            job_id = cur.fetchone()[0]

            cur.execute(
                "INSERT INTO folders (household_id, owner_user_id, name, path_cache) "
                "VALUES (%s, %s, %s, %s) RETURNING id",
                (household_id, user_id, "Phase 0 Folder", "/Phase 0 Folder"),
            )
            folder_id = cur.fetchone()[0]

            cur.execute(
                "INSERT INTO tags (name, color_hex) VALUES (%s, %s) RETURNING id",
                ("phase-0-smoke", "#2563EB"),
            )
            tag_id = cur.fetchone()[0]

            evidence = '[{"page_number":1,"source_engine":"system","source_text":"Phase 0"}]'
            cur.execute(
                "INSERT INTO field_candidates "
                "(document_id, field_path, source_engine, value_type, text_value, evidence_json) "
                "VALUES (%s, %s, %s, %s, %s, %s::jsonb) RETURNING id",
                (document_id, "document.title", "system", "string", "Phase 0 document", evidence),
            )
            candidate_id = cur.fetchone()[0]

            cur.execute(
                "INSERT INTO canonical_fields "
                "(document_id, selected_candidate_id, field_path, value_type, text_value, "
                "source_kind, review_status, evidence_json, accepted_by_user_id, accepted_at) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s, now()) RETURNING id",
                (
                    document_id,
                    candidate_id,
                    "document.title",
                    "string",
                    "Phase 0 document",
                    "system",
                    "auto_accepted",
                    evidence,
                    user_id,
                ),
            )
            canonical_field_id = cur.fetchone()[0]

            assert all(
                [
                    household_id,
                    user_id,
                    session_id,
                    document_id,
                    asset_id,
                    job_id,
                    folder_id,
                    tag_id,
                    candidate_id,
                    canonical_field_id,
                ]
            )
        conn.rollback()

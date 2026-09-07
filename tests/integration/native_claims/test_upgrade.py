"""Rollback-only pre-105 reconstruction verifies a populated legacy upgrade."""

from pathlib import Path
from typing import LiteralString, cast

from psycopg.sql import SQL

from lib.db.connection import db_connection
from tests.integration.native_model_emission.upgrade_support import restore_105


def test_105_upgrade_keeps_existing_claim_identity_payload_and_timestamps(processing):
    with db_connection() as conn, conn.cursor() as cur:
        try:
            restore_105(cur)  # Undo106 only within this rollback-only historical reconstruction.
            # Other isolated test cases may have populated105. Remove its dependent
            # rows only in this transaction; rollback restores all such history.
            cur.execute("DROP TRIGGER extraction_claim_native_guard ON extraction_claims")
            cur.execute("DROP TRIGGER extraction_claim_native_retention ON extraction_claims")
            cur.execute("DELETE FROM extraction_claims WHERE origin_kind='native_structure'")
            cur.execute("""ALTER TABLE extraction_claims
                DROP CONSTRAINT extraction_claim_native_scope,
                DROP CONSTRAINT extraction_claim_native_identity,
                DROP CONSTRAINT extraction_claim_origin_branch,
                DROP COLUMN origin_kind,DROP COLUMN native_claim_set_id,
                DROP COLUMN native_page_number,DROP COLUMN native_payload_json,
                DROP COLUMN native_content_sha256,ALTER COLUMN extraction_id SET NOT NULL""")
            cur.execute("DROP TABLE native_claim_page_checkpoints,native_claim_sets")
            cur.execute(
                "DROP FUNCTION guard_native_claim_set(),guard_native_claim_content(),"
                "retain_native_claim_history()"
            )
            cur.execute(
                """INSERT INTO document_extractions(document_id,schema_name,schema_version,
                source_engine,status)
                VALUES (%s,'invoice','v1','docling','completed') RETURNING id""",
                (processing.document_id,),
            )
            extraction = cur.fetchone()["id"]
            cur.execute(
                """INSERT INTO extraction_claims(extraction_id,document_id,claim_id,method,
                source_engine,canonical_key,raw_value,typed_value_json,value_type,anchor_json,
                metadata_json)
                VALUES (%s,%s,'existing-claim','legacy-docling','docling','invoice.invoice_number',
                '000123','"000123"','identifier','{"page_number":1}',
                '{"compatibility_origin":"established_legacy"}') RETURNING *""",
                (extraction, processing.document_id),
            )
            before = cur.fetchone()
            migration = (
                Path(__file__).resolve().parents[3]
                / "database/105_completion_native_claim_currency.sql"
            ).read_text()
            cur.execute(SQL(cast(LiteralString, migration)), prepare=False)
            cur.execute("SELECT * FROM extraction_claims WHERE id=%s", (before["id"],))
            after = cur.fetchone()
            assert {key: after[key] for key in before} == before
            assert after["origin_kind"] == "legacy_extraction"
            assert after["native_claim_set_id"] is None and after["native_payload_json"] is None
        finally:
            conn.rollback()

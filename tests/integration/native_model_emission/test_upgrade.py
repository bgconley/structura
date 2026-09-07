from pathlib import Path
from typing import LiteralString, cast

import pytest
from psycopg import errors
from psycopg.sql import SQL
from psycopg.types.json import Jsonb

from lib.db.connection import db_connection
from lib.extraction.native_claims.service import NativeClaimService
from tests.integration.native_claims.conftest import page_request, setup_source
from tests.integration.native_model_emission.upgrade_support import restore_105


def test_representative_105_upgrade_preserves_recorded_text_payload_hash_ids_and_timestamps(
    processing,
):
    processing, _, claimed, binding, checkpoints = setup_source(processing)
    with processing.scope(claimed):
        NativeClaimService().checkpoint(binding, page_request(checkpoints[0]))
        NativeClaimService().seal(binding)
    with db_connection() as conn, conn.cursor() as cur:
        try:
            restore_105(cur)
            cur.execute(
                "SELECT * FROM extraction_claims WHERE native_claim_set_id=%s ORDER BY id",
                (binding.claim_set_id,),
            )
            before = cur.fetchall()
            cur.execute("SELECT * FROM native_claim_sets WHERE id=%s", (binding.claim_set_id,))
            header = cur.fetchone()
            migration = (
                Path(__file__).resolve().parents[3]
                / "database/106_completion_native_model_emission.sql"
            ).read_text()
            cur.execute(SQL(cast(LiteralString, migration)), prepare=False)
            cur.execute(
                "SELECT * FROM extraction_claims WHERE native_claim_set_id=%s ORDER BY id",
                (binding.claim_set_id,),
            )
            after = cur.fetchall()
            assert [{k: r[k] for k in before[0]} for r in after] == before
            assert all(
                r["native_member_index"] is None and r["native_member_sha256"] is None
                for r in after
            )
            cur.execute("SELECT * FROM native_claim_sets WHERE id=%s", (binding.claim_set_id,))
            changed = cur.fetchone()
            assert {k: changed[k] for k in header} == header
            assert changed["interpretation_kind"] == "structure_normalization"
        finally:
            conn.rollback()


def test_105_page_count_limit_remains_1000_in_database(processing):
    _, _, _, binding, checkpoints = setup_source(processing)
    checkpoint = checkpoints[0]
    request = page_request(checkpoint).model_dump(mode="json")
    with (
        pytest.raises(errors.RaiseException, match="unchanged"),
        db_connection() as conn,
        conn.cursor() as cur,
    ):
        cur.execute(
            """INSERT INTO native_claim_page_checkpoints
        (claim_set_id,document_id,parse_generation_id,page_number,page_id,request_json,content_sha256,claim_count)
        VALUES (%s,%s,%s,1,%s,%s,%s,1001)""",
            (
                binding.claim_set_id,
                binding.processing.document_id,
                binding.processing.parse_generation_id,
                checkpoint.page.id,
                Jsonb(request),
                "a" * 64,
            ),
        )

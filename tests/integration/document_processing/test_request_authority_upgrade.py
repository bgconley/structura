from pathlib import Path
from typing import LiteralString, cast

import pytest
from psycopg.errors import RaiseException
from psycopg.sql import SQL

from lib.db.connection import db_connection
from lib.document_processing.service import DocumentProcessingService


def test_096_upgrade_preserves_history_and_never_infers_authority(processing):
    first = processing.start()
    service = DocumentProcessingService()
    with processing.scope(processing.claim()):
        service.initialize_inventory(first.binding, processing.inventory)
        checkpoint = processing.checkpoint(first)
        service.checkpoint(first.binding, checkpoint)
        service.seal(first.binding, processing.structure(first, [checkpoint]))
    second = processing.start()
    migration = (
        Path(__file__).resolve().parents[3]
        / "database/097_completion_processing_request_authority.sql"
    ).read_text()
    with db_connection() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT * FROM document_parse_page_checkpoints WHERE parse_generation_id=%s",
            (first.binding.parse_generation_id,),
        )
        retained = cur.fetchall()
        # Reconstruct the real pre-097 run shape transactionally. No source
        # database or other test sees this temporary downgrade/upgrade.
        cur.execute("DROP FUNCTION processing_request_is_authorized(uuid)")
        cur.execute(
            """ALTER TABLE document_processing_runs
            DROP COLUMN origin_kind, DROP COLUMN origin_session_id,
            DROP COLUMN origin_api_token_id, DROP COLUMN origin_scope_ceiling,
            DROP COLUMN required_capability"""
        )
        cur.execute(SQL(cast(LiteralString, migration)), prepare=False)
        cur.execute(
            """SELECT id,origin_kind,status,
            processing_job_is_current(id,parse_generation_id) AS current
            FROM document_processing_runs WHERE document_id=%s ORDER BY generation""",
            (processing.document_id,),
        )
        rows = cur.fetchall()
        assert [row["id"] for row in rows] == [
            first.binding.processing_run_id,
            second.binding.processing_run_id,
        ]
        assert [row["status"] for row in rows] == ["superseded", "requested"]
        assert all(
            row["origin_kind"] == "legacy_unestablished" and not row["current"] for row in rows
        )
        cur.execute(
            "SELECT * FROM document_parse_page_checkpoints WHERE parse_generation_id=%s",
            (first.binding.parse_generation_id,),
        )
        assert cur.fetchall() == retained
        cur.execute("SAVEPOINT forbidden_rebind")
        with pytest.raises(RaiseException, match="immutable"):
            cur.execute(
                "UPDATE document_processing_runs SET origin_kind='session',origin_session_id=%s "
                "WHERE id=%s",
                (processing.principal.session_id, second.binding.processing_run_id),
            )
        cur.execute("ROLLBACK TO SAVEPOINT forbidden_rebind")
        conn.rollback()

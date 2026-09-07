from uuid import uuid4

from lib.db.connection import db_connection
from lib.extraction.native_claims.model_emission.service import NativeModelEmissionService
from tests.integration.native_claims.test_currency import _human_legacy_snapshot


def test_model_import_and_document_cascade_preserve_existing_human_authority_until_delete(
    model_source,
):
    processing, _, claimed, binding, _ = model_source
    with db_connection() as conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO users(email,display_name) VALUES (%s,'Former reviewer') RETURNING id",
            (f"model-history-{uuid4()}@example.com",),
        )
        actor = cur.fetchone()["id"]
        cur.execute(
            """INSERT INTO canonical_fields
        (document_id,field_path,value_type,numeric_value,currency_code,source_kind,review_status,accepted_by_user_id,evidence_json)
        VALUES (%s,'invoice.total_amount','money',42.1500,'USD','human','user_corrected',%s,
        '[{"pageNumber":1,"sourceText":"Human retained original evidence"}]') RETURNING id""",
            (processing.document_id, actor),
        )
        field = cur.fetchone()["id"]
        cur.execute(
            """INSERT INTO canonical_field_decisions
        (document_id,field_path,ordinal,disposition,origin,canonical_field_id,actor_user_id)
        VALUES (%s,'invoice.total_amount',1,'corrected','legacy_current_field',%s,%s)""",
            (processing.document_id, field, actor),
        )
        cur.execute(
            """INSERT INTO canonical_line_items
        (document_id,line_item_type,ordinal,description,net_amount,currency_code,source_kind,review_status,accepted_by_user_id)
        VALUES (%s,'invoice_item',1,'Human retained line',42.1500,'USD','human','user_corrected',%s)
        RETURNING id""",
            (processing.document_id, actor),
        )
        line = cur.fetchone()["id"]
        cur.execute(
            """INSERT INTO canonical_line_item_decisions
        (document_id,line_item_type,ordinal,canonical_line_item_id,disposition,origin,actor_user_id)
        VALUES (%s,'invoice_item',1,%s,'corrected','legacy_current_line',%s)""",
            (processing.document_id, line, actor),
        )
        cur.execute(
            """INSERT INTO canonical_fact_history
        (document_id,canonical_field_id,canonical_line_item_id,action,new_value_json,actor_user_id)
        VALUES (%s,%s,%s,'human_corrected','{"amount":"42.1500"}',%s)""",
            (processing.document_id, field, line, actor),
        )
        cur.execute("DELETE FROM users WHERE id=%s", (actor,))
    before = _human_legacy_snapshot(processing.document_id)
    assert before["canonical_field_decisions"][0]["actor_user_id"] is None
    with processing.scope(claimed):
        NativeModelEmissionService().checkpoint(binding, 1)
        NativeModelEmissionService().seal(binding)
    processing.start()
    assert _human_legacy_snapshot(processing.document_id) == before
    with db_connection() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM documents WHERE id=%s", (processing.document_id,))
        conn.commit()
    with db_connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT id FROM native_claim_sets WHERE id=%s", (binding.claim_set_id,))
        assert cur.fetchall() == []

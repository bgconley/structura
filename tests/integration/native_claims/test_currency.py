from uuid import uuid4

import pytest
from psycopg import sql
from psycopg.errors import CheckViolation, ForeignKeyViolation, RaiseException
from psycopg.types.json import Jsonb

from lib.auth.request_authority import RequestCredential
from lib.db.connection import db_connection
from lib.extraction.claim_repository import persist_extraction_claims
from lib.extraction.claims import Claim, ClaimAnchor
from lib.extraction.models import ExtractionRunScope
from lib.extraction.native_claims.errors import NativeClaimConflict, NativeClaimError
from lib.extraction.native_claims.models import NativePageRequest
from lib.extraction.native_claims.service import NativeClaimService
from tests.integration.native_claims.conftest import page_request, setup_source


def populated(native_source):
    processing, run, claimed, binding, checkpoints = native_source
    service = NativeClaimService()
    with processing.scope(claimed):
        service.checkpoint(binding, page_request(checkpoints[0]))
        service.seal(binding)
    return processing, run, claimed, binding, checkpoints


def test_replay_retains_two_physical_rows_and_rebuild_ignores_legacy_normalizers(
    native_source, monkeypatch
):
    processing, run, claimed, binding, checkpoints = populated(native_source)
    service = NativeClaimService()
    with processing.scope(claimed):
        assert service.start(run.binding) == binding
        baseline = service.rebuild(
            binding, credential=RequestCredential.from_principal(processing.principal)
        )
        first = service.checkpoint(binding, page_request(checkpoints[0]))
        assert service.checkpoint(binding, page_request(checkpoints[0])) == first
        assert service.seal(binding) == service.seal(binding)

        def forbidden(*args, **kwargs):
            raise AssertionError(
                "Compatibility/model normalization cannot rebuild persisted claims"
            )

        monkeypatch.setattr("lib.extraction.claims.claims_from_region_envelope", forbidden)
        monkeypatch.setattr(
            "lib.document_parsing.model_output.PageParseOutput.model_validate_json", forbidden
        )
        assert (
            service.rebuild(
                binding, credential=RequestCredential.from_principal(processing.principal)
            )
            == baseline
        )
    assert baseline["claim_count"] == 2 and len(baseline["line_rows"]) == 2
    assert all(
        r["claims"][0]["typed_value"]["amount"] == "9007199254740.1234"
        for r in baseline["line_rows"]
    )
    with db_connection() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT id,claim_id,group_id,extraction_id,origin_kind FROM extraction_claims "
            "WHERE native_claim_set_id=%s",
            (binding.claim_set_id,),
        )
        rows = cur.fetchall()
        assert (
            len({r["id"] for r in rows})
            == len({r["claim_id"] for r in rows})
            == len({r["group_id"] for r in rows})
            == 2
        )
        assert all(
            r["extraction_id"] is None and r["origin_kind"] == "native_structure" for r in rows
        )
        cur.execute(
            "SELECT count(*) AS n FROM line_item_candidates WHERE document_id=%s",
            (processing.document_id,),
        )
        assert cur.fetchone()["n"] == 0


def test_conflicting_page_mapping_cannot_replace_sealed_claims(native_source):
    processing, _, claimed, binding, checkpoints = populated(native_source)
    payload = page_request(checkpoints[0]).model_dump(mode="json")
    payload["claims"][0]["anchor"]["text_start"] = 4
    service = NativeClaimService()
    with processing.scope(claimed):
        before = service.rebuild(
            binding, credential=RequestCredential.from_principal(processing.principal)
        )
        with pytest.raises(NativeClaimConflict):
            service.checkpoint(binding, NativePageRequest.model_validate(payload))
        assert (
            service.rebuild(
                binding, credential=RequestCredential.from_principal(processing.principal)
            )
            == before
        )


def test_partial_restart_and_explicit_zero_target_account_every_page(processing):
    processing, _, claimed, binding, checkpoints = setup_source(
        processing, pages=2, state="partial"
    )
    service = NativeClaimService()
    with processing.scope(claimed):
        service.checkpoint(binding, page_request(checkpoints[0], disposition="partial"))
        with pytest.raises(NativeClaimError):
            service.seal(binding)
        # A fresh service resumes the same immutable set with an explicit abstention.
        NativeClaimService().checkpoint(
            binding,
            NativePageRequest(
                page_number=2, disposition="insufficient_signal", reasons=("source_incomplete",)
            ),
        )
        completion = NativeClaimService().seal(binding)
        assert completion["source_pages"] == 2 and completion["claim_count"] == 2
        assert completion["page_dispositions"] == {"partial": 1, "insufficient_signal": 1}
        assert completion["requires_review"] is True


def test_zero_claim_set_is_explicit_and_not_an_unfinished_success(native_source):
    processing, _, claimed, binding, _ = native_source
    service = NativeClaimService()
    with processing.scope(claimed):
        with pytest.raises(NativeClaimError):
            service.seal(binding)
        service.checkpoint(
            binding,
            NativePageRequest(
                page_number=1, disposition="no_extraction_target", reasons=("no_target",)
            ),
        )
        completion = service.seal(binding)
        assert completion["claim_count"] == 0 and completion["page_dispositions"] == {
            "no_extraction_target": 1
        }
        assert (
            service.rebuild(
                binding, credential=RequestCredential.from_principal(processing.principal)
            )["claims_are_accepted_facts"]
            is False
        )


@pytest.mark.parametrize(
    "table,column",
    [
        ("native_claim_sets", "id"),
        ("native_claim_page_checkpoints", "claim_set_id"),
        ("extraction_claims", "native_claim_set_id"),
    ],
)
@pytest.mark.parametrize("action", ["update", "delete"])
def test_individual_native_content_and_history_are_immutable(native_source, table, column, action):
    _, _, _, binding, _ = populated(native_source)
    with pytest.raises(RaiseException), db_connection() as conn, conn.cursor() as cur:
        # Only the fixed parametrized table/column allowlist enters SQL identifiers.
        query = sql.SQL(
            "UPDATE {} SET created_at=clock_timestamp() WHERE {}=%s"
            if action == "update"
            else "DELETE FROM {} WHERE {}=%s"
        ).format(sql.Identifier(table), sql.Identifier(column))
        # nosemgrep: python.sqlalchemy.security.sqlalchemy-execute-raw-query.sqlalchemy-execute-raw-query  # noqa: E501
        cur.execute(query, (binding.claim_set_id,))


def test_all_populated_native_edges_allow_whole_document_cascade(native_source):
    processing, _, _, binding, _ = populated(native_source)
    with db_connection() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM documents WHERE id=%s", (processing.document_id,))
        conn.commit()
    with db_connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT id FROM native_claim_sets WHERE id=%s", (binding.claim_set_id,))
        assert cur.fetchone() is None
        cur.execute(
            "SELECT id FROM extraction_claims WHERE native_claim_set_id=%s", (binding.claim_set_id,)
        )
        assert cur.fetchone() is None


def test_native_source_references_reject_independent_original_deletion(native_source):
    processing, _, _, _, _ = populated(native_source)
    with db_connection() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM document_assets WHERE id=%s", (processing.asset_id,))
        with pytest.raises(ForeignKeyViolation):
            conn.commit()
        conn.rollback()


def test_legacy_branch_cannot_omit_extraction_parent(native_source):
    processing, _, _, _, _ = native_source
    with pytest.raises(CheckViolation), db_connection() as conn, conn.cursor() as cur:
        cur.execute(
            """INSERT INTO extraction_claims(document_id,claim_id,method,source_engine,
            canonical_key,raw_value,typed_value_json,value_type,anchor_json)
            VALUES (%s,'legacy-invalid','test','granite',
            'invoice.invoice_number','A','"A"','identifier','{}')""",
            (processing.document_id,),
        )


def test_native_branch_cannot_use_null_page_to_bypass_its_composite_scope(native_source):
    processing, _, claimed, binding, checkpoints = native_source
    with processing.scope(claimed):
        NativeClaimService().checkpoint(binding, page_request(checkpoints[0]))
    with pytest.raises(CheckViolation), db_connection() as conn, conn.cursor() as cur:
        cur.execute(
            """INSERT INTO extraction_claims
            (document_id,claim_id,method,source_engine,canonical_key,raw_value,typed_value_json,
             value_type,group_id,anchor_json,evidence_json,metadata_json,origin_kind,
             native_claim_set_id,native_page_number,native_payload_json,native_content_sha256)
            SELECT document_id,claim_id,method,source_engine,canonical_key,raw_value,
             typed_value_json,value_type,group_id,anchor_json,evidence_json,metadata_json,
             origin_kind,native_claim_set_id,NULL,native_payload_json,native_content_sha256
            FROM extraction_claims WHERE native_claim_set_id=%s LIMIT 1""",
            (binding.claim_set_id,),
        )


def test_legacy_upserts_human_decisions_and_deleted_actor_history_survive_native_work(
    native_source,
):
    processing, _, claimed, binding, checkpoints = native_source
    with db_connection() as conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO users(email,display_name) VALUES (%s,'Former reviewer') RETURNING id",
            (f"native-history-{uuid4()}@example.com",),
        )
        actor = cur.fetchone()["id"]
        cur.execute(
            """INSERT INTO document_extractions(document_id,schema_name,schema_version,status,
            source_engine,normalized_json)
            VALUES (%s,'invoice','v1','completed','docling','{}') RETURNING id""",
            (processing.document_id,),
        )
        extraction_id = cur.fetchone()["id"]
        claim = Claim(
            claim_id="retained-legacy-id",
            document_id=str(processing.document_id),
            source_engine="docling",
            anchor=ClaimAnchor(page_number=1, docling_element_ids=("legacy-element",)),
            canonical_key="invoice.invoice_number",
            raw_value="Legacy A",
            typed_value="Legacy A",
            value_type="identifier",
            confidence=None,
            method="docling-text-v1",
        )
        persist_extraction_claims(
            cur, extraction_id=extraction_id, claims=[claim], run_scope=ExtractionRunScope()
        )
        persist_extraction_claims(
            cur, extraction_id=extraction_id, claims=[claim], run_scope=ExtractionRunScope()
        )
        cur.execute(
            """INSERT INTO canonical_fields(document_id,field_path,value_type,numeric_value,
            currency_code,source_kind,review_status,accepted_by_user_id,evidence_json)
            VALUES (%s,'invoice.total_amount','money',42.1500,'USD','human','user_corrected',%s,%s)
            RETURNING id""",
            (
                processing.document_id,
                actor,
                Jsonb([{"pageNumber": 1, "sourceText": "Retained original human evidence"}]),
            ),
        )
        field = cur.fetchone()["id"]
        cur.execute(
            """INSERT INTO canonical_field_decisions(document_id,field_path,ordinal,disposition,
            origin,canonical_field_id,actor_user_id)
            VALUES (%s,'invoice.total_amount',1,'corrected',
            'legacy_current_field',%s,%s)""",
            (processing.document_id, field, actor),
        )
        cur.execute(
            """INSERT INTO canonical_field_path_guards(document_id,field_path,actor_user_id)
            VALUES (%s,'invoice.tax_total',%s)""",
            (processing.document_id, actor),
        )
        cur.execute(
            """INSERT INTO canonical_line_items(document_id,line_item_type,ordinal,description,
            net_amount,currency_code,source_kind,review_status,accepted_by_user_id)
            VALUES (%s,'invoice_item',1,'Retained human line',42.1500,'USD','human',
            'user_corrected',%s) RETURNING id""",
            (processing.document_id, actor),
        )
        line = cur.fetchone()["id"]
        cur.execute(
            """INSERT INTO canonical_line_item_decisions(document_id,line_item_type,ordinal,
            canonical_line_item_id,disposition,origin,actor_user_id)
            VALUES (%s,'invoice_item',1,%s,'corrected','legacy_current_line',%s)""",
            (processing.document_id, line, actor),
        )
        cur.execute(
            """INSERT INTO canonical_fact_history(document_id,canonical_field_id,
            canonical_line_item_id,action,new_value_json,actor_user_id)
            VALUES (%s,%s,%s,'human_corrected','{"amount":"42.1500"}',%s)""",
            (processing.document_id, field, line, actor),
        )
        cur.execute("DELETE FROM users WHERE id=%s", (actor,))
    before = _human_legacy_snapshot(processing.document_id)
    service = NativeClaimService()
    with processing.scope(claimed):
        service.checkpoint(binding, page_request(checkpoints[0]))
        service.seal(binding)
        service.rebuild(binding, credential=RequestCredential.from_principal(processing.principal))
    processing.start()  # A later native run changes authority, never accepted records.
    assert _human_legacy_snapshot(processing.document_id) == before
    assert before["extraction_claims"][0]["origin_kind"] == "legacy_extraction"
    assert before["canonical_field_decisions"][0]["actor_user_id"] is None
    assert before["canonical_line_item_decisions"][0]["actor_user_id"] is None


def _human_legacy_snapshot(document_id):
    result = {}
    tables = (
        "canonical_fields",
        "canonical_field_decisions",
        "canonical_field_path_guards",
        "canonical_line_items",
        "canonical_line_item_decisions",
        "canonical_fact_history",
    )
    with db_connection() as conn, conn.cursor() as cur:
        for table in tables:
            # The fixed test table allowlist uses quoted identifiers, never user SQL.
            # nosemgrep: python.sqlalchemy.security.sqlalchemy-execute-raw-query.sqlalchemy-execute-raw-query  # noqa: E501
            cur.execute(
                sql.SQL("SELECT * FROM {} WHERE document_id=%s ORDER BY id").format(
                    sql.Identifier(table)
                ),
                (document_id,),
            )
            result[table] = cur.fetchall()
        cur.execute(
            "SELECT * FROM extraction_claims WHERE document_id=%s "
            "AND extraction_id IS NOT NULL ORDER BY id",
            (document_id,),
        )
        result["extraction_claims"] = cur.fetchall()
    return result

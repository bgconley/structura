from dataclasses import replace
from uuid import uuid4

import pytest
from psycopg import errors

from lib.auth import AuthService
from lib.auth.authorization_policy import AuthorizationError
from lib.auth.request_authority import RequestCredential
from lib.db.connection import db_connection
from lib.extraction.native_claims.errors import NativeClaimError
from lib.extraction.native_claims.model_emission.service import NativeModelEmissionService
from lib.jobs import JobService
from tests.fixtures.page_understanding_sources import invoice_page, prose_page, quote
from tests.integration.native_model_emission.conftest import populated, setup_source


def test_exact_persisted_replay_preserves_physical_sql_ids_and_provenance(model_source):
    processing, run, claimed, binding, _ = model_source
    service = NativeModelEmissionService()
    with processing.scope(claimed):
        assert service.start(run.binding) == binding
        first = service.checkpoint(binding, 1)
        with db_connection() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT id,claim_id,native_member_index,native_member_sha256,native_payload_json "
                "FROM extraction_claims WHERE native_claim_set_id=%s ORDER BY native_member_index",
                (binding.claim_set_id,),
            )
            before = cur.fetchall()
        assert service.checkpoint(binding, 1) == first
        assert service.seal(binding)["claim_count"] == 5
        assert service.checkpoint(binding, 1) == first
    with db_connection() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT id,claim_id,native_member_index,native_member_sha256,native_payload_json "
            "FROM extraction_claims WHERE native_claim_set_id=%s ORDER BY native_member_index",
            (binding.claim_set_id,),
        )
        assert cur.fetchall() == before
    result = service.rebuild(
        binding, credential=RequestCredential.from_principal(processing.principal)
    )
    assert len(result["line_rows"]) == 2 and result["claims_are_accepted_facts"] is False
    assert before[2]["native_payload_json"]["proposed"]["typed_value"] == {
        "amount": "12.3400",
        "currency": "USD",
    }
    assert before[0]["native_payload_json"]["member"]["pointer"] == "/extraction/claims/0"


def test_missing_page_then_partial_and_unsupported_pages_are_retained_without_fake_completion(
    processing,
):
    partial = invoice_page()
    partial["extraction"].update({"disposition": "partial", "reasons": ["content_omitted"]})
    next(
        f
        for f in partial["extraction"]["families"][0]["fields"]
        if f["canonical_key"] == "invoice.due_date"
    ).update({"state": "omitted", "evidence": [quote(0, "Invoice")]})
    processing, _, claimed, binding, _ = setup_source(processing, [partial, prose_page()])
    service = NativeModelEmissionService()
    with processing.scope(claimed):
        service.checkpoint(binding, 1)
        with pytest.raises(NativeClaimError, match="inventory is incomplete"):
            service.seal(binding)
        service.checkpoint(binding, 2)
        completion = service.seal(binding)
    assert completion["page_dispositions"] == {"partial": 1, "unsupported_family": 1}
    result = service.rebuild(
        binding, credential=RequestCredential.from_principal(processing.principal)
    )
    assert result["pages"][1]["members"] == []
    assert result["pages"][1]["classification_json"]["primary_family"] == "legal_notice"


def test_retained_rebuild_survives_job_success_and_reparse_without_provider_decode(
    model_source, monkeypatch
):
    processing, _, claimed, binding, _ = populated(model_source)
    service = NativeModelEmissionService()
    credential = RequestCredential.from_principal(processing.principal)
    before = service.rebuild(binding, credential=credential)
    JobService().complete_job(job_id=claimed.state.job_id, claim_token=claimed.claim_token)
    processing.start()

    def forbidden(*args, **kwargs):
        pytest.fail("Retained rebuild decoded provider raw or used active write authority")

    monkeypatch.setattr(
        "lib.document_parsing.page_understanding.codec.decode_page_understanding", forbidden
    )
    monkeypatch.setattr("lib.document_parsing.raw_output.decode_page_understanding", forbidden)
    monkeypatch.setattr(
        "lib.extraction.native_claims.model_emission.import_page.decode_page_understanding",
        forbidden,
    )
    monkeypatch.setattr("lib.extraction.native_claims.authority_repository.lock_source", forbidden)
    monkeypatch.setattr(
        "lib.extraction.native_claims.model_emission.service.installed_configuration", forbidden
    )
    assert service.rebuild(binding, credential=credential) == before
    AuthService().revoke_authenticated_session(processing.principal)
    with pytest.raises(AuthorizationError):
        service.rebuild(binding, credential=credential)


@pytest.mark.parametrize(
    "relation", ["extraction_claims", "native_claim_page_checkpoints", "native_claim_sets"]
)
def test_native_model_content_and_individual_deletion_are_immutable(model_source, relation):
    _, _, _, binding, _ = populated(model_source)
    statements = {
        "extraction_claims": (
            "UPDATE extraction_claims SET raw_value='changed' WHERE native_claim_set_id=%s",
            "DELETE FROM extraction_claims WHERE native_claim_set_id=%s",
        ),
        "native_claim_page_checkpoints": (
            "UPDATE native_claim_page_checkpoints SET claim_count=0 WHERE claim_set_id=%s",
            "DELETE FROM native_claim_page_checkpoints WHERE claim_set_id=%s",
        ),
        "native_claim_sets": (
            "UPDATE native_claim_sets SET interpretation_kind='structure_normalization' "
            "WHERE id=%s",
            "DELETE FROM native_claim_sets WHERE id=%s",
        ),
    }
    for statement in statements[relation]:
        with pytest.raises(errors.RaiseException), db_connection() as conn, conn.cursor() as cur:
            cur.execute(statement, (binding.claim_set_id,))


def test_model_claims_do_not_publish_or_mutate_human_facts(model_source):
    processing, _, _, binding, _ = populated(model_source)
    with db_connection() as conn, conn.cursor() as cur:
        cur.execute(
            """SELECT
          (SELECT count(*) FROM canonical_fields WHERE document_id=%s) AS fields,
          (SELECT count(*) FROM canonical_line_items WHERE document_id=%s) AS lines,
          (SELECT count(*) FROM field_candidates WHERE document_id=%s) AS candidates,
          (SELECT count(*) FROM line_item_candidates WHERE document_id=%s) AS line_candidates""",
            (processing.document_id,) * 4,
        )
        assert cur.fetchone() == {"fields": 0, "lines": 0, "candidates": 0, "line_candidates": 0}
    foreign = replace(RequestCredential.from_principal(processing.principal), household_id=uuid4())
    with pytest.raises(AuthorizationError):
        NativeModelEmissionService().rebuild(binding, credential=foreign)


def test_whole_document_cascade_removes_all_model_claim_references(model_source):
    processing, _, _, binding, _ = populated(model_source)
    with db_connection() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM documents WHERE id=%s", (processing.document_id,))
        conn.commit()
    with db_connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT id FROM native_claim_sets WHERE id=%s", (binding.claim_set_id,))
        assert cur.fetchall() == []
        cur.execute(
            "SELECT id FROM extraction_claims WHERE native_claim_set_id=%s", (binding.claim_set_id,)
        )
        assert cur.fetchall() == []

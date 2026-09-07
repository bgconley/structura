"""Real SQL generation/history consumers using an explicitly declared v2 fixture."""

from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest

from lib.auth.request_authority import RequestCredential
from lib.db.connection import db_connection
from lib.document_parsing.source_adapter import DocumentSource
from lib.document_processing.configuration_types import ParseRequestSettings
from lib.document_processing.errors import ProcessingAuthorityLost
from lib.document_processing.service import DocumentProcessingService
from lib.document_processing.understanding_configuration import understanding_configuration
from lib.evaluation.artifact_verification import verify_capture_source
from lib.evaluation.capture_models import CaptureDeclaration, CaptureIntegrityError
from lib.evaluation.persisted_capture import capture_sealed_generation
from lib.evidence.read_service import GenerationEvidenceReader
from lib.evidence.render_execution import retain_source_pages
from lib.evidence.write_service import RetainedEvidenceWriter
from lib.extraction.native_claims.models import (
    NativeAnchorRequest,
    NativeClaimRequest,
    NativePageRequest,
)
from lib.extraction.native_claims.service import NativeClaimService
from lib.search.indexing.configuration import index_configuration
from lib.search.indexing.service import CandidateIndexService
from tests.fixtures.page_understanding_client import UnderstandingClient
from tests.integration.document_processing.test_parse_execution import execute_candidate_parse
from tests.integration.document_processing.test_parse_execution import (
    source_execution as source_execution,
)


@pytest.fixture
def understanding_source(source_execution):
    processing, storage, deployment = source_execution
    with db_connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT uri FROM document_assets WHERE id=%s", (processing.asset_id,))
        uri = cur.fetchone()["uri"]
    with DocumentSource(
        storage.path_for_uri(uri),
        asset_id=processing.asset_id,
        expected_sha256=processing.original_sha256,
        mime_type="image/tiff",
    ) as source:
        processing.configuration = understanding_configuration(
            deployment,
            source,
            request=ParseRequestSettings(
                max_output_tokens=14000, temperature=0, seed=None, timeout_seconds=137
            ),
        )
    return processing, storage, deployment, uri


def capture(processing, run, *, budget=14000):
    return capture_sealed_generation(
        document_id=processing.document_id,
        processing_run_id=run.binding.processing_run_id,
        parse_generation_id=run.binding.parse_generation_id,
        access=processing.access,
        declaration=CaptureDeclaration(
            item_id="v2-controlled-fixture",
            commit="a" * 40,
            max_output_tokens=budget,
            temperature=0,
        ),
    )


@pytest.mark.parametrize("transition", ["supersede", "cancel"])
def test_v2_history_capture_evidence_index_and_105_remain_exact(
    understanding_source, transition, monkeypatch
):
    processing, storage, deployment, uri = understanding_source
    run = processing.start()
    claimed = processing.claim()
    claims = NativeClaimService()
    with processing.scope(claimed):
        first = UnderstandingClient(fail_page=2)
        with pytest.raises(RuntimeError, match="outage"):
            execute_candidate_parse(run, storage, deployment, first)
        resumed = UnderstandingClient()
        execute_candidate_parse(run, storage, deployment, resumed)
        replay = UnderstandingClient(fail_page=1)
        execute_candidate_parse(run, storage, deployment, replay)
        assert first.calls == [1, 2] and resumed.calls == [2] and replay.calls == []
        checkpoints = DocumentProcessingService().load_checkpoints(run.binding)
        # 105 derives a separate exact recorded-text claim, never a model_emission import.
        claim_set = claims.start(run.binding)
        claims.checkpoint(
            claim_set,
            NativePageRequest(
                page_number=1,
                disposition="partial",
                reasons=("source_incomplete",),
                claims=(
                    NativeClaimRequest(
                        canonical_key="invoice.invoice_number",
                        value_type="identifier",
                        anchor=NativeAnchorRequest(
                            element_id=checkpoints[0].page.elements[0].id, text_start=8, text_end=14
                        ),
                    ),
                ),
            ),
        )
        claims.checkpoint(
            claim_set,
            NativePageRequest(
                page_number=2, disposition="no_extraction_target", reasons=("no_target",)
            ),
        )
        claims.seal(claim_set)
        retained = retain_source_pages(
            run.binding, storage=storage, service=RetainedEvidenceWriter(storage)
        )
        assert retained.state == "sealed" and retained.new_pages == 2
        index = CandidateIndexService(storage)
        indexed = index.start(
            run.binding,
            request_key=uuid4(),
            configuration=index_configuration(model_mode="fixture", modalities=("text",)),
        )
        assert index.load_preparation(indexed).parse_configuration == processing.configuration
        manifest = index.prepare(indexed)
        assert manifest.inputs
    before = capture(processing, run)
    assert before.capture.configuration == processing.configuration
    assert before.generation_settings_provenance == "frozen_configuration"
    assert before.commit_provenance == "externally_declared"
    assert before.invocation_authenticity == "not_evaluated"
    assert (
        verify_capture_source(
            before, original_asset_id=processing.asset_id, original_path=storage.path_for_uri(uri)
        ).verified_pages
        == 2
    )
    with pytest.raises(CaptureIntegrityError):
        capture(processing, run, budget=8192)
    if transition == "supersede":
        processing.start()
    else:
        DocumentProcessingService().cancel(run.binding, processing.access)
    after = capture(processing, run)
    assert after.capture == before.capture
    assert after.run_status == {"supersede": "superseded", "cancel": "cancelled"}[transition]
    reader = GenerationEvidenceReader(storage)
    assert (
        reader.manifest(
            processing.document_id, run.binding.parse_generation_id, processing.access
        ).parser_configuration
        == processing.configuration
    )
    page = reader.page(
        processing.document_id, run.binding.parse_generation_id, 1, processing.access
    )
    assert page.page == checkpoints[0].page
    media = reader.render(
        processing.document_id, run.binding.parse_generation_id, 1, processing.access
    )
    assert b"".join(media.chunks())

    def forbidden(*args, **kwargs):
        pytest.fail("Retained105 claim read reparsed the combined model envelope")

    monkeypatch.setattr(
        "lib.document_parsing.page_understanding.codec.decode_page_understanding", forbidden
    )
    projection = claims.rebuild(
        claim_set, credential=RequestCredential.from_principal(processing.principal)
    )
    assert projection["claim_count"] == 1
    with db_connection() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT canonical_asset_id FROM documents WHERE id=%s", (processing.document_id,)
        )
        assert cur.fetchone()["canonical_asset_id"] is None
        cur.execute(
            "SELECT count(*) AS n FROM canonical_fields WHERE document_id=%s",
            (processing.document_id,),
        )
        assert cur.fetchone()["n"] == 0


def test_new_v2_run_supersedes_during_http_without_transaction_or_checkpoint(understanding_source):
    processing, storage, deployment, _ = understanding_source
    old = processing.start()
    claimed = processing.claim()
    with ThreadPoolExecutor(max_workers=1) as pool:
        client = UnderstandingClient(
            after_generate=lambda: pool.submit(processing.start).result(timeout=5)
        )
        with processing.scope(claimed), pytest.raises(ProcessingAuthorityLost):
            execute_candidate_parse(old, storage, deployment, client)
    assert client.calls == [1]
    with db_connection() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT count(*) AS n FROM document_parse_page_checkpoints "
            "WHERE parse_generation_id=%s",
            (old.binding.parse_generation_id,),
        )
        assert cur.fetchone()["n"] == 0

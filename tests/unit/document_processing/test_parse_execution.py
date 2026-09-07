from __future__ import annotations

from dataclasses import replace

import pytest

from lib.document_parsing.source_adapter import DocumentSourceError
from lib.document_processing.errors import ProcessingAuthorityLost, ProcessingError
from lib.document_processing.parse_execution import execute_parse_candidate
from lib.document_processing.parser_configuration import (
    parser_configuration,
    validate_parser_configuration,
)

from .conftest import PageClient


def execute(harness, client, **kwargs):
    return execute_parse_candidate(
        harness.binding,
        storage=harness.storage,
        client=client,
        deployment=harness.deployment,
        service=harness.service,
        **kwargs,
    )


def test_fifty_page_batches_automatically_cover_supported_long_document(execution):
    harness = execution(103)
    client = PageClient()
    with harness.scope():
        result = execute(harness, client)
    assert client.calls == list(range(1, 104))
    assert (result.page_count, result.new_pages, result.resumed_pages, result.batches) == (
        103,
        103,
        0,
        3,
    )
    assert result.deployment_declaration == "fixture:synthetic-v1"
    assert len(harness.service.structure.chunks) == 103
    assert {page.state for page in harness.service.structure.pages} == {"processed"}


def test_outage_resumes_checkpoints_and_sealed_retry_never_repeats_model_calls(execution):
    harness = execution(4)
    client = PageClient(fail_page=3)
    with harness.scope(), pytest.raises(RuntimeError, match="outage"):
        execute(harness, client, batch_pages=2)
    assert len(harness.service.checkpoints) == 2 and harness.service.structure is None
    resumed = PageClient()
    with harness.scope():
        result = execute(harness, resumed, batch_pages=2)
        replay = execute(harness, PageClient(fail_page=1), batch_pages=2)
    assert resumed.calls == [3, 4]
    assert (result.resumed_pages, result.new_pages) == (2, 2)
    assert replay.structure_sha256 == result.structure_sha256
    assert (replay.resumed_pages, replay.new_pages, replay.batches) == (4, 0, 0)


def test_lost_run_after_model_call_never_checkpoints_seals_or_calls_next_page(execution):
    harness = execution()
    client = PageClient(after_generate=lambda: setattr(harness.service, "active", False))
    with harness.scope(), pytest.raises(RuntimeError, match="authority loss"):
        execute(harness, client)
    assert (
        client.calls == [1]
        and harness.service.checkpoints == []
        and harness.service.structure is None
    )


def test_unclaimed_attempt_and_invalid_budgets_do_not_read_source(execution, monkeypatch):
    harness = execution()
    monkeypatch.setattr(
        "lib.document_processing.parse_execution.load_processing_source",
        lambda binding: pytest.fail("Unclaimed/invalid execution read the source"),
    )
    with pytest.raises(ProcessingAuthorityLost):
        execute(harness, PageClient())
    for budget in [0, 501, 2.5, True]:
        with harness.scope(), pytest.raises(ProcessingError, match="batch"):
            execute(harness, PageClient(), batch_pages=budget)


def test_frozen_versions_and_declared_deployment_must_match_before_source_io(
    execution, monkeypatch
):
    harness = execution()
    monkeypatch.setattr(
        harness.storage,
        "path_for_uri",
        lambda uri: pytest.fail("Configuration drift reached source IO"),
    )
    for field in [
        "profile",
        "served_model",
        "source_engine",
        "model_revision",
        "prompt_version",
        "output_schema_version",
        "normalizer_version",
        "chunker_version",
        "renderer",
        "renderer_version",
    ]:
        changed = harness.registered.model_copy(
            update={
                "configuration": harness.registered.configuration.model_copy(
                    update={field: "changed"}
                )
            }
        )
        monkeypatch.setattr(
            "lib.document_processing.parse_execution.load_processing_source",
            lambda binding, value=changed: value,
        )
        with harness.scope(), pytest.raises(ProcessingError, match="configuration"):
            execute(harness, PageClient())


def test_fixture_cannot_be_replayed_as_a_live_declared_run(execution):
    harness = execution()
    live = harness.deployment.model_copy(update={"mode": "live"})
    assert (
        parser_configuration(live, harness.registered.mime_type).model_revision
        == "declared-live:synthetic-v1"
    )
    with pytest.raises(ProcessingError, match="configuration"):
        validate_parser_configuration(
            harness.registered.configuration, live, harness.registered.mime_type
        )
    for revision in ["", " ", harness.deployment.served_model]:
        with pytest.raises((ValueError, ProcessingError)):
            parser_configuration(
                harness.deployment.model_copy(update={"revision": revision}),
                harness.registered.mime_type,
            )


def test_corrupted_bytes_and_registered_size_do_not_reach_model(execution, monkeypatch):
    harness = execution()
    source = harness.registered
    client = PageClient()
    changed = source.model_copy(update={"byte_size": source.byte_size + 1})
    monkeypatch.setattr(
        "lib.document_processing.parse_execution.load_processing_source", lambda binding: changed
    )
    with harness.scope(), pytest.raises(ProcessingError, match="size"):
        execute(harness, client)
    monkeypatch.setattr(
        "lib.document_processing.parse_execution.load_processing_source", lambda binding: source
    )
    harness.storage.path_for_uri(source.uri).write_bytes(b"changed original")
    with harness.scope(), pytest.raises(DocumentSourceError, match="registered hash"):
        execute(harness, client)
    assert client.calls == [] and harness.service.inventory is None


@pytest.mark.parametrize(
    "field,value",
    [
        ("model_name", "wrong-model"),
        ("prompt_version", "wrong-prompt"),
        ("structured_output_used", False),
        ("finish_reason", "length"),
    ],
)
def test_invocation_mismatch_cannot_checkpoint(execution, field, value):
    harness = execution()

    class WrongClient(PageClient):
        def generate(self, request):
            return replace(super().generate(request), **{field: value})

    with harness.scope(), pytest.raises(ProcessingError, match="invocation"):
        execute(harness, WrongClient())
    assert harness.service.checkpoints == []


def test_pdf_render_scale_is_used_for_new_pages_and_resume(execution, tmp_path, monkeypatch):
    import pypdfium2 as pdfium

    harness = execution()
    path = tmp_path / "scale.pdf"
    pdf = pdfium.PdfDocument.new()
    page = pdf.new_page(20, 30)
    page.close()
    pdf.save(path)
    pdf.close()
    stored = harness.storage.store_bytes(path.read_bytes(), kind="canonical", role="original")
    config = parser_configuration(harness.deployment, "application/pdf", render_scale=1.5)
    source = harness.registered.model_copy(
        update={
            "mime_type": "application/pdf",
            "configuration": config,
            "uri": stored.uri,
            "original_sha256": stored.sha256,
            "byte_size": stored.byte_size,
        }
    )
    harness.service.configuration = config
    monkeypatch.setattr(
        "lib.document_processing.parse_execution.load_processing_source", lambda binding: source
    )
    with harness.scope():
        execute(harness, PageClient())
        replay = execute(harness, PageClient(fail_page=1))
    rendered = harness.service.checkpoints[0].page.source
    assert (rendered.pixel_width, rendered.pixel_height) == (30, 45)
    assert rendered.renderer_version == config.renderer_version
    assert replay.new_pages == 0


def test_all_five_hundred_pages_are_processed_and_page_501_is_rejected_before_model(execution):
    harness = execution(500)
    client = PageClient()
    with harness.scope():
        result = execute(harness, client)
    assert client.calls == list(range(1, 501)) and result.batches == 10
    unsupported = execution(501)
    no_call = PageClient()
    with unsupported.scope(), pytest.raises(DocumentSourceError, match="page count"):
        execute(unsupported, no_call)
    assert no_call.calls == [] and unsupported.service.inventory is None

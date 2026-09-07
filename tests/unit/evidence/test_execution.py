from __future__ import annotations

import copy

import pytest

from lib.evidence.errors import EvidenceConflict, EvidenceUnavailable
from lib.evidence.manifest import completion_manifest, expected_render_set
from lib.evidence.render_execution import retain_source_pages


def execute(harness, writer, **kwargs):
    return retain_source_pages(harness.binding, storage=harness.storage, service=writer, **kwargs)


def test_all_pages_retain_in_bounded_batches_and_replay_without_rendering(retained, monkeypatch):
    harness, writer = retained
    first = execute(harness, writer, max_new_pages=1)
    assert (first.state, first.new_pages, len(first.remaining_page_ids)) == ("pending", 1, 2)
    done = execute(harness, writer, max_new_pages=2)
    assert (done.state, done.new_pages, done.remaining_page_ids) == ("sealed", 2, ())
    monkeypatch.setattr(
        "lib.evidence.render_execution.DocumentSource",
        lambda *a, **k: pytest.fail("Replay rendered source"),
    )
    replay = execute(harness, writer)
    assert replay.new_pages == 0 and replay.completion_sha256 == done.completion_sha256
    assert [a.page_number for a in writer.assets] == [1, 2, 3]


@pytest.mark.parametrize(
    "field", ["structure_sha256", "inventory_sha256", "config_sha256", "original_sha256"]
)
def test_expected_manifest_rejects_wrong_persisted_generation_hash(retained, field):
    _, writer = retained
    row = {**writer.row, field: "0" * 64}
    with pytest.raises(EvidenceConflict):
        expected_render_set(row, writer.checkpoints)


def test_checkpoint_mutation_cannot_be_hidden_by_a_matching_page_count(retained):
    _, writer = retained
    checkpoints = copy.deepcopy(writer.checkpoints)
    checkpoints[1]["raw_output"] += " "
    with pytest.raises(EvidenceConflict):
        expected_render_set(writer.row, checkpoints)
    with pytest.raises(EvidenceConflict):
        completion_manifest(writer.expected, ())


def test_renderer_drift_fails_before_original_bytes_are_read(retained, monkeypatch):
    harness, writer = retained
    writer.row["config_json"]["renderer_version"] = "historical-different-version"
    monkeypatch.setattr(
        harness.storage, "path_for_uri", lambda *a: pytest.fail("Drift reached source IO")
    )
    with pytest.raises(EvidenceConflict):
        execute(harness, writer)


def test_missing_retained_bytes_prevent_replay_seal(retained):
    harness, writer = retained
    execute(harness, writer)
    harness.storage.path_for_uri(writer.assets[1].uri).unlink()
    with pytest.raises(EvidenceUnavailable):
        execute(harness, writer)


def test_interrupted_staging_cleans_only_new_unreferenced_objects(retained, monkeypatch):
    harness, writer = retained
    execute(harness, writer, max_new_pages=1)
    retained_path = harness.storage.path_for_uri(writer.assets[0].uri)
    cleaned = []

    def cleanup(stored):
        cleaned.append(stored)
        assert all(stored.uri != item.uri for item in writer.assets)
        if stored.created:
            stored.path.unlink()

    monkeypatch.setattr("lib.evidence.render_execution.cleanup_unreferenced_stored_object", cleanup)
    monkeypatch.setattr(
        writer,
        "checkpoint",
        lambda *a: (_ for _ in ()).throw(RuntimeError("Controlled checkpoint failure")),
    )
    with pytest.raises(RuntimeError, match="checkpoint"):
        execute(harness, writer)
    assert len(cleaned) == 1 and retained_path.exists()
    assert not cleaned[0].path.exists()


@pytest.mark.parametrize("budget", [0, 33, True, 1.5])
def test_invalid_bounds_do_not_open_source(retained, monkeypatch, budget):
    harness, writer = retained
    monkeypatch.setattr(
        writer, "start", lambda *a: pytest.fail("Invalid bounds acquired authority")
    )
    with pytest.raises(EvidenceConflict):
        execute(harness, writer, max_new_pages=budget)


def digital_pdf(rotation):
    stream = (
        b"BT /F1 12 Tf 10 40 Td (Independent original digital text "
        b"has more than thirty-two characters.) Tj ET"
    )
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        (
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 200 100] /Rotate {rotation} "
            "/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>"
        ).encode(),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
    ]
    output = bytearray(b"%PDF-1.4\n")
    offsets = []
    for number, obj in enumerate(objects, 1):
        offsets.append(len(output))
        output.extend(f"{number} 0 obj\n".encode() + obj + b"\nendobj\n")
    start = len(output)
    output.extend(b"xref\n0 6\n0000000000 65535 f \n")
    for offset in offsets:
        output.extend(f"{offset:010d} 00000 n \n".encode())
    output.extend(f"trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n{start}\n%%EOF\n".encode())
    return bytes(output)


@pytest.mark.parametrize("rotation", [0, 90])
def test_digital_text_page_excluded_from_visual_index_still_retains_exact_raster(
    execution, monkeypatch, rotation
):
    from lib.document_processing.parse_execution import execute_parse_candidate
    from lib.document_processing.parser_configuration import parser_configuration
    from lib.search.indexing.projection import visual_reasons
    from tests.unit.document_processing.conftest import MemoryProcessingService, PageClient
    from tests.unit.evidence.conftest import MemoryEvidenceWriter

    harness = execution(1)
    stored = harness.storage.store_bytes(digital_pdf(rotation), kind="canonical", role="original")
    configuration = parser_configuration(harness.deployment, "application/pdf")
    harness.registered = harness.registered.model_copy(
        update={
            "uri": stored.uri,
            "mime_type": "application/pdf",
            "byte_size": stored.byte_size,
            "original_sha256": stored.sha256,
            "configuration": configuration,
        }
    )
    harness.service = MemoryProcessingService(configuration)
    monkeypatch.setattr(
        "lib.document_processing.parse_execution.load_processing_source",
        lambda binding: harness.registered,
    )
    with harness.scope():
        execute_parse_candidate(
            harness.binding,
            storage=harness.storage,
            client=PageClient(),
            deployment=harness.deployment,
            service=harness.service,
        )
    page = harness.service.structure.pages[0]
    assert visual_reasons(page, original_is_image=False) == ()
    assert page.source.native_text_origin == "pdf_native"
    writer = MemoryEvidenceWriter(harness)
    result = execute(harness, writer)
    assert result.state == "sealed" and len(writer.assets) == 1
    assert writer.assets[0].render.image_sha256 == page.source.image_sha256
    assert (writer.assets[0].render.pixel_width, writer.assets[0].render.pixel_height) == (
        (400, 200) if rotation == 0 else (200, 400)
    )
    assert harness.service.structure.source.pages[0].rotation_degrees == rotation


def test_blank_partial_and_insufficient_pages_remain_in_retention_denominator(execution):
    import json
    from dataclasses import replace

    from lib.document_processing.parse_execution import execute_parse_candidate
    from tests.unit.document_processing.conftest import PageClient
    from tests.unit.evidence.conftest import MemoryEvidenceWriter

    class Outcomes(PageClient):
        def generate(self, request):
            response = super().generate(request)
            output = {**response.normalized_json, "elements": []}
            output["state"] = ("processed", "partial", "insufficient_signal")[
                output["page_number"] - 1
            ]
            return replace(response, normalized_json=output, raw_text=json.dumps(output))

    harness = execution(3)
    with harness.scope():
        execute_parse_candidate(
            harness.binding,
            storage=harness.storage,
            client=Outcomes(),
            deployment=harness.deployment,
            service=harness.service,
        )
    writer = MemoryEvidenceWriter(harness)
    result = execute(harness, writer)
    assert result.state == "sealed" and len(result.completed_page_ids) == 3
    assert len(writer.assets) == 3 and harness.service.structure.chunks == ()
    assert [page.state for page in harness.service.structure.pages] == [
        "processed",
        "partial",
        "insufficient_signal",
    ]


def test_authority_loss_after_expensive_render_prevents_storage_and_registration(
    retained, monkeypatch
):
    from lib.document_parsing.source_adapter import DocumentSource

    harness, writer = retained
    original = DocumentSource.render

    def render(*args, **kwargs):
        result = original(*args, **kwargs)
        writer.active = False
        return result

    monkeypatch.setattr(DocumentSource, "render", render)
    monkeypatch.setattr(
        harness.storage, "store_bytes", lambda *a, **k: pytest.fail("Stale render was stored")
    )
    with pytest.raises(RuntimeError, match="authority loss"):
        execute(harness, writer)
    assert writer.assets == [] and writer.state == "building"


def test_seal_requires_complete_frozen_asset_snapshot_before_io_or_transaction(
    retained, monkeypatch
):
    from lib.evidence.write_service import RetainedEvidenceWriter

    harness, writer = retained
    service = RetainedEvidenceWriter(harness.storage)
    monkeypatch.setattr(service, "snapshot", writer.snapshot)
    monkeypatch.setattr(
        "lib.evidence.write_service.snapshot_render",
        lambda *a: pytest.fail("Incomplete snapshot read bytes"),
    )
    monkeypatch.setattr(
        "lib.evidence.write_service.db_connection",
        lambda *a, **k: pytest.fail("Incomplete verified inventory entered seal transaction"),
    )
    with pytest.raises(EvidenceConflict, match="incomplete"):
        service.seal(writer.binding)

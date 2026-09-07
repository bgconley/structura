from __future__ import annotations

import copy
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from lib.document_parsing.source_adapter import renderer_identity
from lib.document_processing.models import content_digest
from lib.evaluation.annotation_render_binding import rebind_annotation_renders
from lib.evaluation.artifact_verification import verify_capture_source
from lib.evaluation.capture_models import CaptureDeclaration, CaptureIntegrityError
from lib.evaluation.persisted_capture import validate_persisted_capture
from tests.unit.evaluation.conftest import FIXTURES


@pytest.fixture
def declaration():
    return CaptureDeclaration(
        item_id="captured-fixture", commit="a" * 40, max_output_tokens=8192, temperature=0
    )


@pytest.fixture
def stored(inputs):
    capture = inputs[2]
    config = capture.configuration.model_dump(mode="json")
    config["model_revision"] = "fixture:authored-v1"
    structure = capture.structure.model_dump(mode="json")
    return {
        "document_id": uuid4(),
        "processing_run_id": capture.structure.processing_run_id,
        "parse_generation_id": capture.structure.parse_generation_id,
        "creator_run_id": capture.structure.processing_run_id,
        "original_asset_id": capture.structure.source.original_asset_id,
        "original_sha256": capture.structure.source.original_sha256,
        "asset_sha256": capture.structure.source.original_sha256,
        "mime_type": capture.structure.source.mime_type,
        "byte_size": capture.structure.source.byte_size,
        "config_json": config,
        "config_sha256": content_digest(config),
        "inventory_json": structure["source"],
        "inventory_sha256": content_digest(structure["source"]),
        "structure_json": structure,
        "structure_sha256": content_digest(structure),
        "run_status": "sealed",
        "parse_state": "sealed",
        "sealed_at": datetime.now(UTC),
        "checkpoints": [
            dict(
                parse_generation_id=str(capture.structure.parse_generation_id),
                page_number=page.page_number,
                page_id=str(page.id),
                page_json=page.model_dump(mode="json"),
                invocation_json=invocation.model_dump(mode="json"),
                raw_output=raw.raw_output,
                content_sha256=content_digest(
                    dict(
                        page=page.model_dump(mode="json"),
                        invocation=invocation.model_dump(mode="json"),
                        raw=raw.raw_output,
                    )
                ),
            )
            for page, invocation, raw in zip(
                capture.structure.pages,
                capture.structure.invocations,
                capture.raw_pages,
                strict=True,
            )
        ],
    }


@pytest.mark.parametrize("status", ["sealed", "superseded", "cancelled"])
def test_sealed_history_captures_exact_evidence_without_current_selection(
    stored, declaration, status
):
    stored["run_status"] = status
    result = validate_persisted_capture(stored, declaration=declaration)
    assert result.run_status == status
    assert result.capture.structure.parse_generation_id == stored["parse_generation_id"]
    assert len(result.capture.raw_pages) == 2
    assert result.capture.fixture_type == "deterministic_fixture"
    assert result.capture.model_mode == "fixture"
    assert result.storage_integrity == "verified"
    assert (
        result.commit_provenance == result.generation_settings_provenance == "externally_declared"
    )
    assert (
        result.original_artifact_verification == result.invocation_authenticity == "not_evaluated"
    )


@pytest.mark.parametrize(
    "change",
    [
        "config_hash",
        "inventory_hash",
        "structure_hash",
        "checkpoint_hash",
        "raw",
        "missing_page",
        "wrong_page",
        "wrong_creator",
        "asset_hash",
        "source_size",
        "unsealed",
        "inconsistent_chunks",
    ],
)
def test_persisted_corruption_is_rejected_without_raw_data_errors(stored, declaration, change):
    if change in {"config_hash", "inventory_hash", "structure_hash"}:
        stored[change.replace("_hash", "_sha256")] = "0" * 64
    elif change == "checkpoint_hash":
        stored["checkpoints"][0]["content_sha256"] = "0" * 64
    elif change == "raw":
        stored["checkpoints"][0]["raw_output"] = "PRIVATE-CORRUPTION"
    elif change == "missing_page":
        stored["checkpoints"].pop()
    elif change == "wrong_page":
        stored["checkpoints"][0]["page_id"] = str(uuid4())
    elif change == "wrong_creator":
        stored["creator_run_id"] = uuid4()
    elif change == "asset_hash":
        stored["asset_sha256"] = "0" * 64
    elif change == "source_size":
        stored["byte_size"] += 1
    elif change == "unsealed":
        stored["parse_state"] = "building"
    else:
        stored["structure_json"]["chunks"].pop()
        stored["structure_sha256"] = content_digest(stored["structure_json"])
    with pytest.raises(CaptureIntegrityError) as caught:
        validate_persisted_capture(stored, declaration=declaration)
    assert "PRIVATE-CORRUPTION" not in str(caught.value)


def test_mode_comes_from_frozen_declaration_and_unknown_prefix_fails(stored, declaration):
    stored["config_json"]["model_revision"] = "declared-live:operator-declared-v1"
    stored["config_sha256"] = content_digest(stored["config_json"])
    result = validate_persisted_capture(stored, declaration=declaration)
    assert result.capture.fixture_type == "model_backed"
    assert result.capture.model_mode == "live"
    assert result.invocation_authenticity == "not_evaluated"
    for revision in ("v1", "fixture:", "declared-live: "):
        stored["config_json"]["model_revision"] = revision
        stored["config_sha256"] = content_digest(stored["config_json"])
        with pytest.raises(CaptureIntegrityError):
            validate_persisted_capture(stored, declaration=declaration)


def _with_installed_renderer(stored, annotation):
    row = copy.deepcopy(stored)
    rebound = rebind_annotation_renders(
        annotation,
        original_path=FIXTURES / "original.tiff",
        original_asset_id=row["original_asset_id"],
        reference_page_paths={page: FIXTURES / f"page-{page}.png" for page in (1, 2)},
    )
    renderer, version = renderer_identity(row["mime_type"])
    row["config_json"].update(renderer=renderer, renderer_version=version)
    row["config_sha256"] = content_digest(row["config_json"])
    for checkpoint, page, binding in zip(
        row["checkpoints"], row["structure_json"]["pages"], rebound.record.pages, strict=True
    ):
        # This builds a current-runtime fixture capture only after the pinned
        # historical reference pixels have matched the independently read source.
        source_update = dict(
            renderer=renderer,
            renderer_version=version,
            image_sha256=binding.rebound_image_sha256,
        )
        checkpoint["page_json"]["source"].update(source_update)
        page["source"].update(source_update)
        checkpoint["content_sha256"] = content_digest(
            dict(
                page=checkpoint["page_json"],
                invocation=checkpoint["invocation_json"],
                raw=checkpoint["raw_output"],
            )
        )
    row["structure_sha256"] = content_digest(row["structure_json"])
    return row


def test_optional_verifier_reproduces_registered_original_and_all_pages(
    stored, declaration, inputs
):
    captured = validate_persisted_capture(
        _with_installed_renderer(stored, inputs[1]), declaration=declaration
    )
    proof = verify_capture_source(
        captured,
        original_asset_id=captured.source.original_asset_id,
        original_path=FIXTURES / "original.tiff",
    )
    assert proof.verified_pages == 2
    assert proof.rendered_source_identity == "reproduced"
    assert proof.source_pixel_support == "not_evaluated"


def test_optional_verifier_rejects_wrong_asset_source_and_old_renderer(
    stored, declaration, tmp_path
):
    captured = validate_persisted_capture(stored, declaration=declaration)
    with pytest.raises(CaptureIntegrityError):
        verify_capture_source(
            captured, original_asset_id=uuid4(), original_path=FIXTURES / "original.tiff"
        )
    with pytest.raises(CaptureIntegrityError):
        verify_capture_source(
            captured,
            original_asset_id=captured.source.original_asset_id,
            original_path=FIXTURES / "original.tiff",
        )
    private = tmp_path / "source.bin"
    private.write_bytes(b"PRIVATE-CONTENT")
    with pytest.raises(CaptureIntegrityError) as caught:
        verify_capture_source(
            captured, original_asset_id=captured.source.original_asset_id, original_path=private
        )
    assert "PRIVATE-CONTENT" not in str(caught.value)


def test_optional_verifier_bounded_read_rejects_oversized_file(stored, declaration, tmp_path):
    path = tmp_path / "oversized.png"
    with path.open("wb") as file:
        file.write(b"\x89PNG\r\n\x1a\n")
        file.truncate(100 * 1024 * 1024 + 1)
    captured = validate_persisted_capture(stored, declaration=declaration)
    with pytest.raises(CaptureIntegrityError):
        verify_capture_source(
            captured, original_asset_id=captured.source.original_asset_id, original_path=path
        )

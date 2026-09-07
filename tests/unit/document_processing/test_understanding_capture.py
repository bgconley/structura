"""Historical v2 capture decoding is source-bound without installed-factory IO."""

from datetime import UTC, datetime

import pytest

from lib.document_processing.models import content_digest
from lib.evaluation.capture_models import CaptureDeclaration, CaptureIntegrityError
from lib.evaluation.persisted_capture import validate_persisted_capture
from tests.fixtures.page_understanding_client import UnderstandingClient
from tests.unit.document_processing.test_understanding_execution import execute
from tests.unit.document_processing.test_understanding_execution import (
    understanding as understanding,
)


def stored(harness):
    structure = harness.service.structure.model_dump(mode="json")
    inventory = structure["source"]
    return {
        "document_id": harness.binding.document_id,
        "processing_run_id": harness.binding.processing_run_id,
        "parse_generation_id": harness.binding.parse_generation_id,
        "creator_run_id": harness.binding.processing_run_id,
        "original_asset_id": harness.registered.original_asset_id,
        "original_sha256": inventory["original_sha256"],
        "asset_sha256": inventory["original_sha256"],
        "mime_type": inventory["mime_type"],
        "byte_size": inventory["byte_size"],
        "config_json": harness.service.configuration.model_dump(mode="json"),
        "config_sha256": harness.service.configuration.fingerprint,
        "inventory_json": inventory,
        "inventory_sha256": content_digest(inventory),
        "structure_json": structure,
        "structure_sha256": content_digest(structure),
        "run_status": "superseded",
        "parse_state": "sealed",
        "sealed_at": datetime.now(UTC),
        "checkpoints": [
            {
                "parse_generation_id": harness.binding.parse_generation_id,
                "page_number": p.page.page_number,
                "page_id": p.page.id,
                "page_json": p.page.model_dump(mode="json"),
                "invocation_json": p.invocation.model_dump(mode="json"),
                "raw_output": p.raw_output,
                "content_sha256": content_digest(
                    {
                        "page": p.page.model_dump(mode="json"),
                        "invocation": p.invocation.model_dump(mode="json"),
                        "raw": p.raw_output,
                    }
                ),
            }
            for p in harness.service.checkpoints
        ],
    }


def declaration(**updates):
    return CaptureDeclaration(
        **{
            "item_id": "v2-fixture",
            "commit": "a" * 40,
            "max_output_tokens": 14000,
            "temperature": 0,
            **updates,
        }
    )


def test_historical_v2_capture_keeps_raw_and_frozen_settings_without_factory_or_model(
    understanding, monkeypatch
):
    harness = understanding()
    with harness.scope():
        execute(harness, UnderstandingClient())
    row = stored(harness)
    monkeypatch.setattr(
        "lib.document_processing.understanding_configuration.installed_understanding_configuration",
        lambda *a, **k: pytest.fail("Historical capture reads installed source/model definitions"),
    )
    captured = validate_persisted_capture(row, declaration=declaration())
    assert captured.generation_settings_provenance == "frozen_configuration"
    assert captured.commit_provenance == "externally_declared"
    assert captured.invocation_authenticity == "not_evaluated"
    assert captured.capture.configuration == harness.service.configuration
    assert captured.capture.raw_pages[0].raw_output == harness.service.checkpoints[0].raw_output
    assert captured.capture.fixture_type == "deterministic_fixture"
    assert (
        type(captured.capture).model_validate_json(captured.capture.model_dump_json())
        == captured.capture
    )
    with pytest.raises(CaptureIntegrityError):
        validate_persisted_capture(row, declaration=declaration(max_output_tokens=8192))


@pytest.mark.parametrize(
    "field", ["original_asset_id", "original_sha256", "source_inventory_sha256"]
)
def test_historical_context_source_mismatch_cannot_pass_with_rehashed_configuration(
    understanding, field
):
    harness = understanding()
    with harness.scope():
        execute(harness, UnderstandingClient())
    row = stored(harness)
    row["config_json"]["context"][field] = (
        "00000000-0000-0000-0000-000000000000" if field == "original_asset_id" else "0" * 64
    )
    row["config_sha256"] = content_digest(row["config_json"])
    with pytest.raises(CaptureIntegrityError):
        validate_persisted_capture(row, declaration=declaration())

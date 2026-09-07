from __future__ import annotations

import json
from uuid import uuid4

import pytest
from pydantic import ValidationError

from lib.evaluation.annotations import DocumentAnnotation
from lib.evaluation.captures import DocumentCapture
from lib.evaluation.identity import artifact_digest
from lib.evaluation.manifest import EvaluationManifest
from lib.evaluation.scorer import score_evaluation
from tests.unit.evaluation.conftest import evaluate


@pytest.mark.parametrize("field", ["goldMetrics", "metrics", "thresholds"])
def test_computed_scores_cannot_be_supplied_as_inputs(inputs, field):
    for model in inputs:
        payload = model.model_dump(mode="json")
        payload[field] = {"precision": 1.0}
        with pytest.raises(ValidationError, match="Extra inputs"):
            type(model).model_validate(payload)


def test_manifest_pin_and_exact_document_membership_are_mandatory(inputs):
    manifest, annotation, capture = inputs
    with pytest.raises(ValueError, match="frozen identity"):
        score_evaluation(manifest, [annotation], [capture], expected_manifest_sha256="0" * 64)
    for annotation_rows, capture_rows in [
        ([], [capture]),
        ([annotation], []),
        ([annotation, annotation], [capture]),
    ]:
        with pytest.raises(ValueError, match="exactly once"):
            score_evaluation(
                manifest,
                annotation_rows,
                capture_rows,
                expected_manifest_sha256=artifact_digest(manifest),
            )


@pytest.mark.parametrize("change", ["source", "run", "parse", "profile", "configuration"])
def test_binding_rejects_source_run_parse_profile_configuration_changes(inputs, change):
    data = inputs[2].model_dump(mode="json")
    if change == "source":
        data["structure"]["source"]["original_sha256"] = "1" * 64
    elif change == "run":
        data["structure"]["processing_run_id"] = str(uuid4())
    elif change == "parse":
        data["structure"]["parse_generation_id"] = str(uuid4())
    elif change == "profile":
        data["configuration"]["profile"] = "another-profile"
    else:
        data["configuration_sha256"] = "2" * 64
    with pytest.raises(ValueError, match="binding"):
        evaluate(inputs, capture=DocumentCapture.model_validate(data))


def test_edited_capture_cannot_reuse_original_frozen_digest(inputs):
    manifest, annotation, capture = inputs
    data = capture.model_dump(mode="json")
    data["max_output_tokens"] = 4096
    with pytest.raises(ValueError, match="binding"):
        score_evaluation(
            manifest,
            [annotation],
            [DocumentCapture.model_validate(data)],
            expected_manifest_sha256=artifact_digest(manifest),
        )


@pytest.mark.parametrize("change", ["raw", "normalized", "render", "invocation", "origin"])
def test_rehashed_capture_still_requires_internal_raw_render_and_origin_consistency(inputs, change):
    data = inputs[2].model_dump(mode="json")
    if change == "raw":
        output = json.loads(data["raw_pages"][0]["raw_output"])
        output["elements"][0]["text"] = "secret changed text"
        data["raw_pages"][0]["raw_output"] = json.dumps(output)
    elif change == "normalized":
        data["structure"]["pages"][0]["elements"][0]["text"] = "unsupported changed text"
    elif change == "render":
        data["structure"]["pages"][0]["source"]["image_sha256"] = "3" * 64
    elif change == "invocation":
        data["structure"]["invocations"][0]["profile"] = "other-profile"
    else:
        data["structure"]["chunks"][0]["text_origins"] = ["pdf_native"]
    with pytest.raises(ValueError):
        evaluate(inputs, capture=DocumentCapture.model_validate(data))


def test_fixture_cannot_claim_live_execution_or_blind_holdout(inputs):
    data = inputs[2].model_dump(mode="json")
    data["model_mode"] = "live"
    with pytest.raises(ValidationError, match="Fixture"):
        DocumentCapture.model_validate(data)
    manifest = inputs[0].model_copy(update={"split": "blind_holdout"})
    with pytest.raises(ValueError, match="Blind holdout"):
        score_evaluation(
            manifest, [inputs[1]], [inputs[2]], expected_manifest_sha256=artifact_digest(manifest)
        )


@pytest.mark.parametrize("purpose", ["prompt_tuning", "development", "evaluation"])
def test_declared_holdout_exposure_is_rejected(inputs, purpose):
    data = inputs[0].model_dump(mode="json")
    data["split"] = "blind_holdout"
    data["exposures"] = [
        dict(
            item_id=inputs[1].item_id,
            purpose=purpose,
            occurred_at="2026-09-01T12:00:00Z",
            actor_reference="test-author",
        )
    ]
    with pytest.raises(ValidationError, match="untouched holdout"):
        EvaluationManifest.model_validate(data)


def test_holdout_group_overlap_and_post_freeze_labels_are_rejected(inputs):
    data = inputs[0].model_dump(mode="json")
    data["split"] = "blind_holdout"
    data["development_template_groups"] = [inputs[1].template_group]
    with pytest.raises(ValidationError, match="overlap"):
        EvaluationManifest.model_validate(data)
    labels = inputs[1].model_dump(mode="json")
    labels["provenance"]["created_at"] = "2026-09-03T00:00:00Z"
    with pytest.raises(ValueError, match="precede"):
        evaluate(inputs, annotation=DocumentAnnotation.model_validate(labels))


def test_invalid_sensitive_counts_and_nonfinite_geometry_fail_closed(inputs):
    data = inputs[1].model_dump(mode="json")
    data["pages"][0]["sensitive_text"][0]["occurrences"] = 2
    with pytest.raises(ValueError, match="occurrence"):
        evaluate(inputs, annotation=DocumentAnnotation.model_validate(data))
    data["pages"][0]["regions"][0]["bbox"]["left"] = float("nan")
    with pytest.raises(ValidationError):
        DocumentAnnotation.model_validate(data)

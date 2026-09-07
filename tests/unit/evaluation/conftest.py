from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from lib.document_parsing.model_output import PageParseOutput
from lib.document_parsing.normalization import normalize_page
from lib.document_parsing.searchable_text import page_chunks
from lib.evaluation.annotations import DocumentAnnotation
from lib.evaluation.captures import DocumentCapture
from lib.evaluation.identity import artifact_digest
from lib.evaluation.manifest import EvaluationManifest
from lib.evaluation.scorer import score_evaluation

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "evaluation"


@pytest.fixture
def inputs() -> tuple[EvaluationManifest, DocumentAnnotation, DocumentCapture]:
    return (
        EvaluationManifest.model_validate_json((FIXTURES / "manifest.json").read_text()),
        DocumentAnnotation.model_validate_json((FIXTURES / "annotation.json").read_text()),
        DocumentCapture.model_validate_json((FIXTURES / "capture.json").read_text()),
    )


def evaluate(
    inputs: tuple[EvaluationManifest, DocumentAnnotation, DocumentCapture],
    *,
    capture: DocumentCapture | None = None,
    annotation: DocumentAnnotation | None = None,
) -> dict[str, Any]:
    manifest, original_annotation, original_capture = inputs
    annotation, capture = annotation or original_annotation, capture or original_capture
    payload = manifest.model_dump(mode="json")
    payload["cases"][0]["annotation_sha256"] = artifact_digest(annotation)
    payload["cases"][0]["capture_sha256"] = artifact_digest(capture)
    manifest = EvaluationManifest.model_validate(payload)
    return score_evaluation(
        manifest, [annotation], [capture], expected_manifest_sha256=artifact_digest(manifest)
    )


def replace_output(capture: DocumentCapture, output: dict[str, Any]) -> DocumentCapture:
    payload = capture.model_dump(mode="json")
    index = output["page_number"] - 1
    source = capture.structure.pages[index].source
    assert source is not None
    raw = json.dumps(output, sort_keys=True)
    page = normalize_page(
        PageParseOutput.model_validate(output), source, capture.structure.parse_generation_id
    )
    payload["structure"]["pages"][index] = page.model_dump(mode="json")
    payload["raw_pages"][index]["raw_output"] = raw
    payload["structure"]["invocations"][index]["raw_output_sha256"] = hashlib.sha256(
        raw.encode()
    ).hexdigest()
    payload["structure"]["chunks"] = []
    changed = DocumentCapture.model_validate(payload)
    payload["structure"]["chunks"] = [
        chunk.model_dump(mode="json")
        for page in changed.structure.pages
        for chunk in page_chunks(page, changed.structure.parse_generation_id)
    ]
    return DocumentCapture.model_validate(payload)

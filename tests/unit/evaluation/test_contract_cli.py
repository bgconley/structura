from __future__ import annotations

import hashlib
import json
import stat
import subprocess
import sys
from pathlib import Path

import jsonschema
import pytest

from lib.evaluation.annotations import DocumentAnnotation
from lib.evaluation.captures import DocumentCapture
from lib.evaluation.identity import artifact_digest
from lib.evaluation.manifest import EvaluationManifest
from tests.unit.evaluation.conftest import FIXTURES

ROOT = Path(__file__).resolve().parents[3]


@pytest.mark.parametrize(
    "name,model",
    [
        ("source_annotation", DocumentAnnotation),
        ("parse_capture", DocumentCapture),
        ("parse_evaluation", EvaluationManifest),
    ],
)
def test_committed_input_schemas_match_runtime_contracts(name, model):
    schema = json.loads((ROOT / "contracts" / "evaluation" / f"{name}.v1.schema.json").read_text())
    assert schema == {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": f"structura:{name}.v1",
        **model.model_json_schema(),
    }
    jsonschema.Draft202012Validator.check_schema(schema)


def test_synthetic_original_and_renders_match_annotation_hashes(inputs):
    annotation = inputs[1]
    assert hashlib.sha256((FIXTURES / "original.tiff").read_bytes()).hexdigest() == (
        annotation.original_sha256
    )
    for page in annotation.pages:
        assert hashlib.sha256(
            (FIXTURES / f"page-{page.page_number}.png").read_bytes()
        ).hexdigest() == (page.image_sha256)


def test_cli_scores_provided_inputs_only_and_reports_nonacceptance(inputs, tmp_path):
    output = tmp_path / "report.json"
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "score_document_parse.py"),
            "--manifest",
            str(FIXTURES / "manifest.json"),
            "--expected-manifest-sha256",
            artifact_digest(inputs[0]),
            "--annotations",
            str(FIXTURES / "annotation.json"),
            "--captures",
            str(FIXTURES / "capture.json"),
            "--output",
            str(output),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    report = json.loads(output.read_text())
    assert stat.S_IMODE(output.stat().st_mode) == 0o600
    assert report["documents_scored"] == 1
    assert report["unevaluated_stages"]["release_acceptance"] == "not_evaluated"
    assert "INV-001" not in output.read_text()
    assert "release acceptance remains not evaluated" in result.stdout


def test_cli_rejects_bad_input_without_echoing_private_payload(inputs, tmp_path):
    data = inputs[2].model_dump(mode="json")
    data["private_source"] = "PRIVATE-MARKER-DO-NOT-LOG"
    capture = tmp_path / "capture.json"
    capture.write_text(json.dumps(data))
    output = tmp_path / "report.json"
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "score_document_parse.py"),
            "--manifest",
            str(FIXTURES / "manifest.json"),
            "--expected-manifest-sha256",
            artifact_digest(inputs[0]),
            "--annotations",
            str(FIXTURES / "annotation.json"),
            "--captures",
            str(capture),
            "--output",
            str(output),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 2
    assert "PRIVATE-MARKER" not in result.stdout + result.stderr
    assert not output.exists()


def test_cli_refuses_to_overwrite_an_input_or_existing_report(inputs, tmp_path):
    annotation = tmp_path / "annotation.json"
    original = (FIXTURES / "annotation.json").read_bytes()
    annotation.write_bytes(original)
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "score_document_parse.py"),
            "--manifest",
            str(FIXTURES / "manifest.json"),
            "--expected-manifest-sha256",
            artifact_digest(inputs[0]),
            "--annotations",
            str(annotation),
            "--captures",
            str(FIXTURES / "capture.json"),
            "--output",
            str(annotation),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 2
    assert annotation.read_bytes() == original
    assert "new writable private file" in result.stderr
    assert "INV-001" not in result.stdout + result.stderr

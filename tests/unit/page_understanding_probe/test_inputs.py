"""Source-only truth and byte reconstruction, without any model execution."""

import hashlib
import json
import re
import shutil
from pathlib import Path

import pytest

from lib.config import Settings
from lib.evaluation.text_scoring import annotated_text, normalized_text
from scripts.gpu.page_understanding_probe import inputs


def test_original_reconstruction_matches_frozen_bytes_and_labels():
    result = inputs.load_inputs()
    assert len(result.original) == 12960384
    assert hashlib.sha256(result.original).hexdigest() == result.annotation.original_sha256
    assert [page["family"] for page in result.expectations["pages"]] == [
        "invoice",
        "receipt",
        "medical_eob",
    ]
    assert [len(page["rows"]) for page in result.expectations["pages"]] == [2, 2, 2]
    assert result.annotation.provenance.source_only
    for page in result.annotation.pages:
        text = normalized_text(annotated_text(page))
        for item in page.sensitive_text:
            matches = re.findall(rf"(?<!\w){re.escape(normalized_text(item.text))}(?!\w)", text)
            assert len(matches) == item.occurrences, (page.page_number, item.text)
    fields = {
        c["canonical_key"]: c["typed_value"]
        for p in result.expectations["pages"]
        for c in p["fields"]
    }
    assert fields["receipt.transaction.receipt_number"] == "0000789"
    assert fields["medical_eob.total_plan_paid"] == {"amount": "120.00", "currency": "USD"}
    assert fields["invoice.amount_paid"] == {"amount": "0.00", "currency": "USD"}
    assert (
        result.expectations["pages"][0]["rows"][1]["claims"][-1]["typed_value"]["amount"] == "-5.25"
    )


@pytest.mark.parametrize("filename", ["page-1.png", "source-recipe.json", "expectations.json"])
def test_frozen_source_identity_rejects_tampering(tmp_path, filename):
    directory = tmp_path / "fixture"
    shutil.copytree(inputs.FIXTURE, directory)
    path = directory / filename
    if filename == "expectations.json":
        expected = json.loads(path.read_text())
        expected["original_sha256"] = "0" * 64
        path.write_text(json.dumps(expected))
    else:
        with path.open("ab") as stream:
            stream.write(b" ")
    with pytest.raises(RuntimeError):
        inputs.load_inputs(directory)


def test_preflight_requires_fixed_live_profile_fresh_runtime_and_clean_commit(
    tmp_path, monkeypatch
):
    output = tmp_path / "fresh"
    settings = Settings(runtime_root=output, model_mode="live")
    commit = "a" * 40
    calls = []
    monkeypatch.setattr(inputs.subprocess, "check_output", lambda *a, **k: commit)
    monkeypatch.setattr(
        inputs.subprocess, "run", lambda *a, **k: type("Result", (), {"returncode": 0})()
    )
    monkeypatch.setattr(inputs, "verify_isolated_database", lambda value: calls.append(value))
    assert inputs.preflight(settings, output, commit) == commit and len(calls) == 1
    for bad, target, revision in (
        (settings.model_copy(update={"model_mode": "fixture"}), output, commit),
        (settings, tmp_path / "other", commit),
        (settings, output, "b" * 40),
    ):
        with pytest.raises(RuntimeError):
            inputs.preflight(bad, target, revision)
    assert len(calls) == 1
    output.mkdir()
    with pytest.raises(RuntimeError):
        inputs.preflight(settings, output, commit)


def test_bounded_fixture_read(tmp_path: Path):
    path = tmp_path / "oversized"
    path.write_bytes(b"12345")
    with pytest.raises(RuntimeError, match="bound"):
        inputs._read(path, 4)


def test_untracked_probe_code_or_source_cannot_claim_old_commit(tmp_path, monkeypatch):
    commit = "a" * 40
    monkeypatch.setattr(inputs.subprocess, "check_output", lambda *a, **k: commit)

    def result(command, **kwargs):
        return type("Result", (), {"returncode": 1 if "ls-files" in command else 0})()

    monkeypatch.setattr(inputs.subprocess, "run", result)
    monkeypatch.setattr(inputs, "verify_isolated_database", lambda _: pytest.fail("DB touched"))
    with pytest.raises(RuntimeError, match="belong"):
        inputs.preflight(
            Settings(runtime_root=tmp_path / "fresh", model_mode="live"), tmp_path / "fresh", commit
        )


def test_authored_obligations_use_frozen_registry_types():
    from lib.document_parsing.page_understanding.registry import RULE_BY_KEY

    expectations = inputs.load_inputs().expectations
    for page in expectations["pages"]:
        fields = [*page["fields"], *(claim for row in page["rows"] for claim in row["claims"])]
        for field in fields:
            rule = RULE_BY_KEY[field["canonical_key"]]
            assert rule.value_type == field["value_type"]
            assert field["canonical_key"].startswith(page["family"] + ".")

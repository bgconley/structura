from __future__ import annotations

from pathlib import Path

import pytest

from lib.model_runtime.model_corpus_report_statuses import (
    assert_model_corpus_report_statuses_pass,
)


def test_model_corpus_report_statuses_reject_not_evaluated_statuses() -> None:
    artifact = {"checks": {"status": "not_evaluated"}}

    with pytest.raises(SystemExit, match="checks.status='not_evaluated'"):
        assert_model_corpus_report_statuses_pass("qwen", artifact, Path("qwen.json"))


def test_model_corpus_report_statuses_reject_non_empty_failure_lists() -> None:
    artifact = {"checks": {"status": "passed", "failures": [{"name": "goldCorpusQuality"}]}}

    with pytest.raises(SystemExit, match="checks.failures"):
        assert_model_corpus_report_statuses_pass("qwen", artifact, Path("qwen.json"))


def test_model_corpus_report_statuses_reject_non_empty_problem_lists() -> None:
    artifact = {
        "checks": {
            "status": "passed",
            "repeatabilityFingerprints": {
                "status": "passed",
                "missingByReport": [{"runId": "phase85-pass-2"}],
            },
        },
    }

    with pytest.raises(SystemExit, match="checks.repeatabilityFingerprints.missingByReport"):
        assert_model_corpus_report_statuses_pass("qwen", artifact, Path("qwen.json"))


def test_model_corpus_report_statuses_reject_positive_problem_counts() -> None:
    artifact = {
        "acceptanceGates": {
            "hardCorrectnessInvariants": {
                "status": "passed",
                "totalViolationCount": 1,
            },
        },
    }

    with pytest.raises(
        SystemExit, match="acceptanceGates.hardCorrectnessInvariants.totalViolationCount"
    ):
        assert_model_corpus_report_statuses_pass("qwen", artifact, Path("qwen.json"))


def test_model_corpus_report_statuses_accept_passed_and_not_required_statuses() -> None:
    artifact = {
        "status": "passed",
        "checks": {"status": "passed"},
        "acceptanceGates": {
            "repeatabilityFingerprints": {"status": "not_required"},
        },
    }

    assert_model_corpus_report_statuses_pass("qwen", artifact, Path("qwen.json"))

from __future__ import annotations

from typing import Any

from lib.extraction.candidate_admission_models import CANDIDATE_GATE_VERSION
from lib.extraction.contract_registry import CONTRACT_REGISTRY_VERSION
from lib.extraction.region_envelope import REGION_ENVELOPE_VERSION
from lib.model_runtime.profiles import (
    GRANITE_VISION_PROFILE,
    QWEN_SEMANTIC_PROFILE,
    QWEN_VISION_PROFILE,
    TEXT_EMBED_PROFILE,
    VISUAL_EMBED_PROFILE,
    get_model_profile,
)
from lib.model_runtime.reliability_report import build_phase85_run_manifest
from lib.model_runtime.reliability_report_lineage_acceptance import report_lineage_check
from lib.model_runtime.reliability_versions import (
    GRANITE_PROMPT_VERSION,
    RECONCILER_VERSION,
    VISUAL_INPUT_PLAN_VERSION,
)
from lib.semantic_annotations.extraction_plan_repository import PLANNER_VERSION
from lib.semantic_annotations.prompting import SMART_PROMPT_VERSION


def test_report_lineage_fails_for_missing_report_identity() -> None:
    report = _lineage_report()
    report.pop("fixtureType")
    report["runManifest"].pop("model_mode")

    summary = report_lineage_check([report])

    assert summary["status"] == "failed"
    assert summary["failures"] == [
        {
            "reportIndex": 0,
            "runId": "phase85-pass-1",
            "missing": ["fixtureType", "runManifest.model_mode"],
            "invalid": [],
        }
    ]


def test_report_lineage_fails_for_missing_live_model_profile_lineage() -> None:
    report = _lineage_report()
    report["runManifest"].pop("text_embedding_profile")

    summary = report_lineage_check([report])

    assert summary["status"] == "failed"
    assert summary["failures"] == [
        {
            "reportIndex": 0,
            "runId": "phase85-pass-1",
            "missing": ["runManifest.text_embedding_profile"],
            "invalid": [],
        }
    ]


def test_report_lineage_fails_for_stale_live_model_profile_lineage() -> None:
    report = _lineage_report()
    report["runManifest"]["visual_embedding_profile"] = "qwen3-vl-embedding-2b-1024:v1"

    summary = report_lineage_check([report])

    assert summary["status"] == "failed"
    assert summary["failures"] == [
        {
            "reportIndex": 0,
            "runId": "phase85-pass-1",
            "missing": [],
            "invalid": ["runManifest.visual_embedding_profile"],
        }
    ]


def test_report_lineage_fails_for_missing_task12_manifest_lineage() -> None:
    report = _lineage_report()
    for key in _task12_manifest_lineage():
        report["runManifest"].pop(key)

    summary = report_lineage_check([report])

    assert summary["status"] == "failed"
    assert summary["failures"] == [
        {
            "reportIndex": 0,
            "runId": "phase85-pass-1",
            "missing": [f"runManifest.{key}" for key in _task12_manifest_lineage()],
            "invalid": [],
        }
    ]


def test_report_lineage_requires_vision_fallback_lineage() -> None:
    report = _lineage_report()
    report["runManifest"].pop("vision_fallback_provider")
    report["runManifest"].pop("qwen_vision_fallback_enabled")

    summary = report_lineage_check([report])

    assert summary["status"] == "failed"
    assert summary["failures"] == [
        {
            "reportIndex": 0,
            "runId": "phase85-pass-1",
            "missing": [
                "runManifest.vision_fallback_provider",
                "runManifest.qwen_vision_fallback_enabled",
            ],
            "invalid": [],
        }
    ]


def test_report_lineage_validates_qwen_vision_profile_when_fallback_enabled() -> None:
    report = _lineage_report()
    report["runManifest"].update(
        {
            "vision_fallback_provider": "qwen",
            "qwen_vision_fallback_enabled": True,
            "qwen_vision_profile": "qwen3-vl-unreviewed-floating-latest",
        }
    )

    summary = report_lineage_check([report])

    assert summary["status"] == "failed"
    assert summary["failures"] == [
        {
            "reportIndex": 0,
            "runId": "phase85-pass-1",
            "missing": [],
            "invalid": ["runManifest.qwen_vision_profile"],
        }
    ]


def test_run_manifest_records_qwen_vision_fallback_lineage(monkeypatch) -> None:
    from lib.config import get_settings

    monkeypatch.setenv("STRUCTURA_QWEN_VISION_FALLBACK", "true")
    monkeypatch.setenv("STRUCTURA_QWEN_VISION_PROFILE", QWEN_VISION_PROFILE)
    get_settings.cache_clear()
    try:
        manifest = build_phase85_run_manifest(run_id="phase85-qwen-vision")
    finally:
        get_settings.cache_clear()

    assert manifest["vision_fallback_provider"] == "qwen"
    assert manifest["qwen_vision_fallback_enabled"] is True
    assert manifest["qwen_vision_profile"] == QWEN_VISION_PROFILE


def test_report_lineage_fails_for_stale_task12_manifest_lineage() -> None:
    report = _lineage_report()
    report["runManifest"].update(
        {
            "semantic_prompt_version": "phase8_5-old-semantic-prompt",
            "granite_model": "ibm-granite/old-vision",
            "granite_prompt_version": "phase8_5-old-granite",
            "planner_version": "phase8_5-old-planner",
            "contract_registry_version": "phase8_5-old-contracts",
            "region_envelope_version": "phase8_5-old-envelope",
            "candidate_gate_version": "phase8_5-old-gates",
            "reconciler_version": "phase8_5-old-reconciler",
            "visual_input_plan_version": "phase8_5-old-visual-plan",
            "decoding": {"temperature": 0.4, "top_p": 0.9, "seed": 99},
        }
    )

    summary = report_lineage_check([report])

    assert summary["status"] == "failed"
    assert summary["failures"] == [
        {
            "reportIndex": 0,
            "runId": "phase85-pass-1",
            "missing": [],
            "invalid": [
                "runManifest.semantic_prompt_version",
                "runManifest.granite_model",
                "runManifest.granite_prompt_version",
                "runManifest.planner_version",
                "runManifest.contract_registry_version",
                "runManifest.region_envelope_version",
                "runManifest.candidate_gate_version",
                "runManifest.reconciler_version",
                "runManifest.visual_input_plan_version",
                "runManifest.decoding.temperature",
                "runManifest.decoding.top_p",
                "runManifest.decoding.seed",
            ],
        }
    ]


def test_report_lineage_requires_full_manifest_for_deterministic_fixture() -> None:
    report = _lineage_report(
        fixture_type="deterministic_fixture",
        model_mode="fixture",
    )
    for key in (
        "semantic_profile",
        "granite_profile",
        "text_embedding_profile",
        "visual_embedding_profile",
        *_task12_manifest_lineage(),
    ):
        report["runManifest"].pop(key)

    summary = report_lineage_check([report])

    assert summary["status"] == "failed"
    assert summary["failures"] == [
        {
            "reportIndex": 0,
            "runId": "phase85-pass-1",
            "missing": [
                "runManifest.semantic_profile",
                "runManifest.granite_profile",
                "runManifest.text_embedding_profile",
                "runManifest.visual_embedding_profile",
                *(f"runManifest.{key}" for key in _task12_manifest_lineage()),
            ],
            "invalid": [],
        }
    ]


def test_report_lineage_fails_for_missing_manifest_run_id() -> None:
    report = _lineage_report()
    report["runManifest"].pop("run_id")

    summary = report_lineage_check([report])

    assert summary["status"] == "failed"
    assert summary["failures"] == [
        {
            "reportIndex": 0,
            "runId": "phase85-pass-1",
            "missing": ["runManifest.run_id"],
            "invalid": [],
        }
    ]


def test_report_lineage_fails_for_mismatched_manifest_run_id() -> None:
    report = _lineage_report()
    report["runManifest"]["run_id"] = "phase85-other-run"

    summary = report_lineage_check([report])

    assert summary["status"] == "failed"
    assert summary["failures"] == [
        {
            "reportIndex": 0,
            "runId": "phase85-pass-1",
            "missing": [],
            "invalid": ["runId/runManifest.run_id"],
        }
    ]


def _lineage_report(
    *,
    fixture_type: str = "model_backed",
    model_mode: str = "live",
) -> dict[str, Any]:
    return {
        "runId": "phase85-pass-1",
        "fixtureType": fixture_type,
        "measuredAt": "2026-06-04T12:00:00+00:00",
        "runManifest": {
            "run_id": "phase85-pass-1",
            "pipeline_version": "phase8_5_reliability_v1",
            "model_mode": model_mode,
            "semantic_profile": QWEN_SEMANTIC_PROFILE,
            "granite_profile": GRANITE_VISION_PROFILE,
            "vision_fallback_provider": "granite",
            "qwen_vision_fallback_enabled": False,
            "text_embedding_profile": TEXT_EMBED_PROFILE,
            "visual_embedding_profile": VISUAL_EMBED_PROFILE,
            **_task12_manifest_lineage(),
        },
    }


def _task12_manifest_lineage() -> dict[str, object]:
    return {
        "docling_version": "worker-docling-isolated",
        "semantic_prompt_version": SMART_PROMPT_VERSION,
        "granite_model": get_model_profile(GRANITE_VISION_PROFILE).base_model,
        "granite_prompt_version": GRANITE_PROMPT_VERSION,
        "planner_version": PLANNER_VERSION,
        "contract_registry_version": CONTRACT_REGISTRY_VERSION,
        "region_envelope_version": REGION_ENVELOPE_VERSION,
        "candidate_gate_version": CANDIDATE_GATE_VERSION,
        "reconciler_version": RECONCILER_VERSION,
        "visual_input_plan_version": VISUAL_INPUT_PLAN_VERSION,
        "decoding": {"temperature": 0, "top_p": None, "seed": 0},
    }

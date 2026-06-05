from __future__ import annotations

from datetime import datetime
from typing import Any

from lib.model_runtime.profiles import (
    GRANITE_VISION_PROFILE,
    QWEN_SEMANTIC_PROFILE,
    TEXT_EMBED_PROFILE,
    VISUAL_EMBED_PROFILE,
    get_model_profile,
)
from lib.model_runtime.reliability_report_normalization import dict_value, get_value
from lib.model_runtime.reliability_versions import (
    CANDIDATE_GATE_VERSION,
    CONTRACT_REGISTRY_VERSION,
    GRANITE_PROMPT_VERSION,
    PIPELINE_VERSION,
    PLANNER_VERSION,
    RECONCILER_VERSION,
    REGION_ENVELOPE_VERSION,
    SMART_PROMPT_VERSION,
    VISUAL_INPUT_PLAN_VERSION,
)

VALID_FIXTURE_TYPES = frozenset({"deterministic_fixture", "model_backed"})
VALID_MODEL_MODES = frozenset({"fixture", "live", "required"})
EXPECTED_LIVE_MODEL_PROFILES = {
    "semantic_profile": QWEN_SEMANTIC_PROFILE,
    "granite_profile": GRANITE_VISION_PROFILE,
    "text_embedding_profile": TEXT_EMBED_PROFILE,
    "visual_embedding_profile": VISUAL_EMBED_PROFILE,
}
EXPECTED_TASK12_MANIFEST_VALUES = {
    "semantic_prompt_version": SMART_PROMPT_VERSION,
    "granite_model": get_model_profile(GRANITE_VISION_PROFILE).base_model,
    "granite_prompt_version": GRANITE_PROMPT_VERSION,
    "planner_version": PLANNER_VERSION,
    "contract_registry_version": CONTRACT_REGISTRY_VERSION,
    "region_envelope_version": REGION_ENVELOPE_VERSION,
    "candidate_gate_version": CANDIDATE_GATE_VERSION,
    "reconciler_version": RECONCILER_VERSION,
    "visual_input_plan_version": VISUAL_INPUT_PLAN_VERSION,
}
EXPECTED_DECODING = {
    "temperature": 0,
    "top_p": None,
    "seed": 0,
}

__all__ = ["report_lineage_check"]


def report_lineage_check(
    reports: list[dict[str, Any]],
    *,
    require_model_backed: bool = False,
) -> dict[str, Any]:
    failures: list[dict[str, Any]] = []
    for index, report in enumerate(reports):
        missing: list[str] = []
        invalid: list[str] = []
        fixture_type = get_value(report, "fixtureType", "fixture_type")
        measured_at = get_value(report, "measuredAt", "measured_at")
        run_id = get_value(report, "runId", "run_id")
        run_manifest = dict_value(get_value(report, "runManifest", "run_manifest"))
        manifest_run_id = get_value(run_manifest, "run_id", "runId")
        pipeline_version = get_value(run_manifest, "pipeline_version", "pipelineVersion")
        model_mode = get_value(run_manifest, "model_mode", "modelMode")

        _validate_report_identity(
            missing=missing,
            invalid=invalid,
            run_id=run_id,
            manifest_run_id=manifest_run_id,
            fixture_type=fixture_type,
            measured_at=measured_at,
            pipeline_version=pipeline_version,
            model_mode=model_mode,
            require_model_backed=require_model_backed,
        )
        _validate_run_manifest_lineage(
            missing=missing,
            invalid=invalid,
            run_manifest=run_manifest,
        )

        if missing or invalid:
            failures.append(
                {
                    "reportIndex": index,
                    "runId": get_value(report, "runId", "run_id"),
                    "missing": missing,
                    "invalid": invalid,
                }
            )
    return {
        "status": "passed" if reports and not failures else "failed",
        "failures": failures,
    }


def _validate_report_identity(
    *,
    missing: list[str],
    invalid: list[str],
    run_id: Any,
    manifest_run_id: Any,
    fixture_type: Any,
    measured_at: Any,
    pipeline_version: Any,
    model_mode: Any,
    require_model_backed: bool,
) -> None:
    if not isinstance(run_id, str) or not run_id.strip():
        missing.append("runId")

    if not isinstance(manifest_run_id, str) or not manifest_run_id.strip():
        missing.append("runManifest.run_id")
    elif isinstance(run_id, str) and run_id.strip() and run_id.strip() != manifest_run_id.strip():
        invalid.append("runId/runManifest.run_id")

    if not isinstance(fixture_type, str) or not fixture_type.strip():
        missing.append("fixtureType")
    elif fixture_type.strip() not in VALID_FIXTURE_TYPES:
        invalid.append("fixtureType")

    if not isinstance(measured_at, str) or not measured_at.strip():
        missing.append("measuredAt")
    elif _parse_report_timestamp(measured_at) is None:
        invalid.append("measuredAt")

    if pipeline_version in (None, ""):
        missing.append("runManifest.pipeline_version")
    elif pipeline_version != PIPELINE_VERSION:
        invalid.append("runManifest.pipeline_version")

    if not isinstance(model_mode, str) or not model_mode.strip():
        missing.append("runManifest.model_mode")
    elif model_mode.strip() not in VALID_MODEL_MODES:
        invalid.append("runManifest.model_mode")

    if isinstance(fixture_type, str) and isinstance(model_mode, str):
        expected_fixture_type = (
            "model_backed"
            if model_mode.strip() in {"live", "required"}
            else "deterministic_fixture"
        )
        if fixture_type.strip() != expected_fixture_type:
            invalid.append("fixtureType/runManifest.model_mode")

    if (
        require_model_backed
        and isinstance(fixture_type, str)
        and fixture_type.strip() in VALID_FIXTURE_TYPES
        and fixture_type.strip() != "model_backed"
    ):
        invalid.append("fixtureType/model_backed")


def _validate_run_manifest_lineage(
    *,
    missing: list[str],
    invalid: list[str],
    run_manifest: dict[str, Any],
) -> None:
    for profile_key, expected_profile in EXPECTED_LIVE_MODEL_PROFILES.items():
        actual_profile = get_value(run_manifest, profile_key, _camelize(profile_key))
        lineage_name = f"runManifest.{profile_key}"
        if not isinstance(actual_profile, str) or not actual_profile.strip():
            missing.append(lineage_name)
        elif actual_profile.strip() != expected_profile:
            invalid.append(lineage_name)

    docling_version = get_value(run_manifest, "docling_version", "doclingVersion")
    if not isinstance(docling_version, str) or not docling_version.strip():
        missing.append("runManifest.docling_version")

    for manifest_key, expected_value in EXPECTED_TASK12_MANIFEST_VALUES.items():
        actual_value = get_value(run_manifest, manifest_key, _camelize(manifest_key))
        lineage_name = f"runManifest.{manifest_key}"
        if not isinstance(actual_value, str) or not actual_value.strip():
            missing.append(lineage_name)
        elif actual_value.strip() != expected_value:
            invalid.append(lineage_name)

    decoding = dict_value(get_value(run_manifest, "decoding"))
    if not decoding:
        missing.append("runManifest.decoding")
        return
    for key, expected_decoding_value in EXPECTED_DECODING.items():
        if key not in decoding:
            missing.append(f"runManifest.decoding.{key}")
        elif decoding[key] != expected_decoding_value:
            invalid.append(f"runManifest.decoding.{key}")


def _camelize(value: str) -> str:
    head, *tail = value.split("_")
    return head + "".join(part.capitalize() for part in tail)


def _parse_report_timestamp(value: str) -> datetime | None:
    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed

from __future__ import annotations

import re
from pathlib import Path

README = Path("README.md")
SEMANTIC_PLAN = Path("STRUCTURA_PHASE_8_5_SEMANTIC_ANNOTATION_PLAN.md")
EVENT_CONTRACT_NOTES = Path("contracts/events/README.md")
PHASE85_PLAN = Path("STRUCTURA_PHASE_8_5_IMPLEMENTATION_PLAN.md")
PHASE9_PLAN = Path("STRUCTURA_PHASE_9_IMPLEMENTATION_PLAN.md")
ROOT_PLAN = Path("STRUCTURA_IMPLEMENTATION_PLAN.md")
MODEL_CORPUS_README = Path("tests/fixtures/model_corpus/README.md")


def test_readme_uses_model_corpus_runner_for_model_backed_release_gate() -> None:
    content = README.read_text(encoding="utf-8")

    assert "run_golden_corpus.py --require-model-backed" not in content
    assert "make model-corpus-release" in content
    assert "run_model_corpus.py --require-model-backed" in content


def test_readme_does_not_describe_active_high_quality_qwen_runtime() -> None:
    content = README.read_text(encoding="utf-8")

    assert "Qwen Smart/High Quality" not in content
    assert "model-qwen-semantic" in content


def test_semantic_plan_does_not_advertise_deferred_hq_rescue_controls() -> None:
    content = SEMANTIC_PLAN.read_text(encoding="utf-8")

    forbidden_runtime_controls = (
        "/semantic-annotations/high-quality",
        "/semantic-annotations/allow-8b-rescue",
        "RescuePolicy may enqueue",
        "Qwen smart/HQ gateways",
    )
    for phrase in forbidden_runtime_controls:
        assert phrase not in content


def test_event_contract_notes_describe_smart_parse_only() -> None:
    content = EVENT_CONTRACT_NOTES.read_text(encoding="utf-8")

    assert "Smart/High Quality" not in content
    assert "Smart Parse semantic planning" in content


def test_phase85_plan_uses_current_live_model_commands() -> None:
    content = PHASE85_PLAN.read_text(encoding="utf-8")

    assert "docker compose --profile models-live up -d model-qwen model-granite" not in content
    assert "Add explicit `--high-quality`, `--allow-8b-rescue`" not in content
    assert "Run optional HQ/rescue gates separately from the standard corpus gate" not in content
    assert "model-qwen-semantic model-granite model-embed" in content


def test_phase85_plan_does_not_list_legacy_qwen_rescue_runtime_intents() -> None:
    content = PHASE85_PLAN.read_text(encoding="utf-8")

    forbidden = (
        "semantic_quality_mode`: `smart` or `high_quality`",
        "allow_8b_rescue",
        "high_quality` / `rescue_permitted`",
        "semantic_annotation_high_quality",
        "blackwell-0-high-quality",
        "Replace placeholder `model-qwen`",
        "always-on `model-qwen`",
        "Rescue is user-permitted",
    )
    for phrase in forbidden:
        assert phrase not in content
    assert not re.search(r"\bmodel-qwen\b(?!-semantic)", content)


def test_phase9_plan_does_not_reintroduce_removed_model_qwen_service() -> None:
    content = PHASE9_PLAN.read_text(encoding="utf-8")

    assert "`model-qwen`" not in content
    assert not re.search(r"\bmodel-qwen\b(?!-semantic)", content)
    assert "analysis model profile" in content
    assert "model-qwen-semantic is not an analysis service" in content


def test_root_plan_model_placeholder_section_matches_current_compose() -> None:
    content = ROOT_PLAN.read_text(encoding="utf-8")

    assert not re.search(r"\bmodel-qwen\b(?!-semantic)", content)
    assert "model-granite-placeholder" in content
    assert "model-qwen-semantic" in content


def test_model_corpus_readme_requires_manifest_run_mode() -> None:
    content = MODEL_CORPUS_README.read_text(encoding="utf-8")
    normalized = re.sub(r"\s+", " ", content)

    assert (
        "private `phase8_5_model_manifest.json` must include "
        "`runManifest.model_mode` set to `live` or `required`"
    ) in normalized


def test_model_corpus_readme_requires_known_fixture_type() -> None:
    content = MODEL_CORPUS_README.read_text(encoding="utf-8")
    normalized = re.sub(r"\s+", " ", content)

    assert (
        "Every model corpus manifest must set `fixtureType` to "
        "`deterministic_fixture` or `model_backed`"
    ) in normalized


def test_model_corpus_readme_requires_manifest_profile_lineage() -> None:
    content = MODEL_CORPUS_README.read_text(encoding="utf-8")
    normalized = re.sub(r"\s+", " ", content)

    assert (
        "runManifest model profile fields must match the corresponding "
        "evidence section `profile` values"
    ) in normalized


def test_model_corpus_readme_requires_passing_evidence_artifact_statuses() -> None:
    content = MODEL_CORPUS_README.read_text(encoding="utf-8")
    normalized = re.sub(r"\s+", " ", content)

    assert (
        "Any explicit top-level `status`, report `checks`, or report "
        "`acceptanceGates` status in a model-backed evidence artifact must be "
        "passing or explicitly non-required"
    ) in normalized


def test_model_corpus_readme_rejects_not_evaluated_release_evidence() -> None:
    content = MODEL_CORPUS_README.read_text(encoding="utf-8")
    normalized = re.sub(r"\s+", " ", content)

    assert "`not_evaluated` is not valid release evidence" in normalized


def test_model_corpus_readme_rejects_artifact_failure_lists() -> None:
    content = MODEL_CORPUS_README.read_text(encoding="utf-8")
    normalized = re.sub(r"\s+", " ", content)

    assert "Any non-empty report `failures` list invalidates release evidence" in normalized


def test_model_corpus_readme_rejects_artifact_problem_lists() -> None:
    content = MODEL_CORPUS_README.read_text(encoding="utf-8")
    normalized = re.sub(r"\s+", " ", content)

    assert (
        "Non-empty report diagnostic lists such as `missingByReport`, "
        "`missingMetrics`, `failedMetrics`, or `drift` also invalidate release evidence"
    ) in normalized


def test_model_corpus_readme_rejects_artifact_problem_counts() -> None:
    content = MODEL_CORPUS_README.read_text(encoding="utf-8")
    normalized = re.sub(r"\s+", " ", content)

    assert (
        "Positive report problem counters such as `totalViolationCount`, "
        "`violationCount`, or `targetQueueDeadLetterCount` invalidate release evidence"
    ) in normalized


def test_model_corpus_readme_requires_finite_non_negative_problem_counters() -> None:
    content = MODEL_CORPUS_README.read_text(encoding="utf-8")
    normalized = re.sub(r"\s+", " ", content)

    assert "Report problem counters must be finite non-negative numbers" in normalized


def test_model_corpus_readme_requires_finite_numeric_metrics() -> None:
    content = MODEL_CORPUS_README.read_text(encoding="utf-8")
    normalized = re.sub(r"\s+", " ", content)

    assert (
        "Manifest metrics, thresholds, and evidence metric values must be finite numbers, "
        "not booleans, and must be bounded between 0 and 1" in normalized
    )


def test_gpu_validation_docs_require_report_lineage() -> None:
    content = Path("docs/model-runtime/phase8_5_gpu_validation.md").read_text(encoding="utf-8")
    normalized = re.sub(r"\s+", " ", content)

    assert (
        "Report acceptance also requires `fixtureType`, `measuredAt`, and `runManifest.model_mode`"
    ) in normalized
    assert (
        "live or required reports must include current `semantic_profile`, "
        "`granite_profile`, `text_embedding_profile`, and `visual_embedding_profile`"
    ) in normalized
    assert "top-level `runId` must match `runManifest.run_id`" in normalized


def test_gpu_validation_docs_require_full_repeatability_fingerprint_set() -> None:
    content = Path("docs/model-runtime/phase8_5_gpu_validation.md").read_text(encoding="utf-8")
    normalized = re.sub(r"\s+", " ", content)

    assert (
        "Report acceptance requires the full repeatability fingerprint set: "
        "`documentFamily`, `semanticRegions`, `plannerTasks`, "
        "`candidateFingerprints`, `canonicalOutput`, `reviewTasks`, and "
        "`rejectionDistribution`"
    ) in normalized


def test_gpu_validation_docs_keep_rejection_distribution_out_of_drift_keys() -> None:
    content = Path("docs/model-runtime/phase8_5_gpu_validation.md").read_text(encoding="utf-8")
    normalized = re.sub(r"\s+", " ", content)

    assert (
        "`rejectionDistribution` is recomputed per report as rejected "
        "noise telemetry but is not a canonical-output drift key"
    ) in normalized


def test_gpu_validation_docs_require_distinct_repeatability_run_ids() -> None:
    content = Path("docs/model-runtime/phase8_5_gpu_validation.md").read_text(encoding="utf-8")
    normalized = re.sub(r"\s+", " ", content)

    assert "Repeatability comparisons require distinct `runId` values" in normalized


def test_gpu_validation_docs_require_repeatability_document_evidence() -> None:
    content = Path("docs/model-runtime/phase8_5_gpu_validation.md").read_text(encoding="utf-8")
    normalized = re.sub(r"\s+", " ", content)

    assert (
        "Two-pass repeatability evidence must include non-empty report `documents` rows"
    ) in normalized
    assert "fingerprints are recomputable from captured corpus evidence" in normalized


def test_gpu_validation_docs_require_zero_hard_correctness_count() -> None:
    content = Path("docs/model-runtime/phase8_5_gpu_validation.md").read_text(encoding="utf-8")
    normalized = re.sub(r"\s+", " ", content)

    assert (
        "Hard correctness acceptance requires "
        "`acceptanceGates.hardCorrectnessInvariants.status = passed` and "
        "`totalViolationCount = 0`"
    ) in normalized
    assert "Hard correctness and operational SLO counters must be numeric zero" in normalized


def test_gpu_validation_docs_describe_title_derived_source_invariant() -> None:
    content = Path("docs/model-runtime/phase8_5_gpu_validation.md").read_text(encoding="utf-8")
    normalized = re.sub(r"\s+", " ", content)

    assert "Document-title-derived merchant or seller fields are violations" in normalized
    assert "evidence refs or row-level source fields" in normalized


def test_gpu_validation_docs_require_zero_target_dead_letters() -> None:
    content = Path("docs/model-runtime/phase8_5_gpu_validation.md").read_text(encoding="utf-8")
    normalized = re.sub(r"\s+", " ", content)

    assert (
        "Operational SLO acceptance requires "
        "`acceptanceGates.operationalSLOs.status = passed` and "
        "`metrics.targetQueueDeadLetterCount = 0`"
    ) in normalized


def test_gpu_validation_docs_require_operational_slo_subgates() -> None:
    content = Path("docs/model-runtime/phase8_5_gpu_validation.md").read_text(encoding="utf-8")
    normalized = re.sub(r"\s+", " ", content)

    assert (
        "Operational SLO reports must include passing subgates for "
        "`targetQueueDeadLetters`, `classifiedOperationalFailures`, "
        "`retrySuccessRate`, `runtimeFailureRates`, `runawayFanout`, and "
        "`retrySafeJobs`"
    ) in normalized


def test_gpu_validation_docs_require_clean_gold_metric_lists() -> None:
    content = Path("docs/model-runtime/phase8_5_gpu_validation.md").read_text(encoding="utf-8")
    normalized = re.sub(r"\s+", " ", content)

    assert (
        "Gold corpus acceptance requires "
        "`acceptanceGates.goldCorpusQuality.status = passed` with empty "
        "`missingMetrics` and `failedMetrics` lists"
    ) in normalized
    assert "gold metric summaries must have passing statuses and no invalid values" in normalized


def test_gpu_validation_docs_describe_manifest_builder_inputs() -> None:
    content = Path("docs/model-runtime/phase8_5_gpu_validation.md").read_text(encoding="utf-8")
    normalized = re.sub(r"\s+", " ", content)

    assert "make build-model-corpus-manifest" in normalized
    assert "MODEL_CORPUS_*_EVIDENCE" in normalized
    assert "MODEL_CORPUS_GOLD_METRICS_JSON" in normalized

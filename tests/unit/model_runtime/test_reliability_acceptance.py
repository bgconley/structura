from __future__ import annotations

import subprocess
import sys
from copy import deepcopy
from typing import Any

from lib.extraction.candidate_admission_models import CANDIDATE_GATE_VERSION
from lib.extraction.contract_registry import CONTRACT_REGISTRY_VERSION
from lib.model_runtime.profiles import (
    GRANITE_VISION_PROFILE,
    QWEN_SEMANTIC_PROFILE,
    TEXT_EMBED_PROFILE,
    VISUAL_EMBED_PROFILE,
)
from lib.model_runtime.reliability_acceptance import evaluate_phase85_report_acceptance
from lib.model_runtime.reliability_report import build_phase85_reliability_report
from lib.semantic_annotations.extraction_plan_repository import PLANNER_VERSION


def test_report_acceptance_import_does_not_load_runtime_settings() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import sys; "
                "import lib.model_runtime.reliability_acceptance; "
                "raise SystemExit('lib.config.settings' in sys.modules)"
            ),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr


def test_report_acceptance_passes_for_resident_report_without_gold_metrics() -> None:
    summary = evaluate_phase85_report_acceptance([_resident_report()])

    assert summary["status"] == "passed"
    assert summary["checks"]["reportLineage"]["status"] == "passed"
    assert summary["checks"]["requiredSummaries"]["status"] == "passed"
    assert summary["checks"]["hardCorrectnessInvariants"]["status"] == "passed"
    assert summary["checks"]["operationalSLOs"]["status"] == "passed"
    assert summary["checks"]["goldCorpusQuality"]["status"] == "not_required"
    assert summary["checks"]["repeatabilityFingerprints"]["status"] == "not_required"


def test_report_acceptance_fails_for_missing_report_lineage() -> None:
    report = _resident_report()
    report.pop("fixtureType")
    report["runManifest"].pop("model_mode")

    summary = evaluate_phase85_report_acceptance([report])

    assert summary["status"] == "failed"
    assert summary["checks"]["reportLineage"]["status"] == "failed"
    assert summary["checks"]["reportLineage"]["failures"] == [
        {
            "reportIndex": 0,
            "runId": "phase85-pass-1",
            "missing": ["fixtureType", "runManifest.model_mode"],
            "invalid": [],
        }
    ]


def test_report_acceptance_fails_for_missing_live_model_profile_lineage() -> None:
    report = _resident_report()
    report["runManifest"].pop("text_embedding_profile")

    summary = evaluate_phase85_report_acceptance([report])

    assert summary["status"] == "failed"
    assert summary["checks"]["reportLineage"]["status"] == "failed"
    assert summary["checks"]["reportLineage"]["failures"] == [
        {
            "reportIndex": 0,
            "runId": "phase85-pass-1",
            "missing": ["runManifest.text_embedding_profile"],
            "invalid": [],
        }
    ]


def test_report_acceptance_fails_for_stale_live_model_profile_lineage() -> None:
    report = _resident_report()
    report["runManifest"]["visual_embedding_profile"] = "qwen3-vl-embedding-2b-1024:v1"

    summary = evaluate_phase85_report_acceptance([report])

    assert summary["status"] == "failed"
    assert summary["checks"]["reportLineage"]["status"] == "failed"
    assert summary["checks"]["reportLineage"]["failures"] == [
        {
            "reportIndex": 0,
            "runId": "phase85-pass-1",
            "missing": [],
            "invalid": ["runManifest.visual_embedding_profile"],
        }
    ]


def test_report_acceptance_fails_for_missing_manifest_run_id() -> None:
    report = _resident_report()
    report["runManifest"].pop("run_id")

    summary = evaluate_phase85_report_acceptance([report])

    assert summary["status"] == "failed"
    assert summary["checks"]["reportLineage"]["status"] == "failed"
    assert summary["checks"]["reportLineage"]["failures"] == [
        {
            "reportIndex": 0,
            "runId": "phase85-pass-1",
            "missing": ["runManifest.run_id"],
            "invalid": [],
        }
    ]


def test_report_acceptance_fails_for_mismatched_manifest_run_id() -> None:
    report = _resident_report()
    report["runManifest"]["run_id"] = "phase85-other-run"

    summary = evaluate_phase85_report_acceptance([report])

    assert summary["status"] == "failed"
    assert summary["checks"]["reportLineage"]["status"] == "failed"
    assert summary["checks"]["reportLineage"]["failures"] == [
        {
            "reportIndex": 0,
            "runId": "phase85-pass-1",
            "missing": [],
            "invalid": ["runId/runManifest.run_id"],
        }
    ]


def test_report_acceptance_fails_for_missing_summaries_and_failed_gates() -> None:
    report = _resident_report()
    del report["plannerSummary"]
    report["acceptanceGates"]["hardCorrectnessInvariants"]["status"] = "failed"
    report["acceptanceGates"]["hardCorrectnessInvariants"]["totalViolationCount"] = 1

    summary = evaluate_phase85_report_acceptance([report])

    assert summary["status"] == "failed"
    assert summary["checks"]["requiredSummaries"]["status"] == "failed"
    assert summary["checks"]["hardCorrectnessInvariants"]["status"] == "failed"


def test_report_acceptance_fails_for_malformed_required_summaries() -> None:
    report = _resident_report()
    report["plannerSummary"] = None
    report["candidateAdmissionSummary"] = []

    summary = evaluate_phase85_report_acceptance([report])

    assert summary["status"] == "failed"
    assert summary["checks"]["requiredSummaries"]["status"] == "failed"
    assert summary["checks"]["requiredSummaries"]["invalidByReport"] == [
        {
            "reportIndex": 0,
            "runId": "phase85-pass-1",
            "invalid": ["plannerSummary", "candidateAdmissionSummary"],
        }
    ]


def test_report_acceptance_fails_for_empty_required_summaries() -> None:
    report = _resident_report()
    report["plannerSummary"] = {}
    report["envelopeSummary"] = {}

    summary = evaluate_phase85_report_acceptance([report])

    assert summary["status"] == "failed"
    assert summary["checks"]["requiredSummaries"]["status"] == "failed"
    assert summary["checks"]["requiredSummaries"]["invalidByReport"] == [
        {
            "reportIndex": 0,
            "runId": "phase85-pass-1",
            "invalid": ["plannerSummary", "envelopeSummary"],
        }
    ]


def test_report_acceptance_fails_when_target_dead_letter_count_is_nonzero() -> None:
    report = _resident_report()
    report["acceptanceGates"]["operationalSLOs"]["metrics"]["targetQueueDeadLetterCount"] = 1

    summary = evaluate_phase85_report_acceptance([report])

    assert summary["status"] == "failed"
    assert summary["checks"]["operationalSLOs"]["status"] == "failed"
    assert summary["checks"]["operationalSLOs"]["failures"] == [
        {
            "reportIndex": 0,
            "runId": "phase85-pass-1",
            "status": "passed",
            "details": report["acceptanceGates"]["operationalSLOs"],
            "invalid": ["metrics.targetQueueDeadLetterCount"],
        }
    ]


def test_report_acceptance_fails_when_target_dead_letter_count_is_boolean() -> None:
    report = _resident_report()
    report["acceptanceGates"]["operationalSLOs"]["metrics"]["targetQueueDeadLetterCount"] = False

    summary = evaluate_phase85_report_acceptance([report])

    assert summary["status"] == "failed"
    assert summary["checks"]["operationalSLOs"]["status"] == "failed"
    assert summary["checks"]["operationalSLOs"]["failures"] == [
        {
            "reportIndex": 0,
            "runId": "phase85-pass-1",
            "status": "passed",
            "details": report["acceptanceGates"]["operationalSLOs"],
            "invalid": ["metrics.targetQueueDeadLetterCount"],
        }
    ]


def test_report_acceptance_fails_when_operational_slo_subgate_fails() -> None:
    report = _resident_report()
    report["acceptanceGates"]["operationalSLOs"]["gates"]["retrySuccessRate"]["status"] = "failed"

    summary = evaluate_phase85_report_acceptance([report])

    assert summary["status"] == "failed"
    assert summary["checks"]["operationalSLOs"]["status"] == "failed"
    assert summary["checks"]["operationalSLOs"]["failures"] == [
        {
            "reportIndex": 0,
            "runId": "phase85-pass-1",
            "status": "passed",
            "details": report["acceptanceGates"]["operationalSLOs"],
            "invalid": ["gates.retrySuccessRate.status"],
        }
    ]


def test_report_acceptance_fails_when_operational_slo_subgate_has_violations() -> None:
    report = _resident_report()
    report["acceptanceGates"]["operationalSLOs"]["gates"]["retrySuccessRate"] = {
        "status": "passed",
        "violationCount": 1,
    }

    summary = evaluate_phase85_report_acceptance([report])

    assert summary["status"] == "failed"
    assert summary["checks"]["operationalSLOs"]["status"] == "failed"
    assert summary["checks"]["operationalSLOs"]["failures"] == [
        {
            "reportIndex": 0,
            "runId": "phase85-pass-1",
            "status": "passed",
            "details": report["acceptanceGates"]["operationalSLOs"],
            "invalid": ["gates.retrySuccessRate.violationCount"],
        }
    ]


def test_report_acceptance_recomputes_operational_slos_from_document_rows() -> None:
    report = _resident_report()
    report["documents"] = [
        {
            "document": {"id": "doc-dead-letter"},
            "jobs": [
                {
                    "queue_name": "extraction",
                    "job_type": "extract",
                    "status": "dead_letter",
                    "count": 1,
                    "attempt_count": 5,
                    "max_attempts": 5,
                    "error_jsons": [{}],
                }
            ],
        }
    ]

    summary = evaluate_phase85_report_acceptance([report])

    assert summary["status"] == "failed"
    assert summary["checks"]["operationalSLOs"]["status"] == "failed"
    assert summary["checks"]["operationalSLOs"]["failures"] == [
        {
            "reportIndex": 0,
            "runId": "phase85-pass-1",
            "status": "passed",
            "details": report["acceptanceGates"]["operationalSLOs"],
            "invalid": [
                "recomputed.metrics.targetQueueDeadLetterCount",
                "recomputed.gates.targetQueueDeadLetters.status",
                "recomputed.gates.targetQueueDeadLetters.violationCount",
                "recomputed.gates.classifiedOperationalFailures.status",
                "recomputed.gates.classifiedOperationalFailures.violationCount",
                "recomputed.gates.retrySuccessRate.status",
                "recomputed.gates.retrySuccessRate.violationCount",
                "recomputed.gates.runtimeFailureRates.status",
                "recomputed.gates.runtimeFailureRates.violationCount",
                "recomputed.gates.retrySafeJobs.status",
                "recomputed.gates.retrySafeJobs.violationCount",
            ],
            "recomputed": {
                "status": "failed",
                "metrics": {
                    "targetQueueDeadLetterCount": 1,
                },
                "gates": {
                    "classifiedOperationalFailures": {
                        "status": "failed",
                        "violationCount": 1,
                        "examples": [
                            {
                                "reason": "operational_failure_missing_taxonomy_code",
                                "queueName": "extraction",
                                "jobType": "extract",
                                "status": "dead_letter",
                                "count": 1,
                            }
                        ],
                    },
                    "retrySafeJobs": {
                        "status": "failed",
                        "violationCount": 1,
                        "examples": [
                            {
                                "reason": "operational_failure_missing_retryable_flag",
                                "queueName": "extraction",
                                "jobType": "extract",
                                "status": "dead_letter",
                                "count": 1,
                            }
                        ],
                    },
                    "retrySuccessRate": {
                        "status": "failed",
                        "violationCount": 1,
                        "examples": [
                            {
                                "reason": "retry_success_rate_below_threshold",
                                "observed": 0.0,
                                "required": 1.0,
                            }
                        ],
                    },
                    "runtimeFailureRates": {
                        "status": "failed",
                        "violationCount": 1,
                        "examples": [
                            {
                                "reason": "runtime_failure_rate_above_threshold",
                                "queueName": "extraction",
                                "observed": 1.0,
                                "allowed": 0.0,
                            }
                        ],
                    },
                    "targetQueueDeadLetters": {
                        "status": "failed",
                        "violationCount": 1,
                        "examples": [
                            {
                                "reason": "target_queue_dead_letter",
                                "queueName": "extraction",
                                "jobType": "extract",
                                "status": "dead_letter",
                                "count": 1,
                            }
                        ],
                    },
                },
            },
        }
    ]


def test_report_acceptance_fails_when_hard_invariant_count_is_nonzero() -> None:
    report = _resident_report()
    report["acceptanceGates"]["hardCorrectnessInvariants"]["totalViolationCount"] = 1

    summary = evaluate_phase85_report_acceptance([report])

    assert summary["status"] == "failed"
    assert summary["checks"]["hardCorrectnessInvariants"]["status"] == "failed"
    assert summary["checks"]["hardCorrectnessInvariants"]["failures"] == [
        {
            "reportIndex": 0,
            "runId": "phase85-pass-1",
            "status": "passed",
            "details": report["acceptanceGates"]["hardCorrectnessInvariants"],
            "invalid": ["totalViolationCount"],
        }
    ]


def test_report_acceptance_fails_when_hard_invariant_detail_has_violations() -> None:
    report = _resident_report()
    report["acceptanceGates"]["hardCorrectnessInvariants"]["invariants"] = {
        "promptSchemaArtifactsAdmitted": {
            "status": "failed",
            "violationCount": 1,
            "examples": [{"reason": "admitted_prompt_or_schema_artifact"}],
        }
    }

    summary = evaluate_phase85_report_acceptance([report])

    assert summary["status"] == "failed"
    assert summary["checks"]["hardCorrectnessInvariants"]["status"] == "failed"
    assert summary["checks"]["hardCorrectnessInvariants"]["failures"] == [
        {
            "reportIndex": 0,
            "runId": "phase85-pass-1",
            "status": "passed",
            "details": report["acceptanceGates"]["hardCorrectnessInvariants"],
            "invalid": [
                "invariants.promptSchemaArtifactsAdmitted.status",
                "invariants.promptSchemaArtifactsAdmitted.violationCount",
            ],
        }
    ]


def test_report_acceptance_fails_when_hard_invariant_count_is_boolean() -> None:
    report = _resident_report()
    report["acceptanceGates"]["hardCorrectnessInvariants"]["totalViolationCount"] = False

    summary = evaluate_phase85_report_acceptance([report])

    assert summary["status"] == "failed"
    assert summary["checks"]["hardCorrectnessInvariants"]["status"] == "failed"
    assert summary["checks"]["hardCorrectnessInvariants"]["failures"] == [
        {
            "reportIndex": 0,
            "runId": "phase85-pass-1",
            "status": "passed",
            "details": report["acceptanceGates"]["hardCorrectnessInvariants"],
            "invalid": ["totalViolationCount"],
        }
    ]


def test_report_acceptance_recomputes_hard_invariants_from_document_rows() -> None:
    report = _resident_report()
    report["documents"] = [
        {
            "document": {"id": "doc-unsafe", "document_family": "invoice"},
            "admissionEvents": [
                {
                    "decision": "admitted_review_required",
                    "candidate_kind": "field",
                    "candidate_fingerprint": "field-unsafe",
                    **_admission_event_telemetry(),
                    "evidence_concrete": False,
                    "payload_json": {
                        "candidate": {
                            "field_path": "invoice.total_amount",
                            "value": "42.00",
                            "evidence": [],
                        }
                    },
                }
            ],
        }
    ]

    summary = evaluate_phase85_report_acceptance([report])

    assert summary["status"] == "failed"
    assert summary["checks"]["hardCorrectnessInvariants"]["status"] == "failed"
    assert summary["checks"]["hardCorrectnessInvariants"]["failures"] == [
        {
            "reportIndex": 0,
            "runId": "phase85-pass-1",
            "status": "passed",
            "details": report["acceptanceGates"]["hardCorrectnessInvariants"],
            "invalid": ["recomputed.totalViolationCount"],
            "recomputed": {
                "status": "failed",
                "totalViolationCount": 1,
                "invariants": {
                    "admittedCandidatesWithoutConcreteEvidence": {
                        "description": "Admitted candidates must have concrete evidence locators.",
                        "violationCount": 1,
                        "examples": [
                            {
                                "reason": "admitted_without_concrete_evidence",
                                "documentId": None,
                                "entityId": "field-unsafe",
                            }
                        ],
                    }
                },
            },
        }
    ]


def test_report_acceptance_compares_repeatability_fingerprints_across_two_passes() -> None:
    first = _resident_report()
    second = deepcopy(first)
    second["runId"] = "phase85-pass-2"
    second["repeatabilityFingerprints"]["candidateFingerprints"] = "changed-candidates"

    summary = evaluate_phase85_report_acceptance([first, second])

    assert summary["status"] == "failed"
    assert summary["checks"]["repeatabilityFingerprints"]["status"] == "failed"
    assert summary["checks"]["repeatabilityFingerprints"]["drift"] == ["candidateFingerprints"]


def test_report_acceptance_rejects_duplicate_run_ids_for_repeatability() -> None:
    first = _resident_report()
    second = deepcopy(first)

    summary = evaluate_phase85_report_acceptance([first, second])

    assert summary["status"] == "failed"
    assert summary["checks"]["repeatabilityFingerprints"]["status"] == "failed"
    assert summary["checks"]["repeatabilityFingerprints"]["duplicateRunIds"] == ["phase85-pass-1"]


def test_report_acceptance_requires_run_ids_for_repeatability() -> None:
    first = _resident_report()
    second = deepcopy(first)
    second.pop("runId")

    summary = evaluate_phase85_report_acceptance([first, second])

    assert summary["status"] == "failed"
    assert summary["checks"]["repeatabilityFingerprints"]["status"] == "failed"
    assert summary["checks"]["repeatabilityFingerprints"]["missingRunIds"] == [{"reportIndex": 1}]


def test_report_acceptance_requires_full_repeatability_fingerprint_set() -> None:
    report = _resident_report()
    del report["repeatabilityFingerprints"]["canonicalOutput"]

    summary = evaluate_phase85_report_acceptance([report])

    assert summary["status"] == "failed"
    assert summary["checks"]["repeatabilityFingerprints"]["status"] == "failed"
    assert summary["checks"]["repeatabilityFingerprints"]["missingByReport"] == [
        {
            "reportIndex": 0,
            "runId": "phase85-pass-1",
            "missing": ["canonicalOutput"],
        }
    ]


def test_report_acceptance_recomputes_repeatability_fingerprints_from_document_rows() -> None:
    report = build_phase85_reliability_report(
        run_id="phase85-repeatability",
        title_prefix="Phase 8.5 Repeatability",
        documents=[
            {
                "document": {
                    "id": "doc-1",
                    "document_family": "invoice",
                    "review_status": "needs_review",
                },
                "admissionEvents": [
                    {
                        "decision": "admitted_review_required",
                        "candidate_fingerprint": "actual-candidate-fingerprint",
                        **_admission_event_telemetry(),
                    }
                ],
            }
        ],
    )
    report["repeatabilityFingerprints"]["candidateFingerprints"] = "stale-candidates"

    summary = evaluate_phase85_report_acceptance([report])

    assert summary["status"] == "failed"
    repeatability = summary["checks"]["repeatabilityFingerprints"]
    assert repeatability["status"] == "failed"
    assert repeatability["mismatchedByReport"] == [
        {
            "reportIndex": 0,
            "runId": "phase85-repeatability",
            "mismatched": ["candidateFingerprints"],
        }
    ]


def test_report_acceptance_compares_all_repeatability_fingerprints() -> None:
    first = _resident_report()
    second = deepcopy(first)
    second["runId"] = "phase85-pass-2"
    second["repeatabilityFingerprints"]["canonicalOutput"] = "changed-canonical"

    summary = evaluate_phase85_report_acceptance([first, second])

    assert summary["status"] == "failed"
    assert summary["checks"]["repeatabilityFingerprints"]["status"] == "failed"
    assert summary["checks"]["repeatabilityFingerprints"]["drift"] == ["canonicalOutput"]


def _resident_report() -> dict[str, Any]:
    return {
        "runId": "phase85-pass-1",
        "fixtureType": "model_backed",
        "measuredAt": "2026-06-04T12:00:00+00:00",
        "runManifest": {
            "run_id": "phase85-pass-1",
            "pipeline_version": "phase8_5_reliability_v1",
            "model_mode": "live",
            "semantic_profile": QWEN_SEMANTIC_PROFILE,
            "granite_profile": GRANITE_VISION_PROFILE,
            "text_embedding_profile": TEXT_EMBED_PROFILE,
            "visual_embedding_profile": VISUAL_EMBED_PROFILE,
        },
        "plannerSummary": {"selectedTaskCount": 2},
        "candidateAdmissionSummary": {"admittedCount": 2, "rejectedCount": 0},
        "envelopeSummary": {"concreteEvidenceCoverage": 1.0},
        "visualInputPlanSummary": {"routeDistribution": {"full_page": 1}},
        "retrySummary": {"outcomes": {"succeeded": 1}},
        "extractionPressure": {"selectedTaskCount": 2},
        "safeOutcomeSummary": {"unsafeFailureCount": 0},
        "qualitySummary": {"documents": 1},
        "repeatabilityFingerprints": {
            "documentFamily": "doc-family",
            "semanticRegions": "semantic",
            "plannerTasks": "planner",
            "candidateFingerprints": "candidates",
            "canonicalOutput": "canonical",
            "reviewTasks": "review",
            "rejectionDistribution": "rejections",
        },
        "acceptanceGates": {
            "hardCorrectnessInvariants": {
                "status": "passed",
                "totalViolationCount": 0,
            },
            "goldCorpusQuality": {
                "status": "not_evaluated",
                "missingMetrics": [],
            },
            "operationalSLOs": {
                "status": "passed",
                "metrics": {
                    "targetQueueDeadLetterCount": 0,
                },
                "gates": _passed_operational_slo_gates(),
            },
        },
    }


def _passed_operational_slo_gates() -> dict[str, dict[str, object]]:
    return {
        "targetQueueDeadLetters": {"status": "passed", "violationCount": 0},
        "classifiedOperationalFailures": {"status": "passed", "violationCount": 0},
        "retrySuccessRate": {"status": "passed", "violationCount": 0},
        "runtimeFailureRates": {"status": "passed", "violationCount": 0},
        "runawayFanout": {"status": "passed", "violationCount": 0},
        "retrySafeJobs": {"status": "passed", "violationCount": 0},
    }


def _admission_event_telemetry() -> dict[str, str]:
    return {
        "run_id": "phase85-pass-1",
        "planner_version": PLANNER_VERSION,
        "candidate_gate_version": CANDIDATE_GATE_VERSION,
        "contract_registry_version": CONTRACT_REGISTRY_VERSION,
    }

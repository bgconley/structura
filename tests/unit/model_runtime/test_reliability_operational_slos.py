from __future__ import annotations

from lib.model_runtime.reliability_operational_slos import evaluate_operational_slos
from lib.model_runtime.reliability_report import build_phase85_reliability_report


def test_operational_slos_pass_for_clean_smoke_run() -> None:
    summary = evaluate_operational_slos([_clean_document_report()])

    assert summary["status"] == "passed"
    assert summary["metrics"]["targetQueueDeadLetterCount"] == 0
    assert summary["metrics"]["retrySuccessRate"] == 1.0
    assert summary["gates"]["targetQueueDeadLetters"]["violationCount"] == 0
    assert summary["gates"]["runtimeFailureRates"]["violationCount"] == 0
    assert summary["gates"]["runawayFanout"]["violationCount"] == 0


def test_operational_slos_fail_for_target_dead_letters_and_unclassified_failures() -> None:
    summary = evaluate_operational_slos([_dead_letter_document_report()])

    assert summary["status"] == "failed"
    assert summary["metrics"]["targetQueueDeadLetterCount"] == 1
    assert summary["gates"]["targetQueueDeadLetters"]["violationCount"] == 1
    assert summary["gates"]["classifiedOperationalFailures"]["violationCount"] == 1
    assert summary["gates"]["runtimeFailureRates"]["violationCount"] == 1


def test_operational_slos_fail_for_retry_and_fanout_regressions() -> None:
    summary = evaluate_operational_slos([_retry_and_fanout_document_report()])

    assert summary["status"] == "failed"
    assert summary["metrics"]["retryAttemptCount"] == 2
    assert summary["metrics"]["retrySuccessRate"] == 0.5
    assert summary["gates"]["retrySuccessRate"]["violationCount"] == 1
    assert summary["gates"]["runawayFanout"]["violationCount"] == 2
    assert summary["gates"]["retrySafeJobs"]["violationCount"] == 1


def test_operational_slos_normalize_target_job_queue_and_status() -> None:
    summary = evaluate_operational_slos([_cased_dead_letter_document_report()])

    assert summary["status"] == "failed"
    assert summary["metrics"]["targetQueueDeadLetterCount"] == 1
    assert summary["gates"]["targetQueueDeadLetters"]["violationCount"] == 1
    assert summary["gates"]["classifiedOperationalFailures"]["violationCount"] == 1
    assert summary["gates"]["runtimeFailureRates"]["violationCount"] == 1
    assert summary["gates"]["targetQueueDeadLetters"]["examples"] == [
        {
            "reason": "target_queue_dead_letter",
            "queueName": "extraction",
            "jobType": "extract",
            "status": "dead_letter",
            "count": 1,
        }
    ]


def test_operational_slos_normalize_selected_planner_task_statuses() -> None:
    summary = evaluate_operational_slos([_cased_fanout_document_report()])

    assert summary["status"] == "failed"
    assert summary["gates"]["runawayFanout"]["violationCount"] == 1
    assert summary["gates"]["runawayFanout"]["examples"] == [
        {
            "reason": "selected_tasks_exceed_page_policy",
            "documentId": "doc-cased-fanout",
            "pageNumber": "1",
            "selectedTaskCount": 4,
            "maxTasksPerPagePolicy": 3,
        }
    ]


def test_reliability_report_includes_operational_slo_summary() -> None:
    report = build_phase85_reliability_report(
        run_id="phase85-20260604-smoke-001",
        title_prefix="Phase 8.5 Smoke",
        documents=[_dead_letter_document_report()],
    )

    operational = report["acceptanceGates"]["operationalSLOs"]
    assert operational["status"] == "failed"
    assert operational["metrics"]["targetQueueDeadLetterCount"] == 1


def _clean_document_report() -> dict[str, object]:
    return {
        "document": {"id": "doc-clean"},
        "jobs": [
            _job(queue="docling", status="succeeded"),
            _job(queue="semantic-annotations", status="succeeded"),
            _job(queue="extraction", status="succeeded"),
            _job(queue="visual-embeddings", status="succeeded"),
        ],
        "planner": [
            {
                "selected_task_count": 3,
                "report_json": {
                    "maxTasksPerDocumentPolicy": 6,
                    "maxTasksPerPagePolicy": 3,
                },
            }
        ],
        "plannerTasks": [
            {"status": "selected", "page_number": 1},
            {"status": "selected", "page_number": 1},
            {"status": "selected", "page_number": 2},
        ],
    }


def _cased_dead_letter_document_report() -> dict[str, object]:
    return {
        "document": {"id": "doc-cased-dead-letter"},
        "jobs": [
            {
                "queue_name": " Extraction ",
                "job_type": " extract ",
                "status": " Dead_Letter ",
                "count": 1,
                "attempt_count": 5,
                "max_attempts": 5,
                "error_jsons": [{}],
            }
        ],
    }


def _cased_fanout_document_report() -> dict[str, object]:
    return {
        "document": {"id": "doc-cased-fanout"},
        "planner": [
            {
                "report_json": {
                    "maxTasksPerDocumentPolicy": 6,
                    "maxTasksPerPagePolicy": 3,
                },
            }
        ],
        "plannerTasks": [
            {"status": " Selected ", "page_number": 1},
            {"status": " Selected ", "page_number": 1},
            {"status": " Selected ", "page_number": 1},
            {"status": " Selected ", "page_number": 1},
        ],
    }


def _dead_letter_document_report() -> dict[str, object]:
    return {
        "document": {"id": "doc-dead-letter"},
        "jobs": [
            _job(
                queue="extraction",
                status="dead_letter",
                count=1,
                attempt_count=5,
                max_attempts=5,
                error_jsons=[{}],
            ),
            _job(queue="semantic-annotations", status="succeeded", count=2),
        ],
        "planner": [
            {
                "selected_task_count": 2,
                "report_json": {
                    "maxTasksPerDocumentPolicy": 6,
                    "maxTasksPerPagePolicy": 3,
                },
            }
        ],
        "plannerTasks": [{"status": "selected", "page_number": 1}],
    }


def _retry_and_fanout_document_report() -> dict[str, object]:
    return {
        "document": {"id": "doc-retry-fanout"},
        "jobs": [
            _job(
                queue="extraction",
                status="succeeded",
                count=1,
                attempt_count=2,
                max_attempts=5,
                error_jsons=[{"error_class": "transient_timeout", "retryable": True}],
            ),
            _job(
                queue="docling",
                status="failed",
                count=1,
                attempt_count=6,
                max_attempts=5,
                error_jsons=[{"error_class": "docling_runtime_error", "retryable": True}],
            ),
        ],
        "planner": [
            {
                "selected_task_count": 7,
                "report_json": {
                    "maxTasksPerDocumentPolicy": 6,
                    "maxTasksPerPagePolicy": 3,
                },
            }
        ],
        "plannerTasks": [
            {"status": "selected", "page_number": 1},
            {"status": "selected", "page_number": 1},
            {"status": "selected", "page_number": 1},
            {"status": "selected", "page_number": 1},
            {"status": "selected", "page_number": 2},
            {"status": "selected", "page_number": 2},
            {"status": "selected", "page_number": 2},
        ],
    }


def _job(
    *,
    queue: str,
    status: str,
    count: int = 1,
    attempt_count: int = 1,
    max_attempts: int = 5,
    error_jsons: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    return {
        "queue_name": queue,
        "job_type": "extract" if queue == "extraction" else queue,
        "status": status,
        "count": count,
        "attempt_count": attempt_count,
        "max_attempts": max_attempts,
        "error_jsons": error_jsons or [],
    }

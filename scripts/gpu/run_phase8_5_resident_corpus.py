#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import UUID

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from lib.db.connection import db_connection  # noqa: E402
from lib.documents.ingestion import DocumentIngestionRequest, ingest_document_path  # noqa: E402
from lib.model_runtime.reliability_acceptance import (  # noqa: E402
    evaluate_phase85_report_acceptance,
)
from lib.model_runtime.reliability_job_scope import TARGET_FAILURE_QUEUES  # noqa: E402
from lib.model_runtime.reliability_report import build_phase85_reliability_report  # noqa: E402
from scripts.gpu.phase8_5_resident_manifest import (  # noqa: E402
    ResidentCorpusEntry,
)
from scripts.gpu.phase8_5_resident_manifest import (  # noqa: E402
    gold_metadata_by_document_id as _gold_metadata_by_document_id,
)
from scripts.gpu.phase8_5_resident_manifest import (  # noqa: E402
    resolve_corpus_entries as _resolve_corpus_entries,
)

ACTIVE_JOB_STATUSES = ("queued", "leased", "running", "failed")
PREFLIGHT_TARGET_QUEUES = tuple(sorted(TARGET_FAILURE_QUEUES))
SKIPPED_TEXT_EMBEDDING_STATUSES = ("failed", "leased", "queued", "running")


def main() -> int:
    args = _parse_args()
    run_id = args.run_id or datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    title_prefix = args.title_prefix or f"Phase 8.5 Production Corpus {run_id}"
    report_path = args.report or Path(
        f"/srv/structura/objects/exports/phase85-runs/{run_id}-production-corpus-report.json"
    )

    entries = _resolve_corpus_entries(args)
    if not args.allow_active_jobs:
        _assert_clean_queue()

    started = time.monotonic()
    documents = _ingest_documents(
        entries,
        run_id=run_id,
        title_prefix=title_prefix,
        requested_by=args.requested_by,
    )
    document_ids = [UUID(str(document["document_id"])) for document in documents]
    _emit("all_ingested", run_id=run_id, document_count=len(document_ids), documents=documents)

    last_progress_at = 0.0
    timed_out = False
    while True:
        cancelled = (
            _cancel_text_embedding_jobs(document_ids, run_id=run_id, requested_by=args.requested_by)
            if args.skip_text_embeddings
            else 0
        )
        done, active, target_dead_letters, progress = _terminal_state(document_ids)
        now = time.monotonic()
        if (
            cancelled
            or target_dead_letters
            or done
            or now - last_progress_at >= args.progress_seconds
        ):
            _emit(
                "progress",
                run_id=run_id,
                elapsed_seconds=int(now - started),
                cancelled_text_embedding_jobs=cancelled,
                active=active,
                target_dead_letters=target_dead_letters,
                job_counts=_compact_job_counts(document_ids),
                documents=progress,
            )
            last_progress_at = now
        if done:
            break
        if args.fail_on_target_dead_letter and target_dead_letters:
            break
        if now - started > args.timeout_seconds:
            timed_out = True
            _emit(
                "timeout",
                run_id=run_id,
                elapsed_seconds=int(now - started),
                active=active,
                target_dead_letters=target_dead_letters,
                documents=progress,
            )
            break
        time.sleep(args.poll_seconds)

    report = _fetch_report(
        document_ids,
        run_id=run_id,
        title_prefix=title_prefix,
        gold_metadata_by_document_id=_gold_metadata_by_document_id(documents),
    )
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_json = json.dumps(_json_safe(report), indent=2, sort_keys=True)
    report_path.write_text(report_json, encoding="utf-8")
    _emit(
        "report_written",
        run_id=run_id,
        report=str(report_path),
        elapsed_seconds=int(time.monotonic() - started),
    )
    print(json.dumps(_json_safe(report), indent=2, sort_keys=True), flush=True)

    if timed_out:
        return 2
    if args.fail_on_target_dead_letter and any(
        row["queue_name"] in TARGET_FAILURE_QUEUES for row in _dead_letter_counts(document_ids)
    ):
        return 1
    acceptance_exit = _acceptance_exit_code(report)
    if acceptance_exit:
        return acceptance_exit
    return 0


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run PDFs through the resident Phase 8.5 live pipeline. "
            "This script is intended to run inside the api container."
        )
    )
    parser.add_argument("--pdf", action="append", type=Path)
    parser.add_argument(
        "--manifest",
        type=Path,
        help=(
            'JSON manifest with shape {"documents": [{"path": "..."}]}; '
            "private release manifests may add corpus-level or per-document "
            "goldMetrics and goldThresholds."
        ),
    )
    parser.add_argument("--run-id")
    parser.add_argument("--title-prefix")
    parser.add_argument("--report", type=Path)
    parser.add_argument("--requested-by", default="phase8_5_resident_corpus")
    parser.add_argument("--timeout-seconds", type=int, default=14_400)
    parser.add_argument("--poll-seconds", type=float, default=5.0)
    parser.add_argument("--progress-seconds", type=float, default=20.0)
    parser.add_argument("--allow-active-jobs", action="store_true")
    parser.add_argument("--skip-text-embeddings", action="store_true", default=True)
    parser.add_argument(
        "--include-text-embeddings",
        dest="skip_text_embeddings",
        action="store_false",
    )
    parser.add_argument("--fail-on-target-dead-letter", action="store_true", default=True)
    parser.add_argument(
        "--allow-target-dead-letter",
        dest="fail_on_target_dead_letter",
        action="store_false",
    )
    return parser.parse_args()


def _assert_clean_queue() -> None:
    rows = _active_job_counts()
    if rows:
        _emit("preflight_active_jobs_found", rows=rows)
        raise SystemExit(2)


def _acceptance_exit_code(report: dict[str, Any]) -> int:
    acceptance = evaluate_phase85_report_acceptance([report])
    if acceptance["status"] != "passed":
        _emit("acceptance_gates_failed", acceptance=acceptance)
        return 1
    return 0


def _resolve_owner() -> tuple[UUID, UUID]:
    with db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT hm.household_id, hm.user_id
                FROM household_memberships hm
                JOIN users u ON u.id = hm.user_id
                WHERE hm.role IN ('owner', 'admin')
                  AND NOT u.is_disabled
                ORDER BY hm.role = 'owner' DESC, hm.created_at ASC
                LIMIT 1
                """
            )
            row = cur.fetchone()
    if not row:
        raise SystemExit("No owner/admin household membership found.")
    return UUID(str(row["household_id"])), UUID(str(row["user_id"]))


def _ingest_documents(
    entries: list[ResidentCorpusEntry],
    *,
    run_id: str,
    title_prefix: str,
    requested_by: str,
) -> list[dict[str, Any]]:
    household_id, user_id = _resolve_owner()
    documents: list[dict[str, Any]] = []
    for entry in entries:
        pdf = entry.path
        result = ingest_document_path(
            pdf,
            request=DocumentIngestionRequest(
                household_id=household_id,
                owner_user_id=user_id,
                source="bulk_import",
                filename=pdf.name,
                declared_mime_type="application/pdf",
                supplied_title=f"{title_prefix}: {pdf.stem}",
                hints={
                    "phase": "phase8_5_production_corpus",
                    "runId": run_id,
                    "sourcePath": str(pdf),
                    "textEmbedder": "skipped_by_request",
                },
                requested_by=requested_by,
            ),
        )
        document = {
            "document_id": result.document_id,
            "filename": pdf.name,
            "sha256": result.sha256,
        }
        if entry.gold_metrics is not None and entry.gold_thresholds is not None:
            document["goldMetrics"] = dict(entry.gold_metrics)
            document["goldThresholds"] = dict(entry.gold_thresholds)
        if entry.holdout_label is not None:
            document["holdoutLabel"] = entry.holdout_label
        if entry.overfitting_guards is not None:
            document["overfittingGuards"] = dict(entry.overfitting_guards)
        documents.append(document)
        _emit("ingested", run_id=run_id, **document)
    return documents


def _cancel_text_embedding_jobs(
    document_ids: list[UUID],
    *,
    run_id: str,
    requested_by: str,
) -> int:
    if not document_ids:
        return 0
    with db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE pipeline_jobs
                SET status = 'cancelled',
                    finished_at = now(),
                    lease_expires_at = NULL,
                    scheduled_at = now(),
                    error_json = jsonb_build_object(
                      'error_class', 'JobCancelled',
                      'message', 'Text embedding skipped for private Phase 8.5 corpus run.',
                      'last_error', 'Text embedding skipped for private Phase 8.5 corpus run.',
                      'retryable', false,
                      'requested_by', %s::text,
                      'run_id', %s::text,
                      'cancelled_by', %s::text,
                      'cancelled_at', now()
                    ),
                    updated_at = now()
                WHERE document_id = ANY(%s::uuid[])
                  AND queue_name = 'embeddings'
                  AND job_type = 'embed'
                  AND status::text = ANY(%s)
                RETURNING id
                """,
                (
                    requested_by,
                    run_id,
                    requested_by,
                    [str(document_id) for document_id in document_ids],
                    list(SKIPPED_TEXT_EMBEDDING_STATUSES),
                ),
            )
            count = len(cur.fetchall())
        conn.commit()
    return count


def _terminal_state(
    document_ids: list[UUID],
) -> tuple[bool, list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    counts = _job_counts(document_ids)
    active = [
        row
        for row in counts
        if row["status"] in ACTIVE_JOB_STATUSES and row["queue_name"] in TARGET_FAILURE_QUEUES
    ]
    target_dead_letters = [
        row
        for row in counts
        if row["status"] == "dead_letter" and row["queue_name"] in TARGET_FAILURE_QUEUES
    ]
    progress = _document_progress(document_ids)
    complete_shape = all(
        int(row["pages"] or 0) > 0 and int(row["semantic_succeeded"] or 0) > 0 for row in progress
    )
    return not active and complete_shape, active, target_dead_letters, progress


def _active_job_counts() -> list[dict[str, Any]]:
    with db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                  queue_name,
                  job_type::text AS job_type,
                  status::text AS status,
                  count(*) AS count
                FROM pipeline_jobs
                WHERE status::text = ANY(%s)
                  AND queue_name = ANY(%s)
                GROUP BY queue_name, job_type, status::text
                ORDER BY queue_name, job_type, status::text
                """,
                (list(ACTIVE_JOB_STATUSES), list(PREFLIGHT_TARGET_QUEUES)),
            )
            return [dict(row) for row in cur.fetchall()]


def _job_counts(document_ids: list[UUID]) -> list[dict[str, Any]]:
    with db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                  queue_name,
                  job_type::text AS job_type,
                  status::text AS status,
                  count(*) AS count
                FROM pipeline_jobs
                WHERE document_id = ANY(%s::uuid[])
                GROUP BY queue_name, job_type, status::text
                ORDER BY queue_name, job_type, status::text
                """,
                ([str(document_id) for document_id in document_ids],),
            )
            return [dict(row) for row in cur.fetchall()]


def _dead_letter_counts(document_ids: list[UUID]) -> list[dict[str, Any]]:
    return [row for row in _job_counts(document_ids) if row["status"] == "dead_letter"]


def _compact_job_counts(document_ids: list[UUID]) -> list[dict[str, Any]]:
    return [
        {
            "queue": row["queue_name"],
            "type": row["job_type"],
            "status": row["status"],
            "count": row["count"],
        }
        for row in _job_counts(document_ids)
    ]


def _document_progress(document_ids: list[UUID]) -> list[dict[str, Any]]:
    with db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                  d.id,
                  d.original_filename,
                  d.document_family::text AS document_family,
                  d.review_status::text AS review_status,
                  count(DISTINCT p.id) AS pages,
                  count(DISTINCT a.id) FILTER (WHERE a.status = 'succeeded') AS semantic_succeeded,
                  count(DISTINCT r.id) AS semantic_regions,
                  count(DISTINCT de.id)
                    FILTER (WHERE de.status = 'completed') AS extractions_completed,
                  count(DISTINCT li.id) AS line_items,
                  count(DISTINCT fc.id) AS fields,
                  count(DISTINCT eo.id) AS observations,
                  count(DISTINCT emb.id) FILTER (
                    WHERE emb.modality::text = 'visual' AND emb.is_active
                  ) AS visual_embeddings
                FROM documents d
                LEFT JOIN document_pages p ON p.document_id = d.id
                LEFT JOIN document_semantic_annotations a ON a.document_id = d.id AND a.is_current
                LEFT JOIN semantic_region_annotations r ON r.annotation_id = a.id
                LEFT JOIN document_extractions de ON de.document_id = d.id
                LEFT JOIN line_item_candidates li ON li.document_id = d.id
                LEFT JOIN field_candidates fc ON fc.document_id = d.id
                LEFT JOIN extraction_observations eo ON eo.document_id = d.id
                LEFT JOIN embeddings emb ON emb.document_id = d.id
                WHERE d.id = ANY(%s::uuid[])
                GROUP BY d.id
                ORDER BY d.created_at
                """,
                ([str(document_id) for document_id in document_ids],),
            )
            return [dict(row) for row in cur.fetchall()]


def _fetch_report(
    document_ids: list[UUID],
    *,
    run_id: str,
    title_prefix: str,
    gold_metadata_by_document_id: dict[UUID, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    documents = []
    gold_metadata = gold_metadata_by_document_id or {}
    with db_connection() as conn:
        with conn.cursor() as cur:
            for document_id in document_ids:
                cur.execute(
                    """
                    SELECT
                      id,
                      title,
                      original_filename,
                      document_family::text AS document_family,
                      document_subtype,
                      family_confidence,
                      review_status::text AS review_status,
                      page_count,
                      document_date,
                      counterparty_display
                    FROM documents
                    WHERE id = %s
                    """,
                    (document_id,),
                )
                document_row = cur.fetchone()
                document = dict(document_row) if document_row is not None else {}
                report_document = {
                    "document": document,
                    "jobs": _rows_for_document(cur, document_id, _JOBS_SQL),
                    "semantic": _rows_for_document(cur, document_id, _SEMANTIC_SQL),
                    "semanticRegions": _rows_for_document(
                        cur,
                        document_id,
                        _SEMANTIC_REGIONS_SQL,
                    ),
                    "planner": _rows_for_document(cur, document_id, _PLANNER_SQL),
                    "plannerTasks": _rows_for_document(
                        cur,
                        document_id,
                        _PLANNER_TASKS_SQL,
                    ),
                    "admissionEvents": _rows_for_document(
                        cur,
                        document_id,
                        _ADMISSION_EVENTS_SQL,
                    ),
                    "extractions": _rows_for_document(cur, document_id, _EXTRACTIONS_SQL),
                    "fields": _fields_for_document(cur, document_id),
                    "lineItems": _rows_for_document(cur, document_id, _LINE_ITEMS_SQL),
                    "observations": _rows_for_document(cur, document_id, _OBSERVATIONS_SQL),
                    "embeddings": _rows_for_document(cur, document_id, _EMBEDDINGS_SQL),
                    "reviewTasks": _rows_for_document(cur, document_id, _REVIEW_TASKS_SQL),
                }
                report_document.update(gold_metadata.get(document_id, {}))
                documents.append(report_document)
    return build_phase85_reliability_report(
        run_id=run_id,
        title_prefix=title_prefix,
        documents=documents,
    )


_JOBS_SQL = """
SELECT queue_name,
       job_type::text AS job_type,
       status::text AS status,
       count(*) AS count,
       sum(attempt_count) AS attempt_count,
       max(max_attempts) AS max_attempts,
       jsonb_agg(error_json) FILTER (WHERE error_json <> '{}'::jsonb) AS error_jsons
FROM pipeline_jobs
WHERE document_id = %s
GROUP BY queue_name, job_type, status
ORDER BY queue_name, job_type, status
"""

_SEMANTIC_SQL = """
SELECT quality_mode, profile_name, source_engine::text AS source_engine, model_name,
       prompt_version, status, review_required,
       manifest_json ->> 'document_type' AS document_type,
       manifest_json -> 'document_type_scores' AS document_type_scores,
       manifest_json -> 'deterministic_baseline' AS deterministic_baseline,
       (
         SELECT count(*)
         FROM semantic_region_annotations r
         WHERE r.annotation_id = a.id
       ) AS region_count
FROM document_semantic_annotations a
WHERE document_id = %s AND is_current
ORDER BY created_at DESC
"""

_SEMANTIC_REGIONS_SQL = """
SELECT COALESCE(p.page_number, dp.page_number) AS page_number,
       r.id AS semantic_region_id,
       r.annotation_id AS semantic_annotation_id,
       r.semantic_type, r.priority, r.granite_task, r.target_schema,
       r.grounding_kind, r.review_required, r.reason, r.confidence,
       jsonb_build_object(
         'kind', r.grounding_kind,
         'page_number', COALESCE(p.page_number, dp.page_number),
         'page_id', r.page_id,
         'element_id', r.element_id,
         'table_id', r.table_id,
         'docling_table_id', r.table_id,
         'bbox', r.metadata_json -> 'visual_bbox_hint'
       ) AS grounding,
       r.metadata_json ->> 'importance' AS importance,
       r.metadata_json ->> 'must_extract_reason' AS must_extract_reason
FROM semantic_region_annotations r
JOIN document_semantic_annotations a ON a.id = r.annotation_id
LEFT JOIN page_semantic_annotations p ON p.id = r.page_annotation_id
LEFT JOIN document_pages dp ON dp.id = r.page_id
WHERE r.document_id = %s AND a.is_current
ORDER BY COALESCE(p.page_number, dp.page_number) NULLS LAST,
         r.priority DESC,
         r.semantic_type,
         r.created_at
"""

_PLANNER_SQL = """
SELECT id, planner_version, prompt_version, model_profile, run_id, status,
       selected_task_count, skipped_task_count, abstention_count, missing_contract_count,
       missing_grounding_count, incompatible_schema_count, duplicate_suppressed_count,
       report_json
FROM semantic_extraction_plans
WHERE document_id = %s
ORDER BY created_at
"""

_PLANNER_TASKS_SQL = """
SELECT task.id, task.plan_id, task.semantic_region_id, task.semantic_type,
       task.granite_task, task.extractor_backend, task.resolved_document_type,
       task.target_schema, task.canonical_target_schema, task.model_output_schema_name,
       task.contract_resolution_reason, task.compatibility_mode, task.grounding_kind,
       COALESCE(task.page_number, psa.page_number, dp.page_number, dep.page_number, dtp.page_number)
         AS page_number,
       task.visual_plan_summary,
       task.status, task.skip_reason, task.review_required, task.task_json
FROM semantic_extraction_plan_tasks task
LEFT JOIN semantic_region_annotations region ON region.id = task.semantic_region_id
LEFT JOIN page_semantic_annotations psa ON psa.id = region.page_annotation_id
LEFT JOIN document_pages dp ON dp.id = region.page_id
LEFT JOIN document_elements de ON de.id = region.element_id
LEFT JOIN document_pages dep ON dep.id = de.page_id
LEFT JOIN document_tables dt ON dt.id = region.table_id
LEFT JOIN document_pages dtp ON dtp.id = dt.page_id
WHERE task.document_id = %s
ORDER BY task.created_at
"""

_ADMISSION_EVENTS_SQL = """
SELECT plan_id, plan_task_id, semantic_annotation_id, semantic_region_id, run_id,
       planner_version, candidate_gate_version, contract_registry_version,
       region_envelope_version, candidate_kind, candidate_fingerprint, decision, reasons,
       field_path, semantic_type, model_output_schema_name, source_engine,
       evidence_concrete, payload_json
FROM candidate_admission_events
WHERE document_id = %s
ORDER BY created_at
"""

_EXTRACTIONS_SQL = """
SELECT id, schema_name, schema_version, extraction_scope, semantic_type, granite_task,
       semantic_annotation_id, source_semantic_region_id,
       model_output_schema_name, source_engine::text AS source_engine, model_name,
       prompt_version, status::text AS status, review_status::text AS review_status,
       confidence, is_current, validation_json, normalization_json, metadata_json,
       metadata_json -> 'visualInputPlan' AS visual_plan,
       metadata_json -> 'visualInputAttempts' AS visual_input_attempts
FROM document_extractions
WHERE document_id = %s
ORDER BY created_at
"""

_LINE_ITEMS_SQL = """
SELECT ordinal, line_item_type::text AS line_item_type, code, service_date, description,
       quantity, unit, unit_price, gross_amount, discount_amount, tax_amount, net_amount,
       currency_code, category_hint, confidence, status, source_engine::text AS source_engine,
       validation_json ->> 'candidateAdmissionFingerprint' AS candidate_fingerprint
FROM line_item_candidates
WHERE document_id = %s
ORDER BY ordinal, created_at
"""

_OBSERVATIONS_SQL = """
SELECT observation_family, field_name, value_type, value_json, confidence, status,
       semantic_type, source_engine::text AS source_engine, model_output_schema_name,
       metadata_json ->> 'candidateAdmissionFingerprint' AS candidate_fingerprint
FROM extraction_observations
WHERE document_id = %s
ORDER BY observation_family, field_name, created_at
"""

_EMBEDDINGS_SQL = """
SELECT modality::text AS modality, model_name, embedding_dimensions, count(*) AS count
FROM embeddings
WHERE document_id = %s AND is_active
GROUP BY modality, model_name, embedding_dimensions
ORDER BY modality, model_name
"""

_REVIEW_TASKS_SQL = """
SELECT id, extraction_id, task_type, status::text AS status, priority, reason, metadata_json
FROM review_tasks
WHERE document_id = %s
ORDER BY created_at
"""

_FIELDS_SQL = """
SELECT field_path, ordinal, source_engine::text AS source_engine, value_type::text AS value_type,
       text_value, integer_value, numeric_value, boolean_value, date_value, timestamp_value,
       json_value, currency_code, confidence, status,
       validation_json ->> 'candidateAdmissionFingerprint' AS candidate_fingerprint
FROM field_candidates
WHERE document_id = %s
ORDER BY field_path, ordinal, created_at
"""


def _rows_for_document(cur: Any, document_id: UUID, sql: str) -> list[dict[str, Any]]:
    cur.execute(sql, (document_id,))
    return [dict(row) for row in cur.fetchall()]


def _fields_for_document(cur: Any, document_id: UUID) -> list[dict[str, Any]]:
    rows = _rows_for_document(cur, document_id, _FIELDS_SQL)
    return [
        {
            "field_path": row["field_path"],
            "ordinal": row["ordinal"],
            "value": _scalar_value(row),
            "currency_code": row["currency_code"],
            "confidence": row["confidence"],
            "status": row["status"],
            "source_engine": row["source_engine"],
            "candidate_fingerprint": row["candidate_fingerprint"],
        }
        for row in rows
    ]


def _scalar_value(row: dict[str, Any]) -> Any:
    for key in (
        "text_value",
        "integer_value",
        "numeric_value",
        "boolean_value",
        "date_value",
        "timestamp_value",
        "json_value",
    ):
        value = row.get(key)
        if value is not None:
            return value
    return None


def _json_safe(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (UUID, date, datetime)):
        return str(value)
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, tuple):
        return [_json_safe(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    return value


def _emit(stage: str, **payload: Any) -> None:
    print(json.dumps({"stage": stage, **_json_safe(payload)}, sort_keys=True), flush=True)


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from lib.db.connection import db_connection
from lib.extraction.claims import claims_from_region_envelope
from lib.extraction.medical_eob_reconciliation import (
    reconcile_medical_eob_region_extractions,
)
from lib.extraction.models import (
    ExtractionRunScope,
    ExtractionSourceDocument,
    GatewayExtraction,
    ModelRoute,
    PersistedExtraction,
    ValidationReport,
)
from lib.extraction.normalization import (
    field_candidates_from_extraction,
    line_item_candidates_from_extraction,
    observation_candidates_from_extraction,
)
from lib.extraction.observation_reconciliation import (
    reconcile_document_observation_region_extractions,
)
from lib.extraction.receipt_reconciliation import (
    reconcile_receipt_region_extractions,
)
from lib.extraction.reconciliation import (
    RegionExtraction,
    reconcile_invoice_region_extractions,
)
from lib.extraction.region_envelope import region_envelope_from_normalization_json
from lib.extraction.repository import load_extraction_source, persist_extraction_run
from lib.extraction.validators import validate_extraction_payload

AGGREGATE_RECONCILIATION_SCHEMAS = {"invoice", "receipt", "medical_eob", "document_observation"}
OBSERVATION_AGGREGATE_CANONICAL_TARGETS = {"retail_order", "service_record"}

PENDING_REGION_JOB_STATUSES = ("queued", "leased", "running", "failed")
TERMINAL_FAILURE_REGION_JOB_STATUSES = ("dead_letter", "cancelled")


def maybe_reconcile_semantic_annotation(
    *,
    document_id: UUID,
    semantic_annotation_id: UUID | None,
    schema_name: str,
    canonical_target_schema: str | None = None,
    settled_job_id: UUID | None = None,
) -> PersistedExtraction | None:
    """Build the document aggregate once every region job is terminal.

    ``settled_job_id`` identifies the worker's own in-flight job: the worker
    triggers reconciliation after persisting its region row but before
    ``complete_job``, so that job still reads as ``running`` and must be
    treated as settled or the final region job would always block its own
    aggregate.
    """
    aggregate_schema_name = _aggregate_schema_name(
        schema_name=schema_name,
        canonical_target_schema=canonical_target_schema,
    )
    if semantic_annotation_id is None or aggregate_schema_name is None:
        return None
    lock_key = f"phase85_aggregate:{semantic_annotation_id}:{schema_name}"
    with db_connection() as lock_conn:
        with lock_conn.cursor() as lock_cur:
            lock_cur.execute("SELECT pg_advisory_lock(hashtextextended(%s, 0))", (lock_key,))
        try:
            return _reconcile_semantic_annotation_locked(
                document_id=document_id,
                semantic_annotation_id=semantic_annotation_id,
                schema_name=schema_name,
                canonical_target_schema=canonical_target_schema,
                aggregate_schema_name=aggregate_schema_name,
                settled_job_id=settled_job_id,
                wait_for_region_jobs=True,
            )
        finally:
            with lock_conn.cursor() as lock_cur:
                lock_cur.execute(
                    "SELECT pg_advisory_unlock(hashtextextended(%s, 0))",
                    (lock_key,),
                )


def reconcile_semantic_annotation_from_current_regions(
    *,
    document_id: UUID,
    semantic_annotation_id: UUID | None,
    schema_name: str,
    canonical_target_schema: str | None = None,
) -> PersistedExtraction | None:
    aggregate_schema_name = _aggregate_schema_name(
        schema_name=schema_name,
        canonical_target_schema=canonical_target_schema,
    )
    if semantic_annotation_id is None or aggregate_schema_name is None:
        return None
    lock_key = f"phase85_document_aggregate:{semantic_annotation_id}:{schema_name}"
    with db_connection() as lock_conn:
        with lock_conn.cursor() as lock_cur:
            lock_cur.execute("SELECT pg_advisory_lock(hashtextextended(%s, 0))", (lock_key,))
        try:
            return _reconcile_semantic_annotation_locked(
                document_id=document_id,
                semantic_annotation_id=semantic_annotation_id,
                schema_name=schema_name,
                canonical_target_schema=canonical_target_schema,
                aggregate_schema_name=aggregate_schema_name,
                settled_job_id=None,
                wait_for_region_jobs=False,
            )
        finally:
            with lock_conn.cursor() as lock_cur:
                lock_cur.execute(
                    "SELECT pg_advisory_unlock(hashtextextended(%s, 0))",
                    (lock_key,),
                )


def _reconcile_semantic_annotation_locked(
    *,
    document_id: UUID,
    semantic_annotation_id: UUID,
    schema_name: str,
    canonical_target_schema: str | None,
    aggregate_schema_name: str,
    settled_job_id: UUID | None,
    wait_for_region_jobs: bool,
) -> PersistedExtraction | None:
    with db_connection() as conn:
        with conn.cursor() as cur:
            job_counts = (
                _region_job_status_counts(
                    cur,
                    document_id=document_id,
                    semantic_annotation_id=semantic_annotation_id,
                    schema_name=schema_name,
                    settled_job_id=settled_job_id,
                )
                if wait_for_region_jobs
                else {}
            )
            rows = _current_region_extraction_rows(
                cur,
                document_id=document_id,
                semantic_annotation_id=semantic_annotation_id,
                schema_name=schema_name,
            )
            existing_fingerprint = _current_aggregate_region_fingerprint(
                cur,
                document_id=document_id,
                semantic_annotation_id=semantic_annotation_id,
                aggregate_schema_name=aggregate_schema_name,
            )
            plan_coverage = _plan_skipped_task_summary(
                cur,
                document_id=document_id,
                semantic_annotation_id=semantic_annotation_id,
            )
    if not wait_for_region_jobs:
        job_counts = {"succeeded": len(rows)}
    total_jobs = sum(job_counts.values())
    pending_jobs = sum(job_counts.get(status, 0) for status in PENDING_REGION_JOB_STATUSES)
    if total_jobs == 0 or pending_jobs > 0 or not rows:
        return None
    region_fingerprint = sorted(str(row["id"]) for row in rows)
    if existing_fingerprint == region_fingerprint:
        return None
    missing_region_jobs = sum(
        job_counts.get(status, 0) for status in TERMINAL_FAILURE_REGION_JOB_STATUSES
    )
    aggregate_lineage = _aggregate_lineage_metadata(rows)

    regions: list[RegionExtraction] = []
    for row in rows:
        if not row.get("source_semantic_region_id") or not row.get("semantic_type"):
            continue
        normalization_json = dict(row["normalization_json"] or {})
        region_envelope = region_envelope_from_normalization_json(normalization_json)
        regions.append(
            RegionExtraction(
                extraction_id=row["id"],
                semantic_region_id=row["source_semantic_region_id"],
                semantic_type=row["semantic_type"],
                region_envelope=region_envelope,
                claims=(
                    tuple(claims_from_region_envelope(region_envelope))
                    if region_envelope is not None
                    else ()
                ),
            )
        )
    if not regions:
        return None

    source = load_extraction_source(document_id)
    aggregate_json = _reconcile_regions(
        schema_name=aggregate_schema_name,
        document_id=document_id,
        source=source,
        regions=regions,
    )
    if aggregate_json is None:
        return None
    aggregate_json.setdefault("metadata", {})
    if isinstance(aggregate_json["metadata"], dict) and aggregate_schema_name != schema_name:
        aggregate_json["metadata"]["source_schema_name"] = schema_name
        if canonical_target_schema not in (None, ""):
            aggregate_json["metadata"]["canonical_target_schema"] = canonical_target_schema
    if isinstance(aggregate_json["metadata"], dict):
        aggregate_json["metadata"].update(aggregate_lineage)
        _record_region_coverage(
            aggregate_json["metadata"],
            job_counts=job_counts,
            missing_region_jobs=missing_region_jobs,
            plan_coverage=plan_coverage,
        )
    validation = validate_extraction_payload(aggregate_schema_name, aggregate_json)
    validation = _force_aggregate_review(validation)
    if missing_region_jobs or plan_coverage.get("skipped_task_count"):
        validation = _flag_incomplete_region_coverage(
            validation,
            missing_region_jobs=missing_region_jobs,
            skipped_task_count=int(plan_coverage.get("skipped_task_count") or 0),
        )
    aggregate_json["validation"] = validation.as_json()
    gateway_extraction = GatewayExtraction(
        schema_name=aggregate_schema_name,
        schema_version="v1",
        route=ModelRoute(
            source_engine="system",
            model_name="phase8_5-region-reconciler",
            model_version="v1",
            prompt_version="phase8_5-region-reconciliation-v1",
            route_profile="semantic_region_aggregate",
        ),
        normalized_json=aggregate_json,
        raw_output_json={
            "modelInvoked": False,
            "source": "phase8_5_region_reconciliation",
            "semanticAnnotationId": str(semantic_annotation_id),
            "regionExtractionIds": [str(region.extraction_id) for region in regions],
            "sourceSchemaName": schema_name,
            "canonicalTargetSchema": canonical_target_schema,
            "sourceRunIds": aggregate_lineage.get("source_run_ids", []),
        },
        normalization_json={
            "mapper": "phase8_5_region_reconciler.v1",
            "repairs": ["merged_current_semantic_region_outputs"],
            "rejected_fields": [],
            "sourceFamilies": _aggregate_source_families(aggregate_json),
        },
        metadata={
            "semanticAnnotationId": str(semantic_annotation_id),
            "regionExtractionIds": region_fingerprint,
            **aggregate_lineage,
        },
    )
    field_candidates = field_candidates_from_extraction(
        document_id=document_id,
        schema_name=aggregate_schema_name,
        payload=aggregate_json,
        validation=validation,
        source_engine=gateway_extraction.route.source_engine,
    )
    line_item_candidates = line_item_candidates_from_extraction(
        schema_name=aggregate_schema_name,
        payload=aggregate_json,
        validation=validation,
        source_engine=gateway_extraction.route.source_engine,
    )
    observation_candidates = observation_candidates_from_extraction(
        schema_name=aggregate_schema_name,
        payload=aggregate_json,
        validation=validation,
        source_engine=gateway_extraction.route.source_engine,
    )
    return persist_extraction_run(
        gateway_extraction,
        source=source,
        validation=validation,
        field_candidates=field_candidates,
        line_item_candidates=line_item_candidates,
        observation_candidates=observation_candidates,
        run_scope=ExtractionRunScope.aggregate(
            semantic_annotation_id=semantic_annotation_id,
            metadata=aggregate_lineage,
        ),
    )


def _reconcile_regions(
    *,
    schema_name: str,
    document_id: UUID,
    source: ExtractionSourceDocument,
    regions: list[RegionExtraction],
) -> dict[str, Any] | None:
    created_at = datetime.now(UTC)
    if schema_name == "invoice":
        seller = (
            {"display_name": source.counterparty_display, "party_type": "company"}
            if source.counterparty_display
            else {}
        )
        return reconcile_invoice_region_extractions(
            document_id=document_id,
            seller=seller,
            created_at=created_at,
            regions=regions,
        )
    if schema_name == "receipt":
        return reconcile_receipt_region_extractions(
            document_id=document_id,
            created_at=created_at,
            regions=regions,
        )
    if schema_name == "document_observation":
        return reconcile_document_observation_region_extractions(
            document_id=document_id,
            created_at=created_at,
            regions=regions,
        )
    if schema_name == "medical_eob":
        return reconcile_medical_eob_region_extractions(
            document_id=document_id,
            created_at=created_at,
            regions=regions,
        )
    return None


def _aggregate_schema_name(
    *,
    schema_name: str,
    canonical_target_schema: str | None,
) -> str | None:
    # Observation-only canonical targets (e.g. service records extracted through
    # receipt-shaped contracts) must aggregate as review-only observations even
    # though their region schema_name is a first-class aggregate family.
    if canonical_target_schema in OBSERVATION_AGGREGATE_CANONICAL_TARGETS:
        return "document_observation"
    if schema_name in AGGREGATE_RECONCILIATION_SCHEMAS:
        return schema_name
    return None


def _region_job_status_counts(
    cur: Any,
    *,
    document_id: UUID,
    semantic_annotation_id: UUID,
    schema_name: str,
    settled_job_id: UUID | None = None,
) -> dict[str, int]:
    cur.execute(
        """
        SELECT
          CASE WHEN id = %s THEN 'succeeded' ELSE status END AS status,
          COUNT(*) AS job_count
        FROM pipeline_jobs
        WHERE document_id = %s
          AND job_type = 'extract'
          AND payload_json ->> 'semantic_annotation_id' = %s
          AND payload_json ->> 'target_schema_name' = %s
        GROUP BY 1
        """,
        (settled_job_id, document_id, str(semantic_annotation_id), schema_name),
    )
    return {str(row["status"]): int(row["job_count"]) for row in cur.fetchall()}


def _current_aggregate_region_fingerprint(
    cur: Any,
    *,
    document_id: UUID,
    semantic_annotation_id: UUID,
    aggregate_schema_name: str,
) -> list[str] | None:
    cur.execute(
        """
        SELECT metadata_json -> 'regionExtractionIds' AS region_extraction_ids
        FROM document_extractions
        WHERE document_id = %s
          AND semantic_annotation_id = %s
          AND schema_name = %s
          AND extraction_scope = 'aggregate'
          AND is_current
        ORDER BY created_at DESC
        LIMIT 1
        """,
        (document_id, semantic_annotation_id, aggregate_schema_name),
    )
    row = cur.fetchone()
    if not row:
        return None
    region_ids = row.get("region_extraction_ids")
    if not isinstance(region_ids, list):
        return None
    return sorted(str(item) for item in region_ids)


def _plan_skipped_task_summary(
    cur: Any,
    *,
    document_id: UUID,
    semantic_annotation_id: UUID,
) -> dict[str, Any]:
    cur.execute(
        """
        SELECT tasks.status, tasks.skip_reason, COUNT(*) AS task_count
        FROM semantic_extraction_plan_tasks AS tasks
        JOIN semantic_extraction_plans AS plans ON plans.id = tasks.plan_id
        WHERE tasks.document_id = %s
          AND plans.semantic_annotation_id = %s
          AND plans.created_at = (
            SELECT MAX(created_at)
            FROM semantic_extraction_plans
            WHERE semantic_annotation_id = %s
          )
          AND tasks.status = 'skipped_budget_exceeded'
        GROUP BY tasks.status, tasks.skip_reason
        """,
        (document_id, str(semantic_annotation_id), str(semantic_annotation_id)),
    )
    rows = list(cur.fetchall())
    skipped: list[dict[str, Any]] = [
        {
            "status": str(row["status"]),
            "skip_reason": str(row["skip_reason"]) if row["skip_reason"] is not None else None,
            "count": int(row["task_count"]),
        }
        for row in rows
    ]
    return {
        "skipped_task_count": sum(item["count"] for item in skipped),
        "skipped_tasks": skipped,
    }


def _record_region_coverage(
    metadata: dict[str, Any],
    *,
    job_counts: dict[str, int],
    missing_region_jobs: int,
    plan_coverage: dict[str, Any],
) -> None:
    metadata["region_job_coverage"] = {
        "expected_jobs": sum(job_counts.values()),
        "succeeded_jobs": job_counts.get("succeeded", 0),
        "dead_letter_jobs": job_counts.get("dead_letter", 0),
        "cancelled_jobs": job_counts.get("cancelled", 0),
        "missing_region_jobs": missing_region_jobs,
        "plan_skipped_task_count": int(plan_coverage.get("skipped_task_count") or 0),
        "plan_skipped_tasks": list(plan_coverage.get("skipped_tasks") or []),
    }
    if missing_region_jobs or plan_coverage.get("skipped_task_count"):
        if metadata.get("quality_outcome") == "extracted_cleanly":
            metadata["quality_outcome"] = "needs_human_review"
            metadata["quality_outcome_demotion_reason"] = "aggregate_region_coverage_incomplete"


def _current_region_extraction_rows(
    cur: Any,
    *,
    document_id: UUID,
    semantic_annotation_id: UUID,
    schema_name: str,
) -> list[dict[str, Any]]:
    cur.execute(
        """
        SELECT
          id,
          source_semantic_region_id,
          semantic_type,
          normalization_json,
          metadata_json
        FROM document_extractions
        WHERE document_id = %s
          AND semantic_annotation_id = %s
          AND schema_name = %s
          AND extraction_scope = 'semantic_region'
          AND is_current
          AND status = 'completed'
        ORDER BY created_at ASC
        """,
        (document_id, semantic_annotation_id, schema_name),
    )
    return list(cur.fetchall())


def _aggregate_lineage_metadata(rows: list[dict[str, Any]]) -> dict[str, Any]:
    run_ids = sorted(
        {
            run_id
            for row in rows
            if (run_id := _metadata_run_id(row.get("metadata_json"))) is not None
        }
    )
    if not run_ids:
        return {}
    run_id = run_ids[0] if len(run_ids) == 1 else "mixed:" + ",".join(run_ids)
    return {
        "run_id": run_id,
        "source_run_ids": run_ids,
    }


def _metadata_run_id(metadata: Any) -> str | None:
    if not isinstance(metadata, dict):
        return None
    value = metadata.get("run_id") or metadata.get("runId")
    if value in (None, ""):
        return None
    return str(value)


def _flag_incomplete_region_coverage(
    validation: ValidationReport,
    *,
    missing_region_jobs: int,
    skipped_task_count: int,
) -> ValidationReport:
    checks = [
        *validation.checks,
        {
            "code": "aggregate_region_coverage_incomplete",
            "status": "warning",
            "message": (
                "Aggregate is missing planned region extractions "
                f"({missing_region_jobs} terminal-failed region jobs, "
                f"{skipped_task_count} skipped plan tasks); output may be partial."
            ),
        },
    ]
    return ValidationReport(needs_review=True, checks=checks)


def _force_aggregate_review(validation: ValidationReport) -> ValidationReport:
    checks = [
        *validation.checks,
        {
            "code": "semantic_region_aggregate",
            "status": "warning",
            "message": (
                "Aggregate was merged from model-backed region candidates and requires review."
            ),
        },
    ]
    return ValidationReport(needs_review=True, checks=checks)


def _aggregate_source_families(aggregate_json: dict[str, Any]) -> list[str]:
    metadata = aggregate_json.get("metadata")
    if not isinstance(metadata, dict):
        return []
    source_families = metadata.get("source_families")
    if not isinstance(source_families, list):
        return []
    return [str(item) for item in source_families if item not in (None, "")]

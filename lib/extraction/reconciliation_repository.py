from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from lib.db.connection import db_connection
from lib.extraction.models import (
    ExtractionRunScope,
    GatewayExtraction,
    ModelRoute,
    PersistedExtraction,
    ValidationReport,
)
from lib.extraction.normalization import (
    field_candidates_from_extraction,
    line_item_candidates_from_extraction,
)
from lib.extraction.reconciliation import RegionExtraction, reconcile_invoice_region_extractions
from lib.extraction.repository import load_extraction_source, persist_extraction_run
from lib.extraction.validators import validate_extraction_payload


def maybe_reconcile_semantic_annotation(
    *,
    document_id: UUID,
    semantic_annotation_id: UUID | None,
    schema_name: str,
) -> PersistedExtraction | None:
    if semantic_annotation_id is None or schema_name != "invoice":
        return None
    with db_connection() as conn:
        with conn.cursor() as cur:
            expected_count = _expected_region_job_count(
                cur,
                document_id=document_id,
                semantic_annotation_id=semantic_annotation_id,
                schema_name=schema_name,
            )
            rows = _current_region_extraction_rows(
                cur,
                document_id=document_id,
                semantic_annotation_id=semantic_annotation_id,
                schema_name=schema_name,
            )
            document_fallback = _current_document_extraction_json(
                cur,
                document_id=document_id,
                schema_name=schema_name,
            )
    if expected_count == 0 or len(rows) < expected_count:
        return None

    regions = [
        RegionExtraction(
            extraction_id=row["id"],
            semantic_region_id=row["source_semantic_region_id"],
            semantic_type=row["semantic_type"],
            normalized_json=dict(row["normalized_json"] or {}),
        )
        for row in rows
        if row.get("source_semantic_region_id") and row.get("semantic_type")
    ]
    if not regions:
        return None

    source = load_extraction_source(document_id)
    seller = (
        {"display_name": source.counterparty_display, "party_type": "company"}
        if source.counterparty_display
        else {}
    )
    aggregate_json = reconcile_invoice_region_extractions(
        document_id=document_id,
        seller=seller,
        created_at=datetime.now(UTC),
        regions=regions,
        document_fallback=document_fallback,
    )
    if aggregate_json is None:
        return None
    validation = validate_extraction_payload(schema_name, aggregate_json)
    validation = _force_aggregate_review(validation)
    aggregate_json["validation"] = validation.as_json()
    gateway_extraction = GatewayExtraction(
        schema_name=schema_name,
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
        },
        normalization_json={
            "mapper": "phase8_5_region_reconciler.v1",
            "repairs": ["merged_current_semantic_region_outputs"],
            "rejected_fields": [],
        },
        metadata={"semanticAnnotationId": str(semantic_annotation_id)},
    )
    field_candidates = field_candidates_from_extraction(
        document_id=document_id,
        schema_name=schema_name,
        payload=aggregate_json,
        validation=validation,
        source_engine=gateway_extraction.route.source_engine,
    )
    line_item_candidates = line_item_candidates_from_extraction(
        schema_name=schema_name,
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
        run_scope=ExtractionRunScope.aggregate(semantic_annotation_id=semantic_annotation_id),
    )


def _expected_region_job_count(
    cur: Any,
    *,
    document_id: UUID,
    semantic_annotation_id: UUID,
    schema_name: str,
) -> int:
    cur.execute(
        """
        SELECT COUNT(*) AS expected_count
        FROM pipeline_jobs
        WHERE document_id = %s
          AND job_type = 'extract'
          AND payload_json ->> 'semantic_annotation_id' = %s
          AND payload_json ->> 'target_schema_name' = %s
        """,
        (document_id, str(semantic_annotation_id), schema_name),
    )
    row = cur.fetchone()
    return int(row["expected_count"] if row else 0)


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
          normalized_json
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


def _current_document_extraction_json(
    cur: Any,
    *,
    document_id: UUID,
    schema_name: str,
) -> dict[str, Any]:
    cur.execute(
        """
        SELECT normalized_json
        FROM document_extractions
        WHERE document_id = %s
          AND schema_name = %s
          AND extraction_scope = 'document'
          AND source_engine = 'granite_vision_3b'
          AND is_current
          AND status = 'completed'
        ORDER BY created_at DESC
        LIMIT 1
        """,
        (document_id, schema_name),
    )
    row = cur.fetchone()
    if not row or not isinstance(row.get("normalized_json"), dict):
        return {}
    return dict(row["normalized_json"])


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

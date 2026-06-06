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
from lib.extraction.reconciliation import (
    RegionExtraction,
    reconcile_invoice_region_extractions,
)
from lib.extraction.region_envelope import region_envelope_from_normalization_json
from lib.extraction.repository import load_extraction_source, persist_extraction_run
from lib.extraction.validators import validate_extraction_payload

AGGREGATE_RECONCILIATION_SCHEMAS = {"invoice", "medical_eob", "document_observation"}
OBSERVATION_AGGREGATE_CANONICAL_TARGETS = {"retail_order", "service_record"}


def maybe_reconcile_semantic_annotation(
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
    if expected_count == 0 or len(rows) < expected_count:
        return None

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
    validation = validate_extraction_payload(aggregate_schema_name, aggregate_json)
    validation = _force_aggregate_review(validation)
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
        },
        normalization_json={
            "mapper": "phase8_5_region_reconciler.v1",
            "repairs": ["merged_current_semantic_region_outputs"],
            "rejected_fields": [],
            "sourceFamilies": _aggregate_source_families(aggregate_json),
        },
        metadata={"semanticAnnotationId": str(semantic_annotation_id)},
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
        run_scope=ExtractionRunScope.aggregate(semantic_annotation_id=semantic_annotation_id),
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
    if schema_name in AGGREGATE_RECONCILIATION_SCHEMAS:
        return schema_name
    if canonical_target_schema in OBSERVATION_AGGREGATE_CANONICAL_TARGETS:
        return "document_observation"
    return None


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
          normalization_json
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

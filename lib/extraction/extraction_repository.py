from __future__ import annotations

import json
from typing import Any, cast
from uuid import UUID

from psycopg.types.json import Jsonb

from lib.db.connection import db_connection
from lib.extraction.candidate_admission import persist_candidate_admission_events
from lib.extraction.candidate_admission_boundary import apply_candidate_admission_boundary
from lib.extraction.candidate_repository import (
    insert_field_candidate,
    insert_line_item_candidate,
)
from lib.extraction.canonical_repository import (
    create_review_tasks,
    promote_candidates,
    refresh_document_chunk_projection,
    update_document_rollups,
)
from lib.extraction.errors import ExtractionRepositoryError
from lib.extraction.extraction_plan_task_repository import update_plan_task_visual_summary
from lib.extraction.models import (
    CandidateFact,
    ClassificationDecision,
    ExtractionRunScope,
    ExtractionSourceDocument,
    GatewayExtraction,
    LineItemCandidateFact,
    ObservationCandidateFact,
    PersistedExtraction,
    ValidationReport,
)
from lib.extraction.observation_repository import insert_observation_candidate
from lib.model_runtime.source_engines import is_model_source_engine
from lib.review.task_repository import upsert_review_task
from lib.storage import ObjectStorage, StoredObject, cleanup_unreferenced_stored_object


def persist_classification(
    decision: ClassificationDecision,
    *,
    source: ExtractionSourceDocument,
) -> UUID:
    review_status = "needs_review" if decision.needs_review else "auto_accepted"
    with db_connection() as conn:
        with conn.cursor() as cur:
            _lock_document(cur, source.document_id)
            _supersede_current_extractions(cur, source.document_id, "document_classification")
            extraction_id = _insert_classification_extraction(cur, decision, source, review_status)
            _update_document_classification(cur, decision, source, review_status)
            refresh_document_chunk_projection(cur, source.document_id)
            if decision.needs_review:
                upsert_review_task(
                    cur,
                    document_id=source.document_id,
                    extraction_id=extraction_id,
                    task_type="classification_review",
                    reason="Classification requires review.",
                    priority=80 if decision.family == "medical_eob" else 60,
                    metadata={"fieldPath": "classification.document_family"},
                )
        conn.commit()
    return extraction_id


def persist_extraction_run(
    extraction: GatewayExtraction,
    *,
    source: ExtractionSourceDocument,
    validation: ValidationReport,
    field_candidates: list[CandidateFact],
    line_item_candidates: list[LineItemCandidateFact],
    observation_candidates: list[ObservationCandidateFact] | None = None,
    run_scope: ExtractionRunScope | None = None,
    semantic_task: Any | None = None,
    storage: ObjectStorage | None = None,
) -> PersistedExtraction:
    resolved_scope = run_scope or _run_scope_from_semantic_task(semantic_task)
    object_storage = storage or ObjectStorage()
    created_objects: list[StoredObject] = []
    raw_object = object_storage.store_bytes(
        json.dumps(extraction.raw_output_json, sort_keys=True).encode("utf-8"),
        kind="derived",
        role=f"raw-model-output-{source.document_id}-{extraction.schema_name}",
    )
    _remember_created(created_objects, raw_object)
    normalized_object = object_storage.store_bytes(
        json.dumps(extraction.normalized_json, sort_keys=True).encode("utf-8"),
        kind="derived",
        role=f"normalized-extraction-{source.document_id}-{extraction.schema_name}",
    )
    _remember_created(created_objects, normalized_object)

    try:
        return _persist_extraction_rows(
            extraction,
            source=source,
            validation=validation,
            field_candidates=field_candidates,
            line_item_candidates=line_item_candidates,
            observation_candidates=observation_candidates or [],
            run_scope=resolved_scope,
            raw_object=raw_object,
            normalized_object=normalized_object,
        )
    except Exception:
        _cleanup_created(created_objects)
        raise


def _persist_extraction_rows(
    extraction: GatewayExtraction,
    *,
    source: ExtractionSourceDocument,
    validation: ValidationReport,
    field_candidates: list[CandidateFact],
    line_item_candidates: list[LineItemCandidateFact],
    observation_candidates: list[ObservationCandidateFact],
    run_scope: ExtractionRunScope,
    raw_object: StoredObject,
    normalized_object: StoredObject,
) -> PersistedExtraction:
    review_status = _review_status_for_extraction(
        extraction=extraction,
        validation=validation,
        run_scope=run_scope,
    )
    status = _status_for_persisted_extraction(validation)
    admission_boundary = apply_candidate_admission_boundary(
        extraction=extraction,
        source=source,
        run_scope=run_scope,
        field_candidates=field_candidates,
        line_item_candidates=line_item_candidates,
        observation_candidates=observation_candidates,
    )
    extraction_for_insert = admission_boundary.extraction
    admission = admission_boundary.admission
    with db_connection() as conn:
        with conn.cursor() as cur:
            _lock_document(cur, source.document_id)
            if run_scope.extraction_scope in {"document", "aggregate"}:
                _supersede_current_assets(
                    cur,
                    source.document_id,
                    ("raw_model_output", "normalized_extraction_json"),
                )
            raw_asset_id = _insert_artifact_asset(
                cur,
                document_id=source.document_id,
                stored=raw_object,
                asset_role="raw_model_output",
                mime_type="application/json",
                metadata=_artifact_metadata(extraction_for_insert, run_scope),
                model_name=extraction_for_insert.route.model_name,
                model_version=extraction_for_insert.route.model_version,
            )
            _insert_artifact_asset(
                cur,
                document_id=source.document_id,
                stored=normalized_object,
                asset_role="normalized_extraction_json",
                mime_type="application/json",
                metadata=_artifact_metadata(extraction_for_insert, run_scope),
                model_name=extraction_for_insert.route.model_name,
                model_version=extraction_for_insert.route.model_version,
            )
            _supersede_current_extractions(
                cur,
                source.document_id,
                extraction_for_insert.schema_name,
                extraction_scope=run_scope.extraction_scope,
                source_semantic_region_id=run_scope.source_semantic_region_id,
            )
            extraction_id = _insert_extraction_run_row(
                cur,
                extraction=extraction_for_insert,
                source=source,
                validation=validation,
                status=status,
                review_status=review_status,
                raw_asset_id=raw_asset_id,
                run_scope=run_scope,
            )
            update_plan_task_visual_summary(
                cur,
                plan_task_id=run_scope.plan_task_id,
                extraction_metadata=extraction_for_insert.metadata,
            )
            persist_candidate_admission_events(
                cur,
                extraction_id=extraction_id,
                events=admission.events,
            )
            inserted_candidates = [
                insert_field_candidate(
                    cur,
                    source.document_id,
                    extraction_id,
                    extraction_for_insert.route.source_engine,
                    candidate,
                )
                for candidate in admission.field_candidates
            ]
            inserted_line_item_candidates = [
                insert_line_item_candidate(
                    cur,
                    source.document_id,
                    extraction_id,
                    extraction_for_insert.route.source_engine,
                    line_item,
                )
                for line_item in admission.line_item_candidates
            ]
            inserted_observation_candidates = [
                insert_observation_candidate(
                    cur,
                    source.document_id,
                    extraction_id,
                    extraction_for_insert.route.source_engine,
                    observation,
                    semantic_annotation_id=run_scope.semantic_annotation_id,
                    source_semantic_region_id=run_scope.source_semantic_region_id,
                    semantic_type=run_scope.semantic_type,
                    model_output_schema_name=extraction_for_insert.model_output_schema_name,
                )
                for observation in admission.observation_candidates
            ]
            canonical_count = promote_candidates(
                cur,
                source=source,
                extraction_id=extraction_id,
                candidates=inserted_candidates,
                validation=validation,
                schema_name=extraction.schema_name,
            )
            review_task_count = (
                create_review_tasks(
                    cur,
                    source=source,
                    extraction_id=extraction_id,
                    candidates=inserted_candidates,
                    validation=validation,
                    schema_name=extraction.schema_name,
                )
                + _create_line_item_review_tasks(
                    cur,
                    source=source,
                    extraction_id=extraction_id,
                    candidates=inserted_line_item_candidates,
                    validation=validation,
                    run_scope=run_scope,
                )
                + _create_observation_review_tasks(
                    cur,
                    source=source,
                    extraction_id=extraction_id,
                    candidates=inserted_observation_candidates,
                )
            )
            update_document_rollups(cur, source.document_id)
            refresh_document_chunk_projection(cur, source.document_id)
        conn.commit()
    return PersistedExtraction(
        extraction_id=extraction_id,
        review_status=review_status,
        candidate_count=admission.candidate_count,
        canonical_count=canonical_count,
        review_task_count=review_task_count,
    )


def _create_line_item_review_tasks(
    cur: Any,
    *,
    source: ExtractionSourceDocument,
    extraction_id: UUID,
    candidates: list[dict[str, Any]],
    validation: ValidationReport,
    run_scope: ExtractionRunScope,
) -> int:
    created = 0
    for candidate in candidates:
        if not (
            validation.needs_review
            or candidate.get("status") == "needs_review"
            or run_scope.extraction_scope != "document"
        ):
            continue
        line_item_type = str(candidate.get("line_item_type") or "generic")
        ordinal = int(candidate.get("ordinal") or created + 1)
        upsert_review_task(
            cur,
            document_id=source.document_id,
            extraction_id=extraction_id,
            task_type="line_item_review",
            reason=f"{line_item_type} line item {ordinal} requires review.",
            priority=72,
            metadata={
                "fieldPath": f"line_items.{line_item_type}.{ordinal}",
                "lineItemCandidateId": str(candidate["id"]),
                "lineItemType": line_item_type,
                "ordinal": ordinal,
            },
        )
        created += 1
    return created


def _create_observation_review_tasks(
    cur: Any,
    *,
    source: ExtractionSourceDocument,
    extraction_id: UUID,
    candidates: list[dict[str, Any]],
) -> int:
    created = 0
    for candidate in candidates:
        family = str(candidate.get("observation_family") or "document_observation")
        field_name = str(candidate.get("field_name") or "observation")
        upsert_review_task(
            cur,
            document_id=source.document_id,
            extraction_id=extraction_id,
            task_type="observation_review",
            reason=f"{family}.{field_name} requires review.",
            priority=65,
            metadata={
                "fieldPath": f"observations.{family}.{field_name}",
                "observationId": str(candidate["id"]),
                "observationFamily": family,
                "fieldName": field_name,
            },
        )
        created += 1
    return created


def _insert_classification_extraction(
    cur: Any,
    decision: ClassificationDecision,
    source: ExtractionSourceDocument,
    review_status: str,
) -> UUID:
    cur.execute(
        """
        INSERT INTO document_extractions
          (
            document_id, schema_name, schema_version, status, is_current,
            source_engine, model_name, model_version, prompt_version,
            normalized_json, validation_json, confidence, review_status
          )
        VALUES (
          %s, 'document_classification', 'v1', 'completed', true,
          'system', 'phase4-heuristic-classifier', 'v1', NULL,
          %s::jsonb, %s::jsonb, %s, %s
        )
        RETURNING id
        """,
        (
            source.document_id,
            Jsonb(decision.payload),
            Jsonb({"needs_review": decision.needs_review, "checks": []}),
            decision.confidence,
            review_status,
        ),
    )
    row = cur.fetchone()
    if not row:
        raise ExtractionRepositoryError("Classification extraction insert failed.")
    return cast(UUID, row["id"])


def _update_document_classification(
    cur: Any,
    decision: ClassificationDecision,
    source: ExtractionSourceDocument,
    review_status: str,
) -> None:
    del review_status
    cur.execute(
        """
        UPDATE documents
        SET document_family = CASE
              WHEN metadata_json #> '{phase8_5,semantic_classification}' IS NOT NULL
              THEN document_family ELSE %s::document_family_enum
            END,
            document_subtype = CASE
              WHEN metadata_json #> '{phase8_5,semantic_classification}' IS NOT NULL
              THEN document_subtype ELSE %s
            END,
            family_confidence = CASE
              WHEN metadata_json #> '{phase8_5,semantic_classification}' IS NOT NULL
              THEN family_confidence ELSE %s
            END,
            sensitivity = CASE
              WHEN metadata_json #> '{phase8_5,semantic_classification}' IS NOT NULL
              THEN sensitivity
              WHEN %s = 'medical_eob' THEN 'medical'::sensitivity_enum
              ELSE sensitivity
            END,
            review_status = CASE
              WHEN metadata_json #> '{phase8_5,semantic_classification}' IS NOT NULL
              THEN review_status
              WHEN %s THEN 'needs_review'::review_status_enum
              WHEN review_status = 'unreviewed' THEN 'auto_accepted'::review_status_enum
              ELSE review_status
            END,
            metadata_json = metadata_json || %s::jsonb,
            updated_at = now()
        WHERE id = %s
        """,
        (
            decision.family,
            decision.payload.get("subtype"),
            decision.confidence,
            decision.family,
            decision.needs_review,
            Jsonb({"phase4": {"classification": decision.payload}}),
            source.document_id,
        ),
    )


def _insert_extraction_run_row(
    cur: Any,
    *,
    extraction: GatewayExtraction,
    source: ExtractionSourceDocument,
    validation: ValidationReport,
    status: str,
    review_status: str,
    raw_asset_id: UUID,
    run_scope: ExtractionRunScope,
) -> UUID:
    cur.execute(
        """
        INSERT INTO document_extractions
          (
            document_id, schema_name, schema_version, status, is_current,
            source_engine, model_name, model_version, prompt_version,
            raw_output_asset_id, normalized_json, validation_json, confidence,
            review_status, extraction_scope, semantic_annotation_id,
            source_semantic_region_id, semantic_type, granite_task,
            model_output_schema_name, model_output_schema_version,
            normalization_json, metadata_json, plan_id, plan_task_id,
            canonical_target_schema, compatibility_mode,
            contract_resolution_reason, region_envelope_version
          )
        VALUES (
          %s, %s, %s, %s, true, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s, %s,
          %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s, %s, %s, %s, %s, %s
        )
        RETURNING id
        """,
        (
            source.document_id,
            extraction.schema_name,
            extraction.schema_version,
            status,
            extraction.route.source_engine,
            extraction.route.model_name,
            extraction.route.model_version,
            extraction.route.prompt_version,
            raw_asset_id,
            Jsonb(extraction.normalized_json),
            Jsonb(validation.as_json()),
            _overall_confidence(extraction.normalized_json),
            review_status,
            run_scope.extraction_scope,
            run_scope.semantic_annotation_id,
            run_scope.source_semantic_region_id,
            run_scope.semantic_type,
            run_scope.granite_task,
            extraction.model_output_schema_name,
            extraction.model_output_schema_version,
            Jsonb(extraction.normalization_json),
            Jsonb({**run_scope.metadata, **extraction.metadata}),
            run_scope.plan_id,
            run_scope.plan_task_id,
            run_scope.canonical_target_schema,
            run_scope.compatibility_mode,
            run_scope.contract_resolution_reason,
            run_scope.region_envelope_version,
        ),
    )
    row = cur.fetchone()
    if not row:
        raise ExtractionRepositoryError("Extraction run insert failed.")
    return cast(UUID, row["id"])


def _insert_artifact_asset(
    cur: Any,
    *,
    document_id: UUID,
    stored: StoredObject,
    asset_role: str,
    mime_type: str,
    metadata: dict[str, Any],
    model_name: str,
    model_version: str,
) -> UUID:
    cur.execute(
        """
        INSERT INTO document_assets
          (
            document_id, asset_role, version_no, uri, mime_type, byte_size, sha256,
            model_name, model_version, metadata_json, is_current
          )
        VALUES (
          %s,
          %s,
          COALESCE(
            (
              SELECT MAX(version_no) + 1
              FROM document_assets
              WHERE document_id = %s
                AND asset_role = %s
            ),
            1
          ),
          %s,
          %s,
          %s,
          %s,
          %s,
          %s,
          %s::jsonb,
          true
        )
        RETURNING id
        """,
        (
            document_id,
            asset_role,
            document_id,
            asset_role,
            stored.uri,
            mime_type,
            stored.byte_size,
            stored.sha256,
            model_name,
            model_version,
            Jsonb(metadata),
        ),
    )
    row = cur.fetchone()
    if not row:
        raise ExtractionRepositoryError("Artifact asset insert failed.")
    return cast(UUID, row["id"])


def _lock_document(cur: Any, document_id: UUID) -> None:
    cur.execute(
        """
        SELECT id
        FROM documents
        WHERE id = %s
          AND deleted_at IS NULL
        FOR UPDATE
        """,
        (document_id,),
    )
    if not cur.fetchone():
        raise ExtractionRepositoryError("Document not found.")


def _supersede_current_extractions(
    cur: Any,
    document_id: UUID,
    schema_name: str,
    *,
    extraction_scope: str = "document",
    source_semantic_region_id: UUID | None = None,
) -> None:
    if extraction_scope == "semantic_region":
        cur.execute(
            """
            UPDATE document_extractions
            SET is_current = false,
                status = CASE WHEN status = 'completed' THEN 'superseded' ELSE status END,
                updated_at = now()
            WHERE document_id = %s
              AND schema_name = %s
              AND extraction_scope = %s
              AND source_semantic_region_id = %s
              AND is_current
            """,
            (document_id, schema_name, extraction_scope, source_semantic_region_id),
        )
        return
    cur.execute(
        """
        UPDATE document_extractions
        SET is_current = false,
            status = CASE WHEN status = 'completed' THEN 'superseded' ELSE status END,
            updated_at = now()
        WHERE document_id = %s
          AND schema_name = %s
          AND extraction_scope = %s
          AND is_current
        """,
        (document_id, schema_name, extraction_scope),
    )


def _supersede_current_assets(
    cur: Any,
    document_id: UUID,
    asset_roles: tuple[str, ...],
) -> None:
    cur.execute(
        """
        UPDATE document_assets
        SET is_current = false,
            updated_at = now()
        WHERE document_id = %s
          AND asset_role = ANY(%s::asset_role_enum[])
          AND is_current
        """,
        (document_id, list(asset_roles)),
    )


def _run_scope_from_semantic_task(semantic_task: Any | None) -> ExtractionRunScope:
    if semantic_task is None:
        return ExtractionRunScope.document()
    return ExtractionRunScope.semantic_region(
        semantic_annotation_id=semantic_task.annotation_id,
        source_semantic_region_id=semantic_task.region_id,
        semantic_type=semantic_task.semantic_type,
        granite_task=semantic_task.granite_task,
        plan_id=_uuid_from_metadata(semantic_task.metadata.get("plan_id")),
        plan_task_id=_uuid_from_metadata(semantic_task.metadata.get("plan_task_id")),
        canonical_target_schema=_str_from_metadata(
            semantic_task.metadata.get("canonical_target_schema")
        ),
        compatibility_mode=_str_from_metadata(semantic_task.metadata.get("compatibility_mode")),
        contract_resolution_reason=_str_from_metadata(
            semantic_task.metadata.get("contract_resolution_reason")
        ),
        region_envelope_version=_str_from_metadata(
            semantic_task.metadata.get("region_envelope_version")
        ),
        metadata=dict(semantic_task.metadata),
    )


def _artifact_metadata(
    extraction: GatewayExtraction,
    run_scope: ExtractionRunScope,
) -> dict[str, Any]:
    metadata: dict[str, Any] = {
        "phase": "phase8_5" if run_scope.extraction_scope != "document" else "phase4",
        "schemaName": extraction.schema_name,
        "extractionScope": run_scope.extraction_scope,
    }
    if run_scope.semantic_annotation_id:
        metadata["semanticAnnotationId"] = str(run_scope.semantic_annotation_id)
    if run_scope.source_semantic_region_id:
        metadata["sourceSemanticRegionId"] = str(run_scope.source_semantic_region_id)
    if run_scope.semantic_type:
        metadata["semanticType"] = run_scope.semantic_type
    if run_scope.granite_task:
        metadata["graniteTask"] = run_scope.granite_task
    if extraction.model_output_schema_name:
        metadata["modelOutputSchemaName"] = extraction.model_output_schema_name
    if extraction.model_output_schema_version:
        metadata["modelOutputSchemaVersion"] = extraction.model_output_schema_version
    if run_scope.plan_id:
        metadata["planId"] = str(run_scope.plan_id)
    if run_scope.plan_task_id:
        metadata["planTaskId"] = str(run_scope.plan_task_id)
    if run_scope.canonical_target_schema:
        metadata["canonicalTargetSchema"] = run_scope.canonical_target_schema
    if run_scope.compatibility_mode:
        metadata["compatibilityMode"] = run_scope.compatibility_mode
    if run_scope.contract_resolution_reason:
        metadata["contractResolutionReason"] = run_scope.contract_resolution_reason
    if run_scope.region_envelope_version:
        metadata["regionEnvelopeVersion"] = run_scope.region_envelope_version
    return metadata


def _uuid_from_metadata(value: object) -> UUID | None:
    if value in (None, ""):
        return None
    return UUID(str(value))


def _str_from_metadata(value: object) -> str | None:
    if value in (None, ""):
        return None
    return str(value)


def _status_for_persisted_extraction(validation: ValidationReport) -> str:
    # Validation failures are document-quality/review outcomes, not worker failures.
    del validation
    return "completed"


def _review_status_for_extraction(
    *,
    extraction: GatewayExtraction,
    validation: ValidationReport,
    run_scope: ExtractionRunScope,
) -> str:
    if run_scope.extraction_scope == "semantic_region" and is_model_source_engine(
        extraction.route.source_engine
    ):
        return "needs_review"
    if run_scope.extraction_scope == "aggregate":
        return "needs_review"
    return "needs_review" if validation.needs_review else "auto_accepted"


def _overall_confidence(payload: dict[str, Any]) -> float | None:
    confidence = payload.get("confidence")
    if isinstance(confidence, dict):
        return float(confidence.get("overall") or 0)
    return None


def _remember_created(objects: list[StoredObject], stored: StoredObject) -> None:
    if stored.created:
        objects.append(stored)


def _cleanup_created(objects: list[StoredObject]) -> None:
    for stored in objects:
        cleanup_unreferenced_stored_object(stored)

from __future__ import annotations

import json
from typing import Any, cast
from uuid import UUID

from psycopg.types.json import Jsonb

from lib.db.connection import db_connection
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
from lib.extraction.models import (
    CandidateFact,
    ClassificationDecision,
    ExtractionSourceDocument,
    GatewayExtraction,
    LineItemCandidateFact,
    PersistedExtraction,
    ValidationReport,
)
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
    storage: ObjectStorage | None = None,
) -> PersistedExtraction:
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
    raw_object: StoredObject,
    normalized_object: StoredObject,
) -> PersistedExtraction:
    review_status = "needs_review" if validation.needs_review else "auto_accepted"
    status = _status_for_persisted_extraction(validation)
    with db_connection() as conn:
        with conn.cursor() as cur:
            _lock_document(cur, source.document_id)
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
                metadata={"phase": "phase4", "schemaName": extraction.schema_name},
                model_name=extraction.route.model_name,
                model_version=extraction.route.model_version,
            )
            _insert_artifact_asset(
                cur,
                document_id=source.document_id,
                stored=normalized_object,
                asset_role="normalized_extraction_json",
                mime_type="application/json",
                metadata={"phase": "phase4", "schemaName": extraction.schema_name},
                model_name=extraction.route.model_name,
                model_version=extraction.route.model_version,
            )
            _supersede_current_extractions(cur, source.document_id, extraction.schema_name)
            extraction_id = _insert_extraction_run_row(
                cur,
                extraction=extraction,
                source=source,
                validation=validation,
                status=status,
                review_status=review_status,
                raw_asset_id=raw_asset_id,
            )
            inserted_candidates = [
                insert_field_candidate(
                    cur,
                    source.document_id,
                    extraction_id,
                    extraction.route.source_engine,
                    candidate,
                )
                for candidate in field_candidates
            ]
            for line_item in line_item_candidates:
                insert_line_item_candidate(
                    cur,
                    source.document_id,
                    extraction_id,
                    extraction.route.source_engine,
                    line_item,
                )
            canonical_count = promote_candidates(
                cur,
                source=source,
                extraction_id=extraction_id,
                candidates=inserted_candidates,
                validation=validation,
                schema_name=extraction.schema_name,
            )
            review_task_count = create_review_tasks(
                cur,
                source=source,
                extraction_id=extraction_id,
                candidates=inserted_candidates,
                validation=validation,
                schema_name=extraction.schema_name,
            )
            update_document_rollups(cur, source.document_id)
            refresh_document_chunk_projection(cur, source.document_id)
        conn.commit()
    return PersistedExtraction(
        extraction_id=extraction_id,
        review_status=review_status,
        candidate_count=len(field_candidates) + len(line_item_candidates),
        canonical_count=canonical_count,
        review_task_count=review_task_count,
    )


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
        SET document_family = %s,
            document_subtype = %s,
            family_confidence = %s,
            sensitivity = CASE
              WHEN %s = 'medical_eob' THEN 'medical'::sensitivity_enum
              ELSE sensitivity
            END,
            review_status = CASE
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
) -> UUID:
    cur.execute(
        """
        INSERT INTO document_extractions
          (
            document_id, schema_name, schema_version, status, is_current,
            source_engine, model_name, model_version, prompt_version,
            raw_output_asset_id, normalized_json, validation_json, confidence,
            review_status
          )
        VALUES (%s, %s, %s, %s, true, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s, %s)
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


def _supersede_current_extractions(cur: Any, document_id: UUID, schema_name: str) -> None:
    cur.execute(
        """
        UPDATE document_extractions
        SET is_current = false,
            status = CASE WHEN status = 'completed' THEN 'superseded' ELSE status END,
            updated_at = now()
        WHERE document_id = %s
          AND schema_name = %s
          AND is_current
        """,
        (document_id, schema_name),
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


def _status_for_persisted_extraction(validation: ValidationReport) -> str:
    # Validation failures are document-quality/review outcomes, not worker failures.
    del validation
    return "completed"


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

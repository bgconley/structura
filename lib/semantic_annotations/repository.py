from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast
from uuid import UUID

from psycopg import Cursor
from psycopg.types.json import Jsonb

from lib.db.connection import db_connection
from lib.semantic_annotations.models import (
    DocumentSemanticManifest,
    PageSemanticAnnotation,
    SemanticExtractionTask,
    SemanticGroundingRef,
    SemanticRegionAnnotation,
)
from lib.semantic_annotations.policy import validate_manifest


class SemanticAnnotationRepositoryError(Exception):
    pass


@dataclass(frozen=True)
class PersistedSemanticManifest:
    annotation_id: UUID
    region_ids: tuple[UUID, ...]


def persist_semantic_manifest(manifest: DocumentSemanticManifest) -> UUID:
    return persist_semantic_manifest_record(manifest).annotation_id


def persist_semantic_manifest_record(
    manifest: DocumentSemanticManifest,
) -> PersistedSemanticManifest:
    with db_connection() as conn:
        with conn.cursor() as cur:
            persisted = persist_semantic_manifest_with_cursor(cur, manifest)
        conn.commit()
    return persisted


def persist_semantic_manifest_with_cursor(
    cur: Cursor[dict[str, Any]],
    manifest: DocumentSemanticManifest,
) -> PersistedSemanticManifest:
    _validate_document_refs(cur, manifest)
    cur.execute(
        """
        UPDATE document_semantic_annotations
        SET is_current = false,
            status = 'superseded',
            superseded_at = now()
        WHERE document_id = %s
          AND profile_name = %s
          AND quality_mode = %s
          AND is_current
        """,
        (manifest.document_id, manifest.profile_name, manifest.quality_mode),
    )
    cur.execute(
        """
        INSERT INTO document_semantic_annotations (
          document_id,
          household_id,
          quality_mode,
          status,
          is_current,
          profile_name,
          source_engine,
          model_name,
          model_version,
          prompt_version,
          docling_parse_asset_id,
          docling_parse_sha256,
          input_page_hashes_json,
          manifest_json,
          confidence_json,
          review_required,
          escalation_reason
        )
        VALUES (
          %s, %s, %s, 'succeeded', true, %s, %s, %s, %s, %s, %s, %s,
          %s, %s, %s, %s, %s
        )
        RETURNING id
        """,
        (
            manifest.document_id,
            manifest.household_id,
            manifest.quality_mode,
            manifest.profile_name,
            manifest.source_engine,
            manifest.model_name,
            manifest.model_version,
            manifest.prompt_version,
            manifest.docling_parse_asset_id,
            manifest.docling_parse_sha256,
            Jsonb(list(manifest.input_page_hashes)),
            Jsonb(dict(manifest.manifest)),
            Jsonb(dict(manifest.confidence)),
            manifest.review_required,
            manifest.escalation_reason,
        ),
    )
    annotation_row = cur.fetchone()
    if not annotation_row:
        raise SemanticAnnotationRepositoryError("Semantic annotation was not inserted.")
    annotation_id = cast(UUID, annotation_row["id"])
    page_annotation_ids = _insert_page_annotations(cur, annotation_id, manifest)
    grounding_page_ids = _grounding_page_ids(cur, manifest.document_id)
    region_ids = _insert_region_annotations(
        cur,
        annotation_id,
        manifest,
        page_annotation_ids,
        grounding_page_ids,
    )
    return PersistedSemanticManifest(
        annotation_id=annotation_id,
        region_ids=tuple(region_ids),
    )


def load_current_manifest(
    *,
    document_id: UUID,
    profile_name: str,
    quality_mode: str,
) -> DocumentSemanticManifest | None:
    with db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT *
                FROM document_semantic_annotations
                WHERE document_id = %s
                  AND profile_name = %s
                  AND quality_mode = %s
                  AND is_current
                """,
                (document_id, profile_name, quality_mode),
            )
            annotation = cur.fetchone()
            if not annotation:
                return None
            return _load_manifest_rows(cur, annotation)


def load_current_manifest_by_mode(
    *,
    document_id: UUID,
    quality_mode: str,
) -> DocumentSemanticManifest | None:
    with db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT *
                FROM document_semantic_annotations
                WHERE document_id = %s
                  AND quality_mode = %s
                  AND is_current
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (document_id, quality_mode),
            )
            annotation = cur.fetchone()
            if not annotation:
                return None
            return _load_manifest_rows(cur, annotation)


def load_semantic_extraction_task(region_id: UUID) -> SemanticExtractionTask:
    with db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                  r.id,
                  r.annotation_id,
                  r.document_id,
                  r.page_id,
                  r.element_id,
                  r.table_id,
                  r.semantic_type,
                  r.granite_task,
                  r.target_schema,
                  r.expected_fields_json,
                  r.grounding_kind,
                  r.reason,
                  r.confidence,
                  r.metadata_json
                FROM semantic_region_annotations r
                JOIN document_semantic_annotations a ON a.id = r.annotation_id
                WHERE r.id = %s
                  AND a.status = 'succeeded'
                  AND a.is_current
                """,
                (region_id,),
            )
            row = cur.fetchone()
    if not row:
        raise SemanticAnnotationRepositoryError("Semantic extraction task not found.")
    if not row["granite_task"] or row["granite_task"] == "ignore":
        raise SemanticAnnotationRepositoryError("Semantic region is not a Granite task.")
    return SemanticExtractionTask(
        region_id=row["id"],
        annotation_id=row["annotation_id"],
        document_id=row["document_id"],
        semantic_type=row["semantic_type"],
        granite_task=row["granite_task"],
        target_schema=row["target_schema"],
        expected_fields=tuple(row["expected_fields_json"] or ()),
        grounding=SemanticGroundingRef(
            kind=row["grounding_kind"],
            page_id=row["page_id"],
            element_id=row["element_id"],
            table_id=row["table_id"],
        ),
        reason=row["reason"],
        confidence=float(row["confidence"]) if row["confidence"] is not None else None,
        metadata=dict(row["metadata_json"] or {}),
    )


def _validate_document_refs(
    cur: Cursor[dict[str, Any]],
    manifest: DocumentSemanticManifest,
) -> None:
    cur.execute(
        """
        SELECT id, household_id
        FROM documents
        WHERE id = %s
          AND deleted_at IS NULL
        """,
        (manifest.document_id,),
    )
    document = cur.fetchone()
    if not document or document["household_id"] != manifest.household_id:
        raise SemanticAnnotationRepositoryError("Document semantic manifest ownership mismatch.")
    cur.execute("SELECT id FROM document_pages WHERE document_id = %s", (manifest.document_id,))
    page_ids = {row["id"] for row in cur.fetchall()}
    cur.execute(
        "SELECT id FROM document_elements WHERE document_id = %s",
        (manifest.document_id,),
    )
    element_ids = {row["id"] for row in cur.fetchall()}
    cur.execute(
        "SELECT id FROM document_tables WHERE document_id = %s",
        (manifest.document_id,),
    )
    table_ids = {row["id"] for row in cur.fetchall()}
    validate_manifest(
        manifest,
        valid_page_ids=page_ids,
        valid_element_ids=element_ids,
        valid_table_ids=table_ids,
    )


def _insert_page_annotations(
    cur: Cursor[dict[str, Any]],
    annotation_id: UUID,
    manifest: DocumentSemanticManifest,
) -> dict[UUID, UUID]:
    page_annotation_ids: dict[UUID, UUID] = {}
    for page in manifest.pages:
        cur.execute(
            """
            INSERT INTO page_semantic_annotations (
              annotation_id,
              document_id,
              page_id,
              page_number,
              page_role,
              document_type_hint,
              extraction_usefulness,
              is_boilerplate,
              has_structured_targets,
              ambiguous,
              escalation_required,
              reason,
              confidence,
              metadata_json
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (
                annotation_id,
                manifest.document_id,
                page.page_id,
                page.page_number,
                page.page_role,
                page.document_type_hint,
                page.extraction_usefulness,
                page.is_boilerplate,
                page.has_structured_targets,
                page.ambiguous,
                page.escalation_required,
                page.reason,
                page.confidence,
                Jsonb(dict(page.metadata)),
            ),
        )
        page_row = cur.fetchone()
        if not page_row:
            raise SemanticAnnotationRepositoryError("Page semantic annotation was not inserted.")
        page_annotation_ids[page.page_id] = cast(UUID, page_row["id"])
    return page_annotation_ids


def _insert_region_annotations(
    cur: Cursor[dict[str, Any]],
    annotation_id: UUID,
    manifest: DocumentSemanticManifest,
    page_annotation_ids: dict[UUID, UUID],
    grounding_page_ids: dict[UUID, UUID],
) -> list[UUID]:
    region_ids: list[UUID] = []
    for region in manifest.regions:
        page_id = _region_page_id(region.grounding, grounding_page_ids)
        cur.execute(
            """
            INSERT INTO semantic_region_annotations (
              annotation_id,
              page_annotation_id,
              document_id,
              page_id,
              element_id,
              table_id,
              semantic_type,
              priority,
              granite_task,
              target_schema,
              expected_fields_json,
              grounding_kind,
              unmatched_region,
              review_required,
              reason,
              confidence,
              metadata_json
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (
                annotation_id,
                page_annotation_ids.get(page_id) if page_id else None,
                manifest.document_id,
                page_id,
                region.grounding.element_id,
                region.grounding.table_id,
                region.semantic_type,
                region.priority,
                region.granite_task,
                region.target_schema,
                Jsonb(list(region.expected_fields)),
                region.grounding.kind,
                region.grounding.kind == "unmatched_region",
                region.review_required,
                region.reason,
                region.confidence,
                Jsonb(dict(region.metadata)),
            ),
        )
        region_row = cur.fetchone()
        if not region_row:
            raise SemanticAnnotationRepositoryError("Semantic region annotation was not inserted.")
        region_ids.append(cast(UUID, region_row["id"]))
    return region_ids


def _grounding_page_ids(
    cur: Cursor[dict[str, Any]],
    document_id: UUID,
) -> dict[UUID, UUID]:
    cur.execute(
        """
        SELECT id, page_id
        FROM document_elements
        WHERE document_id = %s
        """,
        (document_id,),
    )
    page_ids = {row["id"]: row["page_id"] for row in cur.fetchall()}
    cur.execute(
        """
        SELECT id, page_id
        FROM document_tables
        WHERE document_id = %s
        """,
        (document_id,),
    )
    page_ids.update({row["id"]: row["page_id"] for row in cur.fetchall()})
    return cast(dict[UUID, UUID], page_ids)


def _load_manifest_rows(
    cur: Cursor[dict[str, Any]],
    annotation: dict[str, Any],
) -> DocumentSemanticManifest:
    cur.execute(
        """
        SELECT *
        FROM page_semantic_annotations
        WHERE annotation_id = %s
        ORDER BY page_number
        """,
        (annotation["id"],),
    )
    pages = [_page_from_row(row) for row in cur.fetchall()]
    cur.execute(
        """
        SELECT *
        FROM semantic_region_annotations
        WHERE annotation_id = %s
        ORDER BY
          CASE priority
            WHEN 'critical' THEN 0
            WHEN 'high' THEN 1
            WHEN 'medium' THEN 2
            ELSE 3
          END,
          created_at
        """,
        (annotation["id"],),
    )
    regions = [_region_from_row(row) for row in cur.fetchall()]
    return DocumentSemanticManifest(
        document_id=annotation["document_id"],
        household_id=annotation["household_id"],
        quality_mode=annotation["quality_mode"],
        profile_name=annotation["profile_name"],
        source_engine=annotation["source_engine"],
        model_name=annotation["model_name"],
        model_version=annotation["model_version"],
        prompt_version=annotation["prompt_version"],
        pages=pages,
        regions=regions,
        confidence=dict(annotation["confidence_json"] or {}),
        manifest=dict(annotation["manifest_json"] or {}),
        review_required=bool(annotation["review_required"]),
        escalation_reason=annotation["escalation_reason"],
        input_page_hashes=tuple(annotation["input_page_hashes_json"] or ()),
        docling_parse_asset_id=annotation["docling_parse_asset_id"],
        docling_parse_sha256=annotation["docling_parse_sha256"],
    )


def _page_from_row(row: dict[str, Any]) -> PageSemanticAnnotation:
    return PageSemanticAnnotation(
        page_id=row["page_id"],
        page_number=int(row["page_number"]),
        page_role=row["page_role"],
        document_type_hint=row["document_type_hint"],
        extraction_usefulness=row["extraction_usefulness"],
        is_boilerplate=bool(row["is_boilerplate"]),
        has_structured_targets=bool(row["has_structured_targets"]),
        ambiguous=bool(row["ambiguous"]),
        escalation_required=bool(row["escalation_required"]),
        reason=row["reason"],
        confidence=float(row["confidence"]) if row["confidence"] is not None else None,
        metadata=dict(row["metadata_json"] or {}),
    )


def _region_from_row(row: dict[str, Any]) -> SemanticRegionAnnotation:
    return SemanticRegionAnnotation(
        semantic_type=row["semantic_type"],
        priority=row["priority"],
        granite_task=row["granite_task"],
        target_schema=row["target_schema"],
        expected_fields=tuple(row["expected_fields_json"] or ()),
        grounding=SemanticGroundingRef(
            kind=row["grounding_kind"],
            page_id=row["page_id"],
            element_id=row["element_id"],
            table_id=row["table_id"],
        ),
        review_required=bool(row["review_required"]),
        reason=row["reason"],
        confidence=float(row["confidence"]) if row["confidence"] is not None else None,
        metadata=dict(row["metadata_json"] or {}),
    )


def _region_page_id(
    grounding: SemanticGroundingRef,
    grounding_page_ids: dict[UUID, UUID],
) -> UUID | None:
    if grounding.page_id is not None:
        return grounding.page_id
    if grounding.element_id is not None:
        return grounding_page_ids.get(grounding.element_id)
    if grounding.table_id is not None:
        return grounding_page_ids.get(grounding.table_id)
    return None

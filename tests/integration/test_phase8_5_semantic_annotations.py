from __future__ import annotations

import os
import uuid

import pytest

pytest.importorskip("psycopg")

from lib.db.connection import db_connection
from lib.extraction.models import ExtractionSourceDocument, ParsedPageText
from lib.semantic_annotations.models import (
    DocumentSemanticManifest,
    PageSemanticAnnotation,
    SemanticAnnotationResult,
    SemanticGroundingRef,
    SemanticRegionAnnotation,
)
from lib.semantic_annotations.policy import SemanticAnnotationValidationError
from lib.semantic_annotations.repository import (
    load_current_manifest,
    load_semantic_extraction_task,
    persist_semantic_manifest,
)
from lib.semantic_annotations.service import SemanticAnnotationService


@pytest.mark.skipif(
    not os.environ.get("STRUCTURA_TEST_DATABASE_URL"),
    reason="Set STRUCTURA_TEST_DATABASE_URL to run live Phase 8.5 semantic annotation tests.",
)
def test_phase8_5_semantic_manifest_supersedes_current_and_persists_grounded_regions() -> None:
    document_id, household_id, page_id, element_id, table_id = _create_parsed_document()
    first = _manifest(
        document_id=document_id,
        household_id=household_id,
        page_id=page_id,
        element_id=element_id,
        table_id=table_id,
        model_version="v1",
    )
    second = _manifest(
        document_id=document_id,
        household_id=household_id,
        page_id=page_id,
        element_id=element_id,
        table_id=table_id,
        model_version="v2",
    )

    first_id = persist_semantic_manifest(first)
    second_id = persist_semantic_manifest(second)

    assert first_id != second_id
    current = load_current_manifest(
        document_id=document_id,
        profile_name="qwen3-vl-4b-semantic:v1",
        quality_mode="smart",
    )
    assert current is not None
    assert current.model_version == "v2"
    assert any(region.grounding.table_id == table_id for region in current.regions)

    with db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT status, is_current
                FROM document_semantic_annotations
                WHERE id = %s
                """,
                (first_id,),
            )
            row = cur.fetchone()
            assert row["status"] == "superseded"
            assert row["is_current"] is False


@pytest.mark.skipif(
    not os.environ.get("STRUCTURA_TEST_DATABASE_URL"),
    reason="Set STRUCTURA_TEST_DATABASE_URL to run live Phase 8.5 semantic annotation tests.",
)
def test_phase8_5_semantic_extraction_task_loads_superseded_annotation_region() -> None:
    document_id, household_id, page_id, element_id, table_id = _create_parsed_document()
    first = _manifest(
        document_id=document_id,
        household_id=household_id,
        page_id=page_id,
        element_id=element_id,
        table_id=table_id,
        model_version="v1",
    )
    second = _manifest(
        document_id=document_id,
        household_id=household_id,
        page_id=page_id,
        element_id=element_id,
        table_id=table_id,
        model_version="v2",
    )

    first_id = persist_semantic_manifest(first)
    persist_semantic_manifest(second)
    with db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id
                FROM semantic_region_annotations
                WHERE annotation_id = %s
                  AND granite_task = 'tables_json'
                ORDER BY created_at ASC
                LIMIT 1
                """,
                (first_id,),
            )
            first_region_id = cur.fetchone()["id"]

    task = load_semantic_extraction_task(first_region_id)

    assert task.annotation_id == first_id
    assert task.region_id == first_region_id
    assert task.target_schema == "medical_eob"


@pytest.mark.skipif(
    not os.environ.get("STRUCTURA_TEST_DATABASE_URL"),
    reason="Set STRUCTURA_TEST_DATABASE_URL to run live Phase 8.5 semantic annotation tests.",
)
def test_phase8_5_semantic_manifest_rolls_back_if_targeted_job_payload_is_invalid() -> None:
    document_id, household_id, page_id, element_id, table_id = _create_parsed_document()
    manifest = _manifest(
        document_id=document_id,
        household_id=household_id,
        page_id=page_id,
        element_id=element_id,
        table_id=table_id,
        model_version="v1",
        first_region_target_schema="unsupported_schema",
    )
    source = ExtractionSourceDocument(
        document_id=document_id,
        household_id=household_id,
        title="Phase 8.5 invalid target",
        original_filename="invalid.pdf",
        mime_type="application/pdf",
        family="medical_eob",
        subtype=None,
        sensitivity="standard",
        document_date=None,
        counterparty_display=None,
        primary_folder_id=None,
        metadata={},
        pages=[
            ParsedPageText(
                page_id=page_id,
                page_number=1,
                text="Explanation of benefits line items",
                image_bytes=b"image",
                image_mime_type="image/png",
                image_sha256="a" * 64,
            )
        ],
        elements=[],
        tables=[],
    )

    with pytest.raises(SemanticAnnotationValidationError):
        SemanticAnnotationService(
            source_loader=lambda _document_id: source,
            gateway=StaticSemanticGateway(manifest),
        ).annotate_document(document_id)

    assert (
        load_current_manifest(
            document_id=document_id,
            profile_name="qwen3-vl-4b-semantic:v1",
            quality_mode="smart",
        )
        is None
    )
    with db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT count(*) AS total
                FROM pipeline_jobs
                WHERE document_id = %s
                  AND job_type = 'extract'
                """,
                (document_id,),
            )
            assert cur.fetchone()["total"] == 0


def _manifest(
    *,
    document_id: uuid.UUID,
    household_id: uuid.UUID,
    page_id: uuid.UUID,
    element_id: uuid.UUID,
    table_id: uuid.UUID,
    model_version: str,
    first_region_target_schema: str = "medical_eob",
) -> DocumentSemanticManifest:
    return DocumentSemanticManifest(
        document_id=document_id,
        household_id=household_id,
        quality_mode="smart",
        profile_name="qwen3-vl-4b-semantic:v1",
        source_engine="qwen3_vl_4b",
        model_name="Qwen/Qwen3-VL-4B-Instruct",
        model_version=model_version,
        prompt_version="phase8_5-semantic-smart-v3",
        pages=[
            PageSemanticAnnotation(
                page_id=page_id,
                page_number=1,
                page_role="claim_summary",
                document_type_hint="medical_eob",
                extraction_usefulness="high",
                has_structured_targets=True,
                confidence=0.91,
            )
        ],
        regions=[
            SemanticRegionAnnotation(
                semantic_type="covered_services_line_item_table",
                priority="high",
                granite_task="tables_json",
                target_schema=first_region_target_schema,
                expected_fields=("service_date", "allowed_amount"),
                grounding=SemanticGroundingRef(kind="table", table_id=table_id),
                reason="Table includes EOB line items.",
                confidence=0.9,
            ),
            SemanticRegionAnnotation(
                semantic_type="billing_summary",
                priority="high",
                granite_task="kvp",
                target_schema="medical_eob",
                expected_fields=("patient_responsibility",),
                grounding=SemanticGroundingRef(kind="element", element_id=element_id),
                reason="Element summarizes patient responsibility.",
                confidence=0.82,
            ),
        ],
        confidence={"overall": 0.86},
        manifest={
            "schema_name": "semantic_annotation_manifest",
            "schema_version": "v1",
            "document_type": "medical_eob",
            "pages": [],
            "regions": [],
            "quality_flags": {"needs_high_quality_pass": False, "visual_degradation": False},
            "confidence": {"overall": 0.86},
        },
        input_page_hashes=("a" * 64,),
    )


class StaticSemanticGateway:
    def __init__(self, manifest: DocumentSemanticManifest) -> None:
        self.manifest = manifest

    def annotate(
        self,
        source: ExtractionSourceDocument,
        *,
        quality_mode: str,
    ) -> SemanticAnnotationResult:
        del source, quality_mode
        return SemanticAnnotationResult(manifest=self.manifest)


def _create_parsed_document() -> tuple[uuid.UUID, uuid.UUID, uuid.UUID, uuid.UUID, uuid.UUID]:
    unique = uuid.uuid4().hex
    with db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO households (name, slug) VALUES (%s, %s) RETURNING id",
                (f"Phase 8.5 {unique}", f"phase-8-5-{unique}"),
            )
            household_id = cur.fetchone()["id"]
            cur.execute(
                """
                INSERT INTO documents (
                  title,
                  ingestion_source,
                  household_id,
                  document_family
                )
                VALUES (%s, 'web_upload', %s, 'medical_eob')
                RETURNING id
                """,
                (f"Phase 8.5 semantic {unique}", household_id),
            )
            document_id = cur.fetchone()["id"]
            cur.execute(
                """
                INSERT INTO document_pages (
                  document_id,
                  page_number,
                  text_content,
                  has_text_layer
                )
                VALUES (%s, 1, 'Explanation of benefits line items', true)
                RETURNING id
                """,
                (document_id,),
            )
            page_id = cur.fetchone()["id"]
            cur.execute(
                """
                INSERT INTO document_elements (
                  document_id,
                  page_id,
                  element_type,
                  ordinal,
                  text_content,
                  bbox_json
                )
                VALUES (%s, %s, 'paragraph', 1, 'patient responsibility summary', '{"l":1}')
                RETURNING id
                """,
                (document_id, page_id),
            )
            element_id = cur.fetchone()["id"]
            cur.execute(
                """
                INSERT INTO document_tables (
                  document_id,
                  page_id,
                  element_id,
                  table_index,
                  table_markdown
                )
                VALUES (%s, %s, %s, 1, '| service | allowed |')
                RETURNING id
                """,
                (document_id, page_id, element_id),
            )
            table_id = cur.fetchone()["id"]
        conn.commit()
    return document_id, household_id, page_id, element_id, table_id

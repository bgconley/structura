from __future__ import annotations

import os
import uuid

import pytest

pytest.importorskip("psycopg")

from lib.db.connection import db_connection
from lib.semantic_annotations.models import (
    DocumentSemanticManifest,
    PageSemanticAnnotation,
    SemanticGroundingRef,
    SemanticRegionAnnotation,
)
from lib.semantic_annotations.repository import (
    load_current_manifest,
    persist_semantic_manifest,
)


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
        profile_name="qwen3-vl-2b-semantic:v1",
        quality_mode="smart",
    )
    assert current is not None
    assert current.model_version == "v2"
    assert current.regions[0].grounding.table_id == table_id

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


def _manifest(
    *,
    document_id: uuid.UUID,
    household_id: uuid.UUID,
    page_id: uuid.UUID,
    element_id: uuid.UUID,
    table_id: uuid.UUID,
    model_version: str,
) -> DocumentSemanticManifest:
    return DocumentSemanticManifest(
        document_id=document_id,
        household_id=household_id,
        quality_mode="smart",
        profile_name="qwen3-vl-2b-semantic:v1",
        source_engine="qwen3_vl_2b",
        model_name="Qwen/Qwen3-VL-2B-Instruct",
        model_version=model_version,
        prompt_version="phase8_5-semantic-smart-v1",
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
                target_schema="medical_eob",
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
        manifest={"document_type": "medical_eob"},
        input_page_hashes=("a" * 64,),
    )


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

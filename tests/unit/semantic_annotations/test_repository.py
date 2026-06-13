from __future__ import annotations

from uuid import uuid4

from lib.semantic_annotations.repository import (
    _supersede_semantic_region_outputs_for_annotations,
)


def test_supersede_semantic_region_outputs_for_superseded_annotations() -> None:
    cursor = RecordingCursor()
    document_id = uuid4()
    first_annotation_id = uuid4()
    second_annotation_id = uuid4()

    _supersede_semantic_region_outputs_for_annotations(
        cursor,
        document_id,
        [first_annotation_id, second_annotation_id],
    )

    assert len(cursor.calls) == 2
    extraction_sql, extraction_params = cursor.calls[0]
    assert "UPDATE document_extractions" in extraction_sql
    assert "extraction_scope = 'semantic_region'" in extraction_sql
    assert "semantic_annotation_id = ANY(%s::uuid[])" in extraction_sql
    assert extraction_params == (
        document_id,
        [first_annotation_id, second_annotation_id],
    )

    asset_sql, asset_params = cursor.calls[1]
    assert "UPDATE document_assets" in asset_sql
    assert "metadata_json ->> 'extractionScope' = 'semantic_region'" in asset_sql
    assert "metadata_json ->> 'semanticAnnotationId' = ANY(%s::text[])" in asset_sql
    assert asset_params == (
        document_id,
        [str(first_annotation_id), str(second_annotation_id)],
    )


class RecordingCursor:
    def __init__(self) -> None:
        self.calls: list[tuple[str, object]] = []

    def execute(self, sql: str, params: object = None) -> None:
        self.calls.append((sql, params))

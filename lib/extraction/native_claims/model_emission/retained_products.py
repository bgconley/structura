"""Revalidate cross-member accounting against retained structure, without raw decoding."""

from lib.document_parsing.page_understanding.model import PageUnderstanding
from lib.document_parsing.structure import SourceBox, StructurePage
from lib.extraction.native_claims.errors import NativeClaimConflict
from lib.extraction.native_claims.model_emission.models import NativeModelClaim
from lib.extraction.native_claims.model_emission.page_models import NativeModelPageRecord


def validate_retained_products(
    page: StructurePage, record: NativeModelPageRecord, claims: tuple[NativeModelClaim, ...]
) -> None:
    if page.source is None:
        raise NativeClaimConflict("Retained model page has no source raster.")
    width, height = page.source.pixel_width, page.source.pixel_height

    def box(value: SourceBox):
        # A coordinate view for validation only; persisted anchors keep their exact
        # source-pixel boxes. No model payload or new source evidence is produced.
        return {
            "left": value.left * 1000 / width,
            "right": value.right * 1000 / width,
            "top": value.top * 1000 / height,
            "bottom": value.bottom * 1000 / height,
        }

    indices = {element.id: index for index, element in enumerate(page.elements)}
    tables = {table.element_id: table for table in page.tables}
    elements = []
    for element in page.elements:
        table = tables.get(element.id)
        elements.append(
            {
                "kind": element.kind,
                "text": element.text,
                "bbox": box(element.bbox),
                "parent_index": indices[element.parent_id] if element.parent_id else None,
                "table": None
                if table is None
                else {
                    "row_count": table.row_count,
                    "column_count": table.column_count,
                    "continuation_key": table.continuation_key,
                    "cells": [
                        {
                            "row": cell.row,
                            "column": cell.column,
                            "row_span": cell.row_span,
                            "column_span": cell.column_span,
                            "text": cell.text,
                            "is_header": cell.is_header,
                            "bbox": box(cell.bbox),
                        }
                        for cell in table.cells
                    ],
                },
            }
        )
    PageUnderstanding.model_validate(
        {
            "schema_version": "structura.page_understanding.v2",
            "page_number": page.page_number,
            "state": page.state,
            "diagnostics": page.diagnostics,
            "elements": elements,
            "classification": record.classification_json,
            "extraction": {**record.coverage_json, "claims": [c.raw_member_json for c in claims]},
        }
    )

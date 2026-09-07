"""Assign generation-owned IDs and validate structure against real source pixels."""

from __future__ import annotations

from uuid import UUID, uuid5

from lib.document_parsing.model_output import ModelBox, PageParseOutput
from lib.document_parsing.structure import (
    SourceBox,
    SourceRender,
    StructureCell,
    StructureElement,
    StructurePage,
    StructureTable,
)


def normalize_page(
    output: PageParseOutput, source: SourceRender, generation_id: UUID
) -> StructurePage:
    if output.page_number != source.page_number:
        raise ValueError("Model page reference does not match the actual source input.")
    prefix = f"page:{source.page_number}"
    elements = []
    tables = []
    for index, element in enumerate(output.elements):
        element_id = uuid5(generation_id, f"{prefix}:element:{index}")
        if element.parent_index is not None and element.parent_index >= index:
            raise ValueError("Model parent must reference an earlier page element.")
        elements.append(
            StructureElement(
                id=element_id,
                ordinal=index + 1,
                parent_id=None
                if element.parent_index is None
                else uuid5(generation_id, f"{prefix}:element:{element.parent_index}"),
                kind=element.kind,
                text=element.text,
                text_origin="model_transcription",
                bbox=_source_box(element.bbox, source),
            )
        )
        if (element.kind == "table") != (element.table is not None):
            raise ValueError("Model table data and element type disagree.")
        if element.table is not None:
            table = element.table
            tables.append(
                StructureTable(
                    id=uuid5(element_id, "table"),
                    element_id=element_id,
                    row_count=table.row_count,
                    column_count=table.column_count,
                    continuation_key=table.continuation_key,
                    cells=tuple(
                        StructureCell(
                            id=uuid5(element_id, f"cell:{cell.row}:{cell.column}"),
                            row=cell.row,
                            column=cell.column,
                            row_span=cell.row_span,
                            column_span=cell.column_span,
                            text=cell.text,
                            text_origin="model_transcription",
                            bbox=_source_box(cell.bbox, source),
                            is_header=cell.is_header,
                        )
                        for cell in table.cells
                    ),
                )
            )
    return StructurePage(
        id=uuid5(generation_id, prefix),
        page_number=source.page_number,
        source=source,
        state=output.state,
        diagnostics=output.diagnostics,
        elements=tuple(elements),
        tables=tuple(tables),
    )


def _source_box(box: ModelBox, source: SourceRender) -> SourceBox:
    # The model sees the full raster. Its 0..1000 coordinates map directly to
    # that exact image; this proves address validity, not pixel/text support.
    return SourceBox(
        left=box.left * source.pixel_width / 1000,
        top=box.top * source.pixel_height / 1000,
        right=box.right * source.pixel_width / 1000,
        bottom=box.bottom * source.pixel_height / 1000,
    )

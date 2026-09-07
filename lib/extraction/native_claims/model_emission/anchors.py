"""Map same-response locators to exact retained generation-owned source structure."""

from lib.document_parsing.page_understanding.locators import PhysicalRow, SourceQuote, TableRow
from lib.document_parsing.structure import StructurePage
from lib.extraction.native_claims.errors import NativeClaimError
from lib.extraction.native_claims.model_emission.models import ModelClaimAnchor, ModelClaimRow


def bind_quote(page: StructurePage, quote: SourceQuote, generation_id) -> ModelClaimAnchor:
    locator = quote.locator
    if page.source is None or locator.element_index >= len(page.elements):
        raise NativeClaimError("Native model claim source is unavailable.")
    element = page.elements[locator.element_index]
    table = cell = None
    text, box = element.text, element.bbox
    if locator.cell_row is not None:
        table = next((t for t in page.tables if t.element_id == element.id), None)
        cell = (
            next(
                (
                    c
                    for c in table.cells
                    if c.row == locator.cell_row and c.column == locator.cell_column
                ),
                None,
            )
            if table
            else None
        )
        if table is None or cell is None:
            raise NativeClaimError("Native model claim cell is unavailable.")
        text, box = cell.text, cell.bbox
    if (
        text[locator.text_start : locator.text_end] != quote.quote
        or locator.text_end > len(text)
        or (cell.text_origin if cell else element.text_origin) != "model_transcription"
    ):
        raise NativeClaimError("Native model claim quote differs from retained transcription.")
    return ModelClaimAnchor(
        parse_generation_id=generation_id,
        page_number=page.page_number,
        page_id=page.id,
        source_page_image_sha256=page.source.image_sha256,
        element_id=element.id,
        table_id=table.id if table else None,
        cell_id=cell.id if cell else None,
        cell_row=locator.cell_row,
        cell_column=locator.cell_column,
        text_start=locator.text_start,
        text_end=locator.text_end,
        source_text=quote.quote,
        bbox=box,
    )


def bind_row(page: StructurePage, row: PhysicalRow | None) -> ModelClaimRow | None:
    if row is None:
        return None
    index = row.element_index if isinstance(row, TableRow) else row.container_index
    if index >= len(page.elements):
        raise NativeClaimError("Native model physical row is unavailable.")
    element = page.elements[index]
    table = next((t for t in page.tables if t.element_id == element.id), None)
    if isinstance(row, TableRow):
        if table is None or row.row >= table.row_count:
            raise NativeClaimError("Native model physical table row is unavailable.")
        return ModelClaimRow(
            kind="table_row", element_id=element.id, table_id=table.id, row_index=row.row
        )
    return ModelClaimRow(
        kind="structural_row", element_id=element.id, table_id=None, row_index=None
    )

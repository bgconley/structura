"""Page-local source occurrences and physical row grouping; no model UUIDs."""

from typing import Annotated, Literal

from pydantic import Field, model_validator

from lib.document_parsing.page_understanding.base import UnderstandingModel
from lib.document_parsing.page_understanding.structure import UnderstandingElement


class TextLocator(UnderstandingModel):
    element_index: int = Field(ge=0, le=399, strict=True)
    cell_row: int | None = Field(ge=0, le=4999, strict=True)
    cell_column: int | None = Field(ge=0, le=99, strict=True)
    text_start: int = Field(ge=0, strict=True)
    text_end: int = Field(gt=0, strict=True)

    @model_validator(mode="after")
    def complete_span(self) -> "TextLocator":
        if (self.cell_row is None) != (
            self.cell_column is None
        ) or self.text_end <= self.text_start:
            raise ValueError("Source locator requires a complete positive text span.")
        return self


class SourceQuote(UnderstandingModel):
    locator: TextLocator
    quote: str = Field(min_length=1, max_length=4096)


class SupportingQuote(SourceQuote):
    role: Literal["label", "currency", "date_context", "value_context", "continuation"]


class TableRow(UnderstandingModel):
    kind: Literal["table_row"]
    element_index: int = Field(ge=0, le=399, strict=True)
    row: int = Field(ge=0, le=4999, strict=True)


class StructuralRow(UnderstandingModel):
    kind: Literal["structural_row"]
    container_index: int = Field(ge=0, le=399, strict=True)


PhysicalRow = Annotated[TableRow | StructuralRow, Field(discriminator="kind")]


def source_text(elements: tuple[UnderstandingElement, ...], locator: TextLocator) -> str:
    if locator.element_index >= len(elements):
        raise ValueError("Source element is unavailable.")
    element = elements[locator.element_index]
    text = element.text
    if locator.cell_row is not None:
        cell = (
            next(
                (
                    c
                    for c in element.table.cells
                    if c.row == locator.cell_row and c.column == locator.cell_column
                ),
                None,
            )
            if element.table
            else None
        )
        if cell is None:
            raise ValueError("Source cell does not start at the referenced coordinate.")
        text = cell.text
    if locator.text_end > len(text):
        raise ValueError("Source span exceeds the recorded text.")
    return text[locator.text_start : locator.text_end]


def validate_quote(elements: tuple[UnderstandingElement, ...], quote: SourceQuote) -> None:
    if not quote.quote.strip() or source_text(elements, quote.locator) != quote.quote:
        raise ValueError("Source quote does not equal its exact recorded occurrence.")


def row_key(row: PhysicalRow) -> tuple[str, int, int | None]:
    """Page-local identity only; persistence must include exact generation and page."""
    if isinstance(row, TableRow):
        return (row.kind, row.element_index, row.row)
    return (row.kind, row.container_index, None)


def validate_row(elements: tuple[UnderstandingElement, ...], row: PhysicalRow) -> None:
    index = row.element_index if isinstance(row, TableRow) else row.container_index
    if index >= len(elements):
        raise ValueError("Physical row source is unavailable.")
    element = elements[index]
    if isinstance(row, TableRow):
        if element.table is None or row.row >= element.table.row_count:
            raise ValueError("Physical table row is unavailable.")
    elif element.kind not in {"list_item", "form_field", "other"} or element.table is not None:
        raise ValueError("Physical group requires a real structural row container.")


def validate_row_member(
    elements: tuple[UnderstandingElement, ...], row: PhysicalRow, locator: TextLocator
) -> None:
    validate_row(elements, row)
    if isinstance(row, TableRow):
        if locator.element_index != row.element_index or locator.cell_row != row.row:
            raise ValueError("Claim value does not belong to its physical table row.")
        table = elements[row.element_index].table
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
        if cell is None or cell.row_span != 1:
            raise ValueError("A merged multi-row value cannot identify one independent line.")
        return
    index = locator.element_index
    while index != row.container_index:
        parent = elements[index].parent_index
        if parent is None:
            raise ValueError("Claim value is outside its structural row hierarchy.")
        index = parent
    if locator.cell_row is not None:
        raise ValueError("Table cells require their own physical table row identity.")


def validate_disjoint_rows(
    elements: tuple[UnderstandingElement, ...], rows: tuple[PhysicalRow, ...]
) -> None:
    """A structural section and its nested rows cannot both become physical lines."""
    containers = {row.container_index for row in rows if isinstance(row, StructuralRow)}
    for row in rows:
        index = row.element_index if isinstance(row, TableRow) else row.container_index
        parent = elements[index].parent_index
        while parent is not None:
            if parent in containers:
                raise ValueError(
                    "Physical row containers cannot overlap through structural ancestry."
                )
            parent = elements[parent].parent_index

"""Separate v2 structural DTOs retain every v1 field without modifying v1 bytes."""

from typing import Literal

from pydantic import Field, model_validator

from lib.document_parsing.page_understanding.base import UnderstandingModel


class UnderstandingBox(UnderstandingModel):
    left: float = Field(ge=0, le=1000, strict=True)
    top: float = Field(ge=0, le=1000, strict=True)
    right: float = Field(gt=0, le=1000, strict=True)
    bottom: float = Field(gt=0, le=1000, strict=True)

    @model_validator(mode="after")
    def positive_area(self) -> "UnderstandingBox":
        if self.right <= self.left or self.bottom <= self.top:
            raise ValueError("Structure box must have positive area.")
        return self


class UnderstandingCell(UnderstandingModel):
    row: int = Field(ge=0, le=5000, strict=True)
    column: int = Field(ge=0, le=100, strict=True)
    row_span: int = Field(ge=1, le=5000, strict=True)
    column_span: int = Field(ge=1, le=100, strict=True)
    text: str = Field(max_length=20000)
    bbox: UnderstandingBox
    is_header: bool = Field(strict=True)


class UnderstandingTable(UnderstandingModel):
    row_count: int = Field(ge=1, le=5000, strict=True)
    column_count: int = Field(ge=1, le=100, strict=True)
    cells: tuple[UnderstandingCell, ...] = Field(max_length=3000)
    continuation_key: str | None = Field(max_length=200)

    @model_validator(mode="after")
    def exact_grid(self) -> "UnderstandingTable":
        if self.row_count * self.column_count > 50000:
            raise ValueError("Table grid exceeds the supported bound.")
        occupied = set()
        for cell in self.cells:
            if (
                cell.row + cell.row_span > self.row_count
                or cell.column + cell.column_span > self.column_count
            ):
                raise ValueError("Cell exceeds the table grid.")
            for row in range(cell.row, cell.row + cell.row_span):
                for column in range(cell.column, cell.column + cell.column_span):
                    if (row, column) in occupied:
                        raise ValueError("Table cells overlap.")
                    occupied.add((row, column))
        return self


class UnderstandingElement(UnderstandingModel):
    kind: Literal[
        "paragraph",
        "heading",
        "header",
        "footer",
        "list_item",
        "caption",
        "table",
        "figure",
        "form_field",
        "other",
    ]
    text: str = Field(max_length=100000)
    bbox: UnderstandingBox
    parent_index: int | None = Field(ge=0, strict=True)
    table: UnderstandingTable | None

    @model_validator(mode="after")
    def table_matches_kind(self) -> "UnderstandingElement":
        if (self.kind == "table") != (self.table is not None):
            raise ValueError("Table content and element kind disagree.")
        return self

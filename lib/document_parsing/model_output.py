"""Small model-facing page schema, independent of storage IDs and trust decisions."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from lib.document_parsing.structure import StructureModel


class ModelBox(StructureModel):
    left: float = Field(ge=0, le=1000)
    top: float = Field(ge=0, le=1000)
    right: float = Field(gt=0, le=1000)
    bottom: float = Field(gt=0, le=1000)


class ModelCell(StructureModel):
    row: int = Field(ge=0, le=5000)
    column: int = Field(ge=0, le=100)
    row_span: int = Field(ge=1, le=5000)
    column_span: int = Field(ge=1, le=100)
    text: str = Field(max_length=20000)
    bbox: ModelBox
    is_header: bool


class ModelTable(StructureModel):
    row_count: int = Field(ge=1, le=5000)
    column_count: int = Field(ge=1, le=100)
    cells: tuple[ModelCell, ...] = Field(max_length=3000)
    continuation_key: str | None = Field(max_length=200)


class ModelElement(StructureModel):
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
    bbox: ModelBox
    # Zero-based index of an earlier element, never a client/model-assigned UUID.
    parent_index: int | None = Field(ge=0)
    table: ModelTable | None


class PageParseOutput(StructureModel):
    page_number: int = Field(ge=1)
    state: Literal["processed", "partial", "insufficient_signal"]
    diagnostics: tuple[Literal["content_omitted", "unreadable_region"], ...]
    elements: tuple[ModelElement, ...] = Field(max_length=400)

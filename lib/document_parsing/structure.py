"""Versioned immutable structure; derived transcription never certifies source truth."""

from __future__ import annotations

from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

Sha256 = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
PositiveInt = Annotated[int, Field(gt=0)]
TextOrigin = Literal["pdf_native", "model_transcription", "legacy_docling"]
SourceMediaType = Literal["application/pdf", "image/png", "image/jpeg", "image/tiff", "image/webp"]


class StructureModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)


class SourcePage(StructureModel):
    page_number: PositiveInt
    width: float = Field(gt=0)
    height: float = Field(gt=0)
    unit: Literal["pdf_canvas", "pixels"]
    rotation_degrees: Literal[0, 90, 180, 270] = 0


class SourceInventory(StructureModel):
    original_asset_id: UUID
    original_sha256: Sha256
    mime_type: SourceMediaType
    byte_size: PositiveInt
    pages: tuple[SourcePage, ...] = Field(min_length=1, max_length=500)

    @model_validator(mode="after")
    def complete_page_inventory(self) -> SourceInventory:
        if tuple(page.page_number for page in self.pages) != tuple(range(1, len(self.pages) + 1)):
            raise ValueError("Source pages must be complete and ordered.")
        return self


class SourceRender(StructureModel):
    page_number: PositiveInt
    image_sha256: Sha256
    pixel_width: PositiveInt
    pixel_height: PositiveInt
    renderer: str = Field(min_length=1)
    renderer_version: str = Field(min_length=1)
    # Describes the displayed source raster, including original intrinsic rotation.
    coordinate_space: Literal["rendered_source_pixels"] = "rendered_source_pixels"
    native_text: str | None = None
    native_text_origin: Literal["pdf_native"] | None = None

    @model_validator(mode="after")
    def native_origin_is_explicit(self) -> SourceRender:
        if (self.native_text is None) != (self.native_text_origin is None):
            raise ValueError("Native text and its source attribution must be supplied together.")
        return self


class SourceBox(StructureModel):
    left: float = Field(ge=0)
    top: float = Field(ge=0)
    right: float = Field(gt=0)
    bottom: float = Field(gt=0)

    @model_validator(mode="after")
    def positive_area(self) -> SourceBox:
        if self.right <= self.left or self.bottom <= self.top:
            raise ValueError("Source boxes must have positive area.")
        return self


class StructureElement(StructureModel):
    id: UUID
    ordinal: PositiveInt
    parent_id: UUID | None = None
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
    text: str
    text_origin: TextOrigin
    bbox: SourceBox


class StructureCell(StructureModel):
    id: UUID
    row: int = Field(ge=0)
    column: int = Field(ge=0)
    row_span: PositiveInt = 1
    column_span: PositiveInt = 1
    text: str
    text_origin: TextOrigin
    bbox: SourceBox
    is_header: bool = False


class StructureTable(StructureModel):
    id: UUID
    element_id: UUID
    row_count: PositiveInt
    column_count: PositiveInt
    cells: tuple[StructureCell, ...]
    continuation_key: str | None = None

    @model_validator(mode="after")
    def cell_ownership(self) -> StructureTable:
        occupied: set[tuple[int, int]] = set()
        if self.row_count * self.column_count > 50000:
            raise ValueError("Table grid exceeds the supported limit.")
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


class StructurePage(StructureModel):
    id: UUID
    page_number: PositiveInt
    source: SourceRender | None
    state: Literal[
        "processed", "partial", "deferred", "insufficient_signal", "unsupported", "failed"
    ]
    diagnostics: tuple[
        Literal[
            "content_omitted",
            "unreadable_region",
            "resource_limit",
            "invalid_output",
            "render_failed",
        ],
        ...,
    ] = ()
    elements: tuple[StructureElement, ...] = ()
    tables: tuple[StructureTable, ...] = ()

    @model_validator(mode="after")
    def validate_page_structure(self) -> StructurePage:
        if self.source is None:
            if (
                self.elements
                or self.tables
                or self.state not in {"deferred", "unsupported", "failed"}
            ):
                raise ValueError("Parsed content requires a real source raster.")
            return self
        if self.source.page_number != self.page_number:
            raise ValueError("Source raster belongs to another page.")
        element_ids = {element.id for element in self.elements}
        if len(element_ids) != len(self.elements):
            raise ValueError("Element IDs must be unique.")
        if tuple(element.ordinal for element in self.elements) != tuple(
            range(1, len(self.elements) + 1)
        ):
            raise ValueError("Elements must have complete ordered ordinals.")
        preceding: set[UUID] = set()
        for element in self.elements:
            if element.parent_id is not None and element.parent_id not in preceding:
                raise ValueError("Parent must be an earlier element on the same page.")
            preceding.add(element.id)
        cells = tuple(cell for table in self.tables for cell in table.cells)
        located_items: tuple[StructureElement | StructureCell, ...] = (*self.elements, *cells)
        for item in located_items:
            if (
                item.bbox.right > self.source.pixel_width
                or item.bbox.bottom > self.source.pixel_height
            ):
                raise ValueError("Locator exceeds its source raster.")
        table_elements = {element.id for element in self.elements if element.kind == "table"}
        if {table.element_id for table in self.tables} != table_elements or len(self.tables) != len(
            table_elements
        ):
            raise ValueError("Each table must belong to one table element on its page.")
        if self.state in {"deferred", "unsupported", "failed"} and (self.elements or self.tables):
            raise ValueError("Unprocessed pages must not claim derived content.")
        return self


class ParseInvocation(StructureModel):
    request_id: UUID
    page_numbers: tuple[PositiveInt, ...]
    profile: str
    served_model: str
    source_engine: str
    prompt_version: str
    output_schema_version: str
    raw_output_sha256: Sha256
    finish_reason: str | None
    latency_ms: int = Field(ge=0)


class StructureChunk(StructureModel):
    id: UUID
    page_number: PositiveInt
    element_ids: tuple[UUID, ...] = Field(min_length=1)
    text: str = Field(min_length=1)
    text_origins: tuple[TextOrigin, ...] = Field(min_length=1)


class DocumentStructure(StructureModel):
    schema_version: Literal["structura.document_structure.v1"] = "structura.document_structure.v1"
    parse_generation_id: UUID
    processing_run_id: UUID
    source: SourceInventory
    pages: tuple[StructurePage, ...]
    invocations: tuple[ParseInvocation, ...]
    chunks: tuple[StructureChunk, ...] = ()

    @model_validator(mode="after")
    def validate_generation(self) -> DocumentStructure:
        if tuple(page.page_number for page in self.pages) != tuple(
            page.page_number for page in self.source.pages
        ):
            raise ValueError("Every source page must have an explicit processing state.")
        ids = [page.id for page in self.pages]
        ids += [element.id for page in self.pages for element in page.elements]
        ids += [table.id for page in self.pages for table in page.tables]
        ids += [cell.id for page in self.pages for table in page.tables for cell in table.cells]
        ids += [chunk.id for chunk in self.chunks]
        if len(ids) != len(set(ids)):
            raise ValueError("Structure IDs must be unique within a generation.")
        for chunk in self.chunks:
            page = next(
                (page for page in self.pages if page.page_number == chunk.page_number), None
            )
            if page is None or not set(chunk.element_ids) <= {item.id for item in page.elements}:
                raise ValueError("Chunk elements must belong to its source page.")
        valid_pages = {page.page_number for page in self.source.pages}
        for invocation in self.invocations:
            if not invocation.page_numbers or not set(invocation.page_numbers) <= valid_pages:
                raise ValueError("Invocation must reference real source pages.")
        model_pages = {
            number for invocation in self.invocations for number in invocation.page_numbers
        }
        for page in self.pages:
            items: tuple[StructureElement | StructureCell, ...] = (
                *page.elements,
                *(cell for table in page.tables for cell in table.cells),
            )
            if (
                any(item.text_origin == "model_transcription" for item in items)
                and page.page_number not in model_pages
            ):
                raise ValueError("Model transcription requires recorded invocation provenance.")
        return self

"""Independent labels on original-page renders, never generated parse IDs."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field, model_validator

from lib.document_parsing.structure import SourceBox
from lib.evaluation.identity import Digest, EvaluationModel, Label


class SensitiveText(EvaluationModel):
    text: Label
    kind: Literal["identifier", "amount", "date"]
    occurrences: int = Field(ge=1, le=1000)


class AnnotatedRegion(EvaluationModel):
    id: Label
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
    readability: Literal["readable", "unreadable", "ambiguous", "blank"]
    text: str = Field(max_length=100000)
    bbox: SourceBox

    @model_validator(mode="after")
    def explicit_readability(self) -> AnnotatedRegion:
        if self.readability == "readable" and not self.text.strip() and self.kind != "table":
            raise ValueError("Readable non-table regions require transcription.")
        if self.readability != "readable" and self.text:
            raise ValueError("Unresolved regions must not supply scored transcription.")
        return self


class AnnotatedCell(EvaluationModel):
    row: int = Field(ge=0)
    column: int = Field(ge=0)
    row_span: int = Field(ge=1)
    column_span: int = Field(ge=1)
    text: str = Field(max_length=20000)
    readability: Literal["readable", "unreadable", "ambiguous", "blank"]


class AnnotatedTable(EvaluationModel):
    region_id: Label
    row_count: int = Field(ge=1, le=5000)
    column_count: int = Field(ge=1, le=100)
    cells: tuple[AnnotatedCell, ...] = Field(max_length=3000)
    continuation_group: Label | None

    @model_validator(mode="after")
    def valid_grid(self) -> AnnotatedTable:
        occupied: set[tuple[int, int]] = set()
        if self.row_count * self.column_count > 50000:
            raise ValueError("Annotated table exceeds grid limit.")
        for cell in self.cells:
            if cell.row + cell.row_span > self.row_count or (
                cell.column + cell.column_span > self.column_count
            ):
                raise ValueError("Annotated cell exceeds grid.")
            for row in range(cell.row, cell.row + cell.row_span):
                for column in range(cell.column, cell.column + cell.column_span):
                    if (row, column) in occupied:
                        raise ValueError("Annotated cells overlap.")
                    occupied.add((row, column))
            if cell.readability == "readable" and not cell.text.strip():
                raise ValueError("Readable cell requires transcription.")
            if cell.readability != "readable" and cell.text:
                raise ValueError("Unresolved cell cannot supply scored transcription.")
        return self


class AnnotatedPage(EvaluationModel):
    page_number: int = Field(ge=1)
    image_sha256: Digest
    pixel_width: int = Field(ge=1)
    pixel_height: int = Field(ge=1)
    regions: tuple[AnnotatedRegion, ...] = Field(max_length=400)
    tables: tuple[AnnotatedTable, ...] = Field(max_length=400)
    # Only unambiguous relations are labeled; tuple order is transcription order.
    reading_order_pairs: tuple[tuple[Label, Label], ...] = Field(max_length=10000)
    sensitive_text: tuple[SensitiveText, ...] = Field(max_length=1000)

    @model_validator(mode="after")
    def valid_references(self) -> AnnotatedPage:
        regions = {region.id: region for region in self.regions}
        if len(regions) != len(self.regions):
            raise ValueError("Annotation region IDs must be unique per page.")
        for region in self.regions:
            if region.bbox.right > self.pixel_width or region.bbox.bottom > self.pixel_height:
                raise ValueError("Annotation box exceeds reference render.")
        pairs = self.reading_order_pairs
        if len(set(pairs)) != len(pairs) or any(
            a == b or a not in regions or b not in regions for a, b in pairs
        ):
            raise ValueError("Reading-order references must be distinct existing regions.")
        positions = {region.id: index for index, region in enumerate(self.regions)}
        if any(positions[a] >= positions[b] for a, b in pairs):
            raise ValueError("Reading-order relations contradict annotated transcription order.")
        table_ids = [table.region_id for table in self.tables]
        expected = {region.id for region in self.regions if region.kind == "table"}
        if set(table_ids) != expected or len(table_ids) != len(expected):
            raise ValueError("Every annotated table region requires exactly one grid.")
        if len({item.text for item in self.sensitive_text}) != len(self.sensitive_text):
            raise ValueError("Repeated sensitive text uses one explicit occurrence count.")
        return self


class AnnotationProvenance(EvaluationModel):
    origin: Literal["human_original", "synthetic_author"]
    annotation_revision: Label
    author_reference: Label
    adjudicator_reference: Label | None
    created_at: datetime
    # These are supplied declarations, not proof of independent human review.
    source_only: Literal[True]


class DocumentAnnotation(EvaluationModel):
    schema_version: Literal["structura.source_annotation.v1"] = "structura.source_annotation.v1"
    item_id: Label
    original_sha256: Digest
    family_labels: tuple[Label, ...] = Field(min_length=1)
    modality: Literal["digital", "scan", "image", "mixed"]
    origin_group: Label
    template_group: Label
    provenance: AnnotationProvenance
    pages: tuple[AnnotatedPage, ...] = Field(min_length=1, max_length=500)

    @model_validator(mode="after")
    def complete_inventory(self) -> DocumentAnnotation:
        if [page.page_number for page in self.pages] != list(range(1, len(self.pages) + 1)):
            raise ValueError("Annotations must inventory every source page in order.")
        if self.provenance.created_at.utcoffset() is None:
            raise ValueError("Annotation timestamp requires timezone.")
        return self

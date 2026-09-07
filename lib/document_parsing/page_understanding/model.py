"""Combined response validation; never a classifier/extractor invocation or publication."""

from typing import Literal

from pydantic import ConfigDict, Field, model_validator

from lib.document_parsing.page_understanding.base import UnderstandingModel
from lib.document_parsing.page_understanding.classification import PageClassification
from lib.document_parsing.page_understanding.coverage import PageExtraction
from lib.document_parsing.page_understanding.coverage_validation import validate_coverage
from lib.document_parsing.page_understanding.locators import (
    SourceQuote,
    row_key,
    validate_quote,
    validate_row_member,
)
from lib.document_parsing.page_understanding.structure import UnderstandingElement

OUTPUT_VERSION = "structura.page_understanding.v2"


class PageUnderstanding(UnderstandingModel):
    model_config = ConfigDict(
        json_schema_extra={
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$id": "https://structura.local/contracts/model_outputs/structura_page_understanding.v2.schema.json",
        }
    )
    schema_version: Literal["structura.page_understanding.v2"]
    page_number: int = Field(ge=1, le=500, strict=True)
    state: Literal["processed", "partial", "insufficient_signal"]
    diagnostics: tuple[Literal["content_omitted", "unreadable_region"], ...]
    elements: tuple[UnderstandingElement, ...] = Field(max_length=400)
    classification: PageClassification
    extraction: PageExtraction

    @model_validator(mode="after")
    def bound_products(self) -> "PageUnderstanding":
        self._structure()
        if self.classification.unknown_reason == "blank_page" and any(
            e.text.strip() or (e.table is not None and any(c.text.strip() for c in e.table.cells))
            for e in self.elements
        ):
            raise ValueError("Blank-page classification cannot discard recorded wording.")
        for alternative in self.classification.alternatives:
            for quote in alternative.evidence:
                validate_quote(self.elements, quote)
        physical_fields = []
        identity: tuple[str | int | None, ...]
        for claim in self.extraction.claims:
            validate_quote(
                self.elements, SourceQuote(locator=claim.primary_source, quote=claim.raw_value)
            )
            for quote in claim.supporting_sources:
                validate_quote(self.elements, quote)
            if claim.physical_row is not None:
                validate_row_member(self.elements, claim.physical_row, claim.primary_source)
                identity = row_key(claim.physical_row)
            else:
                identity = (
                    "field",
                    claim.primary_source.element_index,
                    claim.primary_source.cell_row,
                    claim.primary_source.cell_column,
                    claim.primary_source.text_start,
                    claim.primary_source.text_end,
                )
            physical_fields.append((identity, claim.canonical_key))
        if len(set(physical_fields)) != len(physical_fields):
            raise ValueError("A physical field cannot emit two claims for the same canonical key.")
        validate_coverage(self.elements, self.extraction, self.classification)
        return self

    def _structure(self) -> None:
        if len(set(self.diagnostics)) != len(self.diagnostics):
            raise ValueError("Structural diagnostics must be distinct.")
        if self.state == "processed" and self.diagnostics:
            raise ValueError("Processed structure cannot conceal omitted or unreadable content.")
        if self.state != "processed" and not self.diagnostics:
            raise ValueError("Incomplete structure requires explicit diagnostics.")
        if self.state != "processed" and self.extraction.disposition in {
            "complete",
            "no_extraction_target",
        }:
            raise ValueError("Incomplete structure cannot establish complete extraction coverage.")
        for index, element in enumerate(self.elements):
            if element.parent_index is not None and element.parent_index >= index:
                raise ValueError("Parent must name an earlier structural element.")
            if element.table is not None:
                table = element.table
                occupied = sum(c.row_span * c.column_span for c in table.cells)
                if occupied != table.row_count * table.column_count and (
                    self.state == "processed" or "content_omitted" not in self.diagnostics
                ):
                    raise ValueError("Sparse tables require explicit partial structure.")

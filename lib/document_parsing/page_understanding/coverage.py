"""Explicit page-local obligations and omissions; no inference of document absence."""

from typing import Annotated, Literal

from pydantic import Field, model_validator

from lib.document_parsing.page_understanding.base import UnderstandingModel
from lib.document_parsing.page_understanding.claims import CanonicalKey, ProposedClaim
from lib.document_parsing.page_understanding.locators import PhysicalRow, SourceQuote
from lib.document_parsing.page_understanding.taxonomy import Family, TypedFamily

CoverageState = Literal[
    "present",
    "not_on_this_page",
    "not_applicable",
    "unreadable",
    "ambiguous",
    "omitted",
]


class FieldCoverage(UnderstandingModel):
    """Not on this page never establishes document-level absence or optionality."""

    canonical_key: CanonicalKey
    state: CoverageState
    claim_indices: tuple[Annotated[int, Field(ge=0, lt=3000, strict=True)], ...] = Field(
        max_length=100
    )
    evidence: tuple[SourceQuote, ...] = Field(max_length=8)

    @model_validator(mode="after")
    def accounted_value(self) -> "FieldCoverage":
        if any(isinstance(i, bool) or i < 0 or i >= 3000 for i in self.claim_indices):
            raise ValueError("Coverage claim reference is invalid.")
        if len(set(self.claim_indices)) != len(self.claim_indices):
            raise ValueError("Coverage claim references must be distinct.")
        if self.state == "present" and not self.claim_indices:
            raise ValueError("Present field requires at least one proposed claim.")
        if self.state not in {"present", "ambiguous"} and self.claim_indices:
            raise ValueError("Unextracted coverage cannot contain a proposed value.")
        if self.state in {"omitted", "ambiguous"} and not self.evidence and not self.claim_indices:
            raise ValueError("Known omitted or ambiguous content requires a source locator.")
        return self


class RowCoverage(UnderstandingModel):
    physical_row: PhysicalRow
    fields: tuple[FieldCoverage, ...] = Field(max_length=40)


class ExcludedRow(UnderstandingModel):
    physical_row: PhysicalRow
    reason: Literal["header", "summary", "not_a_line_item", "unreadable", "omitted"]


class FamilyCoverage(UnderstandingModel):
    family: TypedFamily
    fields: tuple[FieldCoverage, ...] = Field(max_length=80)
    rows: tuple[RowCoverage, ...] = Field(max_length=500)
    excluded_rows: tuple[ExcludedRow, ...] = Field(max_length=500)
    row_inventory: Literal["complete", "no_rows_on_this_page", "partial", "unreadable"]


class UnsupportedField(UnderstandingModel):
    family: Family | None
    label: str = Field(min_length=1, max_length=200)
    source: SourceQuote
    reason: Literal["no_registered_key", "unsupported_type"]


class PageExtraction(UnderstandingModel):
    """Model-reported page inventory; no quality score, accepted facts or verified recall."""

    disposition: Literal[
        "complete",
        "partial",
        "no_extraction_target",
        "insufficient_signal",
        "unsupported_family",
    ]
    reasons: tuple[
        Literal[
            "unreadable_content",
            "ambiguous_interpretation",
            "content_omitted",
            "output_budget",
            "unsupported_family",
            "unsupported_field",
            "no_typed_target",
        ],
        ...,
    ] = Field(max_length=7)
    families: tuple[FamilyCoverage, ...] = Field(max_length=3)
    unsupported_families: tuple[Family, ...] = Field(max_length=20)
    unsupported_fields: tuple[UnsupportedField, ...] = Field(max_length=100)
    claims: tuple[ProposedClaim, ...] = Field(max_length=3000)

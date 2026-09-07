"""Uncalibrated page-family observations, never application classification authority."""

from typing import Literal

from pydantic import Field, model_validator

from lib.document_parsing.page_understanding.base import UnderstandingModel
from lib.document_parsing.page_understanding.locators import SourceQuote
from lib.document_parsing.page_understanding.taxonomy import Family


class FamilyAlternative(UnderstandingModel):
    family: Family
    subtype: str | None = Field(min_length=1, max_length=120)
    uncalibrated_score: float | None = Field(ge=0, le=1, strict=True)
    rationale: str = Field(min_length=1, max_length=1000)
    evidence: tuple[SourceQuote, ...] = Field(min_length=1, max_length=8)


class PageClassification(UnderstandingModel):
    outcome: Literal["known", "mixed", "ambiguous", "unknown"]
    primary_family: Family | None
    alternatives: tuple[FamilyAlternative, ...] = Field(max_length=23)
    unknown_reason: Literal["blank_page", "insufficient_signal", "unresolved_family"] | None

    @model_validator(mode="after")
    def truthful_outcome(self) -> "PageClassification":
        families = tuple(item.family for item in self.alternatives)
        if len(set(families)) != len(families):
            raise ValueError("Family alternatives must be distinct.")
        if self.outcome == "unknown":
            if self.primary_family is not None or self.alternatives or self.unknown_reason is None:
                raise ValueError("Unknown classification cannot invent a chosen family.")
        elif self.unknown_reason is not None:
            raise ValueError("Known alternatives cannot carry an unknown-family reason.")
        elif self.outcome == "known":
            if not families or self.primary_family != families[0]:
                raise ValueError("Known family must be the first recorded alternative.")
        elif self.primary_family is not None or len(families) < 2:
            raise ValueError(
                "Mixed or ambiguous classification retains multiple unresolved families."
            )
        return self

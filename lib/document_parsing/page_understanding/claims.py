"""Model-proposed values remain separate from their exact transcription occurrence."""

import re
from datetime import date, time
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import AfterValidator, Field, StrictBool, StrictStr, model_validator
from typing_extensions import TypeAliasType

from lib.document_parsing.page_understanding.base import UnderstandingModel
from lib.document_parsing.page_understanding.locators import (
    PhysicalRow,
    SupportingQuote,
    TextLocator,
)
from lib.document_parsing.page_understanding.registry import RULE_BY_KEY, key_schema

TYPING_VERSION = "page-proposed-value-typing-v2"
DECIMAL_PATTERN = r"^[+-]?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?$"
CanonicalKey = TypeAliasType("CanonicalKey", Annotated[str, Field(json_schema_extra=key_schema)])


def decimal_bound(value: str) -> str:
    digits = value.lstrip("+-").replace(".", "")
    if len(digits) > 38 or ("." in value and len(value.partition(".")[2]) > 12):
        raise ValueError("Proposed decimal exceeds exact typing bounds.")
    if not Decimal(value).is_finite():
        raise ValueError("Proposed decimal must be finite.")
    return value  # Preserve the exact model member, including scale and signed zero.


def valid_date(value: str) -> str:
    date.fromisoformat(value)
    return value


def valid_time(value: str) -> str:
    time.fromisoformat(value)
    return value


ExactDecimal = Annotated[StrictStr, Field(pattern=DECIMAL_PATTERN), AfterValidator(decimal_bound)]
ExactDate = Annotated[
    StrictStr, Field(pattern=r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$"), AfterValidator(valid_date)
]
LocalTime = Annotated[
    StrictStr, Field(pattern=r"^[0-9]{2}:[0-9]{2}(?::[0-9]{2})?$"), AfterValidator(valid_time)
]
NonemptyValue = Annotated[StrictStr, Field(min_length=1, max_length=4096)]


class ProposedMoney(UnderstandingModel):
    amount: ExactDecimal
    currency: Annotated[StrictStr, Field(pattern=r"^[A-Z]{3}$")] | None


class ClaimBase(UnderstandingModel):
    """A proposed interpretation with an exact same-response transcription occurrence."""

    canonical_key: CanonicalKey
    raw_value: NonemptyValue
    primary_source: TextLocator
    supporting_sources: tuple[SupportingQuote, ...] = Field(max_length=8)
    physical_row: PhysicalRow | None
    uncalibrated_score: float | None = Field(ge=0, le=1, strict=True)

    @model_validator(mode="after")
    def known_field_scope(self) -> "ClaimBase":
        rule = RULE_BY_KEY.get(self.canonical_key)
        if rule is None or (rule.scope == "line") != (self.physical_row is not None):
            raise ValueError("Claim key or physical field/line scope is invalid.")
        if getattr(self, "value_type", None) != rule.value_type:
            raise ValueError("Proposed value type does not match the frozen field registry.")
        if self.canonical_key.endswith(".party_type") and getattr(
            self, "typed_value", None
        ) not in {
            "person",
            "company",
            "merchant",
            "provider",
            "payer",
            "government",
            "household_member",
            "other",
        }:
            raise ValueError("Proposed party type is outside the declared schema.")
        if getattr(self, "value_type", None) == "identifier" and (
            getattr(self, "typed_value", None) != self.raw_value.strip()
        ):
            raise ValueError("Identifiers must retain their exact printed characters.")
        if getattr(self, "value_type", None) == "identifiers" and (
            getattr(self, "typed_value", None)
            != tuple(re.split(r"[,;\s]+", self.raw_value.strip()))
        ):
            raise ValueError("Identifier lists must preserve ordered printed tokens.")
        if not self.raw_value.strip():
            raise ValueError("Claim requires nonempty recorded source text.")
        return self


class MoneyClaim(ClaimBase):
    value_type: Literal["money"]
    typed_value: ProposedMoney


class DateClaim(ClaimBase):
    value_type: Literal["date"]
    typed_value: ExactDate


class TimeClaim(ClaimBase):
    value_type: Literal["time"]
    typed_value: LocalTime


class NumberClaim(ClaimBase):
    value_type: Literal["number", "quantity"]
    typed_value: ExactDecimal


class TextClaim(ClaimBase):
    value_type: Literal["text", "party", "enum", "identifier"]
    typed_value: NonemptyValue


class IdentifiersClaim(ClaimBase):
    value_type: Literal["identifiers"]
    typed_value: tuple[NonemptyValue, ...] = Field(min_length=1, max_length=50)


class BooleanClaim(ClaimBase):
    value_type: Literal["boolean"]
    typed_value: StrictBool


ProposedClaim = Annotated[
    MoneyClaim | DateClaim | TimeClaim | NumberClaim | TextClaim | IdentifiersClaim | BooleanClaim,
    Field(discriminator="value_type"),
]

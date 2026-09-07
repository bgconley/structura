"""Application diagnostics distinguish proposed interpretations from literal copying."""

import re
from decimal import Decimal, InvalidOperation
from typing import Any

from lib.document_parsing.page_understanding.claims import (
    DateClaim,
    MoneyClaim,
    NumberClaim,
    TextClaim,
    TimeClaim,
)
from lib.document_parsing.page_understanding.model import PageUnderstanding


def interpretation_diagnostics(page: PageUnderstanding) -> tuple[dict[str, Any], ...]:
    reports = []
    for index, claim in enumerate(page.extraction.claims):
        reasons = []
        if isinstance(claim, MoneyClaim):
            explicit_codes = set(re.findall(r"(?<![A-Z])[A-Z]{3}(?![A-Z])", claim.raw_value))
            for quote in claim.supporting_sources:
                if quote.role == "currency":
                    explicit_codes.update(re.findall(r"(?<![A-Z])[A-Z]{3}(?![A-Z])", quote.quote))
            code = claim.typed_value.currency
            if code is None or explicit_codes != {code}:
                reasons.append("unresolved_currency" if code is None else "ambiguous_currency")
            raw_number = re.sub(r"(?<![A-Z])[A-Z]{3}(?![A-Z])", "", claim.raw_value).strip()
            if not _same_decimal(raw_number, claim.typed_value.amount):
                reasons.append("amount_interpretation")
        elif isinstance(claim, DateClaim) and claim.raw_value.strip() != claim.typed_value:
            reasons.append("date_interpretation")
        elif isinstance(claim, TimeClaim) and claim.raw_value.strip() != claim.typed_value:
            reasons.append("time_interpretation")
        elif isinstance(claim, NumberClaim) and not _same_decimal(
            claim.raw_value, claim.typed_value
        ):
            reasons.append("numeric_interpretation")
        elif isinstance(claim, TextClaim) and claim.raw_value.strip() != claim.typed_value:
            reasons.append("text_interpretation")
        reports.append(
            {
                "claim_index": index,
                "requires_review": True,
                "source_origin": "model_transcription",
                "interpretation_origin": "model_emission",
                "source_pixel_support": "not_evaluated",
                "arithmetic_validation": "not_evaluated",
                "reasons": reasons,
            }
        )
    return tuple(reports)


def _same_decimal(raw: str, proposed: str) -> bool:
    # Locale punctuation and symbols require interpretation; equality is circular
    # even for plain numbers and never establishes original-source support.
    if not re.fullmatch(r"[+-]?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?", raw.strip()):
        return False
    try:
        return Decimal(raw.strip()) == Decimal(proposed)
    except InvalidOperation:
        return False

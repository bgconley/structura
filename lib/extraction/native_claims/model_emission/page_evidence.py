"""Bind every classification/coverage quote to retained source occurrences."""

from typing import Any

from lib.document_parsing.page_understanding.locators import SourceQuote
from lib.extraction.native_claims.model_emission.anchors import bind_quote
from lib.extraction.native_claims.model_emission.page_models import BoundPageEvidence


def bound_page_evidence(page, generation_id, classification, coverage):
    return tuple(
        BoundPageEvidence(pointer=pointer, anchor=bind_quote(page, quote, generation_id))
        for root, value in (("/classification", classification), ("/extraction", coverage))
        for pointer, quote in _quotes(value, root)
    )


def _quotes(value: Any, pointer: str):
    if isinstance(value, dict):
        if "locator" in value and "quote" in value:
            yield (
                pointer,
                SourceQuote.model_validate({"locator": value["locator"], "quote": value["quote"]}),
            )
        else:
            for key, item in value.items():
                yield from _quotes(item, pointer + "/" + key.replace("~", "~0").replace("/", "~1"))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from _quotes(item, pointer + f"/{index}")

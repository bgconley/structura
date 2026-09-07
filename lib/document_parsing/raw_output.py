"""The single structural dispatcher for replay, persistence and evaluation."""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from lib.document_parsing.model_output import PageParseOutput
from lib.document_parsing.normalization import normalize_page
from lib.document_parsing.page_understanding.codec import decode_page_understanding
from lib.document_parsing.structure import SourceRender, StructurePage

V1_OUTPUT_VERSION = "structura.page_parse.v1"
V2_OUTPUT_VERSION: Literal["structura.page_understanding.v2"] = "structura.page_understanding.v2"
V2_NORMALIZER_VERSION = "native-page-understanding-normalizer-v2"


def normalize_raw_page(
    raw: str,
    source: SourceRender,
    generation_id: UUID,
    *,
    output_schema_version: str,
) -> StructurePage:
    if output_schema_version == V1_OUTPUT_VERSION:
        output = PageParseOutput.model_validate_json(raw)
    elif output_schema_version == V2_OUTPUT_VERSION:
        decoded = decode_page_understanding(raw)
        # Typed products remain in the immutable raw checkpoint. They do not
        # replace transcription text or become accepted facts in this projection.
        output = PageParseOutput.model_validate(
            decoded.page.model_dump(
                mode="json", include={"page_number", "state", "diagnostics", "elements"}
            )
        )
    else:
        raise ValueError("Raw page output version is unsupported.")
    return normalize_page(output, source, generation_id)

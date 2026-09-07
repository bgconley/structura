"""Synthetic retained transcription for currency tests, never live-model evidence."""

import hashlib
from uuid import uuid4

from lib.document_parsing.model_output import PageParseOutput
from lib.document_parsing.normalization import normalize_page
from lib.document_parsing.qwen_page_parser import ParsedSourcePage
from lib.document_parsing.searchable_text import page_chunks
from lib.document_parsing.structure import (
    DocumentStructure,
    ParseInvocation,
    SourceInventory,
    SourcePage,
    SourceRender,
)
from lib.document_processing.models import ProcessingBinding, content_digest
from lib.extraction.native_claims.models import NativeClaimBinding
from lib.extraction.native_claims.source_repository import NativeClaimSource


def page_output(
    texts=("USD 9007199254740.1234", "USD 9007199254740.1234"),
    *,
    page_number=1,
    state="processed",
    table=False,
):
    box = {"left": 0, "top": 0, "right": 900, "bottom": 900}
    elements = [
        {"kind": "paragraph", "text": text, "bbox": box, "parent_index": None, "table": None}
        for text in texts
    ]
    if table:
        elements = [
            {
                "kind": "table",
                "text": "Recorded table",
                "bbox": box,
                "parent_index": None,
                "table": {
                    "row_count": len(texts),
                    "column_count": 1,
                    "continuation_key": None,
                    "cells": [
                        {
                            "row": n,
                            "column": 0,
                            "row_span": 1,
                            "column_span": 1,
                            "text": text,
                            "bbox": {**box, "top": n * 100},
                            "is_header": False,
                        }
                        for n, text in enumerate(texts)
                    ],
                },
            }
        ]
    return PageParseOutput.model_validate(
        {
            "page_number": page_number,
            "state": state,
            "diagnostics": [] if state == "processed" else ["content_omitted"],
            "elements": elements,
        }
    )


def replace_output(checkpoint, generation_id, output):
    raw = output.model_dump_json()
    return ParsedSourcePage(
        normalize_page(output, checkpoint.page.source, generation_id),
        checkpoint.invocation.model_copy(
            update={"raw_output_sha256": hashlib.sha256(raw.encode()).hexdigest()}
        ),
        raw,
    )


def pure_source(
    *, table=False, state="processed", texts=("USD 9007199254740.1234", "USD 9007199254740.1234")
):
    processing = ProcessingBinding(uuid4(), uuid4(), uuid4())
    binding = NativeClaimBinding(processing, uuid4())
    output = page_output(texts, state=state, table=table)
    raw = output.model_dump_json()
    source = SourceRender(
        page_number=1,
        image_sha256="a" * 64,
        pixel_width=200,
        pixel_height=100,
        renderer="controlled-test",
        renderer_version="v1",
    )
    page = normalize_page(output, source, processing.parse_generation_id)
    invocation = ParseInvocation(
        request_id=uuid4(),
        page_numbers=(1,),
        profile="controlled-test",
        served_model="qwen38-27b-bf16-oxcart",
        source_engine="qwen3_8_27b",
        prompt_version="test-v1",
        output_schema_version="structura.page_parse.v1",
        raw_output_sha256=hashlib.sha256(raw.encode()).hexdigest(),
        finish_reason="stop",
        latency_ms=1,
    )
    structure = DocumentStructure(
        parse_generation_id=processing.parse_generation_id,
        processing_run_id=processing.processing_run_id,
        source=SourceInventory(
            original_asset_id=uuid4(),
            original_sha256="b" * 64,
            mime_type="image/png",
            byte_size=10,
            pages=(SourcePage(page_number=1, width=200, height=100, unit="pixels"),),
        ),
        pages=(page,),
        invocations=(invocation,),
        chunks=page_chunks(page, processing.parse_generation_id),
    )
    manifest = {
        "pages": [
            {
                "page_number": 1,
                "checkpoint_sha256": content_digest(
                    {
                        "page": page.model_dump(mode="json"),
                        "invocation": invocation.model_dump(mode="json"),
                        "raw": raw,
                    }
                ),
                "invocation": invocation.model_dump(mode="json"),
            }
        ]
    }
    return binding, NativeClaimSource(structure, manifest, uuid4())

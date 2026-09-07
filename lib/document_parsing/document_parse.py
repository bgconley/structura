"""Bounded resumable page orchestration, independent of job/database publication."""

from __future__ import annotations

import hashlib
import math
from collections.abc import Callable, Sequence
from uuid import UUID, uuid5

from lib.document_parsing.page_parser import SourcePageParser, V1SourcePageParser
from lib.document_parsing.qwen_page_parser import (
    PageGenerationClient,
    ParsedSourcePage,
)
from lib.document_parsing.raw_output import V1_OUTPUT_VERSION, V2_OUTPUT_VERSION, normalize_raw_page
from lib.document_parsing.searchable_text import page_chunks
from lib.document_parsing.source_adapter import DocumentSource
from lib.document_parsing.structure import DocumentStructure, StructurePage


def parse_document(
    source: DocumentSource,
    client: PageGenerationClient,
    *,
    generation_id: UUID,
    run_id: UUID,
    max_new_pages: int = 50,
    completed: Sequence[ParsedSourcePage] = (),
    assert_authority: Callable[[], None],
    checkpoint: Callable[[ParsedSourcePage], None],
    timeout_seconds: int = 180,
    render_scale: float = 2,
    page_parser: SourcePageParser | None = None,
) -> DocumentStructure:
    """The owning run service supplies authority and immutable checkpoint storage.

    This computes a candidate artifact only. It cannot activate structure, facts,
    or indexes. Failed render/model calls propagate as operational failures;
    completed checkpoints remain available to the owning retry policy.
    """
    if not 1 <= max_new_pages <= 500:
        raise ValueError("Page budget must be between 1 and 500.")
    if not math.isfinite(render_scale) or not 0 < render_scale <= 4:
        raise ValueError("Source rendering scale is invalid.")
    inventory = source.inventory
    parser = page_parser or V1SourcePageParser(
        client, generation_id, len(inventory.pages), timeout_seconds
    )
    if parser.output_schema_version not in {V1_OUTPUT_VERSION, V2_OUTPUT_VERSION}:
        raise ValueError("Page parser output version is unsupported.")
    prior = {result.page.page_number: result for result in completed}
    if len(prior) != len(completed) or not set(prior) <= set(range(1, len(inventory.pages) + 1)):
        raise ValueError("Resume checkpoints contain duplicate or foreign pages.")
    pages = []
    invocations = []
    requested = 0
    for source_page in inventory.pages:
        number = source_page.page_number
        assert_authority()
        previous = prior.get(number)
        if previous is not None:
            # Resume requires exact generation + original rendered bytes, not
            # just matching page numbers or similar model output.
            rendered = source.render(number, scale=render_scale)
            if (
                previous.page.id != uuid5(generation_id, f"page:{number}")
                or previous.page.source != rendered.identity
                or previous.invocation.page_numbers != (number,)
                or previous.invocation.output_schema_version != parser.output_schema_version
                or hashlib.sha256(previous.raw_output.encode()).hexdigest()
                != previous.invocation.raw_output_sha256
                or normalize_raw_page(
                    previous.raw_output,
                    rendered.identity,
                    generation_id,
                    output_schema_version=parser.output_schema_version,
                )
                != previous.page
            ):
                raise ValueError("Resume checkpoint belongs to another generation or source.")
            result = previous
        elif requested < max_new_pages:
            result = parser.parse_page(source.render(number, scale=render_scale))
            if result.invocation.output_schema_version != parser.output_schema_version:
                raise ValueError("Page parser returned another output version.")
            assert_authority()
            checkpoint(result)
            requested += 1
        else:
            pages.append(
                StructurePage(
                    id=uuid5(generation_id, f"page:{number}"),
                    page_number=number,
                    source=None,
                    state="deferred",
                    diagnostics=("resource_limit",),
                )
            )
            continue
        pages.append(result.page)
        invocations.append(result.invocation)
    assert_authority()
    return DocumentStructure(
        parse_generation_id=generation_id,
        processing_run_id=run_id,
        source=inventory,
        pages=tuple(pages),
        invocations=tuple(invocations),
        chunks=tuple(chunk for page in pages for chunk in page_chunks(page, generation_id)),
    )

"""Validate immutable parser checkpoints without database or publication decisions."""

from __future__ import annotations

import hashlib
import math
from uuid import UUID, uuid5

from lib.document_parsing.qwen_page_parser import ParsedSourcePage
from lib.document_parsing.raw_output import normalize_raw_page
from lib.document_parsing.structure import SourceInventory
from lib.document_processing.configuration_binding import validate_invocation_binding
from lib.document_processing.configuration_types import AnyParseConfiguration
from lib.document_processing.errors import ProcessingError


def validate_checkpoint(
    checkpoint: ParsedSourcePage,
    *,
    generation_id: UUID,
    inventory: SourceInventory,
    configuration: AnyParseConfiguration,
) -> None:
    page, invocation = checkpoint.page, checkpoint.invocation
    source = page.source
    if (
        source is None
        or not 1 <= page.page_number <= len(inventory.pages)
        or page.id != uuid5(generation_id, f"page:{page.page_number}")
        or invocation.page_numbers != (page.page_number,)
        or source.renderer != configuration.renderer
        or source.renderer_version != configuration.renderer_version
        or invocation.profile != configuration.profile
        or invocation.served_model != configuration.served_model
        or invocation.source_engine != configuration.source_engine
        or invocation.prompt_version != configuration.prompt_version
        or invocation.output_schema_version != configuration.output_schema_version
    ):
        raise ProcessingError("Checkpoint does not match its generation, source or configuration.")
    if hashlib.sha256(checkpoint.raw_output.encode()).hexdigest() != invocation.raw_output_sha256:
        raise ProcessingError("Checkpoint raw output does not match its recorded hash.")
    validate_invocation_binding(configuration, invocation, source, inventory)
    source_page = inventory.pages[page.page_number - 1]
    scale = configuration.render_scale if source_page.unit == "pdf_canvas" else 1
    if (source.pixel_width, source.pixel_height) != (
        math.ceil(source_page.width * scale),
        math.ceil(source_page.height * scale),
    ):
        raise ProcessingError("Checkpoint raster does not match the configured source geometry.")
    normalized = normalize_raw_page(
        checkpoint.raw_output,
        source,
        generation_id,
        output_schema_version=configuration.output_schema_version,
    )
    if normalized != page:
        raise ProcessingError("Checkpoint structure does not match its raw response.")

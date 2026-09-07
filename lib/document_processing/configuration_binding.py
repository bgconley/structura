"""Pure historical configuration/source/request consistency; never invocation attestation."""

from __future__ import annotations

from lib.document_parsing.document_context import validate_context_inventory
from lib.document_parsing.invocations import ParseInvocation, ParseInvocationV2
from lib.document_parsing.structure import SourceInventory, SourceRender
from lib.document_processing.configuration_types import AnyParseConfiguration, ParseConfigurationV2
from lib.document_processing.understanding_request import (
    request_digest,
    text_digest,
    understanding_prompt,
)


def validate_configuration_inventory(
    configuration: AnyParseConfiguration, inventory: SourceInventory
) -> None:
    if isinstance(configuration, ParseConfigurationV2):
        validate_context_inventory(configuration.context, inventory)


def validate_invocation_binding(
    configuration: AnyParseConfiguration,
    invocation: ParseInvocation,
    source: SourceRender,
    inventory: SourceInventory,
) -> None:
    """Reconstruct v2 request from retained inputs, without reparsing model claims."""
    validate_configuration_inventory(configuration, inventory)
    validate_recorded_request(configuration, invocation, source)


def validate_recorded_request(
    configuration: AnyParseConfiguration, invocation: ParseInvocation, source: SourceRender
) -> None:
    """Compact page validation after its caller verifies the frozen inventory hash."""
    if not isinstance(configuration, ParseConfigurationV2):
        if isinstance(invocation, ParseInvocationV2):
            raise ValueError("Understanding invocation cannot belong to a v1 configuration.")
        return
    if (
        not isinstance(invocation, ParseInvocationV2)
        or invocation.configuration_sha256 != configuration.fingerprint
        or invocation.context_sha256 != configuration.context.fingerprint
        or invocation.source_inventory_sha256 != configuration.context.source_inventory_sha256
        or invocation.output_schema_sha256 != configuration.definitions.schema_sha256
        or invocation.prompt_sha256 != text_digest(understanding_prompt(configuration, source))
        or invocation.request_sha256 != request_digest(configuration, source)
        or invocation.finish_reason != "stop"
    ):
        raise ValueError("Understanding invocation differs from its frozen request identity.")
    if (configuration.context.mime_type == "application/pdf") != (
        source.native_text_origin == "pdf_native"
    ):
        raise ValueError("Page native text attribution differs from its original media type.")
    selected = next(
        (
            page
            for page in configuration.context.selected_pages
            if page.page_number == source.page_number
        ),
        None,
    )
    if selected is not None and (
        source.native_text_origin != "pdf_native"
        or source.native_text is None
        or len(source.native_text) != selected.source_character_count
        or source.native_text[: len(selected.excerpt)] != selected.excerpt
    ):
        raise ValueError("Page native hint differs from its frozen document context.")

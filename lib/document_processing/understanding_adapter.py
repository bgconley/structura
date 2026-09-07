"""One combined v2 call per new page; retained output never promotes facts."""

from __future__ import annotations

import json
from dataclasses import dataclass
from uuid import UUID, uuid4

from lib.document_parsing.invocations import ParseInvocationV2
from lib.document_parsing.page_understanding.codec import (
    canonical_digest,
    decode_page_understanding,
)
from lib.document_parsing.page_understanding.definitions import model_output_schema
from lib.document_parsing.qwen_page_parser import PageGenerationClient, ParsedSourcePage
from lib.document_parsing.raw_output import V2_OUTPUT_VERSION, normalize_raw_page
from lib.document_parsing.source_adapter import RenderedSourcePage
from lib.document_processing.configuration_types import ParseConfigurationV2
from lib.document_processing.errors import ProcessingError
from lib.document_processing.understanding_request import (
    request_digest,
    text_digest,
    understanding_prompt,
    validate_understanding_request,
)
from lib.model_runtime.contracts import ModelImageInput, VisionGenerateRequest

# Same character limit as the protected capture transport, distinct from the
# standalone strict decoder's 16 MiB byte bound. Never truncate to meet either.
MAX_CAPTURE_CHARACTERS = 2_000_000


@dataclass(frozen=True)
class UnderstandingPageParser:
    client: PageGenerationClient
    generation_id: UUID
    configuration: ParseConfigurationV2

    @property
    def output_schema_version(self) -> str:
        return V2_OUTPUT_VERSION

    def parse_page(self, source: RenderedSourcePage) -> ParsedSourcePage:
        config, settings = self.configuration, self.configuration.request
        prompt = understanding_prompt(config, source.identity)
        request = VisionGenerateRequest(
            profile_name=config.profile,
            prompt_version=config.prompt_version,
            prompt=prompt,
            image_inputs=(
                ModelImageInput(source.image_bytes, "image/png", source.identity.image_sha256),
            ),
            response_schema_name=V2_OUTPUT_VERSION,
            response_json_schema=model_output_schema(),
            max_output_tokens=settings.max_output_tokens,
            temperature=settings.temperature,
            seed=settings.seed,
            timeout_seconds=settings.timeout_seconds,
        )
        validate_understanding_request(request, config, source.identity)
        # The caller's frozen client applies fresh authority immediately before
        # its actual HTTP call, after prompt creation and image hashing.
        response = self.client.generate(request)
        if (
            (
                response.profile_name,
                response.model_name,
                response.source_engine,
                response.prompt_version,
            )
            != (config.profile, config.served_model, config.source_engine, config.prompt_version)
            or response.input_sha256 != (source.identity.image_sha256,)
            or response.finish_reason != "stop"
            or not response.structured_output_used
            or len(response.raw_text) > MAX_CAPTURE_CHARACTERS
        ):
            raise ProcessingError("Understanding response differs from its invocation contract.")
        try:
            decoded = decode_page_understanding(response.raw_text)
            # The raw decoder rejects duplicate members/nonfinite numbers first.
            # A client's repaired dictionary may not replace this exact payload.
            if canonical_digest(json.loads(response.raw_text)) != canonical_digest(
                response.normalized_json
            ):
                raise ValueError("Adapter output does not equal the exact model response.")
            page = normalize_raw_page(
                response.raw_text,
                source.identity,
                self.generation_id,
                output_schema_version=V2_OUTPUT_VERSION,
            )
            invocation = ParseInvocationV2(
                request_id=uuid4(),
                page_numbers=(page.page_number,),
                profile=response.profile_name,
                served_model=response.model_name,
                source_engine=response.source_engine,
                prompt_version=response.prompt_version,
                output_schema_version=V2_OUTPUT_VERSION,
                raw_output_sha256=decoded.raw_output_sha256,
                finish_reason=response.finish_reason,
                latency_ms=response.latency_ms,
                invocation_version="structura.parse_invocation.v2",
                configuration_sha256=config.fingerprint,
                source_inventory_sha256=config.context.source_inventory_sha256,
                context_sha256=config.context.fingerprint,
                prompt_sha256=text_digest(prompt),
                output_schema_sha256=config.definitions.schema_sha256,
                request_sha256=request_digest(config, source.identity),
                reported_model_version=response.model_version or None,
            )
        except ValueError:
            raise ProcessingError(
                "Understanding output violates its bounded response contract."
            ) from None
        return ParsedSourcePage(page, invocation, response.raw_text)

"""Synthetic v2 checkpoint bindings; these are never live-model acceptance evidence."""

import hashlib
import json
from dataclasses import asdict, dataclass
from uuid import uuid4

from lib.document_parsing.document_context import freeze_document_context
from lib.document_parsing.invocations import ParseInvocationV2
from lib.document_parsing.page_understanding.definitions import frozen_definitions
from lib.document_parsing.qwen_page_parser import ParsedSourcePage
from lib.document_parsing.raw_output import normalize_raw_page
from lib.document_parsing.structure import SourceInventory, SourcePage, SourceRender
from lib.document_processing.configuration_types import (
    ParseConfigurationV2,
    ParseRequestSettings,
    UnderstandingDefinitions,
)
from lib.document_processing.models import ProcessingBinding, content_digest
from lib.document_processing.understanding_request import (
    request_digest,
    text_digest,
    understanding_prompt,
)
from lib.extraction.native_claims.models import NativeClaimBinding
from tests.fixtures.page_understanding_sources import invoice_page


@dataclass(frozen=True)
class SyntheticContext:
    inventory: SourceInventory

    def native_text(self, page_number: int) -> str | None:
        return None


def configuration(inventory):
    return ParseConfigurationV2(
        configuration_version="structura.parse_configuration.v2",
        profile="synthetic-qwen-27b",
        served_model="qwen38-27b-bf16-oxcart",
        source_engine="qwen3_8_27b",
        model_revision="synthetic",
        prompt_version="qwen-native-page-understanding-v2",
        output_schema_version="structura.page_understanding.v2",
        normalizer_version="native-page-understanding-normalizer-v2",
        chunker_version="test-v1",
        renderer="test-source-raster",
        renderer_version="v1",
        render_scale=2,
        definitions=UnderstandingDefinitions.model_validate(asdict(frozen_definitions())),
        profile_sha256="a" * 64,
        prompt_template_sha256="a" * 64,
        request_builder_sha256="a" * 64,
        context_recipe_sha256="a" * 64,
        normalizer_sha256="a" * 64,
        context=freeze_document_context(SyntheticContext(inventory)),
        request=ParseRequestSettings(
            max_output_tokens=8192, temperature=0, seed=None, timeout_seconds=180
        ),
    )


def checkpoint(parse, generation_id, output=None):
    output = output or invoice_page()
    raw = json.dumps(output, ensure_ascii=False)
    source = SourceRender(
        page_number=output["page_number"],
        image_sha256="b" * 64,
        pixel_width=200,
        pixel_height=100,
        renderer=parse.renderer,
        renderer_version=parse.renderer_version,
    )
    invocation = ParseInvocationV2(
        invocation_version="structura.parse_invocation.v2",
        request_id=uuid4(),
        page_numbers=(source.page_number,),
        profile=parse.profile,
        served_model=parse.served_model,
        source_engine=parse.source_engine,
        prompt_version=parse.prompt_version,
        output_schema_version=parse.output_schema_version,
        raw_output_sha256=hashlib.sha256(raw.encode()).hexdigest(),
        finish_reason="stop",
        latency_ms=1,
        configuration_sha256=parse.fingerprint,
        source_inventory_sha256=parse.context.source_inventory_sha256,
        context_sha256=parse.context.fingerprint,
        prompt_sha256=text_digest(understanding_prompt(parse, source)),
        output_schema_sha256=parse.definitions.schema_sha256,
        request_sha256=request_digest(parse, source),
        reported_model_version=None,
    )
    return ParsedSourcePage(
        normalize_raw_page(
            raw, source, generation_id, output_schema_version=parse.output_schema_version
        ),
        invocation,
        raw,
    )


def source(output=None):
    inventory = SourceInventory(
        original_asset_id=uuid4(),
        original_sha256="c" * 64,
        mime_type="image/png",
        byte_size=10,
        pages=(SourcePage(page_number=1, width=200, height=100, unit="pixels"),),
    )
    parse = configuration(inventory)
    binding = NativeClaimBinding(
        ProcessingBinding(
            document_id=uuid4(), processing_run_id=uuid4(), parse_generation_id=uuid4()
        ),
        uuid4(),
    )
    return (
        binding,
        parse,
        inventory,
        checkpoint(parse, binding.processing.parse_generation_id, output),
    )


def digest(checkpoint):
    return content_digest(
        {
            "page": checkpoint.page.model_dump(mode="json"),
            "invocation": checkpoint.invocation.model_dump(mode="json"),
            "raw": checkpoint.raw_output,
        }
    )

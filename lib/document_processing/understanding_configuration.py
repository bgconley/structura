"""Explicit opt-in v2 configuration from verified original bytes and installed definitions."""

from __future__ import annotations

import hashlib
from dataclasses import asdict
from pathlib import Path

from lib.document_parsing.document_context import FrozenDocumentContext, freeze_document_context
from lib.document_parsing.page_understanding.definitions import frozen_definitions
from lib.document_parsing.raw_output import V2_NORMALIZER_VERSION, V2_OUTPUT_VERSION
from lib.document_parsing.source_adapter import DocumentSource
from lib.document_processing.configuration_types import (
    ParseConfigurationV2,
    ParseRequestSettings,
    UnderstandingDefinitions,
)
from lib.document_processing.errors import ProcessingError
from lib.document_processing.models import content_digest
from lib.document_processing.parser_configuration import (
    DeclaredParserDeployment,
    parser_configuration,
)
from lib.document_processing.understanding_request import (
    PROMPT_TEMPLATE,
    PROMPT_VERSION,
    text_digest,
)
from lib.model_runtime.profiles import QWEN_INGESTION_PROFILE, get_model_profile


def understanding_configuration(
    deployment: DeclaredParserDeployment,
    source: DocumentSource,
    *,
    request: ParseRequestSettings,
    render_scale: float = 2,
) -> ParseConfigurationV2:
    """No model calls. Caller opens the original with exact registered hash/size first.

    Bounds are validation guards, not measured dense-page capacity. Output budget
    and optional request values are explicit; the v1 factory/default is unchanged.
    """
    context = freeze_document_context(source)
    return installed_understanding_configuration(deployment, context, request, render_scale)


def installed_understanding_configuration(
    deployment: DeclaredParserDeployment,
    context: FrozenDocumentContext,
    request: ParseRequestSettings,
    render_scale: float,
) -> ParseConfigurationV2:
    """Configuration preparation/execution adapter only: source-file hashes require IO.

    Historical codecs and transactional checkpoint validators must not call this.
    This verifies installed definitions, while execution separately reproduces
    the frozen native context from the immutable original before any HTTP call.
    """
    base = parser_configuration(deployment, context.mime_type, render_scale=render_scale)
    profile = get_model_profile(QWEN_INGESTION_PROFILE)
    if profile.max_model_len is None or request.max_output_tokens >= profile.max_model_len:
        raise ProcessingError("Output budget leaves no space for the required model inputs.")
    definitions = UnderstandingDefinitions.model_validate(asdict(frozen_definitions()))
    root = Path(__file__).resolve().parents[1]
    normalizer = _source_digest(
        root / "document_parsing",
        (
            "normalization.py",
            "raw_output.py",
            "structure.py",
            "model_output.py",
            "searchable_text.py",
        ),
    )
    return ParseConfigurationV2(
        **{
            **base.model_dump(),
            "prompt_version": PROMPT_VERSION,
            "output_schema_version": V2_OUTPUT_VERSION,
            "normalizer_version": V2_NORMALIZER_VERSION,
        },
        configuration_version="structura.parse_configuration.v2",
        definitions=definitions,
        profile_sha256=content_digest(asdict(profile)),
        prompt_template_sha256=text_digest(PROMPT_TEMPLATE),
        request_builder_sha256=content_digest(
            {
                "request": _source_digest(
                    Path(__file__).resolve().parent,
                    (
                        "understanding_request.py",
                        "understanding_adapter.py",
                        "configuration_binding.py",
                    ),
                ),
                "vision_adapter": _source_digest(
                    root / "model_runtime" / "clients", ("_openai_vision.py", "qwen_vl.py")
                ),
                "transport_contract": _source_digest(
                    root / "model_runtime", ("contracts.py", "http_client.py")
                ),
            }
        ),
        context_recipe_sha256=_source_digest(
            root / "document_parsing", ("document_context.py", "source_adapter.py")
        ),
        normalizer_sha256=normalizer,
        context=context,
        request=request,
    )


def _source_digest(directory: Path, names: tuple[str, ...]) -> str:
    return content_digest(
        {name: hashlib.sha256((directory / name).read_bytes()).hexdigest() for name in names}
    )

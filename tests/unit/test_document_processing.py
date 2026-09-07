from __future__ import annotations

import hashlib
from dataclasses import replace
from uuid import uuid4

import pytest
from pydantic import ValidationError

from lib.document_parsing.model_output import PageParseOutput
from lib.document_parsing.normalization import normalize_page
from lib.document_parsing.qwen_page_parser import ParsedSourcePage
from lib.document_parsing.structure import (
    ParseInvocation,
    SourceInventory,
    SourcePage,
    SourceRender,
)
from lib.document_processing.checkpoint_validation import validate_checkpoint
from lib.document_processing.errors import ProcessingError
from lib.document_processing.models import ParseConfiguration


@pytest.fixture
def contract():
    generation = uuid4()
    configuration = ParseConfiguration(
        profile="qwen-native",
        served_model="qwen38-27b-bf16-oxcart",
        source_engine="qwen3_8_27b",
        model_revision="revision-a",
        prompt_version="page-v1",
        output_schema_version="structura.page_parse.v1",
        normalizer_version="v1",
        chunker_version="v1",
        renderer="pdfium",
        renderer_version="1",
        render_scale=2,
    )
    inventory = SourceInventory(
        original_asset_id=uuid4(),
        original_sha256="a" * 64,
        mime_type="application/pdf",
        byte_size=100,
        pages=(SourcePage(page_number=1, width=100, height=50, unit="pdf_canvas"),),
    )
    source = SourceRender(
        page_number=1,
        image_sha256="b" * 64,
        pixel_width=200,
        pixel_height=100,
        renderer="pdfium",
        renderer_version="1",
    )
    output = PageParseOutput.model_validate(
        {
            "page_number": 1,
            "state": "processed",
            "diagnostics": [],
            "elements": [
                {
                    "kind": "paragraph",
                    "text": "Visible original",
                    "parent_index": None,
                    "table": None,
                    "bbox": {"left": 0, "top": 0, "right": 1000, "bottom": 1000},
                }
            ],
        }
    )
    raw = output.model_dump_json()
    invocation = ParseInvocation(
        request_id=uuid4(),
        page_numbers=(1,),
        profile=configuration.profile,
        served_model=configuration.served_model,
        source_engine=configuration.source_engine,
        prompt_version=configuration.prompt_version,
        output_schema_version=configuration.output_schema_version,
        raw_output_sha256=hashlib.sha256(raw.encode()).hexdigest(),
        finish_reason="stop",
        latency_ms=1,
    )
    return (
        ParsedSourcePage(normalize_page(output, source, generation), invocation, raw),
        {"generation_id": generation, "inventory": inventory, "configuration": configuration},
    )


def test_configuration_is_immutable_and_identity_includes_source_and_parser_versions(contract):
    _checkpoint, kwargs = contract
    configuration = kwargs["configuration"]
    assert (
        ParseConfiguration.model_validate(
            dict(reversed(list(configuration.model_dump().items())))
        ).fingerprint
        == configuration.fingerprint
    )
    for field in ("model_revision", "normalizer_version", "renderer_version", "chunker_version"):
        changed = configuration.model_copy(update={field: "new-version"})
        assert changed.fingerprint != configuration.fingerprint
    with pytest.raises(ValidationError):
        configuration.render_scale = 1
    with pytest.raises(ValidationError):
        ParseConfiguration.model_validate({**configuration.model_dump(), "authorization": "secret"})


def test_checkpoint_preserves_model_origin_and_rejects_changed_source_geometry(contract):
    checkpoint, kwargs = contract
    validate_checkpoint(checkpoint, **kwargs)
    assert checkpoint.page.elements[0].text_origin == "model_transcription"
    with pytest.raises(ProcessingError, match="geometry"):
        validate_checkpoint(
            checkpoint,
            **{
                **kwargs,
                "configuration": kwargs["configuration"].model_copy(update={"render_scale": 1}),
            },
        )
    with pytest.raises(ProcessingError, match="generation"):
        validate_checkpoint(checkpoint, **{**kwargs, "generation_id": uuid4()})


def test_checkpoint_rejects_wrong_provenance_or_changed_raw_content(contract):
    checkpoint, kwargs = contract
    for field in (
        "profile",
        "served_model",
        "source_engine",
        "prompt_version",
        "output_schema_version",
    ):
        changed = replace(
            checkpoint, invocation=checkpoint.invocation.model_copy(update={field: "other"})
        )
        with pytest.raises(ProcessingError):
            validate_checkpoint(changed, **kwargs)
    with pytest.raises(ProcessingError, match="hash"):
        validate_checkpoint(replace(checkpoint, raw_output="PRIVATE changed response"), **kwargs)
    changed_page = checkpoint.page.model_copy(update={"elements": ()})
    with pytest.raises(ProcessingError, match="raw response"):
        validate_checkpoint(replace(checkpoint, page=changed_page), **kwargs)

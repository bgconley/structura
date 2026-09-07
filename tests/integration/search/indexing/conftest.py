from __future__ import annotations

import hashlib
import io

import pytest
from PIL import Image

from lib.document_parsing.model_output import PageParseOutput
from lib.document_parsing.normalization import normalize_page
from lib.document_parsing.qwen_page_parser import ParsedSourcePage
from lib.document_processing.service import DocumentProcessingService
from lib.search.indexing.models import IndexRenderAsset, VectorObservation
from lib.search.indexing.projection import render_asset_id
from lib.search.indexing.service import CandidateIndexService
from lib.storage import ObjectStorage
from tests.integration.document_processing.conftest import processing  # noqa: F401


@pytest.fixture
def candidate_source(processing, tmp_path, request):  # noqa: F811
    """Real PNG storage; controlled parser output, never live model evidence."""
    storage = ObjectStorage(
        canonical_root=tmp_path / "canonical",
        derived_root=tmp_path / "derived",
        export_root=tmp_path / "exports",
    )
    stream = io.BytesIO()
    with Image.new("RGB", (200, 100), "white") as image:
        # Each isolated document owns distinct controlled bytes. Cleanup must
        # still retain identical hashes referenced by another document.
        for offset, value in enumerate(processing.document_id.bytes):
            image.putpixel((offset, 0), (value, 255 - value, value ^ 0x5A))
        image.save(stream, format="PNG")
    data = stream.getvalue()
    stored = storage.store_bytes(data, kind="derived", role="source-page")
    run = processing.start()
    claimed = processing.claim()
    checkpoint = processing.checkpoint(run)
    count = getattr(request, "param", 1)
    if count != 1:
        output = PageParseOutput.model_validate_json(checkpoint.raw_output).model_dump(mode="json")
        output["elements"] = [
            {**output["elements"][0], "text": f"Controlled independent input {i}"}
            for i in range(count)
        ]
        raw = PageParseOutput.model_validate(output).model_dump_json()
        checkpoint = ParsedSourcePage(
            checkpoint.page,
            checkpoint.invocation.model_copy(
                update={"raw_output_sha256": hashlib.sha256(raw.encode()).hexdigest()}
            ),
            raw,
        )
    source = checkpoint.page.source.model_copy(
        update={"image_sha256": hashlib.sha256(data).hexdigest()}
    )
    checkpoint = ParsedSourcePage(
        normalize_page(
            PageParseOutput.model_validate_json(checkpoint.raw_output),
            source,
            run.binding.parse_generation_id,
        ),
        checkpoint.invocation,
        checkpoint.raw_output,
    )
    parser = DocumentProcessingService()
    with processing.scope(claimed):
        parser.initialize_inventory(run.binding, processing.inventory)
        parser.checkpoint(run.binding, checkpoint)
        parser.seal(run.binding, processing.structure(run, [checkpoint]))
    return processing, run, claimed, CandidateIndexService(storage), checkpoint, stored


def asset_for(binding, checkpoint, stored):
    return IndexRenderAsset(
        id=render_asset_id(binding.index_generation_id, checkpoint.page.id),
        page_id=checkpoint.page.id,
        page_number=1,
        source=checkpoint.page.source,
        uri=stored.uri,
        byte_size=stored.byte_size,
    )


def observation(item, config):
    space = config.space(item.modality)
    from uuid import uuid4

    return VectorObservation(
        input_id=item.id,
        model_input_sha256=item.model_input_sha256,
        values=(0.1,) * space.dimensions,
        profile=space.profile,
        reported_model=space.served_model,
        declared_artifact_revision=space.protocol.artifact_revision,
        model_mode="fixture",
        invocation_id=uuid4(),
        latency_ms=1,
    )

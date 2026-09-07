from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

import pytest

from lib.document_parsing.structure import DocumentStructure
from lib.search.indexing.configuration import index_configuration
from lib.search.indexing.models import IndexRenderAsset, VectorObservation
from lib.search.indexing.projection import project_inputs, render_asset_id
from lib.storage.service import object_uri


@pytest.fixture
def structure():
    path = Path(__file__).resolve().parents[3] / "fixtures/evaluation/capture.json"
    return DocumentStructure.model_validate(json.loads(path.read_text())["structure"])


def assets_for(structure, index_id):
    return tuple(
        IndexRenderAsset(
            id=render_asset_id(index_id, page.id),
            page_id=page.id,
            page_number=page.page_number,
            source=page.source,
            byte_size=100,
            uri=object_uri(kind="derived", sha256=page.source.image_sha256, filename="source.png"),
        )
        for page in structure.pages
    )


@pytest.fixture
def candidate(structure):
    config = index_configuration(model_mode="fixture", modalities=("text",))
    manifest = project_inputs(structure, index_id=uuid4(), configuration=config)
    return config, manifest


def observation(item, config, *, value=0.1):
    space = config.space(item.modality)
    return VectorObservation(
        input_id=item.id,
        model_input_sha256=item.model_input_sha256,
        values=(value,) * (space.dimensions),
        profile=space.profile,
        reported_model=space.served_model,
        declared_artifact_revision=space.protocol.artifact_revision,
        model_mode=config.model_mode,
        invocation_id=uuid4(),
        latency_ms=1,
    )

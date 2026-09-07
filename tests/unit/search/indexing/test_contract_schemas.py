from __future__ import annotations

import json
from pathlib import Path

from lib.search.indexing.configuration import IndexConfiguration
from lib.search.indexing.models import (
    CandidateIndexEvent,
    IndexManifest,
    IndexRenderAsset,
    VectorObservation,
)


def test_reviewable_json_schemas_match_runtime_types():
    directory = Path(__file__).resolve().parents[4] / "contracts/indexing"
    for name, model in (
        ("native_index_configuration.v1.schema.json", IndexConfiguration),
        ("native_index_manifest.v1.schema.json", IndexManifest),
        ("native_index_render.v1.schema.json", IndexRenderAsset),
        ("native_index_vector_observation.v1.schema.json", VectorObservation),
        ("native_index_job.v1.schema.json", CandidateIndexEvent),
    ):
        assert json.loads((directory / name).read_text()) == model.model_json_schema()

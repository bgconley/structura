"""Exact authorized snapshots for external rendering and embedding execution."""

from __future__ import annotations

from typing import Any

from lib.document_parsing.structure import DocumentStructure
from lib.document_processing.models import ParseConfiguration
from lib.search.indexing.authority_repository import fence_index, lock_index
from lib.search.indexing.configuration import IndexConfiguration
from lib.search.indexing.errors import IndexCandidateError
from lib.search.indexing.input_repository import load_manifest
from lib.search.indexing.models import (
    IndexBinding,
    IndexPreparationSource,
    IndexRenderAsset,
    PreparedIndexSnapshot,
)
from lib.search.indexing.vector_repository import validated_checkpoints


def load_preparation(cur: Any, binding: IndexBinding) -> IndexPreparationSource:
    run, header = lock_index(cur, binding)
    cur.execute(
        "SELECT uri,mime_type,byte_size,sha256 FROM document_assets "
        "WHERE id=%s AND document_id=%s AND asset_role='original'",
        (run["original_asset_id"], binding.processing.document_id),
    )
    asset = cur.fetchone()
    structure = DocumentStructure.model_validate(run["structure_json"])
    source = structure.source
    if asset is None or (asset["mime_type"], asset["byte_size"], asset["sha256"]) != (
        source.mime_type,
        source.byte_size,
        source.original_sha256,
    ):
        raise IndexCandidateError("Candidate original metadata differs from its sealed inventory.")
    snapshot = IndexPreparationSource(
        configuration=IndexConfiguration.model_validate(header["config_json"]),
        parse_configuration=ParseConfiguration.model_validate(run["config_json"]),
        structure=structure,
        original_uri=asset["uri"],
        prepared=header["manifest_json"] is not None,
    )
    fence_index(cur, binding)
    return snapshot


def load_prepared(cur: Any, binding: IndexBinding) -> PreparedIndexSnapshot:
    _, header = lock_index(cur, binding)
    configuration = IndexConfiguration.model_validate(header["config_json"])
    manifest = load_manifest(cur, binding, header)
    cur.execute(
        "SELECT asset_json FROM document_generation_render_assets "
        "WHERE index_generation_id=%s ORDER BY page_number",
        (binding.index_generation_id,),
    )
    assets = tuple(IndexRenderAsset.model_validate(row["asset_json"]) for row in cur.fetchall())
    completed = validated_checkpoints(cur, binding, manifest, configuration)
    result = PreparedIndexSnapshot(
        configuration=configuration,
        manifest=manifest,
        assets=assets,
        completed_input_ids=tuple(item.id for item in manifest.inputs if item.id in completed),
    )
    fence_index(cur, binding)
    return result

"""Atomic complete input-manifest assignment; never reads mutable legacy projections."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any
from uuid import UUID

from psycopg.types.json import Jsonb

from lib.document_parsing.structure import DocumentStructure
from lib.document_processing.models import content_digest
from lib.search.indexing.authority_repository import fence_index, lock_index
from lib.search.indexing.configuration import IndexConfiguration
from lib.search.indexing.errors import IndexCheckpointConflict
from lib.search.indexing.models import IndexBinding, IndexInput, IndexManifest, IndexRenderAsset
from lib.search.indexing.projection import project_inputs


def prepare_inputs(
    cur: Any,
    binding: IndexBinding,
    assets: tuple[IndexRenderAsset, ...],
    *,
    commit_sources: Callable[[], None],
) -> IndexManifest:
    """Caller stages verified exact render objects before this bounded transaction.

    At most4096 inputs/500 assets register together. Under the sorted content locks,
    the required callback establishes bytes before references/manifest may commit.
    No rendering, PNG decoding, staging or model work occurs in this transaction.
    """
    run, header = lock_index(
        cur, binding, render_hashes=tuple(a.source.image_sha256 for a in assets)
    )
    manifest = project_inputs(
        DocumentStructure.model_validate(run["structure_json"]),
        index_id=binding.index_generation_id,
        configuration=IndexConfiguration.model_validate(header["config_json"]),
        assets=assets,
    )
    payload = manifest.model_dump(mode="json")
    if header["manifest_json"] is not None:
        if header["manifest_json"] != payload or header["manifest_sha256"] != manifest.fingerprint:
            raise IndexCheckpointConflict(
                "Candidate manifest was already assigned different inputs."
            )
        _verify_rows(cur, binding, manifest, assets)
        commit_sources()
        fence_index(cur, binding)
        return manifest
    # Every referenced parse checkpoint/original was prelocked by lock_index.
    # Atomic blob commits/existing-object checks share the registration hash locks.
    commit_sources()
    for asset in assets:
        asset_json = asset.model_dump(mode="json")
        cur.execute(
            """INSERT INTO document_generation_render_assets
            (id,index_generation_id,document_id,parse_generation_id,original_asset_id,
             page_number,page_id,asset_json,content_sha256) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (
                asset.id,
                binding.index_generation_id,
                binding.processing.document_id,
                binding.processing.parse_generation_id,
                run["original_asset_id"],
                asset.page_number,
                asset.page_id,
                Jsonb(asset_json),
                content_digest(asset_json),
            ),
        )
    for item in manifest.inputs:
        item_json = item.model_dump(mode="json")
        cur.execute(
            """INSERT INTO document_index_inputs
            (id,index_generation_id,ordinal,modality,render_asset_id,input_json,content_sha256)
            VALUES (%s,%s,%s,%s,%s,%s,%s)""",
            (
                item.id,
                binding.index_generation_id,
                item.ordinal,
                item.modality,
                item.render_asset_id,
                Jsonb(item_json),
                content_digest(item_json),
            ),
        )
    cur.execute(
        "UPDATE document_index_generations SET "
        "state='embedding',manifest_json=%s,manifest_sha256=%s "
        "WHERE id=%s AND state='preparing'",
        (Jsonb(payload), manifest.fingerprint, binding.index_generation_id),
    )
    fence_index(cur, binding)
    return manifest


def _verify_rows(
    cur: Any,
    binding: IndexBinding,
    manifest: IndexManifest,
    assets: tuple[IndexRenderAsset, ...],
) -> None:
    cur.execute(
        "SELECT input_json,content_sha256 FROM document_index_inputs WHERE "
        "index_generation_id=%s ORDER BY ordinal",
        (binding.index_generation_id,),
    )
    if tuple((r["input_json"], r["content_sha256"]) for r in cur.fetchall()) != tuple(
        (item.model_dump(mode="json"), content_digest(item.model_dump(mode="json")))
        for item in manifest.inputs
    ):
        raise IndexCheckpointConflict(
            "Persisted candidate inputs do not match the frozen manifest."
        )
    cur.execute(
        "SELECT asset_json,content_sha256 FROM document_generation_render_assets "
        "WHERE index_generation_id=%s ORDER BY page_number",
        (binding.index_generation_id,),
    )
    if tuple((r["asset_json"], r["content_sha256"]) for r in cur.fetchall()) != tuple(
        (asset.model_dump(mode="json"), content_digest(asset.model_dump(mode="json")))
        for asset in sorted(assets, key=lambda a: a.page_number)
    ):
        raise IndexCheckpointConflict(
            "Persisted candidate renders do not match the frozen manifest."
        )


def load_manifest(cur: Any, binding: IndexBinding, header: dict[str, Any]) -> IndexManifest:
    if header["manifest_json"] is None:
        raise IndexCheckpointConflict("Candidate inputs must be sealed before embedding.")
    manifest = IndexManifest.model_validate(header["manifest_json"])
    if (
        manifest.fingerprint != header["manifest_sha256"]
        or manifest.index_generation_id != binding.index_generation_id
        or manifest.parse_generation_id != binding.processing.parse_generation_id
        or manifest.configuration_sha256 != header["config_sha256"]
        or manifest.structure_sha256 != header["structure_sha256"]
    ):
        raise IndexCheckpointConflict("Candidate manifest identity is inconsistent.")
    cur.execute(
        "SELECT asset_json FROM document_generation_render_assets WHERE "
        "index_generation_id=%s ORDER BY page_number",
        (binding.index_generation_id,),
    )
    assets = tuple(IndexRenderAsset.model_validate(row["asset_json"]) for row in cur.fetchall())
    _verify_rows(cur, binding, manifest, assets)
    cur.execute(
        "SELECT structure_json FROM document_parse_generations WHERE id=%s",
        (binding.processing.parse_generation_id,),
    )
    expected = project_inputs(
        DocumentStructure.model_validate(cur.fetchone()["structure_json"]),
        index_id=binding.index_generation_id,
        configuration=IndexConfiguration.model_validate(header["config_json"]),
        assets=assets,
    )
    if manifest != expected:
        raise IndexCheckpointConflict(
            "Candidate manifest differs from its exact sealed source projection."
        )
    return manifest


def load_input(
    cur: Any, binding: IndexBinding, header: dict[str, Any], input_id: UUID
) -> IndexInput:
    """Read one immutable prepared row; deep manifest parity is checked at seal."""
    if header["state"] not in {"embedding", "sealed"} or header["manifest_sha256"] is None:
        raise IndexCheckpointConflict("Candidate inputs must be frozen before embedding.")
    cur.execute(
        "SELECT * FROM document_index_inputs WHERE id=%s AND index_generation_id=%s FOR KEY SHARE",
        (input_id, binding.index_generation_id),
    )
    row = cur.fetchone()
    if row is None:
        raise IndexCheckpointConflict("Vector input is outside the frozen candidate generation.")
    item = IndexInput.model_validate(row["input_json"])
    if (
        content_digest(row["input_json"]) != row["content_sha256"]
        or item.id != row["id"]
        or item.ordinal != row["ordinal"]
        or item.modality != row["modality"]
        or item.render_asset_id != row["render_asset_id"]
    ):
        raise IndexCheckpointConflict("Candidate input identity is inconsistent.")
    return item

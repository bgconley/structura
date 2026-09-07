"""Reproduce/stage exact sealed renders and assemble verified model inputs."""

from __future__ import annotations

from lib.document_parsing.source_adapter import DocumentSource, renderer_identity
from lib.model_runtime.contracts import EmbeddingInput
from lib.search.indexing.errors import IndexCandidateError
from lib.search.indexing.models import (
    IndexBinding,
    IndexInput,
    IndexManifest,
    IndexPreparationSource,
    IndexRenderAsset,
    PreparedIndexSnapshot,
)
from lib.search.indexing.projection import render_asset_id, visual_reasons
from lib.search.indexing.render_verification import read_verified_render
from lib.search.indexing.service import CandidateIndexService
from lib.storage import ObjectStorage, cleanup_unreferenced_stored_object
from lib.storage.service import StoredObject, parse_object_uri


def prepare_index_candidate(
    binding: IndexBinding,
    *,
    storage: ObjectStorage,
    service: CandidateIndexService,
) -> IndexManifest:
    snapshot = service.load_preparation(binding)
    if snapshot.prepared:
        prepared = service.load_prepared(binding)
        return service.prepare(binding, prepared.assets)
    created: list[StoredObject] = []
    try:
        assets = _stage_renders(binding, snapshot, storage, service, created)
        return service.prepare(binding, assets)
    except Exception:
        # The service's DB context has rolled back/closed before cleanup. The
        # shared content lock/reference check retains reused or committed blobs.
        for stored in created:
            cleanup_unreferenced_stored_object(stored)
        raise


def _stage_renders(
    binding: IndexBinding,
    snapshot: IndexPreparationSource,
    storage: ObjectStorage,
    service: CandidateIndexService,
    created: list[StoredObject],
) -> tuple[IndexRenderAsset, ...]:
    structure = snapshot.structure
    config = snapshot.configuration
    eligible = tuple(
        page
        for page in structure.pages
        if "visual" in config.modalities
        and visual_reasons(page, original_is_image=structure.source.mime_type != "application/pdf")
    )
    if not eligible:
        return ()
    original = structure.source
    address = parse_object_uri(snapshot.original_uri)
    if address.kind != "canonical" or address.sha256 != original.original_sha256:
        raise IndexCandidateError(
            "Original object address differs from its frozen source identity."
        )
    parser = snapshot.parse_configuration
    if renderer_identity(original.mime_type) != (parser.renderer, parser.renderer_version):
        raise IndexCandidateError(
            "Installed renderer cannot reproduce this frozen parse generation."
        )
    service.assert_authority(binding)
    assets = []
    with DocumentSource(
        storage.path_for_uri(snapshot.original_uri),
        asset_id=original.original_asset_id,
        expected_sha256=original.original_sha256,
        mime_type=original.mime_type,
        max_bytes=min(original.byte_size, 100 * 1024 * 1024),
        max_pages=500,
    ) as source:
        if source.inventory != original:
            raise IndexCandidateError(
                "Original inventory differs from the sealed parse generation."
            )
        for page in eligible:
            service.assert_authority(binding)
            rendered = source.render(page.page_number, scale=parser.render_scale)
            if rendered.identity != page.source:
                raise IndexCandidateError(
                    "Rendered page differs from its exact sealed source descriptor."
                )
            service.assert_authority(binding)
            stored = storage.store_bytes(
                rendered.image_bytes, kind="derived", role="native-index-source"
            )
            created.append(stored)
            assets.append(
                IndexRenderAsset(
                    id=render_asset_id(binding.index_generation_id, page.id),
                    page_id=page.id,
                    page_number=page.page_number,
                    source=rendered.identity,
                    uri=stored.uri,
                    byte_size=stored.byte_size,
                )
            )
    return tuple(assets)


def verified_model_input(
    item: IndexInput,
    snapshot: PreparedIndexSnapshot,
    storage: ObjectStorage,
) -> EmbeddingInput:
    if item.modality == "text":
        value = EmbeddingInput(text=item.text)
    else:
        asset = next((asset for asset in snapshot.assets if asset.id == item.render_asset_id), None)
        if asset is None:
            raise IndexCandidateError("Candidate visual input has no exact registered render.")
        value = EmbeddingInput(
            text=item.text,
            image_bytes=read_verified_render(asset, storage),
            mime_type=asset.mime_type,
        )
    if value.sha256 != item.content_sha256:
        raise IndexCandidateError("Actual model input differs from its frozen content identity.")
    return value

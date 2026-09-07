"""Bounded original-bound render retention under a caller-owned renewing job lease."""

from __future__ import annotations

from lib.document_parsing.source_adapter import DocumentSource, renderer_identity
from lib.document_parsing.structure import DocumentStructure
from lib.document_processing.configuration_types import decode_parse_configuration
from lib.document_processing.models import ProcessingBinding, content_digest
from lib.evidence.errors import EvidenceConflict
from lib.evidence.models import (
    MAX_RENDER_BYTES,
    RenderSetBinding,
    RenderSetSnapshot,
    RetainedPageAsset,
    RetainedRenderProgress,
    source_render_id,
)
from lib.evidence.write_service import RetainedEvidenceWriter
from lib.storage import ObjectStorage, cleanup_unreferenced_stored_object
from lib.storage.service import parse_object_uri


def retain_source_pages(
    processing: ProcessingBinding,
    *,
    storage: ObjectStorage,
    service: RetainedEvidenceWriter,
    max_new_pages: int = 8,
    max_new_bytes: int = 256 * 1024 * 1024,
) -> RetainedRenderProgress:
    """A pending result requires continuation and must never ACK the producer."""
    if type(max_new_pages) is not int or not 1 <= max_new_pages <= 32:
        raise EvidenceConflict("Retained source page budget must be between 1 and 32.")
    if (
        type(max_new_bytes) is not int
        or not MAX_RENDER_BYTES <= max_new_bytes <= 4 * MAX_RENDER_BYTES
    ):
        raise EvidenceConflict("Retained source byte budget must be between 128 and 512 MiB.")
    binding = service.start(processing)
    before = service.snapshot(binding)
    completed = {asset.page_id for asset in before.assets}
    if len(completed) != len(before.expected.pages):
        _retain_missing(binding, before, storage, service, max_new_pages, max_new_bytes)
    after = service.snapshot(binding)
    if before.expected != after.expected:
        raise EvidenceConflict("Retained source expectations changed during execution.")
    completed_after = {asset.page_id for asset in after.assets}
    done = len(completed_after) == len(after.expected.pages)
    sealed = service.seal(binding) if done else None
    new = tuple(asset for asset in after.assets if asset.page_id not in completed)
    return RetainedRenderProgress(
        state="sealed" if done else "pending",
        render_set_id=binding.render_set_id,
        expected_sha256=after.expected.fingerprint,
        completion_sha256=content_digest(sealed) if sealed is not None else None,
        completed_page_ids=tuple(
            p.page_id for p in after.expected.pages if p.page_id in completed_after
        ),
        remaining_page_ids=tuple(
            p.page_id for p in after.expected.pages if p.page_id not in completed_after
        ),
        new_pages=len(new),
        new_bytes=sum(asset.byte_size for asset in new),
    )


def _retain_missing(
    binding: RenderSetBinding,
    snapshot: RenderSetSnapshot,
    storage: ObjectStorage,
    service: RetainedEvidenceWriter,
    max_pages: int,
    max_bytes: int,
) -> None:
    row = service.execution_source(binding)
    structure = DocumentStructure.model_validate(row["structure_json"])
    config = decode_parse_configuration(row["config_json"])
    expected = snapshot.expected
    original = structure.source
    address = parse_object_uri(row["uri"])
    if (
        content_digest(row["structure_json"]) != expected.structure_sha256
        or config.fingerprint != expected.parse_configuration_sha256
        or original.original_asset_id != expected.original_asset_id
        or original.original_sha256 != expected.original_sha256
        or (row["sha256"], row["mime_type"], row["byte_size"])
        != (original.original_sha256, original.mime_type, original.byte_size)
        or address.kind != "canonical"
        or address.sha256 != original.original_sha256
        or renderer_identity(original.mime_type) != (config.renderer, config.renderer_version)
    ):
        raise EvidenceConflict("Original source or renderer differs from its frozen identity.")
    completed = {asset.page_id for asset in snapshot.assets}
    created = []
    new_count = new_bytes = 0
    try:
        service.assert_authority(binding)
        with DocumentSource(
            storage.path_for_uri(row["uri"]),
            asset_id=original.original_asset_id,
            expected_sha256=original.original_sha256,
            mime_type=original.mime_type,
            max_bytes=min(original.byte_size, 100 * 1024 * 1024),
            max_pages=500,
        ) as source:
            if source.inventory != original:
                raise EvidenceConflict("Original inventory differs from its frozen source.")
            for page in structure.pages:
                if page.id in completed:
                    continue
                if new_count >= max_pages:
                    break
                service.assert_authority(binding)
                rendered = source.render(page.page_number, scale=config.render_scale)
                if rendered.identity != page.source:
                    raise EvidenceConflict(
                        "Rendered page differs from its frozen original evidence."
                    )
                if len(rendered.image_bytes) > MAX_RENDER_BYTES:
                    raise EvidenceConflict("Retained source image exceeds its byte bound.")
                if new_bytes + len(rendered.image_bytes) > max_bytes:
                    break
                service.assert_authority(binding)
                stored = storage.store_bytes(
                    rendered.image_bytes, kind="derived", role="retained-source-page"
                )
                created.append(stored)
                descriptor = expected.pages[page.page_number - 1]
                asset = RetainedPageAsset(
                    id=source_render_id(expected.parse_generation_id, page.id),
                    **descriptor.model_dump(),
                    uri=stored.uri,
                    byte_size=stored.byte_size,
                )
                service.checkpoint(binding, asset)
                new_count += 1
                new_bytes += stored.byte_size
    except BaseException:
        # All service transactions are closed. Shared reference checks preserve
        # committed pages/reused bytes while removing unreferenced new objects.
        for stored in created:
            cleanup_unreferenced_stored_object(stored)
        raise

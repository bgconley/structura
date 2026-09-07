"""Pure exact-source manifests; model transcription is not source verification."""

from __future__ import annotations

from typing import Any

from lib.document_parsing.structure import DocumentStructure, SourceInventory
from lib.document_processing.models import ParseConfiguration, content_digest
from lib.evidence.errors import EvidenceConflict
from lib.evidence.models import ExpectedPage, ExpectedRenderSet, RasterIdentity, RetainedPageAsset


def expected_render_set(
    run: dict[str, Any], checkpoints: list[dict[str, Any]]
) -> ExpectedRenderSet:
    structure = DocumentStructure.model_validate(run["structure_json"])
    inventory = SourceInventory.model_validate(run["inventory_json"])
    config = ParseConfiguration.model_validate(run["config_json"])
    if (
        run["parse_state"] != "sealed"
        or structure.source != inventory
        or content_digest(run["structure_json"]) != run["structure_sha256"]
        or content_digest(run["inventory_json"]) != run["inventory_sha256"]
        or config.fingerprint != run["config_sha256"]
        or structure.processing_run_id != run["id"]
        or structure.parse_generation_id != run["parse_generation_id"]
        or structure.source.original_asset_id != run["original_asset_id"]
        or structure.source.original_sha256 != run["original_sha256"]
        or len(checkpoints) != len(structure.pages)
    ):
        raise EvidenceConflict("Retained source differs from its sealed processing identity.")
    pages = []
    for page, row in zip(structure.pages, checkpoints, strict=True):
        source = page.source
        if (
            source is None
            or page.state not in {"processed", "partial", "insufficient_signal"}
            or row["page_id"] != page.id
            or row["page_number"] != page.page_number
            or row["page_json"] != page.model_dump(mode="json")
            or content_digest(
                {
                    "page": row["page_json"],
                    "invocation": row["invocation_json"],
                    "raw": row["raw_output"],
                }
            )
            != row["content_sha256"]
        ):
            raise EvidenceConflict("Retained source checkpoint does not match the sealed page.")
        pages.append(
            ExpectedPage(
                page_number=page.page_number,
                page_id=page.id,
                checkpoint_sha256=row["content_sha256"],
                source_render_sha256=content_digest(source.model_dump(mode="json")),
                render=RasterIdentity.from_source(source),
            )
        )
    return ExpectedRenderSet(
        document_id=run["document_id"],
        processing_run_id=run["id"],
        parse_generation_id=run["parse_generation_id"],
        original_asset_id=run["original_asset_id"],
        original_sha256=run["original_sha256"],
        inventory_sha256=run["inventory_sha256"],
        structure_sha256=run["structure_sha256"],
        parse_configuration_sha256=run["config_sha256"],
        pages=tuple(pages),
    )


def validate_asset(asset: RetainedPageAsset, expected: ExpectedRenderSet) -> None:
    from lib.evidence.models import source_render_id
    from lib.storage.service import parse_object_uri

    if asset.page_number > len(expected.pages):
        raise EvidenceConflict("Retained image is outside the expected page inventory.")
    page = expected.pages[asset.page_number - 1]
    address = parse_object_uri(asset.uri)
    if (
        asset.id != source_render_id(expected.parse_generation_id, page.page_id)
        or asset.page_id != page.page_id
        or asset.checkpoint_sha256 != page.checkpoint_sha256
        or asset.source_render_sha256 != page.source_render_sha256
        or asset.render != page.render
        or address.kind != "derived"
        or address.sha256 != asset.render.image_sha256
    ):
        raise EvidenceConflict("Retained image does not match its frozen source descriptor.")


def completion_manifest(
    expected: ExpectedRenderSet, assets: tuple[RetainedPageAsset, ...]
) -> dict[str, Any]:
    if tuple(asset.page_id for asset in assets) != tuple(page.page_id for page in expected.pages):
        raise EvidenceConflict("Retained source images are incomplete.")
    for asset in assets:
        validate_asset(asset, expected)
    return {
        "schema_version": "structura.retained_render_completion.v1",
        "expected_sha256": expected.fingerprint,
        "page_count": len(expected.pages),
        "total_bytes": sum(asset.byte_size for asset in assets),
        "pages": [
            {
                "page_id": str(asset.page_id),
                "asset_id": str(asset.id),
                "content_sha256": asset.fingerprint,
            }
            for asset in assets
        ],
    }

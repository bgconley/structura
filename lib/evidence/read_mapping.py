"""Validate compact persisted evidence snapshots without current parser assumptions."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from lib.document_parsing.invocations import decode_parse_invocation
from lib.document_parsing.structure import SourcePage, StructureChunk, StructurePage
from lib.document_processing.configuration_binding import validate_recorded_request
from lib.document_processing.configuration_types import (
    AnyParseConfiguration,
    ParseConfigurationV2,
    decode_parse_configuration,
)
from lib.document_processing.models import content_digest
from lib.evidence.errors import EvidenceUnavailable
from lib.evidence.models import (
    ExpectedPage,
    GenerationEvidencePageSummary,
    GenerationEvidenceRender,
    RasterIdentity,
    RetainedPageAsset,
    source_render_id,
)


def validate_header(row: dict[str, Any]) -> AnyParseConfiguration:
    config = decode_parse_configuration(row["config_json"])
    if (
        config.fingerprint != row["config_sha256"]
        or row["structure_version"] != "structura.document_structure.v1"
        or row["run_status"] not in {"sealed", "superseded", "cancelled"}
        or not 1 <= row["page_count"] <= 500
    ):
        raise EvidenceUnavailable("Retained generation is unavailable.")
    if isinstance(config, ParseConfigurationV2) and (
        config.context.original_asset_id != row["original_asset_id"]
        or config.context.original_sha256 != row["original_sha256"]
        or config.context.source_inventory_sha256 != row["inventory_sha256"]
        or config.context.page_count != row["page_count"]
    ):
        raise EvidenceUnavailable("Retained generation is unavailable.")
    return config


def retained_asset(row: dict[str, Any], page: dict[str, Any]) -> RetainedPageAsset | None:
    raster = RasterIdentity.model_validate(page["raster"])
    if page["asset"] is None:
        return None
    expected = ExpectedPage.model_validate(page["expected_page"])
    asset = RetainedPageAsset.model_validate(page["asset"])
    if (
        asset.fingerprint != page["asset_sha256"]
        or asset.id != UUID(str(page["asset_id"]))
        or asset.page_id != UUID(str(page["asset_page_id"]))
        or asset.page_number != page["asset_page_number"]
        or asset.id != source_render_id(row["parse_generation_id"], UUID(str(page["page_id"])))
        or asset.page_id != UUID(str(page["page_id"]))
        or asset.page_number != page["page_number"]
        or expected.page_id != asset.page_id
        or expected.page_number != asset.page_number
        or expected.checkpoint_sha256 != page["checkpoint_sha256"]
        or asset.checkpoint_sha256 != expected.checkpoint_sha256
        or asset.source_render_sha256 != expected.source_render_sha256
        or asset.render != expected.render
        or asset.render != raster
    ):
        raise EvidenceUnavailable("Retained generation is unavailable.")
    return asset


def render_response(
    row: dict[str, Any], asset: RetainedPageAsset | None
) -> GenerationEvidenceRender | None:
    if asset is None:
        return None
    return GenerationEvidenceRender(
        id=asset.id,
        imageUrl=(
            f"/api/v1/documents/{row['document_id']}/parse-generations/"
            f"{row['parse_generation_id']}/pages/{asset.page_number}/render"
        ),
        sha256=asset.render.image_sha256,
        byteSize=asset.byte_size,
        pixelWidth=asset.render.pixel_width,
        pixelHeight=asset.render.pixel_height,
    )


def page_summary(row: dict[str, Any], page: dict[str, Any]) -> GenerationEvidencePageSummary:
    source = SourcePage.model_validate(page["source_page"])
    if source.page_number != page["page_number"]:
        raise EvidenceUnavailable("Retained generation is unavailable.")
    asset = retained_asset(row, page)
    return GenerationEvidencePageSummary(
        pageId=page["page_id"],
        pageNumber=page["page_number"],
        sourcePage=source,
        parseState=page["parse_state"],
        renderRegistration="registered" if asset else "not_retained",
        render=render_response(row, asset),
    )


def page_content(
    row: dict[str, Any], item: dict[str, Any]
) -> tuple[StructurePage, tuple[StructureChunk, ...]]:
    page = StructurePage.model_validate(item["page_json"])
    chunks = tuple(StructureChunk.model_validate(chunk) for chunk in item["chunks"])
    if (
        page.id != UUID(str(item["page_id"]))
        or page.page_number != item["page_number"]
        or page.source is None
        or RasterIdentity.from_source(page.source) != RasterIdentity.model_validate(item["raster"])
        or content_digest(
            {
                "page": item["page_json"],
                "invocation": item["invocation_json"],
                "raw": item["raw_output"],
            }
        )
        != item["checkpoint_sha256"]
        or any(
            chunk.page_number != page.page_number
            or not set(chunk.element_ids) <= {e.id for e in page.elements}
            for chunk in chunks
        )
    ):
        raise EvidenceUnavailable("Retained generation is unavailable.")
    asset = retained_asset(row, item)
    if asset and content_digest(page.source.model_dump(mode="json")) != asset.source_render_sha256:
        raise EvidenceUnavailable("Retained generation is unavailable.")
    validate_recorded_request(
        validate_header(row), decode_parse_invocation(item["invocation_json"]), page.source
    )
    return page, chunks

"""Interpret recorded model transcription through explicit anchors and exact typers."""

from typing import Any

from lib.document_parsing.structure import StructurePage
from lib.document_processing.models import content_digest
from lib.extraction.claim_registry import (
    CLAIM_FAMILY_REGISTRIES,
    claim_key_is_admissible,
    claim_value_type_is_admissible,
)
from lib.extraction.native_claims.errors import NativeClaimError
from lib.extraction.native_claims.models import (
    NativeClaim,
    NativeClaimAnchor,
    NativeClaimBinding,
    NativeClaimConfiguration,
    NativeClaimRequest,
    NativePageRequest,
)
from lib.extraction.native_claims.source_repository import NativeClaimSource
from lib.extraction.native_claims.values import type_recorded_text


def normalize_page_claims(
    binding: NativeClaimBinding,
    configuration: NativeClaimConfiguration,
    source: NativeClaimSource,
    request: NativePageRequest,
) -> tuple[NativeClaim, ...]:
    page = next((p for p in source.structure.pages if p.page_number == request.page_number), None)
    if page is None or page.source is None:
        raise NativeClaimError("Native claim page is unavailable.")
    if page.state != "processed" and request.disposition in {"complete", "no_extraction_target"}:
        raise NativeClaimError("Incomplete source cannot claim complete extraction coverage.")
    checkpoint = next(
        p for p in source.manifest["pages"] if p["page_number"] == request.page_number
    )
    claims = tuple(
        _normalize(binding, configuration, page, checkpoint, item) for item in request.claims
    )
    if len({claim.claim_id for claim in claims}) != len(claims):
        raise NativeClaimError("A physical source field may occur only once per native claim set.")
    return tuple(sorted(claims, key=lambda claim: claim.claim_id))


def _normalize(
    binding: NativeClaimBinding,
    configuration: NativeClaimConfiguration,
    page: StructurePage,
    checkpoint: dict[str, Any],
    request: NativeClaimRequest,
) -> NativeClaim:
    if (
        "." not in request.canonical_key
        or request.canonical_key.partition(".")[0] not in CLAIM_FAMILY_REGISTRIES
        or not claim_key_is_admissible(request.canonical_key)
        or not claim_value_type_is_admissible(request.canonical_key, request.value_type)
    ):
        raise NativeClaimError("Native claim key or type is outside its declared family registry.")
    locator = request.anchor
    element = next((e for e in page.elements if e.id == locator.element_id), None)
    if element is None or page.source is None:
        raise NativeClaimError("Native claim element is not on its source page.")
    text, origin, box = element.text, element.text_origin, element.bbox
    row_index = None
    if locator.table_id is not None:
        table = next((t for t in page.tables if t.id == locator.table_id), None)
        cell = next((c for c in table.cells if c.id == locator.cell_id), None) if table else None
        if table is None or table.element_id != element.id or cell is None:
            raise NativeClaimError("Native claim cell is not in its exact source table.")
        text, origin, box, row_index = cell.text, cell.text_origin, cell.bbox, cell.row
    if origin != "model_transcription" or locator.text_end > len(text):
        raise NativeClaimError("Native claim text origin or span is invalid.")
    quote = text[locator.text_start : locator.text_end]
    typed = type_recorded_text(request.value_type, quote)
    physical = content_digest(
        {
            "parse_generation_id": str(binding.processing.parse_generation_id),
            "page_id": str(page.id),
            "element_id": str(element.id),
            "table_id": str(locator.table_id) if locator.table_id else None,
            "row_index": row_index,
        }
    )
    identity = content_digest(
        {
            "claim_set_id": str(binding.claim_set_id),
            "physical_source_id": physical,
            "canonical_key": request.canonical_key,
        }
    )
    return NativeClaim(
        claim_id=identity,
        claim_set_id=binding.claim_set_id,
        document_id=binding.processing.document_id,
        canonical_key=request.canonical_key,
        value_type=request.value_type,
        typed_value=typed,
        raw_value=quote,
        physical_source_id=physical,
        group_id=physical if ".line_item." in request.canonical_key else None,
        anchor=NativeClaimAnchor(
            parse_generation_id=binding.processing.parse_generation_id,
            page_number=page.page_number,
            page_id=page.id,
            source_page_image_sha256=page.source.image_sha256,
            element_id=element.id,
            table_id=locator.table_id,
            cell_id=locator.cell_id,
            row_index=row_index,
            text_start=locator.text_start,
            text_end=locator.text_end,
            source_text=quote,
            bbox=box,
        ),
        configuration_sha256=configuration.fingerprint,
        checkpoint_sha256=checkpoint["checkpoint_sha256"],
        invocation_request_id=checkpoint["invocation"]["request_id"],
        raw_output_sha256=checkpoint["invocation"]["raw_output_sha256"],
    )

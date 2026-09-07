"""Validate sealed storage evidence after the authorized snapshot transaction closes."""

from __future__ import annotations

from typing import Any, Literal
from uuid import UUID

from pydantic import ValidationError

from lib.document_parsing.invocations import decode_parse_invocation
from lib.document_parsing.qwen_page_parser import ParsedSourcePage
from lib.document_parsing.searchable_text import page_chunks
from lib.document_parsing.structure import (
    DocumentStructure,
    SourceInventory,
    StructurePage,
)
from lib.document_processing.checkpoint_validation import validate_checkpoint
from lib.document_processing.configuration_types import (
    AnyParseConfiguration,
    ParseConfigurationV2,
    decode_parse_configuration,
)
from lib.document_processing.errors import ProcessingError
from lib.document_processing.models import content_digest
from lib.documents.access_policy import DocumentAccessContext
from lib.evaluation.capture_models import (
    CaptureDeclaration,
    CaptureIntegrityError,
    PersistedGenerationCapture,
    RegisteredCaptureSource,
)
from lib.evaluation.capture_repository import read_capture_rows
from lib.evaluation.captures import CapturedRawPage, DocumentCapture


def capture_sealed_generation(
    *,
    document_id: UUID,
    processing_run_id: UUID,
    parse_generation_id: UUID,
    access: DocumentAccessContext,
    declaration: CaptureDeclaration,
) -> PersistedGenerationCapture:
    row = read_capture_rows(
        document_id=document_id,
        processing_run_id=processing_run_id,
        parse_generation_id=parse_generation_id,
        access=access,
    )
    return validate_persisted_capture(row, declaration=declaration)


def validate_persisted_capture(
    row: dict[str, Any],
    *,
    declaration: CaptureDeclaration,
) -> PersistedGenerationCapture:
    """No current-generation fallback, runtime inference or artifact I/O."""
    try:
        return _validated_capture(row, declaration)
    except (ValueError, KeyError, TypeError, ProcessingError, ValidationError):
        # Pydantic failures may include private raw text. Do not propagate it.
        raise CaptureIntegrityError(
            "Stored processing capture is inconsistent or unsupported."
        ) from None


def _validated_capture(
    row: dict[str, Any],
    declaration: CaptureDeclaration,
) -> PersistedGenerationCapture:
    configuration = decode_parse_configuration(row["config_json"])
    inventory = SourceInventory.model_validate(row["inventory_json"])
    structure = DocumentStructure.model_validate(row["structure_json"])
    source = RegisteredCaptureSource(
        original_asset_id=row["original_asset_id"],
        original_sha256=row["original_sha256"],
        mime_type=row["mime_type"],
        byte_size=row["byte_size"],
    )
    if (
        row["parse_state"] != "sealed"
        or row["sealed_at"] is None
        or row["run_status"] not in {"sealed", "superseded", "cancelled"}
        or row["creator_run_id"] != row["processing_run_id"]
        or configuration.fingerprint != row["config_sha256"]
        or content_digest(row["inventory_json"]) != row["inventory_sha256"]
        or content_digest(row["structure_json"]) != row["structure_sha256"]
        or structure.processing_run_id != row["processing_run_id"]
        or structure.parse_generation_id != row["parse_generation_id"]
        or structure.source != inventory
        or (source.original_asset_id, source.original_sha256, source.mime_type, source.byte_size)
        != (
            inventory.original_asset_id,
            inventory.original_sha256,
            inventory.mime_type,
            inventory.byte_size,
        )
        or row["asset_sha256"] != source.original_sha256
    ):
        raise ValueError("Stored identity/hash mismatch.")
    checkpoints = _validated_checkpoints(row, inventory, configuration)
    if (
        tuple(item.page for item in checkpoints) != structure.pages
        or tuple(item.invocation for item in checkpoints) != structure.invocations
        or any(page.state in {"failed", "deferred", "unsupported"} for page in structure.pages)
        or tuple(
            chunk
            for page in structure.pages
            for chunk in page_chunks(page, structure.parse_generation_id)
        )
        != structure.chunks
    ):
        raise ValueError("Sealed output does not match exact committed checkpoints.")
    fixture_type, model_mode = _frozen_mode(configuration.model_revision)
    capture = DocumentCapture(
        item_id=declaration.item_id,
        fixture_type=fixture_type,
        model_mode=model_mode,
        commit=declaration.commit,
        configuration=configuration,
        configuration_sha256=row["config_sha256"],
        max_output_tokens=declaration.max_output_tokens,
        temperature=declaration.temperature,
        structure=structure,
        raw_pages=tuple(
            CapturedRawPage(
                request_id=item.invocation.request_id,
                page_number=item.page.page_number,
                raw_output=item.raw_output,
            )
            for item in checkpoints
        ),
    )
    return PersistedGenerationCapture(
        capture=capture,
        document_id=row["document_id"],
        run_status=row["run_status"],
        sealed_at=row["sealed_at"],
        structure_sha256=row["structure_sha256"],
        inventory_sha256=row["inventory_sha256"],
        source=source,
        generation_settings_provenance=(
            "frozen_configuration"
            if isinstance(configuration, ParseConfigurationV2)
            else "externally_declared"
        ),
    )


def _validated_checkpoints(
    row: dict[str, Any],
    inventory: SourceInventory,
    configuration: AnyParseConfiguration,
) -> tuple[ParsedSourcePage, ...]:
    result = []
    for checkpoint in row["checkpoints"]:
        payload = {
            "page": checkpoint["page_json"],
            "invocation": checkpoint["invocation_json"],
            "raw": checkpoint["raw_output"],
        }
        if content_digest(payload) != checkpoint["content_sha256"]:
            raise ValueError("Checkpoint digest mismatch.")
        parsed = ParsedSourcePage(
            StructurePage.model_validate(payload["page"]),
            decode_parse_invocation(payload["invocation"]),
            payload["raw"],
        )
        if (
            UUID(str(checkpoint["parse_generation_id"])),
            checkpoint["page_number"],
            UUID(str(checkpoint["page_id"])),
        ) != (row["parse_generation_id"], parsed.page.page_number, parsed.page.id):
            raise ValueError("Checkpoint identity mismatch.")
        validate_checkpoint(
            parsed,
            generation_id=row["parse_generation_id"],
            inventory=inventory,
            configuration=configuration,
        )
        result.append(parsed)
    return tuple(result)


def _frozen_mode(
    revision: str,
) -> tuple[Literal["deterministic_fixture", "model_backed"], Literal["fixture", "live"]]:
    if revision.startswith("fixture:") and revision.removeprefix("fixture:").strip():
        return "deterministic_fixture", "fixture"
    if revision.startswith("declared-live:") and revision.removeprefix("declared-live:").strip():
        return "model_backed", "live"
    raise ValueError("Frozen configuration has no supported execution declaration.")

"""Exact sealed parse/checkpoint lineage and the 097 domain-lock prefix."""

import hashlib
from dataclasses import dataclass
from typing import Any

from lib.document_parsing.qwen_page_parser import ParsedSourcePage
from lib.document_parsing.structure import DocumentStructure, ParseInvocation, StructurePage
from lib.document_processing.authority_repository import lock_current_run
from lib.document_processing.models import ParseConfiguration, ProcessingBinding, content_digest
from lib.extraction.native_claims.errors import NativeClaimError


@dataclass(frozen=True)
class NativeClaimSource:
    structure: DocumentStructure
    manifest: dict[str, Any]
    household_id: Any


def lock_source(cur: Any, binding: ProcessingBinding) -> NativeClaimSource:
    run = lock_current_run(cur, binding)
    return read_locked_source(cur, binding, run)


def read_locked_source(
    cur: Any, binding: ProcessingBinding, run: dict[str, Any]
) -> NativeClaimSource:
    """Verify immutable source content after the caller locks the document/run."""
    if run["parse_state"] != "sealed":
        raise NativeClaimError("Native claims require a sealed parse generation.")
    cur.execute(
        "SELECT id FROM document_parse_generations WHERE id=%s FOR KEY SHARE",
        (binding.parse_generation_id,),
    )
    cur.execute(
        "SELECT id FROM document_assets WHERE id=%s FOR KEY SHARE", (run["original_asset_id"],)
    )
    if cur.fetchone() is None:
        raise NativeClaimError("Native claim source original is unavailable.")
    cur.execute(
        "SELECT * FROM document_parse_page_checkpoints WHERE parse_generation_id=%s "
        "ORDER BY page_number FOR KEY SHARE",
        (binding.parse_generation_id,),
    )
    rows = cur.fetchall()
    structure = DocumentStructure.model_validate(run["structure_json"])
    config = ParseConfiguration.model_validate(run["config_json"])
    if (
        structure.parse_generation_id != binding.parse_generation_id
        or structure.processing_run_id != binding.processing_run_id
        or structure.source.original_asset_id != run["original_asset_id"]
        or structure.source.original_sha256 != run["original_sha256"]
        or structure.source.model_dump(mode="json") != run["inventory_json"]
        or content_digest(run["structure_json"]) != run["structure_sha256"]
        or content_digest(run["inventory_json"]) != run["inventory_sha256"]
        or config.fingerprint != run["config_sha256"]
        or config.source_engine != "qwen3_8_27b"
        or len(rows) != len(structure.pages)
    ):
        raise NativeClaimError("Native claim source binding is inconsistent.")
    pages = []
    for row, page, invocation in zip(rows, structure.pages, structure.invocations, strict=True):
        checkpoint = ParsedSourcePage(
            StructurePage.model_validate(row["page_json"]),
            ParseInvocation.model_validate(row["invocation_json"]),
            row["raw_output"],
        )
        digest = content_digest(
            {
                "page": row["page_json"],
                "invocation": row["invocation_json"],
                "raw": row["raw_output"],
            }
        )
        if (
            page != checkpoint.page
            or invocation != checkpoint.invocation
            or row["page_id"] != page.id
            or row["page_number"] != page.page_number
            or digest != row["content_sha256"]
            or page.source is None
            or hashlib.sha256(row["raw_output"].encode()).hexdigest()
            != invocation.raw_output_sha256
            or invocation.page_numbers != (page.page_number,)
            or invocation.profile != config.profile
            or invocation.served_model != config.served_model
            or invocation.source_engine != config.source_engine
            or invocation.prompt_version != config.prompt_version
            or invocation.output_schema_version != config.output_schema_version
        ):
            raise NativeClaimError("Native claim checkpoint binding is inconsistent.")
        pages.append(
            {
                "page_number": page.page_number,
                "page_id": str(page.id),
                "checkpoint_sha256": digest,
                "source_page_image_sha256": page.source.image_sha256,
                "invocation": invocation.model_dump(mode="json"),
            }
        )
    manifest = {
        "schema_version": "native_claim_source.v1",
        "document_id": str(binding.document_id),
        "processing_run_id": str(binding.processing_run_id),
        "parse_generation_id": str(binding.parse_generation_id),
        "original_asset_id": str(run["original_asset_id"]),
        "original_sha256": run["original_sha256"],
        "structure_sha256": run["structure_sha256"],
        "inventory_sha256": run["inventory_sha256"],
        "parse_configuration_sha256": run["config_sha256"],
        "pages": pages,
    }
    return NativeClaimSource(structure, manifest, run["household_id"])

"""Insert-or-verify candidate pages and one sealed structural artifact per generation."""

from __future__ import annotations

from typing import Any

from psycopg.types.json import Jsonb

from lib.document_parsing.qwen_page_parser import ParsedSourcePage
from lib.document_parsing.searchable_text import page_chunks
from lib.document_parsing.structure import (
    DocumentStructure,
    ParseInvocation,
    SourceInventory,
    StructurePage,
)
from lib.document_processing.authority_repository import lock_current_run
from lib.document_processing.checkpoint_validation import validate_checkpoint
from lib.document_processing.errors import CheckpointConflict, ProcessingError
from lib.document_processing.models import ParseConfiguration, ProcessingBinding, content_digest


def initialize_inventory(cur: Any, binding: ProcessingBinding, inventory: SourceInventory) -> None:
    run = lock_current_run(cur, binding)
    if (
        inventory.original_asset_id != run["original_asset_id"]
        or inventory.original_sha256 != run["original_sha256"]
    ):
        raise ProcessingError("Inventory does not match the requested original.")
    cur.execute(
        "SELECT mime_type, byte_size FROM document_assets WHERE id = %s",
        (inventory.original_asset_id,),
    )
    asset = cur.fetchone()
    if asset is None or (asset["mime_type"], asset["byte_size"]) != (
        inventory.mime_type,
        inventory.byte_size,
    ):
        raise ProcessingError("Inventory does not match the registered source metadata.")
    payload = inventory.model_dump(mode="json")
    digest = content_digest(payload)
    if run["inventory_json"] is not None:
        if run["inventory_sha256"] != digest or run["inventory_json"] != payload:
            raise CheckpointConflict("Parse inventory was already assigned different content.")
        return
    cur.execute(
        """UPDATE document_parse_generations SET inventory_json = %s, inventory_sha256 = %s
        WHERE id = %s AND state = 'building' AND inventory_json IS NULL""",
        (Jsonb(payload), digest, binding.parse_generation_id),
    )
    if cur.rowcount != 1:
        raise CheckpointConflict("Parse inventory cannot be assigned to this generation.")


def persist_checkpoint(cur: Any, binding: ProcessingBinding, checkpoint: ParsedSourcePage) -> None:
    run = lock_current_run(cur, binding)
    if run["inventory_json"] is None:
        raise ProcessingError("Source inventory must be assigned before page checkpoints.")
    validate_checkpoint(
        checkpoint,
        generation_id=binding.parse_generation_id,
        inventory=SourceInventory.model_validate(run["inventory_json"]),
        configuration=ParseConfiguration.model_validate(run["config_json"]),
    )
    page = checkpoint.page.model_dump(mode="json")
    invocation = checkpoint.invocation.model_dump(mode="json")
    digest = content_digest({"page": page, "invocation": invocation, "raw": checkpoint.raw_output})
    cur.execute(
        """SELECT content_sha256 FROM document_parse_page_checkpoints
        WHERE parse_generation_id = %s AND page_number = %s""",
        (binding.parse_generation_id, checkpoint.page.page_number),
    )
    existing = cur.fetchone()
    if existing:
        if existing["content_sha256"] != digest:
            raise CheckpointConflict("Checkpoint already exists with different content.")
        return
    if run["parse_state"] != "building":
        raise CheckpointConflict("Sealed generations cannot acquire new checkpoints.")
    cur.execute(
        """INSERT INTO document_parse_page_checkpoints
        (parse_generation_id, page_number, page_id, page_json, invocation_json,
         raw_output, content_sha256)
        VALUES (%s,%s,%s,%s,%s,%s,%s)""",
        (
            binding.parse_generation_id,
            checkpoint.page.page_number,
            checkpoint.page.id,
            Jsonb(page),
            Jsonb(invocation),
            checkpoint.raw_output,
            digest,
        ),
    )


def list_checkpoints(cur: Any, binding: ProcessingBinding) -> tuple[ParsedSourcePage, ...]:
    lock_current_run(cur, binding)
    return _checkpoint_rows(cur, binding)


def _checkpoint_rows(cur: Any, binding: ProcessingBinding) -> tuple[ParsedSourcePage, ...]:
    cur.execute(
        """SELECT page_json, invocation_json, raw_output FROM document_parse_page_checkpoints
        WHERE parse_generation_id = %s ORDER BY page_number""",
        (binding.parse_generation_id,),
    )
    return tuple(
        ParsedSourcePage(
            StructurePage.model_validate(row["page_json"]),
            ParseInvocation.model_validate(row["invocation_json"]),
            row["raw_output"],
        )
        for row in cur.fetchall()
    )


def seal_generation(cur: Any, binding: ProcessingBinding, structure: DocumentStructure) -> str:
    run = lock_current_run(cur, binding)
    if (
        structure.parse_generation_id != binding.parse_generation_id
        or structure.processing_run_id != binding.processing_run_id
        or run["inventory_json"] != structure.source.model_dump(mode="json")
    ):
        raise ProcessingError("Structural artifact does not match its run and original inventory.")
    checkpoints = _checkpoint_rows(cur, binding)
    if (
        tuple(item.page for item in checkpoints) != structure.pages
        or tuple(item.invocation for item in checkpoints) != structure.invocations
        or any(page.state in {"deferred", "failed", "unsupported"} for page in structure.pages)
        or tuple(
            chunk
            for page in structure.pages
            for chunk in page_chunks(page, binding.parse_generation_id)
        )
        != structure.chunks
    ):
        raise ProcessingError("Structural artifact does not match complete committed checkpoints.")
    payload = structure.model_dump(mode="json")
    digest = content_digest(payload)
    if run["parse_state"] == "sealed":
        if run["structure_sha256"] != digest or run["structure_json"] != payload:
            raise CheckpointConflict("Parse generation was already sealed with different content.")
        return digest
    cur.execute(
        """UPDATE document_parse_generations SET state = 'sealed', structure_json = %s,
        structure_sha256 = %s, sealed_at = clock_timestamp()
        WHERE id = %s AND state = 'building'""",
        (Jsonb(payload), digest, binding.parse_generation_id),
    )
    cur.execute(
        "UPDATE document_processing_runs SET status = 'sealed' WHERE id = %s",
        (binding.processing_run_id,),
    )
    return digest

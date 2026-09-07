"""Writer authority only; historical reads must not depend on an active job/run."""

from __future__ import annotations

from typing import Any, cast

from lib.document_processing.authority_repository import fence_processing_attempt, lock_current_run
from lib.document_processing.errors import ProcessingAuthorityLost
from lib.document_processing.models import ProcessingBinding
from lib.evidence.errors import EvidenceConflict
from lib.evidence.models import ExpectedRenderSet, RenderSetBinding
from lib.jobs.ownership import current_job_attempt
from lib.storage import lock_content_hash


def lock_source(
    cur: Any,
    binding: ProcessingBinding,
    *,
    include_artifacts: bool = False,
    checkpoint_page_number: int | None = None,
) -> dict[str, Any]:
    run = lock_current_run(cur, binding, include_artifacts=include_artifacts)
    if run["parse_state"] != "sealed":
        raise EvidenceConflict("Retained evidence requires a sealed parse generation.")
    cur.execute(
        "SELECT id FROM document_parse_generations WHERE id=%s FOR KEY SHARE",
        (binding.parse_generation_id,),
    )
    cur.execute(
        "SELECT id FROM document_assets WHERE id=%s FOR KEY SHARE", (run["original_asset_id"],)
    )
    if cur.fetchone() is None:
        raise EvidenceConflict("Retained original asset is unavailable.")
    if checkpoint_page_number is not None:
        cur.execute(
            "SELECT page_number FROM document_parse_page_checkpoints "
            "WHERE parse_generation_id=%s AND page_number=%s FOR KEY SHARE",
            (binding.parse_generation_id, checkpoint_page_number),
        )
        if cur.fetchone() is None:
            raise EvidenceConflict("Retained source checkpoint is unavailable.")
    return run


def lock_set(
    cur: Any,
    binding: RenderSetBinding,
    *,
    content_hashes: tuple[str, ...] = (),
    checkpoint_page_number: int | None = None,
) -> tuple[dict[str, Any], ExpectedRenderSet]:
    run = lock_source(cur, binding.processing, checkpoint_page_number=checkpoint_page_number)
    for digest in sorted(set(content_hashes)):
        lock_content_hash(cur, digest)
    cur.execute(
        "SELECT * FROM document_parse_render_sets WHERE id=%s AND document_id=%s "
        "AND processing_run_id=%s AND parse_generation_id=%s FOR UPDATE",
        (
            binding.render_set_id,
            binding.processing.document_id,
            binding.processing.processing_run_id,
            binding.processing.parse_generation_id,
        ),
    )
    row = cur.fetchone()
    if row is None:
        raise ProcessingAuthorityLost("Retained evidence binding is unavailable.")
    expected = ExpectedRenderSet.model_validate(row["expected_json"])
    if (
        expected.fingerprint != row["expected_sha256"]
        or expected.structure_sha256 != run["structure_sha256"]
        or expected.inventory_sha256 != run["inventory_sha256"]
        or expected.parse_configuration_sha256 != run["config_sha256"]
        or expected.processing_run_id != run["id"]
        or expected.parse_generation_id != run["parse_generation_id"]
        or expected.document_id != run["document_id"]
        or expected.original_asset_id != run["original_asset_id"]
        or expected.original_sha256 != run["original_sha256"]
    ):
        raise EvidenceConflict("Retained evidence identity differs from its sealed source.")
    require_producer(row)
    return cast(dict[str, Any], row), expected


def require_producer(row: dict[str, Any]) -> None:
    attempt = current_job_attempt()
    if attempt is None or row["producer_job_id"] != attempt.job_id:
        raise ProcessingAuthorityLost("Retained evidence requires its exact claimed producer.")


def fence_set(cur: Any, binding: RenderSetBinding) -> None:
    fence_processing_attempt(cur, binding.processing)
    cur.execute(
        "SELECT producer_job_id FROM document_parse_render_sets WHERE id=%s",
        (binding.render_set_id,),
    )
    row = cur.fetchone()
    if row is None:
        raise ProcessingAuthorityLost("Retained evidence binding is unavailable.")
    require_producer(row)

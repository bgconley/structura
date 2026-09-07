"""097 request/run locks, then candidate headers, then live job ownership.

Every public mutation uses this order. All source FK references are prelocked
before the job fence; no transaction is retained over filesystem or model IO.
"""

from __future__ import annotations

from typing import Any, cast

from lib.document_parsing.structure import DocumentStructure
from lib.document_processing.authority_repository import fence_processing_attempt, lock_current_run
from lib.document_processing.models import ParseConfiguration, ProcessingBinding, content_digest
from lib.jobs.ownership import current_job_attempt
from lib.search.indexing.configuration import IndexConfiguration
from lib.search.indexing.errors import IndexAuthorityLost, IndexCandidateError
from lib.search.indexing.models import IndexBinding
from lib.storage.reference_cleanup import lock_content_hash


def lock_source(cur: Any, binding: ProcessingBinding) -> dict[str, Any]:
    run = lock_current_run(cur, binding)
    if run["parse_state"] != "sealed":
        raise IndexCandidateError("Candidate indexing requires a sealed parse generation.")
    cur.execute(
        "SELECT id FROM document_parse_generations WHERE id=%s FOR KEY SHARE",
        (binding.parse_generation_id,),
    )
    cur.execute(
        "SELECT id FROM document_assets WHERE id=%s FOR KEY SHARE", (run["original_asset_id"],)
    )
    if cur.fetchone() is None:
        raise IndexCandidateError("Candidate original asset is unavailable.")
    cur.execute(
        "SELECT page_number FROM document_parse_page_checkpoints WHERE parse_generation_id=%s "
        "ORDER BY page_number FOR KEY SHARE",
        (binding.parse_generation_id,),
    )
    page_numbers = tuple(row["page_number"] for row in cur.fetchall())
    structure = DocumentStructure.model_validate(run["structure_json"])
    configuration = ParseConfiguration.model_validate(run["config_json"])
    if (
        structure.parse_generation_id != binding.parse_generation_id
        or structure.processing_run_id != binding.processing_run_id
        or structure.source.original_asset_id != run["original_asset_id"]
        or structure.source.original_sha256 != run["original_sha256"]
        or structure.source.model_dump(mode="json") != run["inventory_json"]
        or content_digest(run["structure_json"]) != run["structure_sha256"]
        or content_digest(run["inventory_json"]) != run["inventory_sha256"]
        or configuration.fingerprint != run["config_sha256"]
        or page_numbers != tuple(page.page_number for page in structure.pages)
    ):
        raise IndexCandidateError("Sealed parse identity does not match its immutable source.")
    return run


def lock_index(
    cur: Any,
    binding: IndexBinding,
    *,
    render_hashes: tuple[str, ...] = (),
) -> tuple[dict[str, Any], dict[str, Any]]:
    run = lock_source(cur, binding.processing)
    # Ingest can hold a duplicate document FK before its content lock. Keep this
    # after the document/source locks, and before candidate/job locks.
    for digest in sorted(set(render_hashes)):
        lock_content_hash(cur, digest)
    return run, _lock_header(cur, binding, run, include_artifacts=True)


def lock_checkpoint_index(cur: Any, binding: IndexBinding) -> dict[str, Any]:
    run = lock_current_run(cur, binding.processing, include_artifacts=False)
    if (
        run["parse_state"] != "sealed"
        or ParseConfiguration.model_validate(run["config_json"]).fingerprint != run["config_sha256"]
    ):
        raise IndexCandidateError("Candidate source is not a consistent sealed generation.")
    return _lock_header(cur, binding, run, include_artifacts=False)


def _lock_header(
    cur: Any, binding: IndexBinding, run: dict[str, Any], *, include_artifacts: bool
) -> dict[str, Any]:
    from psycopg import sql

    columns = (
        "*"
        if include_artifacts
        else "id,config_json,config_sha256,structure_sha256,inventory_sha256,"
        "parse_config_sha256,state,manifest_sha256"
    )
    cur.execute(
        sql.SQL(
            "SELECT {columns} FROM document_index_generations WHERE id=%s AND document_id=%s "
            "AND processing_run_id=%s AND parse_generation_id=%s FOR UPDATE"
        ).format(columns=sql.SQL(columns)),
        (
            binding.index_generation_id,
            binding.processing.document_id,
            binding.processing.processing_run_id,
            binding.processing.parse_generation_id,
        ),
    )
    header = cur.fetchone()
    if header is None:
        raise IndexAuthorityLost("Candidate index binding is unavailable.")
    config = IndexConfiguration.model_validate(header["config_json"])
    if (
        config.fingerprint != header["config_sha256"]
        or header["structure_sha256"] != run["structure_sha256"]
        or header["inventory_sha256"] != run["inventory_sha256"]
        or header["parse_config_sha256"] != run["config_sha256"]
    ):
        raise IndexCandidateError("Candidate index does not match its frozen source/configuration.")
    assert_current_index(cur, binding)
    return cast(dict[str, Any], header)


def assert_current_index(cur: Any, binding: IndexBinding) -> None:
    attempt = current_job_attempt()
    if attempt is None:
        raise IndexAuthorityLost("Candidate indexing requires a claimed producer job.")
    # Fresh statement after any lock wait; a previous index can never regain its slot.
    cur.execute(
        """SELECT i.id FROM document_index_generations i
        WHERE i.id=%s AND i.revoked_at IS NULL AND i.producer_job_id=%s
          AND NOT EXISTS (SELECT 1 FROM document_index_generations later
            WHERE later.document_id=i.document_id AND later.slot=i.slot
              AND later.generation>i.generation)""",
        (binding.index_generation_id, attempt.job_id),
    )
    if cur.fetchone() is None:
        raise IndexAuthorityLost("Candidate index no longer owns its publication slot.")


def fence_index(cur: Any, binding: IndexBinding) -> None:
    fence_processing_attempt(cur, binding.processing)
    assert_current_index(cur, binding)

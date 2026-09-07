"""Source/set locks precede producer job fencing; no implicit current publication."""

from typing import Any

from lib.document_processing.authority_repository import fence_processing_attempt
from lib.document_processing.models import content_digest
from lib.extraction.native_claims.errors import NativeClaimConflict, NativeClaimError
from lib.extraction.native_claims.models import NativeClaimBinding
from lib.extraction.native_claims.record_types import decode_configuration
from lib.extraction.native_claims.source_repository import NativeClaimSource, lock_source
from lib.jobs.ownership import current_job_attempt


def lock_set(cur: Any, binding: NativeClaimBinding) -> tuple[dict[str, Any], NativeClaimSource]:
    source = lock_source(cur, binding.processing)
    cur.execute(
        "SELECT * FROM native_claim_sets WHERE id=%s AND document_id=%s "
        "AND processing_run_id=%s AND parse_generation_id=%s FOR UPDATE",
        (
            binding.claim_set_id,
            binding.processing.document_id,
            binding.processing.processing_run_id,
            binding.processing.parse_generation_id,
        ),
    )
    row = cur.fetchone()
    if row is None:
        raise NativeClaimError("Native claim set is unavailable.")
    validate_set_source(row, source)
    assert_producer(row)
    return row, source


def validate_set_source(row: dict[str, Any], source: NativeClaimSource) -> None:
    config = decode_configuration(row["configuration_json"])
    if (
        config.fingerprint != row["configuration_sha256"]
        or row.get("interpretation_kind", "structure_normalization") != config.derivation
        or source.manifest != row["source_manifest_json"]
        or content_digest(source.manifest) != row["source_manifest_sha256"]
        or len(source.structure.pages) != row["expected_pages"]
    ):
        raise NativeClaimConflict("Native claim set does not match its immutable source.")


def assert_producer(row: dict[str, Any]) -> None:
    attempt = current_job_attempt()
    if attempt is None or attempt.job_id != row["producer_job_id"]:
        raise NativeClaimError("Native claim mutation requires its bound producer job.")


def fence_set(cur: Any, binding: NativeClaimBinding, row: dict[str, Any]) -> None:
    assert_producer(row)
    fence_processing_attempt(cur, binding.processing)

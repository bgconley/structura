"""Allocate one immutable native interpretation of a sealed parse/configuration."""

from typing import Any
from uuid import uuid5

from psycopg.types.json import Jsonb

from lib.document_processing.authority_repository import fence_processing_attempt
from lib.document_processing.models import ProcessingBinding, content_digest
from lib.extraction.native_claims.authority_repository import fence_set, lock_set
from lib.extraction.native_claims.errors import NativeClaimError
from lib.extraction.native_claims.models import NativeClaimBinding, NativeClaimConfiguration
from lib.extraction.native_claims.source_repository import lock_source
from lib.jobs.ownership import current_job_attempt


def start_set(
    cur: Any,
    processing: ProcessingBinding,
    configuration: NativeClaimConfiguration,
) -> NativeClaimBinding:
    config = NativeClaimConfiguration.model_validate(configuration.model_dump(mode="json"))
    if config.registry_sha256 != NativeClaimConfiguration().registry_sha256:
        raise NativeClaimError("Native claim registry configuration is unsupported.")
    source = lock_source(cur, processing)
    identity = uuid5(processing.parse_generation_id, f"native-claims-v1:{config.fingerprint}")
    binding = NativeClaimBinding(processing, identity)
    cur.execute("SELECT id FROM native_claim_sets WHERE id=%s", (identity,))
    if cur.fetchone():
        row, _ = lock_set(cur, binding)
        fence_set(cur, binding, row)
        return binding
    # All source FKs are already locked. Producer FK acquisition reuses the
    # live job/root locks obtained here, as in the 098 header allocator.
    fence_processing_attempt(cur, processing)
    attempt = current_job_attempt()
    if attempt is None:
        raise NativeClaimError("Native claims require a claimed producer job.")
    cur.execute(
        """INSERT INTO native_claim_sets
        (id,document_id,household_id,processing_run_id,parse_generation_id,producer_job_id,
         configuration_json,configuration_sha256,source_manifest_json,source_manifest_sha256,
         expected_pages) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
        (
            identity,
            processing.document_id,
            source.household_id,
            processing.processing_run_id,
            processing.parse_generation_id,
            attempt.job_id,
            Jsonb(config.model_dump(mode="json")),
            config.fingerprint,
            Jsonb(source.manifest),
            content_digest(source.manifest),
            len(source.structure.pages),
        ),
    )
    fence_processing_attempt(cur, processing)
    return binding

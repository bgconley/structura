"""Fixed-slot build allocation and permanent supersession; no search selection."""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

from psycopg.types.json import Jsonb

from lib.document_processing.authority_repository import fence_processing_attempt
from lib.document_processing.models import ProcessingBinding
from lib.jobs.ownership import current_job_attempt
from lib.search.indexing.authority_repository import fence_index, lock_index, lock_source
from lib.search.indexing.configuration import IndexConfiguration
from lib.search.indexing.errors import IndexAuthorityLost, IndexCheckpointConflict
from lib.search.indexing.models import IndexBinding


def start_index(
    cur: Any,
    processing: ProcessingBinding,
    *,
    request_key: UUID,
    configuration: IndexConfiguration,
) -> IndexBinding:
    configuration = IndexConfiguration.model_validate(configuration.model_dump(mode="json"))
    run = lock_source(cur, processing)
    cur.execute(
        "SELECT * FROM document_index_generations WHERE processing_run_id=%s AND "
        "request_key=%s FOR UPDATE",
        (processing.processing_run_id, request_key),
    )
    existing = cur.fetchone()
    if existing:
        binding = IndexBinding(processing, existing["id"])
        if existing["config_json"] != configuration.model_dump(mode="json"):
            raise IndexCheckpointConflict(
                "Candidate request key already has a different configuration."
            )
        fence_index(cur, binding)
        return binding
    # The document lock obtained by lock_source serializes every slot allocator.
    cur.execute(
        "SELECT COALESCE(MAX(generation),0)+1 AS generation FROM document_index_generations "
        "WHERE document_id=%s AND slot='native-parse-candidate-v1'",
        (processing.document_id,),
    )
    generation = cur.fetchone()["generation"]
    cur.execute(
        "UPDATE document_index_generations SET revoked_at=clock_timestamp() "
        "WHERE document_id=%s AND slot='native-parse-candidate-v1' AND revoked_at IS NULL",
        (processing.document_id,),
    )
    # Prelock producer/root before its FK INSERT. Source FKs were prelocked first.
    fence_processing_attempt(cur, processing)
    attempt = current_job_attempt()
    if attempt is None:
        raise IndexAuthorityLost("Candidate indexing requires a claimed producer job.")
    binding = IndexBinding(processing, uuid4())
    cur.execute(
        """INSERT INTO document_index_generations
        (id,document_id,household_id,processing_run_id,parse_generation_id,producer_job_id,
         generation,request_key,structure_sha256,inventory_sha256,parse_config_sha256,
         config_json,config_sha256)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
        (
            binding.index_generation_id,
            processing.document_id,
            run["household_id"],
            processing.processing_run_id,
            processing.parse_generation_id,
            attempt.job_id,
            generation,
            request_key,
            run["structure_sha256"],
            run["inventory_sha256"],
            run["config_sha256"],
            Jsonb(configuration.model_dump(mode="json")),
            configuration.fingerprint,
        ),
    )
    fence_index(cur, binding)
    return binding


def cancel_index(cur: Any, binding: IndexBinding) -> None:
    lock_index(cur, binding)
    cur.execute(
        "UPDATE document_index_generations SET revoked_at=clock_timestamp() WHERE id=%s",
        (binding.index_generation_id,),
    )
    # A cancellation preserves the historical sealed state, and cannot revive it.
    fence_processing_attempt(cur, binding.processing)

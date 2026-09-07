"""Bounded native candidate embedding under the caller's independently renewed lease."""

from __future__ import annotations

import time
from uuid import uuid4

from lib.document_processing.models import content_digest
from lib.jobs.ownership import current_job_attempt
from lib.model_runtime.contracts import EmbeddingRequest
from lib.model_runtime.embedding_identity import embedding_input_hashes
from lib.search.embeddings.validation import validated_response_vectors
from lib.search.indexing.errors import IndexAuthorityLost, IndexCandidateError
from lib.search.indexing.execution_inputs import verified_model_input
from lib.search.indexing.model_clients import CandidateEmbeddingClients
from lib.search.indexing.models import (
    IndexBinding,
    IndexExecutionResult,
    IndexModalityCounts,
    PreparedIndexSnapshot,
    VectorObservation,
)
from lib.search.indexing.service import CandidateIndexService
from lib.storage import ObjectStorage


def execute_index_candidate(
    binding: IndexBinding,
    *,
    clients: CandidateEmbeddingClients,
    storage: ObjectStorage,
    service: CandidateIndexService,
    max_new_inputs: int = 128,
    timeout_seconds: int = 90,
) -> IndexExecutionResult:
    """One input per HTTP call; no implicit retries, fanout, ACK or active selection.

    Call under keep_job_lease. A pending result is an explicit bounded continuation,
    never a successful job completion. Only persisted before/after checkpoint
    state contributes completion/resume counts. Adapter attempts are observed here;
    independent transport observation is required for a live HTTP evidence report.
    """
    if type(max_new_inputs) is not int or not 1 <= max_new_inputs <= 4096:
        raise IndexCandidateError("Candidate execution input budget must be between 1 and 4096.")
    if type(timeout_seconds) is not int or not 1 <= timeout_seconds <= 120:
        raise IndexCandidateError("Candidate request timeout must be between 1 and 120 seconds.")
    if current_job_attempt() is None:
        raise IndexAuthorityLost("Candidate execution requires a claimed producer job.")
    start = time.monotonic()
    snapshot = service.load_prepared(binding)
    clients.validate(snapshot.configuration)
    completed_before = set(snapshot.completed_input_ids)
    pending = tuple(item for item in snapshot.manifest.inputs if item.id not in completed_before)
    started = completed = 0
    for item in pending[:max_new_inputs]:
        value = verified_model_input(item, snapshot, storage)
        client = clients.for_modality(item.modality)
        request = EmbeddingRequest(
            profile_name=snapshot.configuration.space(item.modality).profile,
            inputs=(value,),
            output_dimensions=snapshot.configuration.space(item.modality).dimensions,
            timeout_seconds=timeout_seconds,
            purpose="document",
        )
        if embedding_input_hashes(request, client.profile) != (item.model_input_sha256,):
            raise IndexCandidateError(
                "Embedding request differs from its frozen input/model identity."
            )
        invocation = uuid4()
        # Expensive object reads/hashing/PNG validation happen first; no DB TX is
        # open during HTTP. One input means the client's individual-request path
        # cannot conceal a later page dispatch after this authority check.
        service.assert_authority(binding)
        started += 1
        response = client.embed(request)
        completed += 1
        vectors = validated_response_vectors(response, request=request, profile=client.profile)
        if response.identity_source != "reported_model":
            raise IndexCandidateError("Candidate response must report its expected model identity.")
        service.checkpoint(
            binding,
            VectorObservation(
                input_id=item.id,
                model_input_sha256=response.input_sha256[0],
                values=vectors[0],
                profile=response.profile_name,
                reported_model=response.model_name,
                reported_model_version=response.model_version,
                declared_artifact_revision=response.artifact_revision or "",
                identity_source=response.identity_source,
                model_mode=snapshot.configuration.model_mode,
                invocation_id=invocation,
                latency_ms=response.latency_ms,
            ),
        )
    after = service.load_prepared(binding)
    if after.manifest != snapshot.manifest or after.configuration != snapshot.configuration:
        raise IndexCandidateError("Candidate execution snapshot changed unexpectedly.")
    done = len(after.completed_input_ids) == len(after.manifest.inputs)
    completion = service.seal(binding) if done else None
    return IndexExecutionResult(
        state="sealed" if done else "pending",
        manifest_sha256=after.manifest.fingerprint,
        completion_sha256=content_digest(completion) if completion is not None else None,
        counts=_counts(snapshot, after),
        adapter_calls_started=started,
        adapter_calls_completed=completed,
        elapsed_ms=max(0, int((time.monotonic() - start) * 1000)),
        model_mode=after.configuration.model_mode,
        timeout_seconds=timeout_seconds,
        max_new_inputs=max_new_inputs,
    )


def _counts(
    before: PreparedIndexSnapshot, after: PreparedIndexSnapshot
) -> tuple[IndexModalityCounts, ...]:
    completed_before = set(before.completed_input_ids)
    completed_after = set(after.completed_input_ids)
    results = []
    for modality in after.configuration.modalities:
        inputs = {item.id for item in after.manifest.inputs if item.modality == modality}
        done = inputs & completed_after
        resumed = inputs & completed_before
        results.append(
            IndexModalityCounts(
                modality=modality,
                eligible=len(inputs),
                completed=len(done),
                resumed=len(resumed),
                new=len(done - resumed),
                remaining=len(inputs - done),
            )
        )
    return tuple(results)

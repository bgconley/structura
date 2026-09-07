"""Real Oxcart parse -> persisted Blackbird document vectors -> compatible queries.

Uses one pre-authored synthetic original in an isolated database. It does not
activate application search, infer production quality, or alter resident models.
"""

from __future__ import annotations

import argparse
import hashlib
import subprocess  # nosec B404
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any, TypedDict
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from lib.config import Settings, get_settings  # noqa: E402
from lib.document_processing.models import ProcessingRun  # noqa: E402
from lib.document_processing.parser_configuration import DeclaredParserDeployment  # noqa: E402
from lib.evaluation.annotations import DocumentAnnotation  # noqa: E402
from lib.model_runtime.clients.text_embeddings import TextEmbeddingClient  # noqa: E402
from lib.model_runtime.clients.visual_embeddings import VisualQueryEmbeddingClient  # noqa: E402
from lib.model_runtime.contracts import (  # noqa: E402
    EmbeddingInput,
    EmbeddingRequest,
    EmbeddingResponse,
)
from lib.model_runtime.credentials import model_api_key  # noqa: E402
from lib.model_runtime.ingestion_clients import ingestion_vision_client  # noqa: E402
from lib.model_runtime.profiles import get_model_profile  # noqa: E402
from lib.search.embeddings.validation import validated_response_vectors  # noqa: E402
from lib.search.indexing.configuration import IndexConfiguration, index_configuration  # noqa: E402
from lib.search.indexing.execution import execute_index_candidate  # noqa: E402
from lib.search.indexing.execution_inputs import prepare_index_candidate  # noqa: E402
from lib.search.indexing.model_clients import candidate_embedding_clients  # noqa: E402
from lib.search.indexing.service import CandidateIndexService  # noqa: E402
from scripts.gpu.index_probe_evidence import (  # noqa: E402
    ObservedTransport,
    PersistedProbeVector,
    capture_index_vectors,
)
from scripts.gpu.probe_database import verify_isolated_database  # noqa: E402
from scripts.gpu.probe_embedding_profiles import cosine  # noqa: E402
from scripts.gpu.probe_persisted_parse import (  # noqa: E402
    ObservedClient,
    ProbeSource,
    freeze_reference,
    ingest_and_replay,
    register_source,
    score_persisted_run,
    write_private,
)
from scripts.gpu.probe_retained_evidence import (  # noqa: E402
    retain_and_replay,
    verify_historical_api,
)

QUERIES = (
    ("Which page has the invoice line items and service amount 12.50?", 1),
    ("When is payment due on 2026-09-30?", 2),
)


class RankedInput(TypedDict):
    input_id: str
    page_number: int
    similarity: float


def query_persisted_vectors(
    vectors: tuple[PersistedProbeVector, ...],
    configuration: IndexConfiguration,
    settings: Settings,
) -> dict[str, Any]:
    measurements = []
    modalities = []
    for modality in configuration.modalities:
        space = configuration.space(modality)
        profile = get_model_profile(space.profile)
        transport = ObservedTransport()
        try:
            client_type = TextEmbeddingClient if modality == "text" else VisualQueryEmbeddingClient
            client = client_type(
                profile=profile,
                http_client_base_url=(
                    settings.model_text_embed_url
                    if modality == "text"
                    else settings.model_visual_embed_url
                ),
                api_key=model_api_key(
                    settings.model_text_embed_api_key
                    if modality == "text"
                    else settings.model_visual_embed_api_key,
                    settings.model_text_embed_api_key_file
                    if modality == "text"
                    else settings.model_visual_embed_api_key_file,
                ),
                transport=transport,
            )
            request = EmbeddingRequest(
                profile_name=space.profile,
                inputs=tuple(EmbeddingInput(text=text) for text, _ in QUERIES),
                output_dimensions=space.dimensions,
                timeout_seconds=90,
                purpose="query",
            )
            response = client.embed(request)
            encoded = validated_response_vectors(response, request=request, profile=profile)
            expected_calls = len(QUERIES) if modality == "visual" else 1
            if transport.started != expected_calls or transport.responses != expected_calls:
                raise RuntimeError("Query HTTP counts differ from the frozen protocol contract.")
            modalities.append(
                {
                    "modality": modality,
                    "profile": response.profile_name,
                    "reported_model": response.model_name,
                    "reported_model_version": response.model_version,
                    "identity_source": response.identity_source,
                    "declared_artifact_revision": response.artifact_revision,
                    "actual_http_attempts": transport.started,
                    "actual_http_responses": transport.responses,
                    "query_count": len(QUERIES),
                    "request_latency_ms": response.latency_ms,
                }
            )
            measurements.extend(_query_measurements(vectors, modality, response, encoded))
        finally:
            transport.close()
    return {"modalities": modalities, "measurements": measurements}


def _query_measurements(
    vectors: tuple[PersistedProbeVector, ...],
    modality: str,
    response: EmbeddingResponse,
    encoded: tuple[tuple[float, ...], ...],
) -> list[dict[str, Any]]:
    measurements = []
    for (text, expected_page), query, query_sha in zip(
        QUERIES, encoded, response.input_sha256, strict=True
    ):
        ranked = sorted(
            (
                RankedInput(
                    input_id=str(vector.input_id),
                    page_number=vector.page_number,
                    similarity=cosine(query, vector.values),
                )
                for vector in vectors
                if vector.modality == modality
            ),
            key=lambda item: (-item["similarity"], item["input_id"]),
        )
        measurements.append(
            {
                "modality": modality,
                "query": text,
                "expected_page": expected_page,
                "top_page_matches": bool(ranked and ranked[0]["page_number"] == expected_page),
                "ranked_inputs": ranked,
                "profile": response.profile_name,
                "query_input_sha256": query_sha,
                "query_vector": query,
                "purpose": "query",
            }
        )
    return measurements


def index_and_replay(
    run: ProcessingRun, source: ProbeSource, settings: Settings, output_dir: Path
) -> dict[str, Any]:
    config = index_configuration(model_mode="live")
    service = CandidateIndexService(source.storage)
    binding = service.start(run.binding, request_key=uuid4(), configuration=config)
    manifest = prepare_index_candidate(binding, storage=source.storage, service=service)
    if len(manifest.pages) != 2 or {item.modality for item in manifest.inputs} != {
        "text",
        "visual",
    }:
        raise RuntimeError("Synthetic index must retain both source pages and both modalities.")
    text_transport, visual_transport = ObservedTransport(), ObservedTransport()
    try:
        clients = candidate_embedding_clients(
            config, settings, text_transport=text_transport, visual_transport=visual_transport
        )
        attempts = []
        # Commit one input, then resume through a new executor invocation. The
        # existing exact producer claim/lease remains active until everything seals.
        first = execute_index_candidate(
            binding, clients=clients, storage=source.storage, service=service, max_new_inputs=1
        )
        attempts.append(asdict(first))
        if first.state != "pending" or text_transport.started + visual_transport.started != 1:
            raise RuntimeError("Bounded first indexing pass did not checkpoint exactly one input.")
        result = first
        for _ in range(32):
            result = execute_index_candidate(
                binding, clients=clients, storage=source.storage, service=service
            )
            attempts.append(asdict(result))
            if result.state == "sealed":
                break
        if result.state != "sealed":
            raise RuntimeError("Bounded synthetic index did not seal; producer cannot ACK.")
        before, vectors = capture_index_vectors(binding, manifest, config)
        calls = {"text": text_transport.started, "visual": visual_transport.started}
        replay = execute_index_candidate(
            binding, clients=clients, storage=source.storage, service=service
        )
        after, _ = capture_index_vectors(binding, manifest, config)
        expected = {
            modality: sum(item.modality == modality for item in manifest.inputs)
            for modality in config.modalities
        }
        if (
            replay.state != "sealed"
            or before != after
            or calls != {"text": text_transport.started, "visual": visual_transport.started}
            or calls != expected
            or text_transport.started != text_transport.responses
            or visual_transport.started != visual_transport.responses
        ):
            raise RuntimeError(
                "Persisted index replay changed bytes or repeated completed model work."
            )
        write_private(output_dir / "index-capture.json", before)
        return {
            "index_generation_id": str(binding.index_generation_id),
            "configuration_sha256": config.fingerprint,
            "manifest_sha256": manifest.fingerprint,
            "completion_sha256": before["completion_sha256"],
            "execution_attempts": attempts,
            "sealed_replay": asdict(replay),
            "actual_document_http_calls": calls,
            "sealed_replay_http_calls": 0,
            "queries": query_persisted_vectors(vectors, config, settings),
            "quality_acceptance": "not_evaluated",
        }
    finally:
        text_transport.close()
        visual_transport.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--deployment-revision", required=True)
    args = parser.parse_args()
    settings = get_settings()
    if settings.model_mode not in {"live", "required"}:
        parser.error("This probe requires live models and an isolated integration database.")
    if settings.runtime_root.resolve() != args.output_dir.resolve():
        parser.error("--output-dir must match isolated STRUCTURA_RUNTIME_ROOT for evidence reads.")
    verify_isolated_database(settings.database_url)
    args.output_dir.mkdir(mode=0o700, parents=False, exist_ok=False)
    commit = subprocess.check_output(  # nosec B603
        ["/usr/bin/git", "rev-parse", "HEAD"], cwd=ROOT, text=True, timeout=5
    ).strip()
    fixture = ROOT / "tests/fixtures/evaluation"
    annotation = DocumentAnnotation.model_validate_json((fixture / "annotation.json").read_text())
    original = (fixture / "original.tiff").read_bytes()
    if hashlib.sha256(original).hexdigest() != annotation.original_sha256:
        raise RuntimeError("Synthetic original does not match its pre-authored source annotation.")
    source = register_source(args.output_dir, original)
    annotation, recorded_at = freeze_reference(
        source, fixture=fixture, output_dir=args.output_dir, commit=commit, annotation=annotation
    )
    # Query labels are frozen before any parse/embedding invocation, independently
    # of the later model outputs. This remains a tiny exposed regression fixture.
    write_private(args.output_dir / "query-reference.json", {"queries": QUERIES, "commit": commit})
    indexed, retained = [], []

    def before_ack(run: ProcessingRun) -> None:
        retained.append(retain_and_replay(run, source))
        indexed.append(index_and_replay(run, source, settings, args.output_dir))

    deployment = DeclaredParserDeployment(
        mode="live", served_model="qwen38-27b-bf16-oxcart", revision=args.deployment_revision
    )
    run, execution = ingest_and_replay(
        source, ObservedClient(ingestion_vision_client(settings)), deployment, before_ack=before_ack
    )
    score = score_persisted_run(
        source,
        run,
        annotation,
        output_dir=args.output_dir,
        number=1,
        commit=commit,
        reference_recorded_at=recorded_at,
    )
    write_private(
        args.output_dir / "report.json",
        {
            "commit": commit,
            "parse_execution": execution,
            "parse_score": score,
            "index": indexed[0],
            "retained_evidence": {
                "execution": retained[0],
                "api": verify_historical_api(run, source, args.output_dir),
            },
            "production_activated": False,
            "release_acceptance": "not_evaluated",
        },
    )
    print("Persisted parse/index replay and query probe completed; release gates remain open.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

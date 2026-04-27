from __future__ import annotations

import argparse
import signal
import sys
import time
from uuid import UUID

from lib.jobs import JobService, record_service_health
from lib.search.embedding_service import EmbeddingService
from workers.runtime import start_health_server

SUPPORTED_MODALITIES = {"text", "visual", "mixed"}


class EmbeddingWorkerError(Exception):
    pass


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Structura embedding worker")
    parser.add_argument("--worker", default="worker-embeddings")
    parser.add_argument("--queue", default="embeddings")
    parser.add_argument("--poll-seconds", type=float, default=5.0)
    parser.add_argument("--heartbeat-seconds", type=float, default=30.0)
    parser.add_argument("--health-host", default="127.0.0.1")
    parser.add_argument("--health-port", type=int, default=0)
    return parser.parse_args()


def process_next_embedding_job(
    *,
    worker_name: str = "worker-embeddings",
    queue_name: str = "embeddings",
    document_id: UUID | None = None,
    service: EmbeddingService | None = None,
) -> bool:
    job_service = JobService()
    claimed = job_service.claim_next_job_record(
        worker_name=worker_name,
        queue_name=queue_name,
        document_id=document_id,
    )
    if not claimed:
        return False

    embedding_service = service or EmbeddingService()
    try:
        target_document_id = _document_id_for_job(claimed.document_id, claimed.payload)
        summary = embedding_service.embed_document(
            target_document_id,
            force_reembed=bool(claimed.payload.get("force_reembed", False)),
            modalities=_modalities_for_job(claimed.payload),
        )
        job_service.complete_job(
            job_id=claimed.state.job_id,
            result={
                "embedding_status": "succeeded",
                "source_count": summary.source_count,
                "inserted_count": summary.inserted_count,
                "skipped_count": summary.skipped_count,
                "model_name": summary.model_name,
                "model_version": summary.model_version,
                "dimensions": summary.dimensions,
                "modality_counts": summary.modality_counts,
            },
        )
    except Exception as exc:
        job_service.fail_job(
            job_id=claimed.state.job_id,
            error_class=exc.__class__.__name__,
            message="Phase 5 embedding job failed",
            retryable=True,
            suppress=False,
        )
    return True


def _document_id_for_job(document_id: UUID | None, payload: dict[str, object]) -> UUID:
    if document_id:
        return document_id
    payload_document_id = payload.get("document_id")
    if not payload_document_id:
        raise EmbeddingWorkerError("Embedding job is missing document_id.")
    return UUID(str(payload_document_id))


def _modalities_for_job(payload: dict[str, object]) -> tuple[str, ...]:
    modalities = payload.get("modalities")
    if not isinstance(modalities, list):
        return ("text",)
    requested = tuple(str(modality) for modality in modalities if str(modality).strip()) or (
        "text",
    )
    unsupported = sorted(set(requested) - SUPPORTED_MODALITIES)
    if unsupported:
        raise EmbeddingWorkerError(f"Unsupported embedding modalities: {', '.join(unsupported)}")
    return requested


def main() -> None:
    args = parse_args()
    running = True
    server = start_health_server(args.worker, args.health_host, args.health_port)
    last_heartbeat = 0.0

    def handle_stop(_signum: int, _frame: object) -> None:
        nonlocal running
        running = False

    signal.signal(signal.SIGTERM, handle_stop)
    signal.signal(signal.SIGINT, handle_stop)

    print(f"{args.worker}: embedding worker started", flush=True)
    while running:
        now = time.monotonic()
        if now - last_heartbeat >= args.heartbeat_seconds:
            _record_health(args.worker, args.queue, args.heartbeat_seconds)
            last_heartbeat = now
        processed = process_next_embedding_job(worker_name=args.worker, queue_name=args.queue)
        if not processed:
            time.sleep(args.poll_seconds)
    if server:
        server.shutdown()
    print(f"{args.worker}: embedding worker stopped", flush=True)


def _record_health(worker_name: str, queue_name: str, heartbeat_seconds: float) -> None:
    try:
        record_service_health(
            service_name=worker_name,
            status="ok",
            metrics={
                "queue": queue_name,
                "heartbeat_seconds": heartbeat_seconds,
                "supported_modalities": ["text", "visual", "mixed"],
            },
        )
    except Exception as exc:
        print(f"{worker_name}: health snapshot skipped: {exc}", flush=True)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(0)

from __future__ import annotations

import argparse
import signal
import sys
import time
from typing import Any, Protocol, cast
from uuid import UUID

from lib.jobs import JobService, record_service_health
from lib.semantic_annotations.models import QualityMode
from lib.semantic_annotations.service import (
    SemanticAnnotationRunResult,
    SemanticAnnotationService,
)
from workers.runtime import start_health_server


class SemanticAnnotationWorkerError(Exception):
    pass


class SemanticAnnotationServiceProtocol(Protocol):
    def annotate_document(
        self,
        document_id: UUID,
        *,
        quality_mode: QualityMode,
        requested_by: str,
    ) -> SemanticAnnotationRunResult: ...


class SemanticJobServiceProtocol(Protocol):
    def claim_next_job_record(self, **kwargs: object) -> Any: ...

    def complete_job(self, **kwargs: object) -> None: ...

    def fail_job(self, **kwargs: object) -> None: ...


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Structura semantic annotation worker")
    parser.add_argument("--worker", default="worker-semantic-annotations")
    parser.add_argument("--queue", default="semantic-annotations")
    parser.add_argument("--poll-seconds", type=float, default=5.0)
    parser.add_argument("--heartbeat-seconds", type=float, default=30.0)
    parser.add_argument("--health-host", default="127.0.0.1")
    parser.add_argument("--health-port", type=int, default=0)
    return parser.parse_args()


def process_next_semantic_annotation_job(
    *,
    worker_name: str = "worker-semantic-annotations",
    queue_name: str = "semantic-annotations",
    document_id: UUID | None = None,
    job_service: SemanticJobServiceProtocol | None = None,
    service: SemanticAnnotationServiceProtocol | None = None,
) -> bool:
    jobs = job_service or JobService()
    claimed = jobs.claim_next_job_record(
        worker_name=worker_name,
        queue_name=queue_name,
        document_id=document_id,
    )
    if not claimed:
        return False

    semantic_service = service or SemanticAnnotationService()
    try:
        target_document_id = _document_id_for_job(claimed.document_id, claimed.payload)
        if claimed.state.job_type != "semantic_annotate":
            raise SemanticAnnotationWorkerError(
                f"Unsupported semantic annotation job: {claimed.state.job_type}"
            )
        result = semantic_service.annotate_document(
            target_document_id,
            quality_mode=cast(QualityMode, str(claimed.payload.get("quality_mode") or "smart")),
            requested_by=str(claimed.payload.get("requested_by") or "system"),
        )
        annotation_id = result.annotation_id
        queued_granite_job_ids = tuple(result.queued_granite_job_ids)
        jobs.complete_job(
            job_id=claimed.state.job_id,
            result={
                "semantic_annotation_status": "succeeded",
                "annotation_id": str(annotation_id),
                "queued_granite_job_ids": [str(job_id) for job_id in queued_granite_job_ids],
            },
        )
    except SemanticAnnotationWorkerError as exc:
        jobs.fail_job(
            job_id=claimed.state.job_id,
            error_class=exc.__class__.__name__,
            message=str(exc),
            retryable=False,
            suppress=False,
        )
    except Exception as exc:
        jobs.fail_job(
            job_id=claimed.state.job_id,
            error_class=exc.__class__.__name__,
            message="Semantic annotation job failed",
            retryable=True,
            suppress=False,
        )
    return True


def _document_id_for_job(document_id: UUID | None, payload: dict[str, object]) -> UUID:
    if document_id:
        return document_id
    payload_document_id = payload.get("document_id")
    if not payload_document_id:
        raise SemanticAnnotationWorkerError("Semantic annotation job is missing document_id.")
    return UUID(str(payload_document_id))


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

    print(f"{args.worker}: semantic annotation worker started", flush=True)
    while running:
        now = time.monotonic()
        if now - last_heartbeat >= args.heartbeat_seconds:
            _record_health(args.worker, args.queue, args.heartbeat_seconds)
            last_heartbeat = now
        processed = process_next_semantic_annotation_job(
            worker_name=args.worker,
            queue_name=args.queue,
        )
        if not processed:
            time.sleep(args.poll_seconds)
    if server:
        server.shutdown()
    print(f"{args.worker}: semantic annotation worker stopped", flush=True)


def _record_health(worker_name: str, queue_name: str, heartbeat_seconds: float) -> None:
    try:
        record_service_health(
            service_name=worker_name,
            status="ok",
            metrics={"queue": queue_name, "heartbeat_seconds": heartbeat_seconds},
        )
    except Exception as exc:
        print(f"{worker_name}: health snapshot skipped: {exc}", flush=True)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(0)

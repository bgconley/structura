from __future__ import annotations

import argparse
import signal
import sys
import time
from uuid import UUID

from lib.extraction import ExtractionService
from lib.jobs import JobService, record_service_health
from lib.search.jobs import enqueue_embed_document_job
from workers.runtime import start_health_server


class ExtractionWorkerError(Exception):
    pass


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Structura extraction worker")
    parser.add_argument("--worker", default="worker-extraction")
    parser.add_argument("--queue", default="extraction")
    parser.add_argument("--poll-seconds", type=float, default=5.0)
    parser.add_argument("--heartbeat-seconds", type=float, default=30.0)
    parser.add_argument("--health-host", default="127.0.0.1")
    parser.add_argument("--health-port", type=int, default=0)
    return parser.parse_args()


def process_next_extraction_job(
    *,
    worker_name: str = "worker-extraction",
    queue_name: str = "extraction",
    document_id: UUID | None = None,
    service: ExtractionService | None = None,
) -> bool:
    job_service = JobService()
    claimed = job_service.claim_next_job_record(
        worker_name=worker_name,
        queue_name=queue_name,
        document_id=document_id,
    )
    if not claimed:
        return False

    extraction_service = service or ExtractionService()
    target_document_id: UUID | None = None
    try:
        target_document_id = _document_id_for_job(claimed.document_id, claimed.payload)
        if claimed.state.job_type == "classify":
            result = extraction_service.classify_document(
                target_document_id,
                force_reclassify=bool(claimed.payload.get("force_reclassify", False)),
            )
            job_service.complete_job(
                job_id=claimed.state.job_id,
                result={
                    "classification_status": "succeeded",
                    "family": result.decision.family,
                    "extraction_id": str(result.extraction_id),
                    "queued_extraction_job_id": (
                        str(result.queued_extraction_job_id)
                        if result.queued_extraction_job_id
                        else None
                    ),
                },
            )
            _enqueue_embedding_refresh(
                target_document_id,
                household_id=claimed.household_id,
                force_reembed=False,
            )
        elif claimed.state.job_type == "extract":
            schema_name = str(claimed.payload.get("target_schema_name") or "")
            route_profile = str(
                claimed.payload.get("route_profile") or "docling_plus_structured_extraction"
            )
            persisted = extraction_service.extract_document(
                target_document_id,
                schema_name=schema_name,
                route_profile=route_profile,
            )
            job_service.complete_job(
                job_id=claimed.state.job_id,
                result={
                    "extraction_status": "succeeded",
                    "extraction_id": str(persisted.extraction_id),
                    "review_status": persisted.review_status,
                    "candidate_count": persisted.candidate_count,
                    "canonical_count": persisted.canonical_count,
                    "review_task_count": persisted.review_task_count,
                },
            )
            _enqueue_embedding_refresh(
                target_document_id,
                household_id=claimed.household_id,
                force_reembed=False,
            )
        else:
            raise ExtractionWorkerError(
                f"Unsupported extraction queue job: {claimed.state.job_type}"
            )
    except Exception as exc:
        job_service.fail_job(
            job_id=claimed.state.job_id,
            error_class=exc.__class__.__name__,
            message="Phase 4 extraction job failed",
            retryable=True,
            suppress=False,
        )
    return True


def _document_id_for_job(document_id: UUID | None, payload: dict[str, object]) -> UUID:
    if document_id:
        return document_id
    payload_document_id = payload.get("document_id")
    if not payload_document_id:
        raise ExtractionWorkerError("Extraction job is missing document_id.")
    return UUID(str(payload_document_id))


def _enqueue_embedding_refresh(
    document_id: UUID,
    *,
    household_id: UUID | None,
    force_reembed: bool,
) -> None:
    from lib.db.connection import db_connection

    with db_connection() as conn:
        with conn.cursor() as cur:
            enqueue_embed_document_job(
                cur,
                document_id=document_id,
                household_id=household_id,
                force_reembed=force_reembed,
            )
        conn.commit()


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

    print(f"{args.worker}: extraction worker started", flush=True)
    while running:
        now = time.monotonic()
        if now - last_heartbeat >= args.heartbeat_seconds:
            _record_health(args.worker, args.queue, args.heartbeat_seconds)
            last_heartbeat = now
        processed = process_next_extraction_job(worker_name=args.worker, queue_name=args.queue)
        if not processed:
            time.sleep(args.poll_seconds)
    if server:
        server.shutdown()
    print(f"{args.worker}: extraction worker stopped", flush=True)


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

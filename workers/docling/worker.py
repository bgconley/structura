from __future__ import annotations

import argparse
import signal
import sys
import time
from uuid import UUID, uuid4

from lib.documents.quality import evaluate_document_quality
from lib.jobs import JobService, record_service_health
from lib.jobs.event_payloads import build_classify_document_job_payload
from lib.search.jobs import enqueue_embed_document_job, enqueue_visual_embed_document_job
from lib.semantic_annotations.jobs import enqueue_semantic_annotation_job
from workers.docling.converter import DoclingConverter
from workers.docling.service import (
    DoclingWorkerError,
    convert_document,
    mark_document_parse_failed,
)
from workers.runtime import start_health_server


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Structura Docling conversion worker")
    parser.add_argument("--worker", default="worker-docling")
    parser.add_argument("--queue", default="docling")
    parser.add_argument("--poll-seconds", type=float, default=5.0)
    parser.add_argument("--heartbeat-seconds", type=float, default=30.0)
    parser.add_argument("--health-host", default="127.0.0.1")
    parser.add_argument("--health-port", type=int, default=0)
    return parser.parse_args()


def process_next_docling_job(
    *,
    worker_name: str = "worker-docling",
    queue_name: str = "docling",
    document_id: UUID | None = None,
    converter: DoclingConverter | None = None,
) -> bool:
    job_service = JobService()
    claimed = job_service.claim_next_job_record(
        worker_name=worker_name,
        queue_name=queue_name,
        document_id=document_id,
    )
    if not claimed:
        return False

    target_document_id: UUID | None = None
    try:
        target_document_id = _document_id_for_docling(claimed.document_id, claimed.payload)
        summary = convert_document(
            target_document_id,
            job_id=claimed.state.job_id,
            converter=converter,
        )
        quality = evaluate_document_quality(target_document_id)
        completed = job_service.complete_job(
            job_id=claimed.state.job_id,
            result={
                "parse_status": "succeeded",
                "docling_asset_id": str(summary.docling_asset_id),
                "page_count": summary.page_count,
                "element_count": summary.element_count,
                "table_count": summary.table_count,
                "chunk_count": summary.chunk_count,
                "phase8_quality": {
                    "review_required": quality.review_required,
                    "visual_embedding_eligible": quality.visual_embedding_eligible,
                    "qwen_route_eligible": quality.qwen_route_eligible,
                },
            },
        )
        if getattr(completed, "status", None) == "cancelled":
            return True
    except Exception as exc:
        if target_document_id:
            mark_document_parse_failed(
                document_id=target_document_id,
                error_class=exc.__class__.__name__,
                message="Docling canonical conversion failed",
                job_id=claimed.state.job_id,
            )
        job_service.fail_job(
            job_id=claimed.state.job_id,
            error_class=exc.__class__.__name__,
            message="Docling canonical conversion failed",
            retryable=True,
            suppress=False,
        )
        return True

    downstream_failures: list[str] = []
    try:
        classify_priority = 38
        classify_job_id = uuid4()
        job_service.create_job(
            job_id=classify_job_id,
            job_type="classify",
            household_id=claimed.household_id,
            document_id=target_document_id,
            payload=build_classify_document_job_payload(
                job_id=classify_job_id,
                document_id=target_document_id,
                requested_by="system",
                priority=classify_priority,
                metadata={"stage": "phase4.classify"},
            ),
            priority=classify_priority,
            queue_name="extraction",
        )
    except Exception as exc:
        downstream_failures.append(f"classify:{exc.__class__.__name__}")
    try:
        _enqueue_embedding_refresh(
            target_document_id,
            household_id=claimed.household_id,
            include_visual=quality.visual_embedding_eligible,
        )
    except Exception as exc:
        downstream_failures.append(f"embeddings:{exc.__class__.__name__}")
    try:
        _enqueue_semantic_annotation(
            target_document_id,
            household_id=claimed.household_id,
        )
    except Exception as exc:
        downstream_failures.append(f"semantic:{exc.__class__.__name__}")
    if downstream_failures:
        _record_downstream_enqueue_failure(
            worker_name=worker_name,
            document_id=target_document_id,
            job_id=claimed.state.job_id,
            failures=downstream_failures,
        )
    return True


def _document_id_for_docling(document_id: UUID | None, payload: dict[str, object]) -> UUID:
    if document_id:
        return document_id
    payload_document_id = payload.get("document_id")
    if not payload_document_id:
        raise DoclingWorkerError("Docling job is missing document_id.")
    return UUID(str(payload_document_id))


def _enqueue_embedding_refresh(
    document_id: UUID,
    *,
    household_id: UUID | None,
    include_visual: bool,
) -> None:
    from lib.db.connection import db_connection

    with db_connection() as conn:
        with conn.cursor() as cur:
            enqueue_embed_document_job(
                cur,
                document_id=document_id,
                household_id=household_id,
                force_reembed=False,
            )
            if include_visual:
                enqueue_visual_embed_document_job(
                    cur,
                    document_id=document_id,
                    household_id=household_id,
                    force_reembed=False,
                )
        conn.commit()


def _enqueue_semantic_annotation(document_id: UUID, *, household_id: UUID | None) -> None:
    from lib.db.connection import db_connection

    with db_connection() as conn:
        with conn.cursor() as cur:
            enqueue_semantic_annotation_job(
                cur,
                document_id=document_id,
                household_id=household_id,
                quality_mode="smart",
                requested_by="system",
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

    print(f"{args.worker}: Docling worker started", flush=True)
    while running:
        now = time.monotonic()
        if now - last_heartbeat >= args.heartbeat_seconds:
            _record_health(args.worker, args.queue, args.heartbeat_seconds)
            last_heartbeat = now
        processed = process_next_docling_job(worker_name=args.worker, queue_name=args.queue)
        if not processed:
            time.sleep(args.poll_seconds)
    if server:
        server.shutdown()
    print(f"{args.worker}: Docling worker stopped", flush=True)


def _record_health(worker_name: str, queue_name: str, heartbeat_seconds: float) -> None:
    try:
        record_service_health(
            service_name=worker_name,
            status="ok",
            metrics={"queue": queue_name, "heartbeat_seconds": heartbeat_seconds},
        )
    except Exception as exc:
        print(f"{worker_name}: health snapshot skipped: {exc}", flush=True)


def _record_downstream_enqueue_failure(
    *,
    worker_name: str,
    document_id: UUID,
    job_id: UUID,
    failures: list[str],
) -> None:
    try:
        record_service_health(
            service_name=worker_name,
            status="degraded",
            metrics={
                "document_id": str(document_id),
                "job_id": str(job_id),
                "stage": "post_parse_enqueue",
                "failures": failures,
            },
        )
    except Exception as exc:
        print(f"{worker_name}: downstream enqueue failure snapshot skipped: {exc}", flush=True)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(0)

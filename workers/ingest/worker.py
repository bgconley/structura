from __future__ import annotations

import argparse
import signal
import sys
import time
from uuid import UUID

from lib.db.connection import db_connection
from lib.jobs import JobService, record_service_health
from workers.runtime import start_health_server


class IngestWorkerError(Exception):
    pass


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Structura ingest worker")
    parser.add_argument("--worker", default="worker-ingest")
    parser.add_argument("--queue", default="ingest")
    parser.add_argument("--poll-seconds", type=float, default=5.0)
    parser.add_argument("--heartbeat-seconds", type=float, default=30.0)
    parser.add_argument("--health-host", default="127.0.0.1")
    parser.add_argument("--health-port", type=int, default=0)
    return parser.parse_args()


def process_next_ingest_job(
    *,
    worker_name: str = "worker-ingest",
    queue_name: str = "ingest",
    document_id: UUID | None = None,
) -> bool:
    job_service = JobService()
    claimed = job_service.claim_next_job_record(
        worker_name=worker_name,
        queue_name=queue_name,
        document_id=document_id,
    )
    if not claimed:
        return False

    try:
        target_document_id = _document_id_for_job(claimed.document_id, claimed.payload)
        summary = _acknowledge_ingested_document(target_document_id)
        job_service.complete_job(
            job_id=claimed.state.job_id,
            result={
                "ingest_status": "acknowledged",
                "document_id": str(target_document_id),
                "original_asset_id": str(summary["asset_id"]),
                "sha256": summary["sha256"],
            },
        )
    except Exception as exc:
        job_service.fail_job(
            job_id=claimed.state.job_id,
            error_class=exc.__class__.__name__,
            message="Phase 1 ingest acknowledgement failed",
            retryable=True,
            suppress=False,
        )
    return True


def _document_id_for_job(document_id: UUID | None, payload: dict[str, object]) -> UUID:
    if document_id:
        return document_id
    payload_document_id = payload.get("document_id")
    if not payload_document_id:
        raise IngestWorkerError("Ingest job is missing document_id.")
    return UUID(str(payload_document_id))


def _acknowledge_ingested_document(document_id: UUID) -> dict[str, object]:
    with db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                  d.id AS document_id,
                  a.id AS asset_id,
                  a.sha256,
                  a.byte_size
                FROM documents d
                JOIN document_assets a ON a.document_id = d.id
                WHERE d.id = %s
                  AND d.deleted_at IS NULL
                  AND a.asset_role = 'original'
                ORDER BY a.created_at ASC
                LIMIT 1
                """,
                (document_id,),
            )
            row = cur.fetchone()
    if not row:
        raise IngestWorkerError("Ingest job document or original asset is missing.")
    return dict(row)


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

    print(f"{args.worker}: ingest worker started", flush=True)
    while running:
        now = time.monotonic()
        if now - last_heartbeat >= args.heartbeat_seconds:
            _record_health(args.worker, args.queue, args.heartbeat_seconds)
            last_heartbeat = now
        processed = process_next_ingest_job(worker_name=args.worker, queue_name=args.queue)
        if not processed:
            time.sleep(args.poll_seconds)
    if server:
        server.shutdown()
    print(f"{args.worker}: ingest worker stopped", flush=True)


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

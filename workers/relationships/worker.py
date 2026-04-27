from __future__ import annotations

import argparse
import signal
import sys
import time
from uuid import UUID

from lib.db.connection import db_connection
from lib.jobs import JobService, record_service_health
from lib.relationships.service import RelationshipService
from workers.runtime import start_health_server


class RelationshipWorkerError(Exception):
    pass


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Structura relationship worker")
    parser.add_argument("--worker", default="worker-relationships")
    parser.add_argument("--queue", default="relationships")
    parser.add_argument("--poll-seconds", type=float, default=5.0)
    parser.add_argument("--heartbeat-seconds", type=float, default=30.0)
    parser.add_argument("--health-host", default="127.0.0.1")
    parser.add_argument("--health-port", type=int, default=0)
    return parser.parse_args()


def process_next_relationship_job(
    *,
    worker_name: str = "worker-relationships",
    queue_name: str = "relationships",
    document_id: UUID | str | None = None,
    service: RelationshipService | None = None,
) -> bool:
    target_filter = UUID(str(document_id)) if document_id else None
    job_service = JobService()
    claimed = job_service.claim_next_job_record(
        worker_name=worker_name,
        queue_name=queue_name,
        document_id=target_filter,
    )
    if not claimed:
        return False

    relationship_service = service or RelationshipService()
    target_document_id: UUID | None = None
    try:
        target_document_id = _document_id_for_job(claimed.document_id, claimed.payload)
        household_id = claimed.household_id or _household_id_for_document(target_document_id)
        if not household_id:
            raise RelationshipWorkerError("Relationship job is missing household_id.")
        deadline_count = relationship_service.refresh_deadlines(target_document_id)
        suggestion_count = relationship_service.suggest_for_document(
            target_document_id,
            household_id=household_id,
        )
        job_service.complete_job(
            job_id=claimed.state.job_id,
            result={
                "relationship_status": "succeeded",
                "document_id": str(target_document_id),
                "suggestion_count": suggestion_count,
                "deadline_count": deadline_count,
            },
        )
    except Exception as exc:
        job_service.fail_job(
            job_id=claimed.state.job_id,
            error_class=exc.__class__.__name__,
            message="Phase 7 relationship job failed",
            retryable=True,
            suppress=False,
        )
    return True


def _document_id_for_job(document_id: UUID | None, payload: dict[str, object]) -> UUID:
    if document_id:
        return document_id
    payload_document_id = payload.get("document_id")
    if not payload_document_id:
        raise RelationshipWorkerError("Relationship job is missing document_id.")
    return UUID(str(payload_document_id))


def _household_id_for_document(document_id: UUID) -> UUID | None:
    with db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT household_id FROM documents WHERE id = %s", (document_id,))
            row = cur.fetchone()
    return UUID(str(row["household_id"])) if row and row.get("household_id") else None


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

    print(f"{args.worker}: relationship worker started", flush=True)
    while running:
        now = time.monotonic()
        if now - last_heartbeat >= args.heartbeat_seconds:
            _record_health(args.worker, args.queue, args.heartbeat_seconds)
            last_heartbeat = now
        processed = process_next_relationship_job(worker_name=args.worker, queue_name=args.queue)
        if not processed:
            time.sleep(args.poll_seconds)
    if server:
        server.shutdown()
    print(f"{args.worker}: relationship worker stopped", flush=True)


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

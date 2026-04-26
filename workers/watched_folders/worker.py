from __future__ import annotations

import argparse
import signal
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

from lib.automation import watched_folder_repository
from lib.automation.watched_folder_policy import (
    WatchedFolderPolicyError,
    file_is_stable,
    is_safe_candidate_file,
    iter_candidate_files,
    normalize_watch_policy,
    validate_watch_path,
)
from lib.config import get_settings
from lib.db.connection import db_connection
from lib.documents.ingestion import (
    DocumentIngestionRequest,
    document_exists_for_sha256,
    ingest_document_path,
    source_file_sha256,
)
from lib.jobs import record_service_health
from workers.runtime import start_health_server


@dataclass(frozen=True)
class WatchScanSummary:
    accepted: int = 0
    rejected: int = 0
    skipped: int = 0

    def add(self, *, accepted: int = 0, rejected: int = 0, skipped: int = 0) -> WatchScanSummary:
        return WatchScanSummary(
            accepted=self.accepted + accepted,
            rejected=self.rejected + rejected,
            skipped=self.skipped + skipped,
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Structura watched-folder worker")
    parser.add_argument("--worker", default="worker-watched-folders")
    parser.add_argument("--poll-seconds", type=float, default=15.0)
    parser.add_argument("--heartbeat-seconds", type=float, default=30.0)
    parser.add_argument("--health-host", default="127.0.0.1")
    parser.add_argument("--health-port", type=int, default=0)
    return parser.parse_args()


def scan_once(
    *,
    worker_name: str = "worker-watched-folders",
    household_id: UUID | None = None,
    user_id: UUID | None = None,
) -> WatchScanSummary:
    settings = get_settings()
    total = WatchScanSummary()
    with db_connection() as conn:
        with conn.cursor() as cur:
            watched = watched_folder_repository.enabled_watched_folders(
                cur,
                household_id=household_id,
            )
    for watched_folder in watched:
        owner_user_id = user_id or watched_folder.get("owner_user_id")
        if not owner_user_id:
            total = total.add(rejected=1)
            continue
        summary = _scan_watched_folder(
            watched_folder,
            owner_user_id=_uuid(owner_user_id),
            runtime_root=settings.runtime_root,
            watched_folder_root=settings.watched_folder_root,
            worker_name=worker_name,
        )
        total = total.add(
            accepted=summary.accepted,
            rejected=summary.rejected,
            skipped=summary.skipped,
        )
        with db_connection() as conn:
            with conn.cursor() as cur:
                watched_folder_repository.update_watched_folder_scan(
                    cur,
                    watched_folder_id=_uuid(watched_folder["id"]),
                    accepted=summary.accepted,
                    rejected=summary.rejected,
                    skipped=summary.skipped,
                )
            conn.commit()
    _record_health(worker_name, total)
    return total


def _scan_watched_folder(
    watched_folder: dict[str, object],
    *,
    owner_user_id: UUID,
    runtime_root: Path,
    watched_folder_root: Path,
    worker_name: str,
) -> WatchScanSummary:
    try:
        path = validate_watch_path(
            str(watched_folder["path"]),
            runtime_root=runtime_root,
            allowed_roots=[watched_folder_root],
        )
        policy_json = watched_folder.get("policy_json")
        policy = normalize_watch_policy(policy_json if isinstance(policy_json, dict) else {})
    except WatchedFolderPolicyError:
        return WatchScanSummary(rejected=1)

    summary = WatchScanSummary()
    for candidate in iter_candidate_files(path, recursive=bool(policy["recursive"])):
        if not is_safe_candidate_file(candidate, watch_root=path):
            summary = summary.add(rejected=1)
            continue
        if candidate.parent.name in {"processed", "failed"}:
            summary = summary.add(skipped=1)
            continue
        if candidate.suffix.lower() != ".pdf":
            summary = summary.add(rejected=1)
            _move_if_configured(candidate, policy=policy, target_name="failed")
            continue
        if not file_is_stable(candidate, min_age_seconds=int(policy["stabilityDelaySeconds"])):
            summary = summary.add(skipped=1)
            continue
        sha256 = source_file_sha256(candidate)
        household_id = _uuid(watched_folder["household_id"])
        if document_exists_for_sha256(household_id=household_id, sha256=sha256):
            summary = summary.add(skipped=1)
            continue
        try:
            ingest_document_path(
                candidate,
                request=DocumentIngestionRequest(
                    household_id=household_id,
                    owner_user_id=owner_user_id,
                    source="watched_folder",
                    filename=candidate.name,
                    declared_mime_type="application/pdf",
                    supplied_title=None,
                    hints={
                        "watchedFolderId": str(watched_folder["id"]),
                        "sourcePath": str(candidate),
                        "worker": worker_name,
                    },
                    requested_by="watched_folder",
                ),
            )
            summary = summary.add(accepted=1)
            _move_if_configured(candidate, policy=policy, target_name="processed")
        except Exception:
            summary = summary.add(rejected=1)
            _move_if_configured(candidate, policy=policy, target_name="failed")
    return summary


def _move_if_configured(candidate: Path, *, policy: dict[str, object], target_name: str) -> None:
    processed_policy = policy.get("processedFilePolicy")
    if processed_policy == "leave":
        return
    if target_name == "processed" and processed_policy != "move_processed":
        return
    if target_name == "failed" and processed_policy not in {"move_failed", "move_processed"}:
        return
    target_dir = candidate.parent / target_name
    target_dir.mkdir(exist_ok=True)
    target = target_dir / candidate.name
    if target.exists():
        target = target_dir / f"{candidate.stem}-{int(time.time())}{candidate.suffix}"
    candidate.replace(target)


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

    print(f"{args.worker}: watched-folder worker started", flush=True)
    while running:
        now = time.monotonic()
        if now - last_heartbeat >= args.heartbeat_seconds:
            _record_health(args.worker, WatchScanSummary())
            last_heartbeat = now
        scan_once(worker_name=args.worker)
        time.sleep(args.poll_seconds)
    if server:
        server.shutdown()
    print(f"{args.worker}: watched-folder worker stopped", flush=True)


def _record_health(worker_name: str, summary: WatchScanSummary) -> None:
    try:
        record_service_health(
            service_name=worker_name,
            status="ok",
            metrics={
                "accepted": summary.accepted,
                "rejected": summary.rejected,
                "skipped": summary.skipped,
            },
        )
    except Exception as exc:
        print(f"{worker_name}: health snapshot skipped: {exc}", flush=True)


def _uuid(value: object) -> UUID:
    if isinstance(value, UUID):
        return value
    return UUID(str(value))


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(0)

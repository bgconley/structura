from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from uuid import UUID

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from lib.automation.watched_folder_policy import (  # noqa: E402
    WatchedFolderPolicyError,
    file_is_stable,
    validate_watch_path,
)
from lib.config import get_settings  # noqa: E402
from lib.documents.ingestion import source_file_sha256  # noqa: E402
from lib.documents.maintenance import (  # noqa: E402
    DocumentMaintenanceError,
    enqueue_document_reprocess,
    enqueue_search_projection_rebuild,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Structura operator CLI")
    subcommands = parser.add_subparsers(dest="command", required=True)

    bulk = subcommands.add_parser("bulk-import", help="Validate and optionally import PDFs")
    bulk.add_argument("path")
    bulk.add_argument("--execute", action="store_true")
    bulk.add_argument("--api-base-url", default="http://127.0.0.1:8000")
    bulk.add_argument("--api-token")

    dry_run = subcommands.add_parser("dry-run-import", help="Alias for bulk-import dry-run")
    dry_run.add_argument("path")
    reprocess = subcommands.add_parser("reprocess-document", help="Request document reprocessing")
    reprocess.add_argument("document_id")
    reprocess.add_argument("--requested-by", default="operator")

    rebuild = subcommands.add_parser("rebuild-search-projection", help="Request projection rebuild")
    rebuild.add_argument("document_id")
    rebuild.add_argument("--no-force-reembed", action="store_true")

    subcommands.add_parser("evaluate", help="Run local benchmark guidance")
    subcommands.add_parser(
        "backup-restore-check",
        help="Non-destructive backup/restore readiness check",
    )

    args = parser.parse_args()
    if args.command in {"bulk-import", "dry-run-import"}:
        execute = bool(getattr(args, "execute", False))
        _bulk_import(
            Path(args.path),
            execute=execute,
            api_base_url=getattr(args, "api_base_url", ""),
            api_token=getattr(args, "api_token", None),
        )
    elif args.command == "reprocess-document":
        _reprocess_document(args.document_id, requested_by=args.requested_by)
    elif args.command == "rebuild-search-projection":
        _rebuild_search_projection(
            args.document_id,
            force_reembed=not args.no_force_reembed,
        )
    elif args.command == "evaluate":
        print("Run `python -m lib.search.benchmark` for the Phase 5/6 retrieval benchmark harness.")
    elif args.command == "backup-restore-check":
        _backup_restore_check()


def _bulk_import(path: Path, *, execute: bool, api_base_url: str, api_token: str | None) -> None:
    settings = get_settings()
    try:
        watch_path = validate_watch_path(path, runtime_root=settings.runtime_root)
    except WatchedFolderPolicyError as exc:
        raise SystemExit(f"Invalid import path: {exc}") from exc
    candidates = sorted(candidate for candidate in watch_path.glob("*.pdf") if candidate.is_file())
    stable = [candidate for candidate in candidates if file_is_stable(candidate, min_age_seconds=1)]
    rows = [
        {
            "path": str(candidate),
            "sha256": source_file_sha256(candidate),
            "bytes": candidate.stat().st_size,
        }
        for candidate in stable
    ]
    print(
        json.dumps(
            {"dryRun": not execute, "acceptedPdfCount": len(rows), "files": rows},
            indent=2,
        )
    )
    if execute and not api_token:
        raise SystemExit("--api-token is required for executing imports through the API.")
    if execute:
        raise SystemExit(
            "Bulk import execution is intentionally routed through watched-folder configuration "
            "in Phase 6; "
            "create a watched folder and let worker-watched-folders enqueue ingest jobs."
        )


def _reprocess_document(document_id: str, *, requested_by: str) -> None:
    try:
        result = enqueue_document_reprocess(UUID(document_id), requested_by=requested_by)
    except (ValueError, DocumentMaintenanceError) as exc:
        raise SystemExit(f"Could not enqueue document reprocess: {exc}") from exc
    print(
        json.dumps(
            {
                "documentId": str(result.document_id),
                "jobIds": [str(job_id) for job_id in result.job_ids],
            },
            indent=2,
        )
    )


def _rebuild_search_projection(document_id: str, *, force_reembed: bool) -> None:
    try:
        result = enqueue_search_projection_rebuild(UUID(document_id), force_reembed=force_reembed)
    except (ValueError, DocumentMaintenanceError) as exc:
        raise SystemExit(f"Could not enqueue search projection rebuild: {exc}") from exc
    print(
        json.dumps(
            {
                "documentId": str(result.document_id),
                "forceReembed": force_reembed,
                "jobIds": [str(job_id) for job_id in result.job_ids],
            },
            indent=2,
        )
    )


def _backup_restore_check() -> None:
    settings = get_settings()
    checks = {
        "runtimeRootExists": settings.runtime_root.exists(),
        "canonicalObjectsExists": settings.canonical_objects_root.exists(),
        "derivedObjectsExists": settings.derived_objects_root.exists(),
        "exportObjectsExists": settings.export_objects_root.exists(),
    }
    print(json.dumps(checks, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

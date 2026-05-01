#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json

# GPU validation invokes fixed docker compose commands.
import subprocess  # nosec B404
import sys
import time
from pathlib import Path
from typing import Any, cast
from uuid import UUID

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from lib.config import get_settings  # noqa: E402
from lib.db.connection import db_connection  # noqa: E402
from scripts.gpu.phase8_5_corpus_run_guard import (  # noqa: E402
    DEFAULT_CORPUS_LOCK_PATH,
    CorpusRunGuard,
)

CONTROLLED_WORKERS = (
    "worker-docling",
    "worker-extraction",
    "worker-semantic-annotations",
    "worker-embeddings",
    "worker-visual-embeddings",
)
CORPUS_RUN_ID = "phase8_5_private_corpus"
CORPUS_REQUESTED_BY = "agent"
CORPUS_LOCK_PATH = DEFAULT_CORPUS_LOCK_PATH

_ACTIVE_CORPUS_RUN: CorpusRunGuard | None = None


def main() -> int:
    global _ACTIVE_CORPUS_RUN
    args = _parse_args()
    with CorpusRunGuard(
        root=ROOT,
        lock_path=args.lock_path,
        title_prefix=args.title_prefix,
    ) as guard:
        _ACTIVE_CORPUS_RUN = guard
        try:
            return _run_corpus(args)
        finally:
            _ACTIVE_CORPUS_RUN = None


def _run_corpus(args: argparse.Namespace) -> int:
    settings = get_settings()
    if settings.model_mode == "fixture":
        raise SystemExit("Refusing private corpus run with STRUCTURA_MODEL_MODE=fixture.")
    owner = _resolve_owner(args.household_id, args.user_id)
    if args.stop_workers:
        _stop_controlled_workers()

    summaries = []
    had_extraction_failures = False
    for pdf_path in args.pdf:
        document_id = _ingest_pdf(pdf_path, owner=owner, title_prefix=args.title_prefix)
        _run_docling(document_id, timeout_seconds=args.docling_timeout_seconds)
        _cancel_text_embedding_jobs(document_id)
        _drain_semantic(document_id, label="smart")
        extraction_failures = _drain_extraction(document_id)
        if extraction_failures:
            had_extraction_failures = True
        _cancel_text_embedding_jobs(document_id)
        _drain_visual_embedding(document_id)
        _cancel_text_embedding_jobs(document_id)
        summary = _summarize_document(document_id)
        if extraction_failures:
            summary["extractionFailures"] = extraction_failures
        summaries.append(summary)
        print(json.dumps({"document_summary": summary}, sort_keys=True), flush=True)

    report = {
        "corpus": "phase8_5_private_documents",
        "text_embedder": "skipped_by_request",
        "has_extraction_failures": had_extraction_failures,
        "documents": summaries,
    }
    print(json.dumps(report, indent=2, sort_keys=True))
    return 1 if had_extraction_failures else 0


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run private PDFs through Phase 8.5 live VLMs.")
    parser.add_argument("--pdf", action="append", type=Path)
    parser.add_argument(
        "--manifest",
        type=Path,
        help='Local private corpus manifest. Expected shape: {"documents": [{"path": "..."}]}',
    )
    parser.add_argument("--title-prefix", default="Phase 8.5 Private Corpus")
    parser.add_argument("--requested-by", default=CORPUS_REQUESTED_BY)
    parser.add_argument("--household-id", type=UUID)
    parser.add_argument("--user-id", type=UUID)
    parser.add_argument("--docling-timeout-seconds", type=int, default=1800)
    parser.add_argument(
        "--lock-path",
        type=Path,
        default=CORPUS_LOCK_PATH,
        help=(
            "Singleton lock path. The private corpus runner refuses to start while "
            "another run owns this lock."
        ),
    )
    parser.add_argument("--no-stop-workers", dest="stop_workers", action="store_false")
    parser.set_defaults(stop_workers=True)
    args = parser.parse_args()
    pdfs = list(args.pdf or [])
    if args.manifest:
        pdfs.extend(_load_manifest_pdf_paths(args.manifest))
    if not pdfs:
        parser.error("at least one --pdf or --manifest document path is required")
    args.pdf = pdfs
    return args


def _load_manifest_pdf_paths(manifest_path: Path) -> list[Path]:
    if not manifest_path.exists():
        raise SystemExit(f"Private corpus manifest does not exist: {manifest_path}")
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    documents = payload.get("documents") if isinstance(payload, dict) else None
    if not isinstance(documents, list):
        raise SystemExit("Private corpus manifest must contain a documents array.")
    paths: list[Path] = []
    for index, item in enumerate(documents, start=1):
        if not isinstance(item, dict) or not item.get("path"):
            raise SystemExit(f"Manifest document {index} is missing a path.")
        paths.append(Path(str(item["path"])))
    return paths


def _resolve_owner(household_id: UUID | None, user_id: UUID | None) -> tuple[UUID, UUID]:
    if household_id and user_id:
        return household_id, user_id
    with db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT hm.household_id, hm.user_id
                FROM household_memberships hm
                JOIN users u ON u.id = hm.user_id
                WHERE (%s::uuid IS NULL OR hm.household_id = %s)
                  AND (%s::uuid IS NULL OR hm.user_id = %s)
                  AND hm.role IN ('owner', 'admin')
                  AND NOT u.is_disabled
                ORDER BY hm.role = 'owner' DESC, hm.created_at ASC
                LIMIT 1
                """,
                (household_id, household_id, user_id, user_id),
            )
            row = cur.fetchone()
    if not row:
        raise SystemExit("No owner/admin household membership found for private corpus run.")
    return UUID(str(row["household_id"])), UUID(str(row["user_id"]))


def _stop_controlled_workers() -> None:
    command = ["docker", "compose", "stop", *CONTROLLED_WORKERS]
    # Fixed command, no shell, no untrusted executable.
    subprocess.run(command, cwd=ROOT, check=False)  # nosec B603


def _ingest_pdf(
    pdf_path: Path,
    *,
    owner: tuple[UUID, UUID],
    title_prefix: str,
) -> UUID:
    if not pdf_path.exists():
        raise SystemExit(f"PDF does not exist: {pdf_path}")
    household_id, user_id = owner
    code = (
        "from pathlib import Path\n"
        "from uuid import UUID\n"
        "import json, sys\n"
        "from lib.documents.ingestion import DocumentIngestionRequest, ingest_document_path\n"
        "path = Path(sys.argv[1])\n"
        "household_id = UUID(sys.argv[2])\n"
        "user_id = UUID(sys.argv[3])\n"
        "title_prefix = sys.argv[4]\n"
        "result = ingest_document_path(\n"
        "    path,\n"
        "    request=DocumentIngestionRequest(\n"
        "        household_id=household_id,\n"
        "        owner_user_id=user_id,\n"
        "        source='bulk_import',\n"
        "        filename=path.name,\n"
        "        declared_mime_type='application/pdf',\n"
        "        supplied_title=f'{title_prefix}: {path.stem}',\n"
        "        hints={\n"
        f"            'phase': {CORPUS_RUN_ID!r},\n"
        "            'textEmbedder': 'skipped_by_request',\n"
        "            'sourcePath': str(path),\n"
        "        },\n"
        f"        requested_by={CORPUS_REQUESTED_BY!r},\n"
        "    ),\n"
        ")\n"
        "print(json.dumps({\n"
        "    'document_id': str(result.document_id),\n"
        "    'sha256': result.sha256,\n"
        "    'filename': path.name,\n"
        "}))\n"
    )
    payload = _compose_python_json(
        "api",
        code,
        str(pdf_path),
        str(household_id),
        str(user_id),
        title_prefix,
        volumes=(f"{pdf_path.parent}:{pdf_path.parent}:ro",),
    )
    print(
        json.dumps(
            {
                "stage": "ingested",
                "document_id": payload["document_id"],
                "filename": payload["filename"],
                "sha256": payload["sha256"],
            },
            sort_keys=True,
        ),
        flush=True,
    )
    return UUID(str(payload["document_id"]))


def _run_docling(document_id: UUID, *, timeout_seconds: int) -> None:
    code = (
        "from uuid import UUID\n"
        "import sys\n"
        "from workers.docling.worker import process_next_docling_job\n"
        "ok = process_next_docling_job("
        "worker_name='phase8-5-private-docling', document_id=UUID(sys.argv[1]))\n"
        "raise SystemExit(0 if ok else 2)\n"
    )
    _compose_python(
        "worker-docling",
        code,
        str(document_id),
        timeout_seconds=timeout_seconds,
    )
    _require_no_failed_jobs(document_id, queue_name="docling")


def _drain_semantic(document_id: UUID, *, label: str) -> None:
    processed = _drain(
        lambda: _process_one_worker_job(
            "worker-semantic-annotations",
            "workers.semantic_annotations.worker",
            "process_next_semantic_annotation_job",
            worker_name=f"phase8-5-private-semantic-{label}",
            document_id=document_id,
            live_model_env=True,
        ),
        max_jobs=8,
    )
    print(
        json.dumps(
            {"stage": f"semantic_{label}", "document_id": str(document_id), "jobs": processed},
            sort_keys=True,
        ),
        flush=True,
    )
    _require_no_failed_jobs(document_id, queue_name="semantic-annotations")


def _drain_extraction(document_id: UUID) -> list[dict[str, Any]]:
    extraction_jobs = 0
    for _ in range(12):
        extracted = _drain(
            lambda: _process_one_worker_job(
                "worker-extraction",
                "workers.extraction.worker",
                "process_next_extraction_job",
                worker_name="phase8-5-private-extraction",
                document_id=document_id,
                live_model_env=True,
            ),
            max_jobs=24,
        )
        extraction_jobs += extracted
        if extracted == 0:
            break
    print(
        json.dumps(
            {
                "stage": "extraction",
                "document_id": str(document_id),
                "extraction_jobs": extraction_jobs,
            },
            sort_keys=True,
        ),
        flush=True,
    )
    extraction_failures = _failed_jobs(document_id, queue_name="extraction")
    if extraction_failures:
        print(
            json.dumps(
                {
                    "stage": "extraction_failures",
                    "document_id": str(document_id),
                    "jobs": extraction_failures,
                },
                sort_keys=True,
                default=str,
            ),
            flush=True,
        )
    _require_no_failed_jobs(document_id, queue_name="semantic-annotations")
    if _has_model_timeout(extraction_failures):
        print(
            json.dumps(
                {
                    "stage": "model_timeout_fatal",
                    "document_id": str(document_id),
                    "message": (
                        "Stopping private corpus run because a model timeout indicates "
                        "runtime instability that must not be hidden by retries."
                    ),
                },
                sort_keys=True,
            ),
            flush=True,
        )
        raise SystemExit(2)
    return extraction_failures


def _has_model_timeout(failures: list[dict[str, Any]]) -> bool:
    for failure in failures:
        error_json = failure.get("error_json")
        if isinstance(error_json, dict) and error_json.get("error_class") == "ModelTimeoutError":
            return True
    return False


def _drain_visual_embedding(document_id: UUID) -> None:
    processed = _drain(
        lambda: _process_one_worker_job(
            "worker-visual-embeddings",
            "workers.embeddings.worker",
            "process_next_embedding_job",
            worker_name="phase8-5-private-visual-embeddings",
            queue_name="visual-embeddings",
            document_id=document_id,
            live_model_env=True,
        ),
        max_jobs=4,
    )
    print(
        json.dumps(
            {"stage": "visual_embeddings", "document_id": str(document_id), "jobs": processed},
            sort_keys=True,
        ),
        flush=True,
    )
    _require_no_failed_jobs(document_id, queue_name="visual-embeddings")


def _drain(process_one: Any, *, max_jobs: int) -> int:
    count = 0
    for _ in range(max_jobs):
        if not process_one():
            return count
        count += 1
    return count


def _process_one_worker_job(
    service: str,
    module_name: str,
    function_name: str,
    *,
    worker_name: str,
    document_id: UUID,
    queue_name: str | None = None,
    live_model_env: bool,
) -> bool:
    queue_argument = f", queue_name={queue_name!r}" if queue_name else ""
    code = (
        "from uuid import UUID\n"
        "import sys\n"
        f"from {module_name} import {function_name}\n"
        f"ok = {function_name}("
        f"worker_name={worker_name!r}, "
        "document_id=UUID(sys.argv[1])"
        f"{queue_argument})\n"
        "raise SystemExit(0 if ok else 2)\n"
    )
    result = _compose_python(
        service,
        code,
        str(document_id),
        check=False,
        live_model_env=live_model_env,
        timeout_seconds=900,
    )
    if result.returncode == 0:
        return True
    if result.returncode == 2:
        return False
    raise subprocess.CalledProcessError(result.returncode, result.args)


def _compose_python_json(
    service: str,
    code: str,
    *args: str,
    live_model_env: bool = False,
    timeout_seconds: int = 300,
    volumes: tuple[str, ...] = (),
) -> dict[str, object]:
    result = _compose_python(
        service,
        code,
        *args,
        live_model_env=live_model_env,
        timeout_seconds=timeout_seconds,
        volumes=volumes,
    )
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    if not lines:
        raise SystemExit(f"{service} command did not emit JSON.")
    parsed = json.loads(lines[-1])
    if not isinstance(parsed, dict):
        raise SystemExit(f"{service} command JSON output was not an object.")
    return parsed


def _compose_python(
    service: str,
    code: str,
    *args: str,
    check: bool = True,
    live_model_env: bool = False,
    timeout_seconds: int = 300,
    volumes: tuple[str, ...] = (),
) -> subprocess.CompletedProcess[str]:
    command = ["docker", "compose", "run", "--rm", "--no-deps"]
    if _ACTIVE_CORPUS_RUN:
        command.extend(_ACTIVE_CORPUS_RUN.compose_run_options(service))
    for volume in volumes:
        command.extend(["--volume", volume])
    if live_model_env:
        command.extend(
            [
                "-e",
                "STRUCTURA_MODEL_MODE=live",
                "-e",
                "STRUCTURA_EMBEDDING_VISUAL_ENABLED=true",
            ]
        )
    command.extend([service, "python", "-c", code, *args])
    # Fixed docker compose argv, no shell, service names are caller-controlled internals.
    try:
        return subprocess.run(  # nosec B603
            command,
            cwd=ROOT,
            check=check,
            timeout=timeout_seconds,
            text=True,
            capture_output=True,
        )
    except subprocess.TimeoutExpired:
        if _ACTIVE_CORPUS_RUN:
            _ACTIVE_CORPUS_RUN.cleanup_current_run_containers()
        raise


def _cancel_text_embedding_jobs(document_id: UUID) -> None:
    with db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE pipeline_jobs
                SET status = 'cancelled',
                    finished_at = now(),
                    error_json = jsonb_build_object(
                      'message', 'Text embedding skipped for private Phase 8.5 corpus run.',
                      'requested_by', %s::text
                    ),
                    updated_at = now()
                WHERE document_id = %s
                  AND queue_name = 'embeddings'
                  AND job_type = 'embed'
                  AND status IN ('queued', 'failed')
                """,
                (CORPUS_RUN_ID, document_id),
            )
        conn.commit()


def _require_no_failed_jobs(document_id: UUID, *, queue_name: str) -> None:
    rows = _failed_jobs(document_id, queue_name=queue_name)
    if rows:
        raise SystemExit(
            json.dumps(
                {
                    "document_id": str(document_id),
                    "failed_queue": queue_name,
                    "jobs": rows,
                },
                default=str,
            )
        )


def _failed_jobs(document_id: UUID, *, queue_name: str) -> list[dict[str, Any]]:
    with db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, job_type, status::text AS status, error_json
                FROM pipeline_jobs
                WHERE document_id = %s
                  AND queue_name = %s
                  AND status IN ('failed', 'dead_letter')
                ORDER BY updated_at DESC
                """,
                (document_id, queue_name),
            )
            rows = cur.fetchall()
    return cast(list[dict[str, Any]], _json_safe(rows))


def _summarize_document(document_id: UUID) -> dict[str, Any]:
    with db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                  d.id,
                  d.title,
                  d.original_filename,
                  CASE
                    WHEN count(DISTINCT p.id) > 0 THEN 'succeeded'
                    ELSE 'pending'
                  END AS parse_status,
                  d.document_family::text AS document_family,
                  count(DISTINCT p.id) AS page_count,
                  count(DISTINCT e.id) AS element_count,
                  count(DISTINCT t.id) AS table_count,
                  count(DISTINCT c.id) AS chunk_count
                FROM documents d
                LEFT JOIN document_pages p ON p.document_id = d.id
                LEFT JOIN document_elements e ON e.document_id = d.id
                LEFT JOIN document_tables t ON t.document_id = d.id
                LEFT JOIN document_chunks c ON c.document_id = d.id
                WHERE d.id = %s
                GROUP BY d.id
                """,
                (document_id,),
            )
            document = cur.fetchone()
            cur.execute(
                """
                SELECT
                  quality_mode,
                  profile_name,
                  source_engine::text AS source_engine,
                  model_name,
                  status,
                  review_required,
                  (
                    SELECT count(*)
                    FROM semantic_region_annotations r
                    WHERE r.annotation_id = a.id
                  ) AS region_count
                FROM document_semantic_annotations a
                WHERE document_id = %s
                  AND is_current
                ORDER BY quality_mode, profile_name
                """,
                (document_id,),
            )
            semantic = cur.fetchall()
            cur.execute(
                """
                SELECT
                  schema_name,
                  source_engine::text AS source_engine,
                  model_name,
                  prompt_version,
                  status::text AS status,
                  review_status::text AS review_status,
                  count(*) AS run_count
                FROM document_extractions
                WHERE document_id = %s
                GROUP BY
                  schema_name,
                  source_engine,
                  model_name,
                  prompt_version,
                  status,
                  review_status
                ORDER BY schema_name, source_engine, model_name
                """,
                (document_id,),
            )
            extractions = cur.fetchall()
            cur.execute(
                """
                SELECT source_engine::text AS source_engine, count(*) AS total
                FROM field_candidates
                WHERE document_id = %s
                GROUP BY source_engine
                ORDER BY source_engine
                """,
                (document_id,),
            )
            field_candidates = cur.fetchall()
            cur.execute(
                """
                SELECT source_engine::text AS source_engine, count(*) AS total
                FROM line_item_candidates
                WHERE document_id = %s
                GROUP BY source_engine
                ORDER BY source_engine
                """,
                (document_id,),
            )
            line_candidates = cur.fetchall()
            cur.execute(
                """
                SELECT
                  model_name,
                  model_version,
                  modality::text AS modality,
                  embedding_dimensions,
                  metadata_json ->> 'adapter' AS adapter,
                  count(*) AS total
                FROM embeddings
                WHERE document_id = %s
                  AND is_active
                GROUP BY model_name, model_version, modality, embedding_dimensions, adapter
                ORDER BY modality, model_name
                """,
                (document_id,),
            )
            embeddings = cur.fetchall()
            cur.execute(
                """
                SELECT
                  queue_name,
                  job_type::text AS job_type,
                  status::text AS status,
                  count(*) AS total
                FROM pipeline_jobs
                WHERE document_id = %s
                GROUP BY queue_name, job_type, status
                ORDER BY queue_name, job_type, status
                """,
                (document_id,),
            )
            jobs = cur.fetchall()
    return {
        "document": _json_safe(document or {}),
        "semanticAnnotations": _json_safe(semantic),
        "extractions": _json_safe(extractions),
        "fieldCandidates": _json_safe(field_candidates),
        "lineItemCandidates": _json_safe(line_candidates),
        "embeddings": _json_safe(embeddings),
        "jobs": _json_safe(jobs),
    }


def _json_safe(value: Any) -> Any:
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, tuple):
        return [_json_safe(item) for item in value]
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, UUID):
        return str(value)
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


if __name__ == "__main__":
    started = time.monotonic()
    try:
        raise SystemExit(main())
    finally:
        elapsed = int(time.monotonic() - started)
        print(json.dumps({"stage": "finished", "elapsed_seconds": elapsed}), flush=True)

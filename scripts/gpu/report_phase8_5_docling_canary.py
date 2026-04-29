#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from uuid import UUID

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from lib.extraction.repository import load_extraction_source  # noqa: E402
from lib.semantic_annotations.docling_audit import build_docling_audit  # noqa: E402


def main() -> int:
    args = _parse_args()
    document_ids = list(args.document_id or [])
    if args.pdf:
        from scripts.gpu.run_phase8_5_private_corpus import (  # noqa: PLC0415
            _ingest_pdf,
            _resolve_owner,
            _run_docling,
        )

        owner = _resolve_owner(args.household_id, args.user_id)
        for pdf in args.pdf:
            document_id = _ingest_pdf(pdf, owner=owner, title_prefix=args.title_prefix)
            _run_docling(document_id, timeout_seconds=args.docling_timeout_seconds)
            document_ids.append(document_id)
    reports = [_audit_document(document_id) for document_id in document_ids]
    payload = {"documents": reports}
    serialized = json.dumps(payload, indent=2, sort_keys=True)
    if args.json_output:
        args.json_output.write_text(serialized + "\n", encoding="utf-8")
    print(serialized)
    return 0


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Report Docling parse signals for Phase 8.5 PDFs.")
    parser.add_argument("--document-id", action="append", type=UUID)
    parser.add_argument("--pdf", action="append", type=Path)
    parser.add_argument("--json-output", type=Path)
    parser.add_argument("--title-prefix", default="Phase 8.5 Docling Canary")
    parser.add_argument("--household-id", type=UUID)
    parser.add_argument("--user-id", type=UUID)
    parser.add_argument("--docling-timeout-seconds", type=int, default=1800)
    args = parser.parse_args()
    if not args.document_id and not args.pdf:
        parser.error("provide at least one --document-id or --pdf")
    return args


def _audit_document(document_id: UUID) -> dict[str, object]:
    source = load_extraction_source(document_id)
    return build_docling_audit(source).to_json()


if __name__ == "__main__":
    raise SystemExit(main())

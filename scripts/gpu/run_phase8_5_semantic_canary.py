#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any
from uuid import UUID

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from lib.extraction.repository import load_extraction_source  # noqa: E402
from lib.model_runtime.profiles import QWEN_SEMANTIC_PROFILE, get_model_profile  # noqa: E402
from lib.semantic_annotations.docling_audit import build_docling_audit  # noqa: E402
from lib.semantic_annotations.schema_fit import schema_fit_for_region  # noqa: E402
from lib.semantic_annotations.service import default_semantic_annotation_gateway  # noqa: E402
from scripts.gpu.run_phase8_5_private_corpus import (  # noqa: E402
    _ingest_pdf,
    _resolve_owner,
    _run_docling,
)

CANARY_MODES = (
    "qwen3-vl-4b-adaptive",
    "qwen3-vl-4b-current",
    "qwen3-vl-2b-historical",
)


def main() -> int:
    args = parse_args()
    if args.mode == "qwen3-vl-2b-historical":
        raise SystemExit(
            "qwen3-vl-2b-historical canary mode requires a separately running historical "
            "2B service; the active Phase 8.5 runtime uses Qwen3-VL-4B."
        )
    owner = _resolve_owner(args.household_id, args.user_id) if args.pdf else None
    document_ids = list(args.document_id)
    for pdf_path in args.pdf:
        assert owner is not None
        document_id = _ingest_pdf(pdf_path, owner=owner, title_prefix=args.title_prefix)
        _run_docling(document_id, timeout_seconds=args.docling_timeout_seconds)
        document_ids.append(document_id)
    if not document_ids:
        raise SystemExit("at least one --document-id or --pdf is required")

    documents = [
        _semantic_report(document_id=document_id, mode=args.mode) for document_id in document_ids
    ]
    report = {
        "schema_name": "phase8_5_semantic_canary_report",
        "schema_version": "v1",
        "mode": args.mode,
        "skip_granite": True,
        "documents": documents,
    }
    rendered = json.dumps(report, indent=2, sort_keys=True)
    if args.json_output:
        args.json_output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run a Phase 8.5 semantic-only canary.")
    parser.add_argument("--document-id", action="append", type=UUID, default=[])
    parser.add_argument("--pdf", action="append", type=Path, default=[])
    parser.add_argument("--mode", choices=CANARY_MODES, default="qwen3-vl-4b-adaptive")
    parser.add_argument(
        "--skip-granite",
        action="store_true",
        default=True,
        help="Kept for explicitness; this harness never enqueues Granite extraction.",
    )
    parser.add_argument("--json-output", type=Path)
    parser.add_argument("--title-prefix", default="Phase 8.5 Semantic Canary")
    parser.add_argument("--household-id", type=UUID)
    parser.add_argument("--user-id", type=UUID)
    parser.add_argument("--docling-timeout-seconds", type=int, default=1800)
    return parser


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    return build_parser().parse_args(argv)


def _semantic_report(*, document_id: UUID, mode: str) -> dict[str, Any]:
    source = load_extraction_source(document_id)
    audit = build_docling_audit(source)
    result = default_semantic_annotation_gateway().annotate(source, quality_mode="smart")
    manifest = result.manifest
    document_type_hint = (
        str(manifest.manifest["document_type"])
        if isinstance(manifest.manifest.get("document_type"), str)
        else None
    )
    schema_fit = [
        {
            "semantic_type": region.semantic_type,
            "granite_task": region.granite_task,
            "target_schema": region.target_schema,
            "schema_fit": schema_fit_for_region(
                source=source,
                region=region,
                document_type_hint=document_type_hint,
            ).to_json(),
        }
        for region in manifest.regions
    ]
    return {
        "document_id": str(document_id),
        "filename": source.original_filename,
        "title": source.title,
        "mode": mode,
        "skip_granite": True,
        "docling": {
            "page_count": audit.page_count,
            "element_count": audit.element_count,
            "table_count": audit.table_count,
            "lexical_anchors": list(audit.lexical_anchors),
            "suggested_family_hints": list(audit.suggested_family_hints),
        },
        "qwen": {
            "profile_name": manifest.profile_name,
            "profile_base_model": get_model_profile(QWEN_SEMANTIC_PROFILE).base_model,
            "model_name": manifest.model_name,
            "model_version": manifest.model_version,
            "source_engine": manifest.source_engine,
            "prompt_version": manifest.prompt_version,
            "image_fan_in_sequence": _image_fan_in_sequence(
                page_count=len(source.pages),
                confidence=manifest.confidence,
            ),
            "fallback_reason": manifest.confidence.get("fallback_reason"),
        },
        "semantic": {
            "document_type": manifest.manifest.get("document_type"),
            "page_document_hints": [
                {
                    "page_number": page.page_number,
                    "document_type_hint": page.document_type_hint,
                    "page_role": page.page_role,
                    "confidence": page.confidence,
                }
                for page in manifest.pages
            ],
            "regions": [
                {
                    "semantic_type": region.semantic_type,
                    "granite_task": region.granite_task,
                    "target_schema": region.target_schema,
                    "expected_fields": list(region.expected_fields),
                    "priority": region.priority,
                    "confidence": region.confidence,
                    "review_required": region.review_required,
                }
                for region in manifest.regions
            ],
            "schema_fit": schema_fit,
            "confidence": manifest.confidence,
        },
    }


def _image_fan_in_sequence(*, page_count: int, confidence: dict[str, Any]) -> list[int]:
    max_images = get_model_profile(QWEN_SEMANTIC_PROFILE).max_images_per_request or 1
    if confidence.get("fallback_reason"):
        return [min(page_count, max_images)] + [1 for _ in range(page_count)]
    chunk_count = confidence.get("chunk_count")
    if isinstance(chunk_count, int) and chunk_count > 1:
        sequence: list[int] = []
        remaining = page_count
        while remaining > 0:
            size = min(max_images, remaining)
            sequence.append(size)
            remaining -= size
        return sequence
    return [min(page_count, max_images)]


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any
from uuid import UUID

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from lib.extraction.models import ExtractionSourceDocument, ParsedPageText  # noqa: E402
from lib.extraction.repository import load_extraction_source  # noqa: E402
from lib.model_runtime.profiles import QWEN_SEMANTIC_PROFILE, get_model_profile  # noqa: E402
from lib.semantic_annotations.docling_audit import build_docling_audit  # noqa: E402
from lib.semantic_annotations.docling_context import build_docling_context  # noqa: E402
from lib.semantic_annotations.qwen_gateway import (  # noqa: E402
    _max_output_tokens_for_profile,
    _prompt,
)
from lib.semantic_annotations.schema import semantic_annotation_model_output_schema  # noqa: E402
from lib.semantic_annotations.schema_fit import schema_fit_for_region  # noqa: E402
from lib.semantic_annotations.service import default_semantic_annotation_gateway  # noqa: E402
from lib.storage import ObjectStorage  # noqa: E402
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
    image_fan_in_sequence = _image_fan_in_sequence(
        page_count=len(source.pages),
        confidence=manifest.confidence,
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
            "image_fan_in_sequence": image_fan_in_sequence,
            "fallback_reason": manifest.confidence.get("fallback_reason"),
        },
        "token_budget": _token_budget_report(
            source,
            selected_fan_in_sequence=image_fan_in_sequence,
        ),
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


def _token_budget_report(
    source: ExtractionSourceDocument,
    *,
    selected_fan_in_sequence: list[int],
    storage: ObjectStorage | None = None,
) -> dict[str, Any]:
    profile = get_model_profile(QWEN_SEMANTIC_PROFILE)
    compression = profile.visual_token_spatial_compression or 32
    min_visual_tokens = profile.visual_token_min_per_image or 0
    max_visual_tokens = profile.visual_token_max_per_image or 0
    min_pixels = min_visual_tokens * compression * compression if min_visual_tokens else None
    max_pixels = max_visual_tokens * compression * compression if max_visual_tokens else None
    prompt_context = build_docling_context(
        source,
        include_pages_alias=False,
        include_page_image_hashes=False,
        include_element_bboxes=False,
    )
    docling_context_json = json.dumps(prompt_context, sort_keys=True, separators=(",", ":"))
    schema_json = json.dumps(semantic_annotation_model_output_schema(), sort_keys=True)
    schema_token_estimate = _estimate_text_tokens(schema_json)
    requested_output_tokens = _max_output_tokens_for_profile(QWEN_SEMANTIC_PROFILE)
    page_images = [
        _page_image_budget(
            page,
            storage=storage,
            compression=compression,
            min_pixels=min_pixels,
            max_pixels=max_pixels,
        )
        for page in source.pages
    ]
    return {
        "profile_name": QWEN_SEMANTIC_PROFILE,
        "max_model_len": profile.max_model_len,
        "spatial_compression": compression,
        "visual_token_min_per_image": min_visual_tokens,
        "visual_token_max_per_image": max_visual_tokens,
        "mm_processor_kwargs": (
            {"size": {"shortest_edge": min_pixels, "longest_edge": max_pixels}}
            if min_pixels and max_pixels
            else None
        ),
        "selected_fan_in_sequence": list(selected_fan_in_sequence),
        "prompt_context_includes_legacy_pages_alias": "pages" in prompt_context,
        "prompt_context_includes_page_image_hashes": _context_has_key(
            prompt_context, "imageSha256"
        ),
        "prompt_context_includes_element_bboxes": _context_has_key(prompt_context, "bbox"),
        "docling_context_text_token_estimate": _estimate_text_tokens(docling_context_json),
        "prompt_token_estimate": _estimate_text_tokens(_prompt(source)),
        "schema_token_estimate": schema_token_estimate,
        "requested_output_tokens": requested_output_tokens,
        "page_images": page_images,
        "request_windows": _token_budget_windows(
            source,
            page_images=page_images,
            schema_token_estimate=schema_token_estimate,
            requested_output_tokens=requested_output_tokens,
        ),
    }


def _page_image_budget(
    page: ParsedPageText,
    *,
    storage: ObjectStorage | None,
    compression: int,
    min_pixels: int | None,
    max_pixels: int | None,
) -> dict[str, Any]:
    image_bytes = page.image_bytes
    if image_bytes is None and page.image_asset_uri:
        image_bytes = (storage or ObjectStorage()).path_for_uri(page.image_asset_uri).read_bytes()
    dimensions = _image_dimensions(image_bytes or b"")
    if dimensions is None:
        return {
            "page_number": page.page_number,
            "mime_type": page.image_mime_type,
            "width_px": None,
            "height_px": None,
            "byte_size": len(image_bytes or b""),
            "raw_visual_token_estimate": None,
            "qwen_grid_estimate": None,
        }
    width, height = dimensions
    return {
        "page_number": page.page_number,
        "mime_type": page.image_mime_type,
        "width_px": width,
        "height_px": height,
        "byte_size": len(image_bytes or b""),
        "raw_visual_token_estimate": _visual_token_estimate(
            width=width,
            height=height,
            compression=compression,
        ),
        "qwen_grid_estimate": _qwen_grid_estimate(
            width=width,
            height=height,
            compression=compression,
            min_pixels=min_pixels,
            max_pixels=max_pixels,
        ),
    }


def _token_budget_windows(
    source: ExtractionSourceDocument,
    *,
    page_images: list[dict[str, Any]],
    schema_token_estimate: int,
    requested_output_tokens: int,
) -> list[dict[str, Any]]:
    max_images = get_model_profile(QWEN_SEMANTIC_PROFILE).max_images_per_request or 1
    by_page_number = {int(item["page_number"]): item for item in page_images}
    windows: list[dict[str, Any]] = []
    for index in range(0, len(source.pages), max_images):
        pages = source.pages[index : index + max_images]
        page_numbers = [page.page_number for page in pages]
        focus_page_numbers = set(page_numbers) if len(source.pages) > max_images else None
        prompt_tokens = _estimate_text_tokens(
            _prompt(source, focus_page_numbers=focus_page_numbers)
        )
        visual_tokens = sum(
            _page_visual_tokens(by_page_number.get(page_number)) for page_number in page_numbers
        )
        windows.append(
            {
                "page_numbers": page_numbers,
                "image_count": len(pages),
                "prompt_token_estimate": prompt_tokens,
                "schema_token_estimate": schema_token_estimate,
                "visual_token_estimate": visual_tokens,
                "requested_output_tokens": requested_output_tokens,
                "conservative_total_token_estimate": (
                    prompt_tokens + schema_token_estimate + visual_tokens + requested_output_tokens
                ),
            }
        )
    return windows


def _page_visual_tokens(page_budget: dict[str, Any] | None) -> int:
    if not page_budget:
        return 0
    grid = page_budget.get("qwen_grid_estimate")
    if not isinstance(grid, dict):
        return 0
    visual_tokens = grid.get("visual_tokens")
    return int(visual_tokens) if isinstance(visual_tokens, int | float) else 0


def _context_has_key(value: object, key: str) -> bool:
    if isinstance(value, dict):
        return key in value or any(_context_has_key(item, key) for item in value.values())
    if isinstance(value, list):
        return any(_context_has_key(item, key) for item in value)
    return False


def _qwen_grid_estimate(
    *,
    width: int,
    height: int,
    compression: int,
    min_pixels: int | None,
    max_pixels: int | None,
) -> dict[str, int]:
    pixels = width * height
    target_pixels = pixels
    if max_pixels and target_pixels > max_pixels:
        target_pixels = max_pixels
    if min_pixels and target_pixels < min_pixels:
        target_pixels = min_pixels
    scale = math.sqrt(target_pixels / pixels) if pixels > 0 else 1.0
    resized_width = max(1, round(width * scale))
    resized_height = max(1, round(height * scale))
    grid_width = max(1, math.ceil(resized_width / compression))
    grid_height = max(1, math.ceil(resized_height / compression))
    if max_pixels:
        max_visual_tokens = max(1, max_pixels // (compression * compression))
        while grid_width * grid_height > max_visual_tokens:
            if grid_width >= grid_height and grid_width > 1:
                grid_width -= 1
            elif grid_height > 1:
                grid_height -= 1
            else:
                break
        resized_width = min(resized_width, grid_width * compression)
        resized_height = min(resized_height, grid_height * compression)
    return {
        "resized_width_px": resized_width,
        "resized_height_px": resized_height,
        "grid_width": grid_width,
        "grid_height": grid_height,
        "visual_tokens": grid_width * grid_height,
    }


def _visual_token_estimate(*, width: int, height: int, compression: int) -> int:
    return math.ceil((width * height) / (compression * compression))


def _estimate_text_tokens(value: str) -> int:
    if not value:
        return 0
    return math.ceil(len(value) / 4)


def _image_dimensions(image_bytes: bytes) -> tuple[int, int] | None:
    if len(image_bytes) >= 24 and image_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
        return (
            int.from_bytes(image_bytes[16:20], "big"),
            int.from_bytes(image_bytes[20:24], "big"),
        )
    if len(image_bytes) >= 4 and image_bytes.startswith(b"\xff\xd8"):
        return _jpeg_dimensions(image_bytes)
    return None


def _jpeg_dimensions(image_bytes: bytes) -> tuple[int, int] | None:
    index = 2
    while index + 9 < len(image_bytes):
        if image_bytes[index] != 0xFF:
            index += 1
            continue
        marker = image_bytes[index + 1]
        index += 2
        if marker in {0xD8, 0xD9}:
            continue
        if index + 2 > len(image_bytes):
            return None
        segment_length = int.from_bytes(image_bytes[index : index + 2], "big")
        if segment_length < 2 or index + segment_length > len(image_bytes):
            return None
        if marker in {
            0xC0,
            0xC1,
            0xC2,
            0xC3,
            0xC5,
            0xC6,
            0xC7,
            0xC9,
            0xCA,
            0xCB,
            0xCD,
            0xCE,
            0xCF,
        }:
            height = int.from_bytes(image_bytes[index + 3 : index + 5], "big")
            width = int.from_bytes(image_bytes[index + 5 : index + 7], "big")
            return width, height
        index += segment_length
    return None


if __name__ == "__main__":
    raise SystemExit(main())

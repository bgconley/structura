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

    expectations = _load_expectations(args.expectations_json)
    documents = [
        _semantic_report(document_id=document_id, mode=args.mode) for document_id in document_ids
    ]
    scorecard = _score_documents(documents, expectations) if expectations else None
    report = {
        "schema_name": "phase8_5_semantic_canary_report",
        "schema_version": "v1",
        "mode": args.mode,
        "skip_granite": True,
        "documents": documents,
    }
    if scorecard is not None:
        report["scorecard"] = scorecard
    rendered = json.dumps(report, indent=2, sort_keys=True)
    if args.json_output:
        args.json_output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    if scorecard is not None and not bool(scorecard["passed"]):
        return 1
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
    parser.add_argument(
        "--expectations-json",
        type=Path,
        help="Optional private canary expectations keyed by filename, title, or document ID.",
    )
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
            "anchor_counts": audit.anchor_counts,
            "suggested_family_hints": list(audit.suggested_family_hints),
            "family_tension": list(audit.family_tension),
            "table_summaries": [
                {
                    "page_number": table.page_number,
                    "table_index": table.table_index,
                    "table_signal": table.table_signal,
                    "weak_signal_reason": table.weak_signal_reason,
                    "markdown_snippet": table.markdown_snippet,
                    "has_table_json": table.has_table_json,
                }
                for table in audit.table_summaries
            ],
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
                    **page.metadata,
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
                    **region.metadata,
                }
                for region in manifest.regions
            ],
            "schema_fit": schema_fit,
            "confidence": manifest.confidence,
            "document_type_candidates": manifest.manifest.get("document_type_candidates", []),
            "planner_notes": manifest.manifest.get("planner_notes", []),
        },
    }


def _load_expectations(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise SystemExit("--expectations-json must contain a JSON object")
    documents = payload.get("documents")
    if not isinstance(documents, dict):
        raise SystemExit("--expectations-json must contain a documents object")
    return payload


def _score_documents(
    documents: list[dict[str, Any]],
    expectations: dict[str, Any],
) -> dict[str, Any]:
    expected_documents = expectations.get("documents")
    if not isinstance(expected_documents, dict):
        return {"passed": True, "documents": []}
    results = []
    for document in documents:
        expectation = _expectation_for_document(document, expected_documents)
        if expectation is None:
            results.append(
                {
                    "document_key": _document_key(document),
                    "passed": True,
                    "checks": [
                        {
                            "name": "expectation_present",
                            "passed": True,
                            "detail": "no expectation configured",
                        }
                    ],
                }
            )
            continue
        checks = _score_document(document, expectation)
        results.append(
            {
                "document_key": _document_key(document),
                "passed": all(bool(check["passed"]) for check in checks),
                "checks": checks,
            }
        )
    return {
        "passed": all(bool(result["passed"]) for result in results),
        "documents": results,
    }


def _expectation_for_document(
    document: dict[str, Any],
    expected_documents: dict[str, Any],
) -> dict[str, Any] | None:
    for key in (
        str(document.get("filename") or ""),
        str(document.get("title") or ""),
        str(document.get("document_id") or ""),
    ):
        expectation = expected_documents.get(key)
        if isinstance(expectation, dict):
            return expectation
    return None


def _score_document(
    document: dict[str, Any],
    expectation: dict[str, Any],
) -> list[dict[str, Any]]:
    semantic_raw = document.get("semantic")
    semantic: dict[str, Any] = semantic_raw if isinstance(semantic_raw, dict) else {}
    docling_raw = document.get("docling")
    docling: dict[str, Any] = docling_raw if isinstance(docling_raw, dict) else {}
    regions_raw = semantic.get("regions")
    regions: list[Any] = regions_raw if isinstance(regions_raw, list) else []
    pages_raw = semantic.get("page_document_hints")
    pages: list[Any] = pages_raw if isinstance(pages_raw, list) else []
    semantic_types = {
        str(region.get("semantic_type"))
        for region in regions
        if isinstance(region, dict) and region.get("semantic_type")
    }
    target_schemas = {
        str(region.get("target_schema"))
        for region in regions
        if isinstance(region, dict) and region.get("target_schema")
    }
    continuation_groups = {
        str(item.get("continuation_group"))
        for item in [*pages, *regions]
        if isinstance(item, dict) and item.get("continuation_group")
    }
    table_summaries_raw = docling.get("table_summaries")
    table_summaries = table_summaries_raw if isinstance(table_summaries_raw, list) else []
    docling_table_signals = {
        str(table.get("table_signal"))
        for table in table_summaries
        if isinstance(table, dict) and table.get("table_signal")
    }
    planner_table_signals = {
        str(page.get("docling_table_signal"))
        for page in pages
        if isinstance(page, dict) and page.get("docling_table_signal")
    }
    full_page_image_semantic_types = {
        str(region.get("semantic_type"))
        for region in regions
        if isinstance(region, dict)
        and region.get("semantic_type")
        and region.get("requires_full_page_image") is True
    }
    checks = [
        _check_in(
            "document_type",
            semantic.get("document_type"),
            _string_set(expectation.get("expected_document_types")),
            required=False,
        ),
        _check_not_in(
            "forbidden_document_type",
            semantic.get("document_type"),
            _string_set(expectation.get("forbidden_document_types")),
        ),
        _check_contains_all(
            "required_semantic_types",
            semantic_types,
            _string_set(expectation.get("required_semantic_types")),
        ),
        _check_disjoint(
            "forbidden_semantic_types",
            semantic_types,
            _string_set(expectation.get("forbidden_semantic_types")),
        ),
        _check_contains_all(
            "required_target_schemas",
            target_schemas,
            _string_set(expectation.get("required_target_schemas")),
        ),
        _check_disjoint(
            "forbidden_target_schemas",
            target_schemas,
            _string_set(expectation.get("forbidden_target_schemas")),
        ),
        _check_minimum("min_region_count", len(regions), expectation.get("min_region_count")),
        _check_minimum("min_page_count", len(pages), expectation.get("min_page_count")),
        _check_contains_all(
            "required_docling_family_hints",
            set(_string_list(docling.get("suggested_family_hints"))),
            _string_set(expectation.get("required_docling_family_hints")),
        ),
        _check_contains_all(
            "required_lexical_anchors",
            set(_string_list(docling.get("lexical_anchors"))),
            _string_set(expectation.get("required_lexical_anchors")),
        ),
        _check_contains_all(
            "required_continuation_groups",
            continuation_groups,
            _string_set(expectation.get("required_continuation_groups")),
        ),
        _check_contains_all(
            "required_docling_table_signals",
            docling_table_signals | planner_table_signals,
            _string_set(expectation.get("required_docling_table_signals")),
        ),
        _check_contains_all(
            "required_full_page_image_semantic_types",
            full_page_image_semantic_types,
            _string_set(expectation.get("required_full_page_image_semantic_types")),
        ),
    ]
    checks.extend(
        _check_required_region_attributes(
            regions,
            expectation.get("required_region_attributes"),
        )
    )
    if expectation.get("require_page_coverage", True):
        checks.append(
            {
                "name": "page_coverage",
                "passed": len(pages) == int(docling.get("page_count") or 0),
                "expected": docling.get("page_count"),
                "actual": len(pages),
            }
        )
    return checks


def _check_in(
    name: str,
    actual: object,
    expected: set[str],
    *,
    required: bool = True,
) -> dict[str, Any]:
    if not expected and not required:
        return {"name": name, "passed": True, "detail": "not configured"}
    actual_str = str(actual) if actual is not None else ""
    return {
        "name": name,
        "passed": actual_str in expected,
        "expected": sorted(expected),
        "actual": actual_str,
    }


def _check_not_in(name: str, actual: object, forbidden: set[str]) -> dict[str, Any]:
    if not forbidden:
        return {"name": name, "passed": True, "detail": "not configured"}
    actual_str = str(actual) if actual is not None else ""
    return {
        "name": name,
        "passed": actual_str not in forbidden,
        "forbidden": sorted(forbidden),
        "actual": actual_str,
    }


def _check_contains_all(name: str, actual: set[str], required: set[str]) -> dict[str, Any]:
    missing = sorted(required - actual)
    return {
        "name": name,
        "passed": not missing,
        "required": sorted(required),
        "actual": sorted(actual),
        "missing": missing,
    }


def _check_disjoint(name: str, actual: set[str], forbidden: set[str]) -> dict[str, Any]:
    present = sorted(actual & forbidden)
    return {
        "name": name,
        "passed": not present,
        "forbidden": sorted(forbidden),
        "actual": sorted(actual),
        "present": present,
    }


def _check_minimum(name: str, actual: int, expected: object) -> dict[str, Any]:
    if not isinstance(expected, int):
        return {"name": name, "passed": True, "detail": "not configured", "actual": actual}
    return {"name": name, "passed": actual >= expected, "expected": expected, "actual": actual}


def _check_required_region_attributes(
    regions: list[Any],
    requirements: object,
) -> list[dict[str, Any]]:
    if not isinstance(requirements, list):
        return [
            {
                "name": "required_region_attributes",
                "passed": True,
                "detail": "not configured",
            }
        ]
    checks: list[dict[str, Any]] = []
    for index, requirement in enumerate(requirements):
        if not isinstance(requirement, dict):
            checks.append(
                {
                    "name": f"required_region_attributes[{index}]",
                    "passed": False,
                    "detail": "requirement must be an object",
                }
            )
            continue
        semantic_type = requirement.get("semantic_type")
        field = requirement.get("field")
        expected = requirement.get("value")
        matched = any(
            isinstance(region, dict)
            and region.get("semantic_type") == semantic_type
            and region.get(str(field)) == expected
            for region in regions
            if isinstance(field, str)
        )
        checks.append(
            {
                "name": f"required_region_attributes[{index}]",
                "passed": matched,
                "semantic_type": semantic_type,
                "field": field,
                "expected": expected,
            }
        )
    return checks


def _string_set(value: object) -> set[str]:
    return set(_string_list(value))


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str) and item]


def _document_key(document: dict[str, Any]) -> str:
    return str(document.get("filename") or document.get("title") or document.get("document_id"))


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

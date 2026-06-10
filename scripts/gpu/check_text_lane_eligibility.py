"""E0 gate check: text-lane eligibility over live corpus documents.

For every document matching the title prefix (default: the pinned run-9
corpus), evaluates each Docling table through the text-lane grid parser,
table signal, and page-quality screens, and prints a lane verdict per table
plus a per-document rollup. Expected (per the E0 gate): table-bearing text
documents report eligible tables; low-text scans report vision.

Runs on the GPU node from the host venv (same DB access pattern as
run_phase8_5_resident_corpus.py). Read-only.
"""

from __future__ import annotations

import argparse
import json
from typing import Any
from uuid import UUID

from lib.db.connection import db_connection
from lib.documents.quality import PageQualityInput, classify_page_quality
from lib.extraction.source_repository import load_extraction_source
from lib.extraction.text_lane.table_grid import TableGrid
from lib.semantic_annotations.docling_audit import build_docling_audit

DEFAULT_TITLE_PREFIX = "Phase 8.5 Production Corpus 20260610T070545Z"
_DIFFICULT_PAGE_REASONS = frozenset(
    {
        "handwriting",
        "missing_text_layer",
        "low_text_density",
        "low_ocr_confidence",
        "degraded_scan",
    }
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--title-prefix", default=DEFAULT_TITLE_PREFIX)
    parser.add_argument("--document-id", action="append", default=[])
    parser.add_argument("--json", action="store_true", help="emit JSON instead of text")
    return parser


def _document_ids(title_prefix: str) -> list[tuple[UUID, str]]:
    with db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, original_filename
                FROM documents
                WHERE deleted_at IS NULL
                  AND title LIKE %s
                ORDER BY original_filename
                """,
                (title_prefix + "%",),
            )
            return [(row["id"], str(row["original_filename"] or "")) for row in cur.fetchall()]


def _page_reasons(source, page_number: int) -> tuple[str, ...]:  # noqa: ANN001
    page = next((item for item in source.pages if item.page_number == page_number), None)
    if page is None:
        return ("page_not_found",)
    signals = classify_page_quality(
        PageQualityInput(
            page_number=page.page_number,
            text=page.text,
            has_text_layer=page.has_text_layer,
            ocr_confidence=page.ocr_confidence,
            metadata=page.metadata,
        )
    )
    return tuple(reason for reason in signals.reasons if reason in _DIFFICULT_PAGE_REASONS)


def evaluate_document(document_id: UUID) -> dict[str, Any]:
    source = load_extraction_source(document_id)
    audit = build_docling_audit(source)
    signals = {summary.table_id: summary.table_signal for summary in audit.table_summaries}
    tables: list[dict[str, Any]] = []
    for table in source.tables:
        grid = TableGrid.from_parsed_table(table)
        difficult = _page_reasons(source, table.page_number)
        if grid is None:
            lane, reason = "vision", "table_grid_missing"
        elif not grid.data_row_indexes:
            lane, reason = "vision", "table_grid_has_no_data_rows"
        elif signals.get(table.table_id) != "strong":
            lane, reason = "vision", f"table_signal_{signals.get(table.table_id) or 'unknown'}"
        elif difficult:
            lane, reason = "vision", "difficult_page:" + ",".join(difficult)
        else:
            lane, reason = "text", "strong_table_on_text_page"
        tables.append(
            {
                "table_id": str(table.table_id),
                "page_number": table.page_number,
                "grid": (f"{grid.num_rows}x{grid.num_cols}" if grid is not None else None),
                "data_rows": len(grid.data_row_indexes) if grid is not None else 0,
                "lane": lane,
                "reason": reason,
            }
        )
    page_reasons = {
        page.page_number: list(_page_reasons(source, page.page_number)) for page in source.pages
    }
    return {
        "document_id": str(document_id),
        "table_count": len(source.tables),
        "eligible_tables": sum(1 for table in tables if table["lane"] == "text"),
        "all_pages_difficult": bool(page_reasons) and all(page_reasons.values()),
        "page_reasons": page_reasons,
        "tables": tables,
    }


def main() -> int:
    args = build_parser().parse_args()
    documents: list[tuple[UUID, str]]
    if args.document_id:
        documents = [(UUID(value), value) for value in args.document_id]
    else:
        documents = _document_ids(args.title_prefix)
    results = []
    for document_id, filename in documents:
        result = evaluate_document(document_id)
        result["filename"] = filename
        results.append(result)
    if args.json:
        print(json.dumps(results, indent=2, sort_keys=True))
        return 0
    for result in results:
        verdict = (
            "SCAN->vision"
            if result["all_pages_difficult"]
            else f"{result['eligible_tables']}/{result['table_count']} tables text-eligible"
        )
        print(f"{result['filename'] or result['document_id']}: {verdict}")
        for table in result["tables"]:
            print(
                f"    p{table['page_number']} {table['grid']} rows={table['data_rows']} "
                f"-> {table['lane']} ({table['reason']})"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

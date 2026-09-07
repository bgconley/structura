"""Simple deterministic region/grid diagnostics; never pixel-support judgments."""

from __future__ import annotations

from collections import Counter
from typing import Any

from lib.document_parsing.structure import SourceBox, StructurePage
from lib.evaluation.annotations import AnnotatedPage
from lib.evaluation.text_scoring import counts, normalized_text


def intersection_over_union(left: SourceBox, right: SourceBox) -> float:
    intersection = max(0.0, min(left.right, right.right) - max(left.left, right.left)) * max(
        0.0, min(left.bottom, right.bottom) - max(left.top, right.top)
    )
    area_left = (left.right - left.left) * (left.bottom - left.top)
    area_right = (right.right - right.left) * (right.bottom - right.top)
    return intersection / (area_left + area_right - intersection)


def match_regions(gold: AnnotatedPage, actual: StructurePage) -> dict[int, int]:
    candidates = []
    for gi, region in enumerate(gold.regions):
        for ai, element in enumerate(actual.elements):
            if region.kind != element.kind:
                continue
            overlap = intersection_over_union(region.bbox, element.bbox)
            exact_text = bool(region.text) and normalized_text(region.text) == normalized_text(
                element.text
            )
            # 0.1 is a versioned matching heuristic, not an acceptance threshold.
            if exact_text or overlap >= 0.1:
                candidates.append((int(exact_text), overlap, gi, ai))
    matched: dict[int, int] = {}
    used: set[int] = set()
    for _, _, gi, ai in sorted(candidates, key=lambda x: (-x[0], -x[1], x[2], x[3])):
        if gi not in matched and ai not in used:
            matched[gi] = ai
            used.add(ai)
    return matched


def page_layout_scores(gold: AnnotatedPage, actual: StructurePage) -> dict[str, Any]:
    matches = match_regions(gold, actual)
    positions = {region.id: index for index, region in enumerate(gold.regions)}
    ordered = 0
    missing_pairs = 0
    for before, after in gold.reading_order_pairs:
        first, second = matches.get(positions[before]), matches.get(positions[after])
        if first is None or second is None:
            missing_pairs += 1
        elif first < second:
            ordered += 1
    overlap_sum = sum(
        intersection_over_union(gold.regions[gi].bbox, actual.elements[ai].bbox)
        for gi, ai in matches.items()
    )
    return {
        "regions": counts(len(gold.regions), len(actual.elements), len(matches)),
        "geometry": {
            "expected_regions": len(gold.regions),
            "matched_regions": len(matches),
            "iou_sum": overlap_sum,
            "mean_iou_with_missing_zero": overlap_sum / len(gold.regions) if gold.regions else None,
            "source_pixel_support": "not_evaluated",
        },
        "reading_order": {
            "expected_pairs": len(gold.reading_order_pairs),
            "correct_pairs": ordered,
            "missing_pairs": missing_pairs,
            "reversed_pairs": len(gold.reading_order_pairs) - ordered - missing_pairs,
            "accuracy": ordered / len(gold.reading_order_pairs)
            if gold.reading_order_pairs
            else None,
        },
        "tables": _table_scores(gold, actual, matches),
    }


def _table_scores(
    gold: AnnotatedPage, actual: StructurePage, matches: dict[int, int]
) -> dict[str, Any]:
    by_region = {
        element.id: table
        for table in actual.tables
        for element in actual.elements
        if element.id == table.element_id
    }
    positions = {region.id: index for index, region in enumerate(gold.regions)}
    expected_cells = observed_cells = matched_cells = correct_spans = text_expected = text_exact = 0
    matched_tables = grids_exact = 0
    continuation = []
    matched_table_ids = set()
    for table in gold.tables:
        ai = matches.get(positions[table.region_id])
        predicted = by_region.get(actual.elements[ai].id) if ai is not None else None
        expected_cells += len(table.cells)
        text_expected += sum(cell.readability in {"readable", "blank"} for cell in table.cells)
        continuation.append(
            {
                "gold_group": table.continuation_group,
                "actual_group": predicted.continuation_key if predicted else None,
                "matched": predicted is not None,
            }
        )
        if predicted is None:
            continue
        matched_table_ids.add(predicted.id)
        matched_tables += 1
        grids_exact += (table.row_count, table.column_count) == (
            predicted.row_count,
            predicted.column_count,
        )
        cells = {(cell.row, cell.column): cell for cell in predicted.cells}
        for cell in table.cells:
            match = cells.get((cell.row, cell.column))
            if match is not None:
                matched_cells += 1
                correct_spans += (cell.row_span, cell.column_span) == (
                    match.row_span,
                    match.column_span,
                )
                if cell.readability in {"readable", "blank"}:
                    text_exact += normalized_text(cell.text) == normalized_text(match.text)
    observed_cells = sum(len(table.cells) for table in actual.tables)
    continuation.extend(
        {"gold_group": None, "actual_group": table.continuation_key, "matched": True}
        for table in actual.tables
        if table.id not in matched_table_ids
    )
    return {
        "tables": counts(len(gold.tables), len(actual.tables), matched_tables),
        "grid_exact": grids_exact,
        "grid_expected": len(gold.tables),
        "cells": counts(expected_cells, observed_cells, matched_cells),
        "span_exact": correct_spans,
        "span_expected": expected_cells,
        "cell_text_exact": text_exact,
        "cell_text_expected": text_expected,
        "continuation_observations": continuation,
    }


def continuation_scores(observations: list[dict[str, Any]]) -> dict[str, int]:
    # Count pair relationships by groups without quadratic work on long documents.
    gold = Counter(row["gold_group"] for row in observations if row["gold_group"] is not None)
    predicted = [row for row in observations if row["matched"] and row["actual_group"] is not None]
    actual = Counter(row["actual_group"] for row in predicted)
    joint = Counter(
        (row["gold_group"], row["actual_group"])
        for row in predicted
        if row["gold_group"] is not None
    )
    expected = sum(size * (size - 1) // 2 for size in gold.values())
    correct = sum(size * (size - 1) // 2 for size in joint.values())
    false_joins = sum(size * (size - 1) // 2 for size in actual.values()) - correct
    negative_pairs = len(observations) * (len(observations) - 1) // 2 - expected
    return {
        "expected_links": expected,
        "correct_links": correct,
        "omitted_links": expected - correct,
        "false_joins": false_joins,
        "unrelated_pairs": negative_pairs,
    }

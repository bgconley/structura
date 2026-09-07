"""Bounded occurrence-aware sequence scoring, without fuzzy text repairs."""

from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher
from typing import Any

from lib.document_parsing.structure import StructureChunk, StructurePage
from lib.evaluation.annotations import AnnotatedPage

MAX_PAGE_TOKENS = 5000


def normalized_text(text: str) -> str:
    return " ".join(unicodedata.normalize("NFC", text).split())


def counts(expected: int, observed: int, matched: int) -> dict[str, int | float | None]:
    return {
        "expected": expected,
        "observed": observed,
        "matched": matched,
        "omitted": expected - matched,
        "inserted": observed - matched,
        "recall": matched / expected if expected else None,
        "precision": matched / observed if observed else None,
    }


def sequence_counts(expected: str, observed: str) -> dict[str, int | float | None]:
    reference, actual = normalized_text(expected).split(), normalized_text(observed).split()
    if max(len(reference), len(actual)) > MAX_PAGE_TOKENS:
        raise ValueError("Page exceeds the frozen scorer token budget; no truncated scoring.")
    # Each occurrence can match at most once, in order. This is a deterministic
    # contiguous-block alignment, not minimum edit distance or a claimed WER.
    matched = sum(
        block.size
        for block in SequenceMatcher(None, reference, actual, autojunk=False).get_matching_blocks()
    )
    return counts(len(reference), len(actual), matched)


def annotated_text(page: AnnotatedPage) -> str:
    tables = {table.region_id: table for table in page.tables}
    parts = []
    for region in page.regions:
        parts.append(region.text)
        if region.id in tables:
            parts.extend(
                cell.text
                for cell in sorted(
                    tables[region.id].cells, key=lambda cell: (cell.row, cell.column)
                )
            )
    return "\n".join(parts)


def parsed_text(page: StructurePage) -> str:
    tables = {table.element_id: table for table in page.tables}
    parts = []
    for element in page.elements:
        parts.append(element.text)
        if element.id in tables:
            parts.extend(
                cell.text
                for cell in sorted(
                    tables[element.id].cells, key=lambda cell: (cell.row, cell.column)
                )
            )
    return "\n".join(parts)


def chunk_text(chunks: tuple[StructureChunk, ...]) -> str:
    # Consecutive pieces of one element can split a word at max_chars. Restore
    # those pieces without inserting a synthetic token boundary.
    parts: list[str] = []
    previous = None
    for chunk in chunks:
        if previous == chunk.element_ids:
            parts[-1] += chunk.text
        else:
            parts.append(chunk.text)
        previous = chunk.element_ids
    return "\n".join(parts)


def page_text_scores(
    gold: AnnotatedPage, actual: StructurePage, chunks: tuple[StructureChunk, ...]
) -> dict[str, Any]:
    unresolved = sum(r.readability in {"unreadable", "ambiguous"} for r in gold.regions)
    unresolved += sum(
        c.readability in {"unreadable", "ambiguous"} for t in gold.tables for c in t.cells
    )
    if unresolved:
        # Full-page sequence matching cannot safely distinguish an invented
        # transcript from a plausible unresolved region. Do not score it as truth.
        return {
            "status": "not_evaluated",
            "reason": "unresolved_reference_regions",
            "unresolved_regions": unresolved,
        }
    expected, observed = annotated_text(gold), parsed_text(actual)
    expected_normal, observed_normal = normalized_text(expected), normalized_text(observed)
    sensitive = {kind: [0, 0, 0] for kind in ("identifier", "amount", "date")}
    for item in gold.sensitive_text:
        pattern = rf"(?<!\w){re.escape(normalized_text(item.text))}(?!\w)"
        if len(re.findall(pattern, expected_normal)) != item.occurrences:
            raise ValueError("Sensitive-text occurrence labels disagree with source transcription.")
        found = len(re.findall(pattern, observed_normal))
        totals = sensitive[item.kind]
        totals[0] += item.occurrences
        totals[1] += found
        totals[2] += min(item.occurrences, found)
    return {
        "status": "computed",
        "parse_tokens": sequence_counts(expected, observed),
        "searchable_tokens": sequence_counts(expected, chunk_text(chunks)),
        "exact_sensitive_text": {kind: counts(*values) for kind, values in sensitive.items()},
    }

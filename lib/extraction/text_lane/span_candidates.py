"""Deterministic KVP span candidates from Docling elements (ADR 0006, E2).

Builds a bounded set of value spans the selection model may choose from:
label-adjacency pairs (same-line "Label: value", right-of and below-of via
element bboxes) and typed regex hits (money, date, identifier, phone, zip,
email). Every candidate carries an element/text-span anchor, so a selected
span becomes a Claim whose anchor is exact by construction. Span ids are
positional (page/element ordinal/char offsets), never run-specific UUIDs, so
two runs over the same parse render identical selection prompts.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from lib.extraction.models import ExtractionSourceDocument, ParsedElementText

MAX_SPANS_PER_PAGE = 80
_MAX_VALUE_CHARS = 80
_MAX_LABEL_CHARS = 60
_MAX_LABEL_WORDS = 6
_RIGHT_OF_MAX_GAP_POINTS = 220.0
_BELOW_OF_MAX_GAP_POINTS = 30.0

SpanKind = Literal[
    "label_colon",
    "label_right_of",
    "label_below_of",
    "regex_money",
    "regex_date",
    "regex_identifier",
    "regex_phone",
    "regex_zip",
    "regex_email",
]
SpanValueType = Literal["money", "date", "identifier", "text"]

_LABEL_COLON_PATTERN = re.compile(
    r"(?P<label>[A-Za-z][\w .,\-/&()#'%]{0,58}?)\s*[:：]\s*(?P<value>[^\n]{1,80})"
)
_TYPED_PATTERNS: tuple[tuple[SpanKind, SpanValueType, re.Pattern[str]], ...] = (
    (
        "regex_money",
        "money",
        re.compile(
            r"\(?-?[$€£]\s?\d{1,3}(?:,\d{3})*(?:\.\d{2})?\)?|\(?-?\d{1,3}(?:,\d{3})*\.\d{2}\)?-?"
        ),
    ),
    (
        "regex_date",
        "date",
        re.compile(
            r"\b(?:\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{4}-\d{2}-\d{2}|"
            r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.? \d{1,2},? \d{4})\b",
            re.IGNORECASE,
        ),
    ),
    ("regex_email", "text", re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")),
    (
        "regex_phone",
        "text",
        re.compile(r"\b(?:\+?1[ .-]?)?\(?\d{3}\)?[ .-]?\d{3}[ .-]?\d{4}\b"),
    ),
    ("regex_zip", "text", re.compile(r"\b\d{5}(?:-\d{4})?\b")),
    (
        "regex_identifier",
        "identifier",
        re.compile(r"\b(?=[A-Z0-9/#-]*\d)[A-Z0-9][A-Z0-9/#-]{5,24}\b"),
    ),
)


@dataclass(frozen=True)
class SpanCandidate:
    span_id: str
    page_number: int
    page_id: str | None
    element_id: str | None
    value_text: str
    label_text: str | None
    kind: SpanKind
    value_type: SpanValueType
    bbox: list[float] | None
    text_span: dict[str, object] | None

    def describe(self) -> str:
        label = f" label={self.label_text!r}" if self.label_text else ""
        return f"{self.span_id} [{self.kind}]{label} value={self.value_text!r}"


def span_candidates_for_page(
    source: ExtractionSourceDocument,
    page_number: int,
    *,
    limit: int = MAX_SPANS_PER_PAGE,
) -> list[SpanCandidate]:
    page_id = next(
        (str(page.page_id) for page in source.pages if page.page_number == page_number),
        None,
    )
    elements = [
        element
        for element in source.elements
        if element.page_number == page_number and element.text and element.text.strip()
    ]
    labeled: list[SpanCandidate] = []
    typed: list[SpanCandidate] = []
    for element in elements:
        labeled.extend(_label_colon_spans(element, page_id=page_id))
    labeled.extend(_adjacent_pair_spans(elements, page_id=page_id))
    for element in elements:
        typed.extend(_typed_regex_spans(element, page_id=page_id))
    ordered = _dedupe(labeled) + _dedupe(typed)
    seen_ids: set[str] = set()
    unique: list[SpanCandidate] = []
    for candidate in ordered:
        if candidate.span_id in seen_ids:
            continue
        seen_ids.add(candidate.span_id)
        unique.append(candidate)
    return unique[:limit]


def _label_colon_spans(
    element: ParsedElementText,
    *,
    page_id: str | None,
) -> list[SpanCandidate]:
    spans: list[SpanCandidate] = []
    for line_start, line in _lines(element.text):
        for match in _LABEL_COLON_PATTERN.finditer(line):
            label = " ".join(match.group("label").split())
            value = match.group("value").strip()
            if not value or len(label.split()) > _MAX_LABEL_WORDS:
                continue
            start = line_start + match.start("value")
            end = start + len(match.group("value").rstrip())
            spans.append(
                _candidate(
                    element=element,
                    page_id=page_id,
                    value_text=value[:_MAX_VALUE_CHARS],
                    label_text=label[:_MAX_LABEL_CHARS],
                    kind="label_colon",
                    value_type=_value_type_for_text(value),
                    start=start,
                    end=end,
                )
            )
    return spans


def _adjacent_pair_spans(
    elements: list[ParsedElementText],
    *,
    page_id: str | None,
) -> list[SpanCandidate]:
    spans: list[SpanCandidate] = []
    boxes = [(element, _bbox(element)) for element in elements]
    for label_element, label_box in boxes:
        if label_box is None or not _looks_like_label(label_element.text):
            continue
        for value_element, value_box in boxes:
            if value_element is label_element or value_box is None:
                continue
            text = " ".join(value_element.text.split())
            if not text or _looks_like_label(value_element.text):
                continue
            kind: SpanKind | None = None
            if _is_right_of(label_box, value_box):
                kind = "label_right_of"
            elif _is_below_of(label_box, value_box):
                kind = "label_below_of"
            if kind is None:
                continue
            spans.append(
                _candidate(
                    element=value_element,
                    page_id=page_id,
                    value_text=text[:_MAX_VALUE_CHARS],
                    label_text=" ".join(label_element.text.split())[:_MAX_LABEL_CHARS],
                    kind=kind,
                    value_type=_value_type_for_text(text),
                    start=0,
                    end=min(len(value_element.text), _MAX_VALUE_CHARS),
                )
            )
    return spans


def _typed_regex_spans(
    element: ParsedElementText,
    *,
    page_id: str | None,
) -> list[SpanCandidate]:
    spans: list[SpanCandidate] = []
    for kind, value_type, pattern in _TYPED_PATTERNS:
        for match in pattern.finditer(element.text):
            value = match.group(0).strip()
            if not value:
                continue
            spans.append(
                _candidate(
                    element=element,
                    page_id=page_id,
                    value_text=value[:_MAX_VALUE_CHARS],
                    label_text=None,
                    kind=kind,
                    value_type=value_type,
                    start=match.start(),
                    end=match.end(),
                )
            )
    return spans


def _candidate(
    *,
    element: ParsedElementText,
    page_id: str | None,
    value_text: str,
    label_text: str | None,
    kind: SpanKind,
    value_type: SpanValueType,
    start: int,
    end: int,
) -> SpanCandidate:
    return SpanCandidate(
        span_id=f"s{element.page_number}_{element.ordinal}_{start}_{end}",
        page_number=element.page_number,
        page_id=page_id,
        element_id=str(element.element_id),
        value_text=value_text,
        label_text=label_text,
        kind=kind,
        value_type=value_type,
        bbox=_bbox_list(element),
        text_span={"start": start, "end": end, "basis": "element_text"},
    )


def _dedupe(candidates: list[SpanCandidate]) -> list[SpanCandidate]:
    seen: set[tuple[str | None, str]] = set()
    unique: list[SpanCandidate] = []
    for candidate in candidates:
        key = (candidate.element_id, candidate.value_text.casefold())
        if key in seen:
            continue
        seen.add(key)
        unique.append(candidate)
    return unique


def _lines(text: str) -> list[tuple[int, str]]:
    lines: list[tuple[int, str]] = []
    offset = 0
    for line in text.split("\n"):
        lines.append((offset, line))
        offset += len(line) + 1
    return lines


def _looks_like_label(text: str) -> bool:
    normalized = " ".join(text.split())
    if not normalized or len(normalized) > _MAX_LABEL_CHARS:
        return False
    words = normalized.split()
    if len(words) > _MAX_LABEL_WORDS:
        return False
    if normalized.endswith(":"):
        return True
    letters = [char for char in normalized if char.isalpha()]
    if not letters:
        return False
    upper_ratio = sum(1 for char in letters if char.isupper()) / len(letters)
    return upper_ratio >= 0.7 and not any(char.isdigit() for char in normalized)


def _value_type_for_text(text: str) -> SpanValueType:
    stripped = text.strip()
    for kind, value_type, pattern in _TYPED_PATTERNS:
        del kind
        match = pattern.fullmatch(stripped)
        if match is not None:
            return value_type
    return "text"


def _bbox(element: ParsedElementText) -> tuple[float, float, float, float] | None:
    """Reading-space box (left, top, right, bottom) with top < bottom.

    Docling element bboxes persist with coord_origin BOTTOMLEFT (y grows
    upward), so y values are flipped for adjacency math. Evidence anchors
    keep the raw stored values via _bbox_list.
    """
    raw = _raw_bbox(element)
    if raw is None:
        return None
    left, top, right, bottom = raw
    if _coord_origin(element) == "BOTTOMLEFT":
        top, bottom = -top, -bottom
    if top > bottom:
        top, bottom = bottom, top
    return (left, top, right, bottom)


def _raw_bbox(element: ParsedElementText) -> tuple[float, float, float, float] | None:
    value = element.bbox
    if isinstance(value, dict):
        try:
            return (
                float(value["l"]),
                float(value["t"]),
                float(value["r"]),
                float(value["b"]),
            )
        except (KeyError, TypeError, ValueError):
            return None
    if isinstance(value, list | tuple) and len(value) == 4:
        try:
            left, top, right, bottom = (float(item) for item in value)
        except (TypeError, ValueError):
            return None
        return (left, top, right, bottom)
    return None


def _coord_origin(element: ParsedElementText) -> str:
    value = element.bbox
    if isinstance(value, dict):
        return str(value.get("coord_origin") or "").upper()
    return ""


def _bbox_list(element: ParsedElementText) -> list[float] | None:
    box = _raw_bbox(element)
    return list(box) if box is not None else None


def _is_right_of(
    label_box: tuple[float, float, float, float],
    value_box: tuple[float, float, float, float],
) -> bool:
    label_left, label_top, label_right, label_bottom = label_box
    value_left, value_top, value_right, value_bottom = value_box
    del label_left, value_right
    vertical_overlap = min(label_bottom, value_bottom) - max(label_top, value_top)
    if vertical_overlap <= 0:
        return False
    gap = value_left - label_right
    return 0 <= gap <= _RIGHT_OF_MAX_GAP_POINTS


def _is_below_of(
    label_box: tuple[float, float, float, float],
    value_box: tuple[float, float, float, float],
) -> bool:
    label_left, label_top, label_right, label_bottom = label_box
    value_left, value_top, value_right, value_bottom = value_box
    del label_top, value_bottom
    horizontal_overlap = min(label_right, value_right) - max(label_left, value_left)
    if horizontal_overlap <= 0:
        return False
    gap = value_top - label_bottom
    return 0 <= gap <= _BELOW_OF_MAX_GAP_POINTS

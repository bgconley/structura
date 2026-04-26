from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID


@dataclass(frozen=True)
class ParsedPage:
    page_number: int
    text: str = ""
    width: float | None = None
    height: float | None = None
    rotation_degrees: int = 0
    has_text_layer: bool | None = None
    ocr_confidence: float | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ParsedElement:
    page_number: int
    element_type: str = "other"
    ordinal: int = 1
    text: str = ""
    bbox: Mapping[str, Any] | list[Any] | None = None
    confidence: float | None = None
    source_ref: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ParsedTable:
    page_number: int
    table_index: int = 1
    row_count: int | None = None
    column_count: int | None = None
    table_json: Mapping[str, Any] = field(default_factory=dict)
    table_html: str | None = None
    table_markdown: str | None = None
    confidence: float | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ParsedChunk:
    chunk_index: int
    text: str
    chunk_kind: str = "section"
    page_start: int | None = None
    page_end: int | None = None
    heading_path: str | None = None
    markdown: str | None = None
    token_count: int | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CanonicalParseResult:
    docling_json: Mapping[str, Any]
    json_bytes: bytes
    markdown_bytes: bytes | None
    html_bytes: bytes | None
    pages: list[ParsedPage]
    elements: list[ParsedElement]
    tables: list[ParsedTable]
    chunks: list[ParsedChunk]
    converter_name: str
    converter_version: str
    metadata: Mapping[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class PersistedParseSummary:
    docling_asset_id: UUID
    markdown_asset_id: UUID | None
    html_asset_id: UUID | None
    page_count: int
    element_count: int
    table_count: int
    chunk_count: int

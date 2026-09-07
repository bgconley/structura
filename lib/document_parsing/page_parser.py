"""Bound page-parser port used by pure resumable document orchestration."""

from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from lib.document_parsing.qwen_page_parser import (
    OUTPUT_SCHEMA_VERSION,
    PageGenerationClient,
    ParsedSourcePage,
    parse_source_page,
)
from lib.document_parsing.source_adapter import RenderedSourcePage


class SourcePageParser(Protocol):
    @property
    def output_schema_version(self) -> str: ...

    def parse_page(self, source: RenderedSourcePage) -> ParsedSourcePage: ...


@dataclass(frozen=True)
class V1SourcePageParser:
    client: PageGenerationClient
    generation_id: UUID
    page_count: int
    timeout_seconds: int
    output_schema_version: str = OUTPUT_SCHEMA_VERSION

    def parse_page(self, source: RenderedSourcePage) -> ParsedSourcePage:
        return parse_source_page(
            self.client,
            source,
            generation_id=self.generation_id,
            page_count=self.page_count,
            timeout_seconds=self.timeout_seconds,
        )

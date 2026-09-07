"""Bounded immutable source context; native excerpts remain untrusted source text."""

from __future__ import annotations

import hashlib
import json
from typing import Literal, Protocol
from uuid import UUID, uuid5

from pydantic import Field, model_validator

from lib.document_parsing.structure import Sha256, SourceInventory, SourceMediaType, StructureModel

CONTEXT_RECIPE_VERSION: Literal["original-metadata-native-excerpts-v1"] = (
    "original-metadata-native-excerpts-v1"
)
MAX_SELECTED_PAGES = 8
MAX_EXCERPT_CHARACTERS = 384
MAX_CONTEXT_BYTES = 24 * 1024


class NativePageExcerpt(StructureModel):
    page_number: int = Field(ge=1, le=500)
    original_page_id: UUID
    source_page_sha256: Sha256
    text_origin: Literal["pdf_native"]
    source_character_count: int = Field(ge=0, le=1_000_000)
    excerpt: str = Field(max_length=MAX_EXCERPT_CHARACTERS)


class FrozenDocumentContext(StructureModel):
    recipe_version: Literal["original-metadata-native-excerpts-v1"]
    original_asset_id: UUID
    original_sha256: Sha256
    mime_type: SourceMediaType
    source_byte_size: int = Field(gt=0, le=100 * 1024 * 1024)
    source_inventory_sha256: Sha256
    page_count: int = Field(ge=1, le=500)
    selected_pages: tuple[NativePageExcerpt, ...] = Field(max_length=MAX_SELECTED_PAGES)
    omitted_page_numbers: tuple[int, ...] = Field(max_length=500)

    @model_validator(mode="after")
    def bounded_inventory(self) -> FrozenDocumentContext:
        selected = tuple(page.page_number for page in self.selected_pages)
        expected = (
            selected_context_pages(self.page_count) if self.mime_type == "application/pdf" else ()
        )
        if selected != expected or self.omitted_page_numbers != tuple(
            number for number in range(1, self.page_count + 1) if number not in selected
        ):
            raise ValueError("Frozen context page selection differs from its source recipe.")
        for page in self.selected_pages:
            if page.original_page_id != uuid5(
                self.original_asset_id, f"original-page:{page.page_number}"
            ) or len(page.excerpt) != min(page.source_character_count, MAX_EXCERPT_CHARACTERS):
                raise ValueError(
                    "Frozen native excerpt has inconsistent source identity or bounds."
                )
        if len(self.model_dump_json().encode()) > MAX_CONTEXT_BYTES:
            raise ValueError("Frozen source context exceeds its byte budget.")
        return self

    @property
    def fingerprint(self) -> str:
        return _digest(self.model_dump(mode="json"))


def selected_context_pages(page_count: int) -> tuple[int, ...]:
    if not 1 <= page_count <= 500:
        raise ValueError("Source context page inventory is invalid.")
    if page_count <= MAX_SELECTED_PAGES:
        return tuple(range(1, page_count + 1))
    return tuple(
        1 + index * (page_count - 1) // (MAX_SELECTED_PAGES - 1)
        for index in range(MAX_SELECTED_PAGES)
    )


class NativeContextSource(Protocol):
    @property
    def inventory(self) -> SourceInventory: ...

    def native_text(self, page_number: int) -> str | None: ...


def freeze_document_context(source: NativeContextSource) -> FrozenDocumentContext:
    inventory = source.inventory
    selected = (
        selected_context_pages(len(inventory.pages))
        if inventory.mime_type == "application/pdf"
        else ()
    )
    excerpts = []
    for number in selected:
        native = source.native_text(number)
        if native is None:
            raise ValueError("PDF context requires separately attributed native text.")
        excerpts.append(
            NativePageExcerpt(
                page_number=number,
                original_page_id=uuid5(inventory.original_asset_id, f"original-page:{number}"),
                source_page_sha256=_digest(inventory.pages[number - 1].model_dump(mode="json")),
                text_origin="pdf_native",
                source_character_count=len(native),
                excerpt=native[:MAX_EXCERPT_CHARACTERS],
            )
        )
    return FrozenDocumentContext(
        recipe_version=CONTEXT_RECIPE_VERSION,
        original_asset_id=inventory.original_asset_id,
        original_sha256=inventory.original_sha256,
        mime_type=inventory.mime_type,
        source_byte_size=inventory.byte_size,
        source_inventory_sha256=_digest(inventory.model_dump(mode="json")),
        page_count=len(inventory.pages),
        selected_pages=tuple(excerpts),
        omitted_page_numbers=tuple(
            number for number in range(1, len(inventory.pages) + 1) if number not in selected
        ),
    )


def _digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()


def validate_context_inventory(context: FrozenDocumentContext, inventory: SourceInventory) -> None:
    """Check stored source identity only; bytes/native excerpts need a source adapter recheck."""
    if (
        context.original_asset_id != inventory.original_asset_id
        or context.original_sha256 != inventory.original_sha256
        or context.mime_type != inventory.mime_type
        or context.source_byte_size != inventory.byte_size
        or context.page_count != len(inventory.pages)
        or context.source_inventory_sha256 != _digest(inventory.model_dump(mode="json"))
        or any(
            page.source_page_sha256
            != _digest(inventory.pages[page.page_number - 1].model_dump(mode="json"))
            for page in context.selected_pages
        )
    ):
        raise ValueError("Frozen document context differs from its exact original inventory.")

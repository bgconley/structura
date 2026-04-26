from __future__ import annotations

import json
from collections.abc import Mapping
from importlib import import_module
from importlib import metadata as importlib_metadata
from pathlib import Path
from typing import Any, Protocol, cast

from lib.config import get_settings
from lib.documents.parse_models import (
    CanonicalParseResult,
    ParsedChunk,
    ParsedElement,
    ParsedPage,
    ParsedTable,
)


class DoclingConversionError(Exception):
    pass


class DoclingConverter(Protocol):
    def convert(
        self,
        source_path: Path,
        *,
        filename: str,
        mime_type: str,
    ) -> CanonicalParseResult: ...


class RealDoclingConverter:
    def convert(
        self,
        source_path: Path,
        *,
        filename: str,
        mime_type: str,
    ) -> CanonicalParseResult:
        settings = get_settings()
        try:
            converter_module = import_module("docling.document_converter")
            base_models_module = import_module("docling.datamodel.base_models")
            pipeline_options_module = import_module("docling.datamodel.pipeline_options")
            document_converter_class = converter_module.DocumentConverter
            pdf_format_option_class = converter_module.PdfFormatOption
            input_format_class = base_models_module.InputFormat
            pdf_pipeline_options_class = pipeline_options_module.PdfPipelineOptions
            rapid_ocr_options_class = pipeline_options_module.RapidOcrOptions
        except (AttributeError, ImportError) as exc:
            raise DoclingConversionError("Docling is not installed in this runtime.") from exc

        pdf_pipeline_options = pdf_pipeline_options_class()
        pdf_pipeline_options.do_ocr = settings.docling_do_ocr
        pdf_pipeline_options.do_table_structure = settings.docling_do_table_structure
        if settings.docling_do_ocr:
            pdf_pipeline_options.ocr_options = rapid_ocr_options_class(
                backend=settings.docling_ocr_backend,
                lang=["english"],
                rapidocr_params={
                    "Global.model_root_dir": str(settings.docling_ocr_model_root),
                },
            )
        converter = document_converter_class(
            format_options={
                input_format_class.PDF: pdf_format_option_class(
                    pipeline_options=pdf_pipeline_options,
                ),
            },
        )
        try:
            result = converter.convert(
                source_path,
                max_num_pages=settings.docling_max_num_pages,
                max_file_size=settings.docling_max_file_size,
            )
            document = result.document
            docling_dict = document.export_to_dict()
            markdown = document.export_to_markdown()
            html = document.export_to_html() if settings.docling_store_html else None
        except Exception as exc:
            raise DoclingConversionError("Docling conversion failed.") from exc

        markdown_bytes = markdown.encode("utf-8") if settings.docling_store_markdown else None
        html_bytes = html.encode("utf-8") if html else None
        json_bytes = json.dumps(docling_dict, ensure_ascii=False, sort_keys=True).encode("utf-8")
        converter_version = _package_version("docling")
        pages = _pages_from_docling(docling_dict, fallback_text=markdown)
        chunks = _chunks_from_pages(pages, fallback_markdown=markdown)
        return CanonicalParseResult(
            docling_json=docling_dict,
            json_bytes=json_bytes,
            markdown_bytes=markdown_bytes,
            html_bytes=html_bytes,
            pages=pages,
            elements=_elements_from_docling(docling_dict),
            tables=_tables_from_docling(docling_dict),
            chunks=chunks,
            converter_name="docling",
            converter_version=converter_version,
            metadata={
                "inputFilename": filename,
                "inputMimeType": mime_type,
                "adapter": "RealDoclingConverter",
            },
        )


def _package_version(package_name: str) -> str:
    try:
        return importlib_metadata.version(package_name)
    except importlib_metadata.PackageNotFoundError:
        return "unknown"


def _pages_from_docling(
    docling_dict: Mapping[str, Any],
    *,
    fallback_text: str,
) -> list[ParsedPage]:
    pages_obj = docling_dict.get("pages")
    pages: list[ParsedPage] = []
    page_texts = _page_text_map(docling_dict)
    if isinstance(pages_obj, Mapping):
        for key, page_value in sorted(pages_obj.items(), key=lambda item: _page_sort_key(item[0])):
            if isinstance(page_value, Mapping):
                page_number = _positive_int(page_value.get("page_no") or key)
                size = page_value.get("size")
                width, height = _size_points(size)
                text = _text_from_page(page_value) or page_texts.get(page_number, "")
                pages.append(
                    ParsedPage(
                        page_number=page_number,
                        text=text,
                        width=width,
                        height=height,
                        has_text_layer=bool(page_value.get("has_text_layer"))
                        if "has_text_layer" in page_value
                        else None,
                        ocr_confidence=_confidence(page_value.get("confidence")),
                        metadata={"sourceRef": str(key)},
                    )
                )
    elif isinstance(pages_obj, list):
        for index, page_value in enumerate(pages_obj, start=1):
            if isinstance(page_value, Mapping):
                size = page_value.get("size")
                width, height = _size_points(size)
                page_number = _positive_int(page_value.get("page_no") or index)
                text = _text_from_page(page_value) or page_texts.get(page_number, "")
                pages.append(
                    ParsedPage(
                        page_number=page_number,
                        text=text,
                        width=width,
                        height=height,
                        has_text_layer=bool(page_value.get("has_text_layer"))
                        if "has_text_layer" in page_value
                        else None,
                        ocr_confidence=_confidence(page_value.get("confidence")),
                        metadata={"sourceRef": str(index)},
                    )
                )

    if pages:
        return pages
    return [
        ParsedPage(
            page_number=1,
            text=fallback_text,
            width=612,
            height=792,
            has_text_layer=bool(fallback_text.strip()),
            metadata={"fallback": "markdown"},
        )
    ]


def _elements_from_docling(docling_dict: Mapping[str, Any]) -> list[ParsedElement]:
    elements: list[ParsedElement] = []
    for collection_name in ("texts", "pictures", "groups"):
        collection = docling_dict.get(collection_name)
        if not isinstance(collection, list):
            continue
        for index, item in enumerate(collection, start=1):
            if not isinstance(item, Mapping):
                continue
            page_number = _page_number_from_item(item)
            text = _string_value(item.get("text") or item.get("caption") or item.get("name"))
            if not text and collection_name != "pictures":
                continue
            elements.append(
                ParsedElement(
                    page_number=page_number,
                    element_type=_element_type(collection_name, item),
                    ordinal=index,
                    text=text,
                    bbox=_bbox_from_item(item),
                    confidence=_confidence(item.get("confidence")),
                    source_ref=_string_value(item.get("self_ref") or item.get("selfRef")),
                    metadata={"doclingCollection": collection_name},
                )
            )
    return elements


def _tables_from_docling(docling_dict: Mapping[str, Any]) -> list[ParsedTable]:
    tables_obj = docling_dict.get("tables")
    tables: list[ParsedTable] = []
    if not isinstance(tables_obj, list):
        return tables
    for index, item in enumerate(tables_obj, start=1):
        if not isinstance(item, Mapping):
            continue
        data = item.get("data")
        rows = data.get("table_cells") if isinstance(data, Mapping) else None
        tables.append(
            ParsedTable(
                page_number=_page_number_from_item(item),
                table_index=index,
                row_count=_positive_int(item.get("num_rows")) if item.get("num_rows") else None,
                column_count=_positive_int(item.get("num_cols")) if item.get("num_cols") else None,
                table_json=dict(item),
                table_markdown=_string_value(item.get("markdown")),
                confidence=_confidence(item.get("confidence")),
                metadata={"doclingCellCount": len(rows) if isinstance(rows, list) else None},
            )
        )
    return tables


def _chunks_from_pages(pages: list[ParsedPage], *, fallback_markdown: str) -> list[ParsedChunk]:
    chunks: list[ParsedChunk] = []
    for page in pages:
        text = page.text.strip()
        if not text:
            continue
        chunks.append(
            ParsedChunk(
                chunk_index=len(chunks) + 1,
                text=text,
                page_start=page.page_number,
                page_end=page.page_number,
                markdown=text,
                token_count=max(len(text.split()), 1),
                metadata={"source": "page_text"},
            )
        )
    if chunks:
        return chunks
    fallback = fallback_markdown.strip()
    if not fallback:
        return []
    return [
        ParsedChunk(
            chunk_index=1,
            text=fallback,
            page_start=1,
            page_end=1,
            markdown=fallback,
            token_count=max(len(fallback.split()), 1),
            metadata={"source": "markdown_fallback"},
        )
    ]


def _page_sort_key(value: object) -> int:
    return _positive_int(value)


def _positive_int(value: object) -> int:
    try:
        return max(int(str(value).replace("#/pages/", "")), 1)
    except (TypeError, ValueError):
        return 1


def _size_points(value: object) -> tuple[float | None, float | None]:
    if not isinstance(value, Mapping):
        return (None, None)
    width = value.get("width")
    height = value.get("height")
    return (_float_or_none(width), _float_or_none(height))


def _text_from_page(page_value: Mapping[str, Any]) -> str:
    for key in ("text", "text_content", "content"):
        value = page_value.get(key)
        if isinstance(value, str):
            return value
    return ""


def _page_text_map(docling_dict: Mapping[str, Any]) -> dict[int, str]:
    page_text: dict[int, list[str]] = {}
    texts = docling_dict.get("texts")
    if not isinstance(texts, list):
        return {}
    for item in texts:
        if not isinstance(item, Mapping):
            continue
        text = _string_value(item.get("text"))
        if not text:
            continue
        page_text.setdefault(_page_number_from_item(item), []).append(text)
    return {page_number: "\n".join(parts) for page_number, parts in page_text.items()}


def _page_number_from_item(item: Mapping[str, Any]) -> int:
    for key in ("page_no", "pageNumber", "page_number"):
        if key in item:
            return _positive_int(item[key])
    prov = item.get("prov")
    if isinstance(prov, list) and prov:
        first = prov[0]
        if isinstance(first, Mapping):
            return _positive_int(first.get("page_no") or first.get("pageNumber"))
    return 1


def _bbox_from_item(item: Mapping[str, Any]) -> Mapping[str, Any] | None:
    bbox = item.get("bbox")
    if isinstance(bbox, Mapping):
        return bbox
    prov = item.get("prov")
    if isinstance(prov, list) and prov:
        first = prov[0]
        if isinstance(first, Mapping) and isinstance(first.get("bbox"), Mapping):
            return cast(Mapping[str, Any], first["bbox"])
    return None


def _element_type(collection_name: str, item: Mapping[str, Any]) -> str:
    if collection_name == "pictures":
        return "figure"
    label = _string_value(item.get("label")).lower()
    if label in {"section_header", "title"}:
        return "heading"
    if label in {"list_item", "paragraph", "caption", "code"}:
        return "code_block" if label == "code" else label
    return "paragraph"


def _confidence(value: object) -> float | None:
    numeric = _float_or_none(value)
    if numeric is None:
        return None
    return min(max(numeric, 0.0), 1.0)


def _float_or_none(value: object) -> float | None:
    try:
        return float(cast(Any, value)) if value is not None else None
    except (TypeError, ValueError):
        return None


def _string_value(value: object) -> str:
    return value if isinstance(value, str) else ""

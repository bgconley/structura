from __future__ import annotations

import json

from lib.extraction.models import ExtractionSourceDocument
from lib.model_runtime.reliability_versions import SMART_PROMPT_VERSION as SMART_PROMPT_VERSION
from lib.semantic_annotations.docling_context import build_docling_context


def build_semantic_planner_prompt(
    source: ExtractionSourceDocument,
    *,
    focus_page_numbers: set[int] | None = None,
) -> str:
    context = build_docling_context(
        source,
        focus_page_numbers=focus_page_numbers,
        include_pages_alias=False,
        include_page_image_hashes=False,
        include_element_bboxes=False,
        stable_references=True,
    )
    context_json = json.dumps(context, sort_keys=True, separators=(",", ":"))
    return (
        "You are Structura's semantic document-understanding layer for "  # nosec B608
        "Docling-grounded documents. "
        "Return valid JSON only as compact semantic_annotation_model_output JSON matching "
        "the provided JSON Schema. This is semantic inventory and extraction intent, "
        "not canonical extraction: do not output field values, money amounts, dates, "
        "names, addresses, or canonical facts. "
        "Use stable Docling page_id, element_id, and table_id refs from the context "
        "(such as page-1, page-1-element-3, and page-1-table-2) instead of inventing "
        "coordinates; copy these refs exactly into output grounding fields. "
        "visual_bbox_hint is advisory only and never replaces Docling grounding. "
        "First inventory every input page image. When focusPages is "
        "present, document.pageOutline is context-only; pages[] must contain exactly "
        "the focusPages/input image pages from document.focusPageContract and must "
        "not copy or summarize pageOutline-only pages. Regions must also be grounded "
        "only to focusPages/input image pages. For blank or no-target focus pages, "
        "still emit one pages[] object with extraction_usefulness none, "
        "has_structured_targets false, and no regions. Then select "
        "grounded Granite extraction intent from that inventory. Inspect layout, "
        "table structure, visual grouping, repeated headers, cross-page continuations, "
        "OCR-like visible text, and Docling text/table signals. Emit all materially "
        "extractable regions that could change downstream factual coverage; bounded "
        "recall is preferred over sparse omission. Use no more than 12 regions total "
        "per request and usually no more than 3 materially extractable regions per page. "
        "Emit document_type_candidates with competing family scores and evidence terms "
        "when family fit is ambiguous. For each page, set page_family_hints, "
        "docling_table_signal, continuation_group, and requires_cross_page_context "
        "when those fields clarify routing. For each region, set importance, "
        "source_signal, coverage_role, extraction_scope, requires_full_page_image, "
        "must_extract_reason, negative_routing_reason, min_expected_items, and "
        "visual_bbox_hint when visually obvious. Use planner_notes for routing "
        "warnings such as weak Docling tables or conflicting family anchors. "
        "Do not output every visible field. expected_fields must contain field names "
        "only, using snake_case names such as total_amount or patient_responsibility. "
        "If Docling table signal is weak but the page visually contains a line-item "
        "or tabular structure, still emit the region, set source_signal to visual or "
        "mixed, set requires_full_page_image when full page context is needed, and "
        "record docling_table_signal=weak. Preserve continuation_group for any line "
        "items, services, ordered goods, medical services, forms, or payment sections "
        "that continue across pages. Recommend whether Granite should receive "
        "full-page, table, element, or crop context through extraction_scope and "
        "requires_full_page_image. Use target_schema medical_eob "
        "for EOB, insurance, denial, and medical billing documents; invoice for bills "
        "and invoices; receipt for receipts, retail orders, and paid service records; "
        "document_observation for generic observations, seller/title information, "
        "escrow summaries, dispute forms, and useful unsupported forms; otherwise null. "
        "Do not force unfamiliar documents into invoice, receipt, or medical_eob. "
        "Use granite_task kvp for summary/key-value blocks, tables_json for line-item "
        "tables, tables_html or tables_otsl only when table structure requires it, "
        "and ignore for boilerplate/no-target regions. Mark unmatched_region, "
        "review_required=true, and low confidence when a useful target cannot be "
        "grounded to Docling IDs. Set needs_human_review as a diagnostic review "
        "signal when uncertainty, confidence, evidence, or policy should route the "
        "result to review; it must not imply automatic model escalation. Keep each reason "
        "to one short sentence and dedupe repeated headers/boilerplate. "
        "Few-shot planner examples: "
        f"{json.dumps(_few_shot_examples(), sort_keys=True, separators=(',', ':'))} "
        "Docling context: "
        f"{context_json}"
    )


def _few_shot_examples() -> list[dict[str, object]]:
    return [
        {
            "case": "vehicle_service_invoice",
            "document_type": "service_record",
            "pages": [
                {"page_role": "line_items", "continuation_group": "service_lines"},
                {"page_role": "line_items", "continuation_group": "service_lines"},
                {"page_role": "payment_summary"},
            ],
            "regions": [
                {
                    "semantic_type": "service_record_line_item_table",
                    "granite_task": "tables_json",
                    "target_schema": "receipt",
                    "coverage_role": "primary",
                    "source_signal": "mixed",
                    "continuation_group": "service_lines",
                    "requires_full_page_image": True,
                    "expected_fields": ["service_description", "quantity", "line_total"],
                },
                {
                    "semantic_type": "service_record_line_item_table",
                    "granite_task": "tables_json",
                    "target_schema": "receipt",
                    "coverage_role": "continuation",
                    "continuation_group": "service_lines",
                    "requires_full_page_image": True,
                    "expected_fields": ["service_description", "line_total"],
                },
                {
                    "semantic_type": "vehicle_or_asset_block",
                    "granite_task": "kvp",
                    "target_schema": "receipt",
                    "coverage_role": "supporting",
                    "expected_fields": ["vin", "mileage", "repair_order_number"],
                },
                {
                    "semantic_type": "receipt_payment_summary",
                    "granite_task": "kvp",
                    "target_schema": "receipt",
                    "coverage_role": "summary",
                    "expected_fields": ["payment_method", "amount_paid", "total_amount"],
                },
            ],
        },
        {
            "case": "retail_order",
            "document_type": "retail_order",
            "regions": [
                {
                    "semantic_type": "retail_order_line_item_table",
                    "granite_task": "tables_json",
                    "target_schema": "receipt",
                    "expected_fields": ["item_description", "quantity", "line_total"],
                },
                {
                    "semantic_type": "receipt_payment_summary",
                    "granite_task": "kvp",
                    "target_schema": "receipt",
                    "expected_fields": ["subtotal", "tax", "shipping", "total_amount"],
                },
            ],
        },
        {
            "case": "medical_denial",
            "document_type": "insurance_denial",
            "regions": [
                {
                    "semantic_type": "denial_or_coverage_decision",
                    "granite_task": "kvp",
                    "target_schema": "medical_eob",
                    "expected_fields": ["request_status", "denial_reason", "appeal_deadline"],
                },
                {
                    "semantic_type": "covered_services_line_item_table",
                    "granite_task": "tables_json",
                    "target_schema": "medical_eob",
                    "expected_fields": ["service_description", "amount_billed", "plan_paid"],
                },
            ],
        },
        {
            "case": "title_seller_information_form",
            "document_type": "real_estate_title",
            "regions": [
                {
                    "semantic_type": "seller_information_block",
                    "granite_task": "kvp",
                    "target_schema": "document_observation",
                    "expected_fields": ["seller_name", "property_address", "wiring_reference"],
                }
            ],
        },
        {
            "case": "escrow_statement",
            "document_type": "mortgage_escrow_statement",
            "regions": [
                {
                    "semantic_type": "escrow_summary",
                    "granite_task": "kvp",
                    "target_schema": "document_observation",
                    "expected_fields": ["shortage_amount", "surplus_amount", "payment_change"],
                }
            ],
        },
        {
            "case": "generic_low_signal_form",
            "document_type": "unsupported_document",
            "regions": [
                {
                    "semantic_type": "no_extraction_target",
                    "granite_task": "ignore",
                    "target_schema": None,
                    "expected_fields": [],
                }
            ],
        },
    ]

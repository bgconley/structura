from __future__ import annotations

import json

from lib.extraction.models import ExtractionSourceDocument
from lib.semantic_annotations.docling_context import build_docling_context

SMART_PROMPT_VERSION = "phase8_5-semantic-smart-v3"
HIGH_QUALITY_PROMPT_VERSION = "phase8_5-semantic-high-quality-v1"
RESCUE_PROMPT_VERSION = "phase8_5-semantic-rescue-v1"


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
    )
    context_json = json.dumps(context, sort_keys=True, separators=(",", ":"))
    return (
        "You are Structura's semantic planner for Docling-grounded documents. "
        "Return valid JSON only as compact semantic_annotation_model_output JSON matching "
        "the provided JSON Schema. This is semantic planning, not extraction: do not "
        "output field values, money amounts, dates, names, addresses, or canonical facts. "
        "Use Docling page_id, element_id, and table_id from the context instead of "
        "inventing coordinates; visual_bbox_hint is advisory only and never replaces "
        "Docling grounding. First account for every input page image, then select "
        "grounded Granite extraction targets from that inventory. Emit all materially "
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
        "mixed, set requires_full_page_image=true, and record docling_table_signal=weak. "
        "Preserve continuation_group for service lines, order items, medical services, "
        "or payment sections that continue across pages. Vehicle or motorcycle repair "
        "orders, service invoices, R/O pages, mileage/VIN service pages, labor/parts "
        "tables, and paid service receipts are service_record documents even when the "
        "page also says invoice; route their service and parts rows as "
        "service_record_line_item_table with target_schema receipt, and route payment "
        "or paid-total areas as receipt_payment_summary. Use target_schema medical_eob "
        "for EOB, insurance, denial, and medical billing documents; invoice for bills "
        "and invoices; receipt for receipts, retail orders, and service records; "
        "document_observation for generic observations, seller/title information, "
        "escrow summaries, dispute forms, and useful unsupported forms; otherwise null. "
        "Do not force unfamiliar documents into invoice, receipt, or medical_eob. "
        "Use granite_task kvp for summary/key-value blocks, tables_json for line-item "
        "tables, tables_html or tables_otsl only when table structure requires it, "
        "and ignore for boilerplate/no-target regions. Mark unmatched_region, "
        "review_required=true, and low confidence when a useful target cannot be "
        "grounded to Docling IDs. Set needs_high_quality_pass only as a diagnostic "
        "review signal; it must not imply automatic Qwen8 escalation. Keep each reason "
        "to one short sentence and dedupe repeated headers/boilerplate. "
        "Few-shot planner examples: "
        f"{json.dumps(_few_shot_examples(), sort_keys=True, separators=(',', ':'))} "
        "Docling context: "
        f"{context_json}"
    )


def _few_shot_examples() -> list[dict[str, object]]:
    return [
        {
            "case": "BMW service invoice",
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
                    "expected_fields": ["service_description", "quantity", "line_total"],
                },
                {
                    "semantic_type": "service_record_line_item_table",
                    "granite_task": "tables_json",
                    "target_schema": "receipt",
                    "coverage_role": "continuation",
                    "continuation_group": "service_lines",
                    "expected_fields": ["service_description", "line_total"],
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
            "case": "BH retail order",
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
            "case": "medical denial",
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
            "case": "title seller information form",
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
            "case": "escrow statement",
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
            "case": "generic low-signal scan",
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

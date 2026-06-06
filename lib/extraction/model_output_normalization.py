from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from lib.extraction.docling_table_quality import (
    DoclingTableQuality,
    apply_table_consistency_projection,
    gate_docling_authoritative_rows,
)
from lib.extraction.evidence_context import EvidenceContext
from lib.extraction.line_item_provenance import line_item_evidence, line_item_provenance
from lib.extraction.model_output_healthcare import (
    healthcare_coverage_decision_output as _healthcare_coverage_decision_output,
)
from lib.extraction.model_output_line_items import (
    INVOICE_LINE_ITEM_KEYS,
    RECEIPT_LINE_ITEM_KEYS,
    RETAIL_ORDER_LINE_ITEM_KEYS,
    SERVICE_RECORD_LINE_ITEM_KEYS,
    canonical_line_item_evidence,
)
from lib.extraction.model_output_line_items import (
    is_non_line_item_heading as _is_non_line_item_heading,
)
from lib.extraction.model_output_line_items import (
    item_matches_contract as _item_matches_contract,
)
from lib.extraction.model_output_line_items import (
    line_item_amount as _line_item_amount,
)
from lib.extraction.model_output_line_items import (
    line_item_description as _line_item_description,
)
from lib.extraction.model_output_observations import (
    looks_like_schema_echo as _looks_like_schema_echo,
)
from lib.extraction.model_output_observations import (
    observation_dicts_from_payload as _observation_dicts_from_payload,
)
from lib.extraction.model_output_observations import (
    observations_from_model_payload as _observations_from_model_payload,
)
from lib.extraction.model_output_payments import (
    invoice_payment_summary_from_payload,
)
from lib.extraction.model_output_payments import (
    invoice_totals as _invoice_totals,
)
from lib.extraction.model_output_payments import (
    receipt_merchant as _receipt_merchant,
)
from lib.extraction.model_output_value_parsing import (
    money_value as _money,
)
from lib.extraction.model_output_value_parsing import (
    number_value as _number,
)
from lib.extraction.model_output_wrappers import (
    unwrap_model_output_payload as _unwrapped_payload,
)
from lib.extraction.region_envelope_projection import finalized_region_output

_REVIEW_ONLY_RECEIPT_LIKE_SEMANTIC_TYPES = frozenset(
    {
        "invoice_line_item_table",
        "receipt_line_item_table",
        "receipt_payment_summary",
        "retail_order_line_item_table",
        "service_record_line_item_table",
    }
)


def normalize_granite_region_output(
    *,
    document_id: UUID,
    schema_name: str,
    model_output_schema_name: str | None,
    payload: Any,
    evidence_context: EvidenceContext | None = None,
    semantic_type: str | None = None,
    target_schema: str | None = None,
    resolved_document_type: str | None = None,
    docling_table_quality: DoclingTableQuality | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    model_payload, wrapper_repairs = _unwrapped_payload(payload)

    def finalize(
        normalized: dict[str, Any],
        metadata: dict[str, Any],
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        return _finalized_output(
            normalized,
            metadata,
            wrapper_repairs,
            evidence_context,
            model_output_schema_name=model_output_schema_name,
            semantic_type=semantic_type,
            target_schema=target_schema or schema_name,
            resolved_document_type=resolved_document_type,
        )

    if model_output_schema_name == "granite_invoice_line_items.v1":
        normalized, metadata = _invoice_line_items_output(
            document_id,
            model_payload,
            evidence_context=evidence_context,
            docling_table_quality=docling_table_quality,
        )
        return finalize(normalized, metadata)
    if model_output_schema_name == "granite_payment_summary.v1":
        normalized, metadata = _invoice_payment_output(document_id, model_payload)
        return finalize(normalized, metadata)
    if model_output_schema_name == "granite_medical_service_lines.v1":
        normalized, metadata = _medical_service_lines_output(
            document_id,
            model_payload,
            evidence_context=evidence_context,
            docling_table_quality=docling_table_quality,
        )
        return finalize(normalized, metadata)
    if model_output_schema_name in {
        "granite_receipt_line_items.v1",
        "granite_retail_order.v1",
    }:
        normalized, metadata = _receipt_line_items_output(
            document_id,
            model_payload,
            evidence_context=evidence_context,
            docling_table_quality=docling_table_quality,
            model_output_schema_name=model_output_schema_name,
        )
        metadata["mapper"] = model_output_schema_name
        return finalize(normalized, metadata)
    if model_output_schema_name == "granite_service_record_line_items.v1":
        normalized, metadata = _service_record_line_items_output(
            document_id,
            model_payload,
            evidence_context=evidence_context,
            docling_table_quality=docling_table_quality,
        )
        return finalize(normalized, metadata)
    if model_output_schema_name == "granite_receipt_payment_summary.v1":
        normalized, metadata = _receipt_payment_output(
            document_id,
            model_payload,
            evidence_context=evidence_context,
        )
        return finalize(normalized, metadata)
    if model_output_schema_name == "granite_healthcare_coverage_decision.v1":
        normalized, metadata = _healthcare_coverage_decision_output(
            document_id,
            model_payload,
            evidence_context=evidence_context,
        )
        return finalize(normalized, metadata)
    if schema_name == "document_observation" or model_output_schema_name in {
        "granite_real_estate_title_seller_info.v1",
        "granite_mortgage_escrow_statement.v1",
        "granite_dispute_form.v1",
        "granite_generic_kvp.v1",
    }:
        normalized, metadata = _document_observation_output(
            document_id,
            model_payload,
            model_output_schema_name=model_output_schema_name,
            evidence_context=evidence_context,
            semantic_type=semantic_type,
            target_schema=target_schema,
            resolved_document_type=resolved_document_type,
        )
        return finalize(normalized, metadata)
    return finalize(
        model_payload,
        {"mapper": None, "repairs": [], "rejected_fields": []},
    )


def _finalized_output(
    normalized: dict[str, Any],
    metadata: dict[str, Any],
    wrapper_repairs: list[str],
    evidence_context: EvidenceContext | None,
    *,
    model_output_schema_name: str | None,
    semantic_type: str | None,
    target_schema: str | None,
    resolved_document_type: str | None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    return finalized_region_output(
        normalized,
        metadata,
        wrapper_repairs,
        evidence_context,
        model_output_schema_name=model_output_schema_name,
        semantic_type=semantic_type,
        target_schema=target_schema,
        resolved_document_type=resolved_document_type,
    )


def invoice_line_item_dicts_from_payload(
    payload: dict[str, Any],
    *,
    evidence_context: EvidenceContext | None = None,
) -> list[dict[str, Any]]:
    model_payload, _repairs = _unwrapped_payload(payload)
    records = _invoice_line_item_records(model_payload)
    if records:
        return _canonical_invoice_line_items(records, evidence_context=evidence_context)
    return []


def _invoice_line_items_output(
    document_id: UUID,
    payload: dict[str, Any],
    *,
    evidence_context: EvidenceContext | None,
    docling_table_quality: DoclingTableQuality | None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    line_items = invoice_line_item_dicts_from_payload(
        payload,
        evidence_context=evidence_context,
    )
    consistency = gate_docling_authoritative_rows(line_items, docling_table_quality)
    line_items = consistency.accepted_rows
    confidence = payload.get("confidence") if isinstance(payload.get("confidence"), dict) else {}
    normalized: dict[str, Any] = {
        "schema_name": "invoice",
        "schema_version": "v1",
        "document_id": str(document_id),
        "line_items": line_items,
        "confidence": confidence,
        "created_at": datetime.now(UTC).isoformat(),
    }
    totals = _invoice_totals(payload)
    if totals:
        normalized["totals"] = totals
    metadata = {
        "mapper": "granite_invoice_line_items.v1",
        "repairs": ["mapped_model_output_to_canonical_invoice_line_items"],
        "rejected_fields": _rejected_fields(
            payload,
            {"line_items", "totals", "confidence"},
        ),
    }
    return apply_table_consistency_projection(normalized, metadata, consistency)


def _invoice_payment_output(
    document_id: UUID,
    payload: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    summary = invoice_payment_summary_from_payload(payload)
    confidence = payload.get("confidence") if isinstance(payload.get("confidence"), dict) else {}
    normalized: dict[str, Any] = {
        "schema_name": "invoice",
        "schema_version": "v1",
        "document_id": str(document_id),
        "invoice": {},
        "totals": {},
        "metadata": {},
        "confidence": confidence,
        "created_at": datetime.now(UTC).isoformat(),
    }
    if summary.get("invoice_number"):
        normalized["invoice"]["invoice_number"] = summary["invoice_number"]
    if summary.get("amount_paid"):
        normalized["totals"]["amount_paid"] = summary["amount_paid"]
    if summary.get("payment_summary"):
        normalized["metadata"]["payment_summary"] = summary["payment_summary"]
    return normalized, {
        "mapper": "granite_payment_summary.v1",
        "repairs": ["mapped_model_output_to_canonical_invoice_payment_summary"],
        "rejected_fields": _rejected_fields(
            payload,
            {"invoice_no", "amount", "payments", "confidence"},
        ),
    }


def _medical_service_lines_output(
    document_id: UUID,
    payload: dict[str, Any],
    *,
    evidence_context: EvidenceContext | None,
    docling_table_quality: DoclingTableQuality | None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    confidence = payload.get("confidence") if isinstance(payload.get("confidence"), dict) else {}
    service_lines = payload.get("service_lines") or []
    if isinstance(service_lines, list):
        service_lines = [
            _with_evidence_context(item, evidence_context)
            for item in service_lines
            if isinstance(item, dict)
        ]
    consistency = gate_docling_authoritative_rows(service_lines, docling_table_quality)
    service_lines = consistency.accepted_rows
    normalized = {
        "schema_name": "medical_eob",
        "schema_version": "v1",
        "document_id": str(document_id),
        "service_lines": service_lines,
        "confidence": confidence,
        "created_at": datetime.now(UTC).isoformat(),
    }
    metadata = {
        "mapper": "granite_medical_service_lines.v1",
        "repairs": ["mapped_model_output_to_canonical_medical_service_lines"],
        "rejected_fields": _rejected_fields(payload, {"service_lines", "confidence"}),
    }
    return apply_table_consistency_projection(normalized, metadata, consistency)


def _receipt_line_items_output(
    document_id: UUID,
    payload: dict[str, Any],
    *,
    evidence_context: EvidenceContext | None,
    docling_table_quality: DoclingTableQuality | None,
    model_output_schema_name: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    allowed_item_keys = (
        RETAIL_ORDER_LINE_ITEM_KEYS
        if model_output_schema_name == "granite_retail_order.v1"
        else RECEIPT_LINE_ITEM_KEYS
    )
    line_items = _canonical_receipt_line_items(
        _invoice_line_item_records(payload),
        evidence_context=evidence_context,
        allowed_item_keys=allowed_item_keys,
    )
    if not line_items:
        line_items = _canonical_receipt_line_items(
            payload.get("line_items") or [],
            evidence_context=evidence_context,
            allowed_item_keys=allowed_item_keys,
        )
    consistency = gate_docling_authoritative_rows(line_items, docling_table_quality)
    line_items = consistency.accepted_rows
    confidence = payload.get("confidence") if isinstance(payload.get("confidence"), dict) else {}
    transaction: dict[str, Any] = {}
    raw_totals = payload.get("totals")
    totals: dict[str, Any] = raw_totals if isinstance(raw_totals, dict) else {}
    for source_key, target_key in (
        ("subtotal", "subtotal"),
        ("tax", "tax"),
        ("tax_total", "tax"),
        ("total", "total"),
    ):
        amount = _money(totals.get(source_key) or payload.get(source_key))
        if amount:
            transaction[target_key] = amount
    normalized: dict[str, Any] = {
        "schema_name": "receipt",
        "schema_version": "v1",
        "document_id": str(document_id),
        "merchant": _receipt_merchant(payload, evidence_context=evidence_context),
        "transaction": transaction,
        "line_items": line_items,
        "confidence": confidence,
        "created_at": datetime.now(UTC).isoformat(),
    }
    retail_order_metadata = _retail_order_metadata(payload)
    if retail_order_metadata:
        normalized["metadata"] = {"retail_order": retail_order_metadata}
    metadata = {
        "mapper": "granite_receipt_line_items.v1",
        "repairs": ["mapped_model_output_to_canonical_receipt_line_items"],
        "rejected_fields": _rejected_fields(
            payload,
            {"line_items", "totals", "confidence", "merchant_name", "order_number", "order_date"},
        ),
    }
    return apply_table_consistency_projection(normalized, metadata, consistency)


def _retail_order_metadata(payload: dict[str, Any]) -> dict[str, Any]:
    metadata: dict[str, Any] = {}
    for key in ("order_number", "order_date"):
        value = payload.get(key)
        if value not in (None, ""):
            metadata[key] = str(value)
    return metadata


def _service_record_line_items_output(
    document_id: UUID,
    payload: dict[str, Any],
    *,
    evidence_context: EvidenceContext | None,
    docling_table_quality: DoclingTableQuality | None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    records = _invoice_line_item_records(payload)
    line_items = _canonical_receipt_line_items(
        records,
        evidence_context=evidence_context,
        allowed_item_keys=SERVICE_RECORD_LINE_ITEM_KEYS,
        description_keys=("description", "service_description"),
        amount_keys=("line_total", "amount"),
        code_keys=("labor_operation", "part_number"),
    )
    repairs = ["mapped_model_output_to_canonical_service_record_line_items"]
    consistency = gate_docling_authoritative_rows(line_items, docling_table_quality)
    line_items = consistency.accepted_rows
    confidence = payload.get("confidence") if isinstance(payload.get("confidence"), dict) else {}
    transaction: dict[str, Any] = {}
    raw_totals = payload.get("totals")
    totals: dict[str, Any] = raw_totals if isinstance(raw_totals, dict) else {}
    for source_key, target_key in (
        ("subtotal", "subtotal"),
        ("tax", "tax"),
        ("tax_total", "tax"),
        ("total", "total"),
    ):
        amount = _money(totals.get(source_key))
        if amount:
            transaction[target_key] = amount
    normalized: dict[str, Any] = {
        "schema_name": "receipt",
        "schema_version": "v1",
        "document_id": str(document_id),
        "merchant": {},
        "transaction": transaction,
        "line_items": line_items,
        "confidence": confidence,
        "created_at": datetime.now(UTC).isoformat(),
        "metadata": {"document_family": "service_record"},
    }
    metadata = {
        "mapper": "granite_service_record_line_items.v1",
        "repairs": repairs,
        "rejected_fields": _rejected_fields(
            payload,
            {"line_items", "totals", "confidence"},
        ),
    }
    return apply_table_consistency_projection(normalized, metadata, consistency)


def _receipt_payment_output(
    document_id: UUID,
    payload: dict[str, Any],
    *,
    evidence_context: EvidenceContext | None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    confidence = payload.get("confidence") if isinstance(payload.get("confidence"), dict) else {}
    transaction: dict[str, Any] = {}
    deferred_fields: list[str] = []
    deferred_identity_fields: list[str] = []
    defer_money_fields = _is_page_scoped_model_summary(evidence_context)
    amount_signal_present = _receipt_payment_amount_signal(payload)
    defer_identity_fields = defer_money_fields
    for source_key, target_key in (
        ("transaction_date", "date_local"),
        ("subtotal", "subtotal"),
        ("tax", "tax"),
        ("tip", "tip"),
        ("discount_total", "discount_total"),
        ("total", "total"),
    ):
        value = payload.get(source_key)
        if target_key in {"subtotal", "tax", "tip", "discount_total", "total"}:
            if value not in (None, "") and defer_money_fields:
                deferred_fields.append(source_key)
                continue
            amount = _money(value)
            if amount:
                transaction[target_key] = amount
        elif value not in (None, ""):
            if defer_identity_fields:
                deferred_identity_fields.append(source_key)
                continue
            transaction[target_key] = str(value)
    merchant: dict[str, Any] = {}
    if defer_identity_fields:
        if payload.get("merchant_name") not in (None, ""):
            deferred_identity_fields.append("merchant_name")
        elif payload.get("merchant") not in (None, ""):
            deferred_identity_fields.append("merchant")
    else:
        merchant = _receipt_merchant(payload, evidence_context=evidence_context)
    normalized: dict[str, Any] = {
        "schema_name": "receipt",
        "schema_version": "v1",
        "document_id": str(document_id),
        "merchant": merchant,
        "transaction": transaction,
        "line_items": [],
        "confidence": confidence,
        "created_at": datetime.now(UTC).isoformat(),
    }
    if payload.get("payment_method") and not defer_identity_fields:
        normalized["metadata"] = {"payment_method": str(payload["payment_method"])}
    if deferred_fields:
        metadata = dict(normalized.get("metadata") or {})
        metadata["deferred_payment_summary_fields"] = deferred_fields
        normalized["metadata"] = metadata
    if deferred_identity_fields:
        metadata = dict(normalized.get("metadata") or {})
        metadata["deferred_payment_summary_identity_fields"] = sorted(
            dict.fromkeys(deferred_identity_fields)
        )
        normalized["metadata"] = metadata
    repairs = ["mapped_model_output_to_canonical_receipt_payment_summary"]
    if deferred_identity_fields:
        repairs.append(
            "deferred_payment_summary_identity_for_page_summary"
            if amount_signal_present
            else "deferred_payment_summary_identity_without_amount_signal"
        )
    return normalized, {
        "mapper": "granite_receipt_payment_summary.v1",
        "repairs": repairs,
        "deferred_payment_summary_fields": deferred_fields,
        **(
            {
                "deferred_payment_summary_identity_fields": sorted(
                    dict.fromkeys(deferred_identity_fields)
                )
            }
            if deferred_identity_fields
            else {}
        ),
        "rejected_fields": _rejected_fields(
            payload,
            {
                "merchant_name",
                "transaction_date",
                "subtotal",
                "tax",
                "tip",
                "discount_total",
                "total",
                "payment_method",
                "confidence",
            },
        ),
    }


def _receipt_payment_amount_signal(payload: dict[str, Any]) -> bool:
    return any(
        _money(payload.get(key)) for key in ("subtotal", "tax", "tip", "discount_total", "total")
    )


def _is_page_scoped_model_summary(evidence_context: EvidenceContext | None) -> bool:
    if evidence_context is None:
        return False
    return not (
        evidence_context.table_id
        or evidence_context.element_id
        or evidence_context.bbox
        or evidence_context.original_bbox
        or evidence_context.expanded_bbox
    )


def _document_observation_output(
    document_id: UUID,
    payload: dict[str, Any],
    *,
    model_output_schema_name: str | None,
    evidence_context: EvidenceContext | None,
    semantic_type: str | None,
    target_schema: str | None,
    resolved_document_type: str | None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    repairs: list[str] = []
    observations: list[dict[str, Any]] = []
    if _looks_like_schema_echo(payload):
        repairs.append("schema_echo_rejected")
    else:
        observations = _observations_from_model_payload(
            payload,
            model_output_schema_name,
            evidence_context=evidence_context,
        )
        if model_output_schema_name is None:
            repairs.append("uncontracted_observation_payload_rejected")
    if _should_defer_review_only_receipt_like_observations(
        model_output_schema_name=model_output_schema_name,
        semantic_type=semantic_type,
        target_schema=target_schema,
        resolved_document_type=resolved_document_type,
    ):
        deferred_observation_count = len(observations)
        repairs = ["deferred_review_only_receipt_like_observations"]
        observations = []
    else:
        deferred_observation_count = 0
    confidence = payload.get("confidence") if isinstance(payload.get("confidence"), dict) else {}
    output_metadata: dict[str, Any] = {"model_output_schema_name": model_output_schema_name}
    if deferred_observation_count:
        output_metadata["deferred_observation_count"] = deferred_observation_count
        output_metadata["deferred_semantic_type"] = semantic_type
    accepted_observation_keys = {"confidence", *{item["field_name"] for item in observations}}
    if model_output_schema_name == "granite_generic_kvp.v1":
        accepted_observation_keys.add("fields")
    return (
        {
            "schema_name": "document_observation",
            "schema_version": "v1",
            "document_id": str(document_id),
            "observations": observations,
            "confidence": confidence,
            "created_at": datetime.now(UTC).isoformat(),
            "metadata": output_metadata,
        },
        {
            "mapper": model_output_schema_name,
            "repairs": repairs,
            **(
                {"deferred_observation_count": deferred_observation_count}
                if deferred_observation_count
                else {}
            ),
            "rejected_fields": _rejected_fields(
                payload,
                accepted_observation_keys,
            ),
        },
    )


def _should_defer_review_only_receipt_like_observations(
    *,
    model_output_schema_name: str | None,
    semantic_type: str | None,
    target_schema: str | None,
    resolved_document_type: str | None,
) -> bool:
    if model_output_schema_name != "granite_generic_kvp.v1":
        return False
    if (target_schema or "").strip().lower() != "document_observation":
        return False
    return (semantic_type or "").strip().lower() in _REVIEW_ONLY_RECEIPT_LIKE_SEMANTIC_TYPES


def observation_dicts_from_payload(payload: dict[str, Any]) -> list[dict[str, Any]]:
    return _observation_dicts_from_payload(payload)


def _canonical_invoice_line_items(
    items: list[Any],
    *,
    evidence_context: EvidenceContext | None,
) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        if not _item_matches_contract(item, INVOICE_LINE_ITEM_KEYS):
            continue
        description = _line_item_description(item)
        if not description:
            continue
        if _is_non_line_item_heading(item, description):
            continue
        amount = _line_item_amount(item)
        service_date = item.get("service_date") or item.get("date")
        normalized_item = {
            "ordinal": int(item.get("ordinal") or len(normalized) + 1),
            "description": description,
            **({"service_date": service_date} if service_date else {}),
            **line_item_provenance(item, evidence_context),
            **({"quantity": _number(item.get("quantity"))} if item.get("quantity") else {}),
            **({"unit": item.get("unit")} if item.get("unit") else {}),
            **({"unit_price": _money(item.get("unit_price"))} if item.get("unit_price") else {}),
            **({"amount": amount} if amount else {}),
            **(
                {"gl_hint": item.get("gl_hint") or item.get("category_hint")}
                if (item.get("gl_hint") or item.get("category_hint"))
                else {}
            ),
            "evidence": [canonical_line_item_evidence(item, description, evidence_context)],
        }
        normalized.append(normalized_item)
    return normalized


def _canonical_receipt_line_items(
    items: Any,
    *,
    evidence_context: EvidenceContext | None,
    allowed_item_keys: frozenset[str],
    description_keys: tuple[str, ...] = ("description",),
    amount_keys: tuple[str, ...] = ("amount",),
    code_keys: tuple[str, ...] = ("sku", "code"),
) -> list[dict[str, Any]]:
    if not isinstance(items, list):
        return []
    normalized: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        if not _item_matches_contract(item, allowed_item_keys):
            continue
        description = _line_item_description(item, keys=description_keys)
        if not description:
            continue
        amount = _line_item_amount(item, keys=amount_keys)
        code = next((item.get(key) for key in code_keys if item.get(key)), None)
        normalized_item = {
            "ordinal": int(item.get("ordinal") or len(normalized) + 1),
            "description": description,
            **line_item_provenance(item, evidence_context),
            **({"quantity": _number(item.get("quantity"))} if item.get("quantity") else {}),
            **({"unit": item.get("unit")} if item.get("unit") else {}),
            **({"unit_price": _money(item.get("unit_price"))} if item.get("unit_price") else {}),
            **({"discount": _money(item.get("discount"))} if item.get("discount") else {}),
            **({"amount": amount} if amount else {}),
            **({"sku": code} if code else {}),
            **(
                {"tax_category_hint": item.get("tax_category_hint")}
                if item.get("tax_category_hint")
                else {}
            ),
            **({"category_hint": item.get("category_hint")} if item.get("category_hint") else {}),
            "evidence": [canonical_line_item_evidence(item, description, evidence_context)],
        }
        normalized.append(normalized_item)
    return normalized


def _invoice_line_item_records(payload: dict[str, Any]) -> list[Any]:
    if isinstance(payload.get("line_items"), list):
        return list(payload["line_items"])
    return []


def _with_evidence_context(
    item: dict[str, Any],
    evidence_context: EvidenceContext | None,
) -> dict[str, Any]:
    copied = dict(item)
    evidence = copied.get("evidence")
    if isinstance(evidence, list) and evidence:
        copied["evidence"] = [
            _merge_evidence_context(entry, evidence_context)
            for entry in evidence
            if isinstance(entry, dict)
        ]
    else:
        source_text = (
            copied.get("source_text")
            or copied.get("service_description")
            or copied.get("description")
            or copied.get("procedure_code")
            or copied.get("ordinal")
        )
        copied["evidence"] = [
            line_item_evidence(
                copied,
                source_text,
                evidence_context,
            )
        ]
    return copied


def _merge_evidence_context(
    item: dict[str, Any],
    evidence_context: EvidenceContext | None,
) -> dict[str, Any]:
    if evidence_context is None:
        return dict(item)
    grounded = line_item_evidence(item, item.get("source_text") or "", evidence_context)
    return {**item, **{key: value for key, value in grounded.items() if key != "source_text"}}


def _rejected_fields(payload: dict[str, Any], accepted: set[str]) -> list[str]:
    return sorted(key for key in payload if key not in accepted)

from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

from lib.extraction.evidence import has_concrete_evidence
from lib.extraction.model_output_contract_boundary import contract_root_payload
from lib.extraction.model_output_schemas import load_model_output_schema
from lib.extraction.models import ValidationReport
from lib.extraction.schema_registry import ExtractionSchemaError, ExtractionSchemaRegistry

MONEY_TOLERANCE = Decimal("0.02")


def validate_extraction_payload(
    schema_name: str,
    payload: dict[str, Any],
    *,
    registry: ExtractionSchemaRegistry | None = None,
) -> ValidationReport:
    checks: list[dict[str, Any]] = []
    validator = registry or ExtractionSchemaRegistry()
    try:
        validator.validate(schema_name, payload)
        checks.append(_check("json_schema", "passed", "Payload conforms to JSON Schema."))
    except ExtractionSchemaError as exc:
        checks.append(_check("json_schema", "failed", f"JSON Schema validation failed: {exc}"))
        return ValidationReport(needs_review=True, checks=checks)

    if schema_name == "receipt":
        checks.extend(_receipt_checks(payload))
    elif schema_name == "invoice":
        checks.extend(_invoice_checks(payload))
    elif schema_name == "medical_eob":
        checks.extend(_medical_eob_checks(payload))

    checks.append(_evidence_check(payload))
    needs_review = any(check["status"] in {"failed", "warning"} for check in checks)
    return ValidationReport(needs_review=needs_review, checks=checks)


def validate_semantic_region_payload(
    payload: dict[str, Any],
    *,
    model_output_schema_name: str | None,
    model_output_payload: dict[str, Any] | None = None,
) -> ValidationReport:
    checks: list[dict[str, Any]] = [
        _check(
            "region_scope.validation_routing",
            "passed",
            "Semantic-region output was not validated against a full canonical document schema.",
        )
    ]
    if model_output_schema_name:
        checks.append(
            _check(
                "region_scope.model_output_contract_selected",
                "passed",
                f"Region extraction selected model-output contract {model_output_schema_name}.",
            )
        )
        checks.append(
            _model_output_contract_check(
                model_output_schema_name=model_output_schema_name,
                model_output_payload=model_output_payload,
            )
        )
    else:
        checks.append(
            _check(
                "region_scope.model_output_contract_selected",
                "warning",
                "Region extraction did not declare a model-output contract.",
            )
        )
    checks.append(_evidence_check(payload))
    checks.append(
        _check(
            "region_scope.model_candidate_review_required",
            "warning",
            "Model-backed semantic-region candidates require review before canonical use.",
        )
    )
    return ValidationReport(needs_review=True, checks=checks)


def _model_output_contract_check(
    *,
    model_output_schema_name: str,
    model_output_payload: dict[str, Any] | None,
) -> dict[str, Any]:
    if model_output_payload is None:
        return _check(
            "region_scope.model_output_contract",
            "warning",
            "Region extraction did not retain raw model output for "
            "model-output contract validation.",
        )
    try:
        load_model_output_schema(model_output_schema_name)
        _shaped_payload, rejected_fields, contract_errors = contract_root_payload(
            model_output_payload,
            model_output_schema_name=model_output_schema_name,
        )
    except (OSError, ValueError) as exc:
        return _check(
            "region_scope.model_output_contract",
            "failed",
            f"Could not load model-output contract {model_output_schema_name}: {exc}",
        )
    if rejected_fields:
        return _check(
            "region_scope.model_output_contract",
            "failed",
            f"Model output included off-contract fields for {model_output_schema_name}: "
            f"{', '.join(rejected_fields)}",
        )
    if contract_errors:
        return _check(
            "region_scope.model_output_contract",
            "failed",
            f"Model output did not conform to {model_output_schema_name}: "
            f"{'; '.join(contract_errors)}",
        )
    return _check(
        "region_scope.model_output_contract",
        "passed",
        f"Raw model output conforms to {model_output_schema_name}.",
    )


def _receipt_checks(payload: dict[str, Any]) -> list[dict[str, Any]]:
    transaction = payload.get("transaction") or {}
    checks = [
        _presence_check(
            "receipt.required.merchant", payload.get("merchant", {}).get("display_name")
        ),
        _presence_check("receipt.required.date", transaction.get("date_local")),
    ]
    subtotal = _money_amount(transaction.get("subtotal"))
    tax = _money_amount(transaction.get("tax")) or Decimal("0")
    tip = _money_amount(transaction.get("tip")) or Decimal("0")
    discount = _money_amount(transaction.get("discount_total")) or Decimal("0")
    total = _money_amount(transaction.get("total"))
    if subtotal is not None and total is not None:
        expected = subtotal + tax + tip - discount
        checks.append(_money_match("receipt.total_arithmetic", total, expected))
    else:
        checks.append(
            _check(
                "receipt.total_arithmetic",
                "warning",
                "Subtotal and total were not both present for arithmetic validation.",
            )
        )
    return checks


def _invoice_checks(payload: dict[str, Any]) -> list[dict[str, Any]]:
    invoice = payload.get("invoice") or {}
    totals = payload.get("totals") or {}
    checks = [
        _presence_check("invoice.required.seller", payload.get("seller", {}).get("display_name")),
        _presence_check("invoice.required.invoice_number", invoice.get("invoice_number")),
        _presence_check("invoice.required.total", totals.get("total")),
    ]
    issued_on = _date_value(invoice.get("issued_on"))
    due_on = _date_value(invoice.get("due_on"))
    if issued_on and due_on and due_on < issued_on:
        checks.append(
            _check(
                "invoice.due_date_not_before_issue_date",
                "failed",
                "Invoice due date precedes issue date.",
                measured=due_on.isoformat(),
                expected=f">= {issued_on.isoformat()}",
            )
        )
    else:
        checks.append(
            _check(
                "invoice.due_date_not_before_issue_date",
                "passed" if issued_on and due_on else "not_applicable",
                "Invoice date ordering is valid where both dates are present.",
            )
        )

    subtotal = _money_amount(totals.get("subtotal"))
    tax = _money_amount(totals.get("tax_total")) or Decimal("0")
    shipping = _money_amount(totals.get("shipping_total")) or Decimal("0")
    discount = _money_amount(totals.get("discount_total")) or Decimal("0")
    total = _money_amount(totals.get("total"))
    if subtotal is not None and total is not None:
        checks.append(
            _money_match("invoice.total_arithmetic", total, subtotal + tax + shipping - discount)
        )
    else:
        checks.append(
            _check(
                "invoice.total_arithmetic",
                "warning",
                "Subtotal and total were not both present for arithmetic validation.",
            )
        )
    return checks


def _medical_eob_checks(payload: dict[str, Any]) -> list[dict[str, Any]]:
    checks = [
        _presence_check("medical_eob.required.payer", payload.get("payer", {}).get("display_name")),
        _presence_check(
            "medical_eob.required.patient", payload.get("patient", {}).get("display_name")
        ),
    ]
    summary = payload.get("financial_summary") or {}
    allowed = _money_amount(summary.get("total_allowed"))
    plan_paid = _money_amount(summary.get("total_plan_paid"))
    patient_resp = _money_amount(summary.get("total_patient_responsibility"))
    if allowed is not None and plan_paid is not None and patient_resp is not None:
        if plan_paid + patient_resp - allowed > MONEY_TOLERANCE:
            checks.append(
                _check(
                    "medical_eob.allowed_amount_plausible",
                    "failed",
                    "Plan paid plus patient responsibility exceeds allowed amount.",
                    measured=str(plan_paid + patient_resp),
                    expected=f"<= {allowed}",
                )
            )
        else:
            checks.append(
                _check(
                    "medical_eob.allowed_amount_plausible",
                    "passed",
                    "Allowed amount is plausible.",
                )
            )
    else:
        checks.append(
            _check(
                "medical_eob.allowed_amount_plausible",
                "warning",
                "EOB summary amounts were incomplete.",
            )
        )
    return checks


def _evidence_check(payload: dict[str, Any]) -> dict[str, Any]:
    evidence_sets = _collect_evidence(payload)
    if not evidence_sets:
        return _check("evidence.concrete_locator", "failed", "No evidence references were present.")
    if all(has_concrete_evidence(evidence) for evidence in evidence_sets):
        return _check(
            "evidence.concrete_locator", "passed", "Evidence references include concrete locators."
        )
    return _check(
        "evidence.concrete_locator",
        "failed",
        "At least one trusted extracted field lacks a concrete evidence locator.",
    )


def _collect_evidence(value: Any) -> list[list[dict[str, Any]]]:
    if isinstance(value, dict):
        found: list[list[dict[str, Any]]] = []
        evidence = value.get("evidence")
        if isinstance(evidence, list):
            found.append(evidence)
        for child in value.values():
            found.extend(_collect_evidence(child))
        return found
    if isinstance(value, list):
        found_items: list[list[dict[str, Any]]] = []
        for item in value:
            found_items.extend(_collect_evidence(item))
        return found_items
    return []


def _presence_check(code: str, value: object) -> dict[str, Any]:
    if value not in (None, ""):
        return _check(code, "passed", "Required field is present.")
    return _check(code, "failed", "Required field is missing.")


def _money_match(code: str, measured: Decimal, expected: Decimal) -> dict[str, Any]:
    if abs(measured - expected) <= MONEY_TOLERANCE:
        return _check(code, "passed", "Money arithmetic reconciles.")
    return _check(
        code,
        "failed",
        "Money arithmetic does not reconcile.",
        measured=str(measured),
        expected=str(expected),
    )


def _money_amount(value: Any) -> Decimal | None:
    if not isinstance(value, dict):
        return None
    amount = value.get("amount")
    if amount is None:
        return None
    try:
        return Decimal(str(amount))
    except InvalidOperation:
        return None


def _date_value(value: object) -> date | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _check(
    code: str,
    status: str,
    message: str,
    *,
    measured: object | None = None,
    expected: object | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {"code": code, "status": status, "message": message}
    if measured is not None:
        payload["measured_value"] = measured
    if expected is not None:
        payload["expected_value"] = expected
    return payload

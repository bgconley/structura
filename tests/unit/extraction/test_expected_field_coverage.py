from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

from lib.extraction.expected_field_coverage import (
    MATCH_RULE,
    expected_field_coverage,
    normalized_field_name,
    produced_field_names,
)
from lib.extraction.models import (
    ExtractionSourceDocument,
    GatewayExtraction,
    ModelRoute,
    ParsedPageText,
    PersistedExtraction,
)
from lib.extraction.region_envelope import (
    EvidenceRef,
    RegionExtractionEnvelope,
    RegionFact,
    RegionLineItem,
)
from lib.extraction.service import ExtractionService
from lib.semantic_annotations.models import SemanticExtractionTask, SemanticGroundingRef


def test_normalized_field_name_collapses_to_snake_case() -> None:
    assert normalized_field_name("Repair Order Number") == "repair_order_number"
    assert normalized_field_name("line-total") == "line_total"
    assert normalized_field_name("invoice.total_amount") == "invoice_total_amount"
    assert normalized_field_name("  VIN ") == "vin"


def test_exact_and_dotted_fact_names_match_expected_fields() -> None:
    envelope = _envelope(
        facts=[
            _fact("invoice.invoice_number", "6046058/1"),
            _fact("invoice.total_amount", {"amount": 42.0, "currency": "USD"}),
        ]
    )

    coverage = expected_field_coverage(("invoice_number", "total_amount", "due_date"), envelope)

    assert coverage is not None
    assert coverage["expected"] == ["invoice_number", "total_amount", "due_date"]
    assert coverage["missing"] == ["due_date"]
    assert coverage["coverage_ratio"] == round(2 / 3, 4)
    assert coverage["match_rule"] == MATCH_RULE


def test_substring_matching_covers_fuzzy_qwen_names() -> None:
    envelope = _envelope(
        line_items=[
            RegionLineItem(
                description="Brake pad replacement",
                net_amount=129.5,
                source_payload={
                    "service_description": "Brake pad replacement",
                    "line_total": 129.5,
                    "evidence": [],
                },
            )
        ]
    )

    coverage = expected_field_coverage(
        ("service_description", "line_total", "vin"),
        envelope,
    )

    assert coverage is not None
    # "description" (envelope field) and "service_description" (payload key)
    # both satisfy the fuzzy expected name; vin never materialized.
    assert coverage["missing"] == ["vin"]
    assert coverage["coverage_ratio"] == round(2 / 3, 4)
    assert "service_description" in coverage["produced"]
    assert "description" in coverage["produced"]


def test_observation_fact_names_count_as_produced() -> None:
    envelope = _envelope(observations=[_fact("vin", "WBA123"), _fact("mileage", "42000")])

    coverage = expected_field_coverage(("vin", "mileage", "repair_order_number"), envelope)

    assert coverage is not None
    assert coverage["missing"] == ["repair_order_number"]
    assert coverage["coverage_ratio"] == round(2 / 3, 4)


def test_missing_envelope_records_zero_coverage() -> None:
    coverage = expected_field_coverage(("total_amount",), None)

    assert coverage == {
        "expected": ["total_amount"],
        "produced": [],
        "missing": ["total_amount"],
        "coverage_ratio": 0.0,
        "match_rule": MATCH_RULE,
    }


def test_no_expected_fields_returns_none() -> None:
    assert expected_field_coverage((), _envelope()) is None
    assert expected_field_coverage(("", "  "), _envelope()) is None


def test_duplicate_expected_fields_are_deduplicated_by_normalized_name() -> None:
    envelope = _envelope(facts=[_fact("invoice.total_amount", {"amount": 10.0})])

    coverage = expected_field_coverage(("total_amount", "Total Amount"), envelope)

    assert coverage is not None
    assert coverage["expected"] == ["total_amount"]
    assert coverage["coverage_ratio"] == 1.0


def test_produced_names_exclude_empty_values_and_bookkeeping_keys() -> None:
    envelope = _envelope(
        facts=[_fact("invoice.invoice_number", None)],
        line_items=[
            RegionLineItem(
                description="Part",
                quantity=None,
                source_payload={
                    "description": "Part",
                    "quantity": None,
                    "evidence": [{"page_number": 1}],
                    "row_index": 2,
                },
            )
        ],
    )

    produced = produced_field_names(envelope)

    assert produced == ["description"]


def test_extraction_service_records_expected_field_coverage_in_normalization_json() -> None:
    document_id = uuid4()
    region_id = uuid4()
    annotation_id = uuid4()
    source = _source(document_id=document_id)
    task = SemanticExtractionTask(
        region_id=region_id,
        annotation_id=annotation_id,
        document_id=document_id,
        semantic_type="receipt_payment_summary",
        granite_task="kvp",
        target_schema="receipt",
        expected_fields=("total_amount", "payment_method"),
        grounding=SemanticGroundingRef(kind="page", page_id=source.pages[0].page_id),
    )
    captured: dict[str, Any] = {}

    def persist(extraction: GatewayExtraction, **kwargs: object) -> PersistedExtraction:
        captured["extraction"] = extraction
        captured.update(kwargs)
        return PersistedExtraction(
            extraction_id=uuid4(),
            review_status="needs_review",
            candidate_count=0,
            canonical_count=0,
            review_task_count=0,
        )

    ExtractionService(
        gateway=_EnvelopeGateway(
            document_id=document_id,
            annotation_id=annotation_id,
            region_id=region_id,
            page_id=source.pages[0].page_id,
        ),
        source_loader=lambda loaded_document_id: source,
        semantic_task_loader=lambda loaded_region_id: task,
        persister=persist,
    ).extract_document(
        document_id,
        schema_name="receipt",
        route_profile="docling_plus_granite_structured",
        semantic_region_id=region_id,
    )

    coverage = captured["extraction"].normalization_json["expected_field_coverage"]
    assert coverage["expected"] == ["total_amount", "payment_method"]
    assert coverage["missing"] == ["payment_method"]
    assert coverage["coverage_ratio"] == 0.5
    assert "receipt.transaction.total" in coverage["produced"]


class _EnvelopeGateway:
    def __init__(
        self,
        *,
        document_id: UUID,
        annotation_id: UUID,
        region_id: UUID,
        page_id: UUID,
    ) -> None:
        self.document_id = document_id
        self.annotation_id = annotation_id
        self.region_id = region_id
        self.page_id = page_id

    def extract(
        self,
        source: ExtractionSourceDocument,
        *,
        schema_name: str,
        route_profile: str,
        semantic_task: SemanticExtractionTask | None = None,
    ) -> GatewayExtraction:
        del source, semantic_task
        envelope = _envelope(
            document_id=self.document_id,
            facts=[
                RegionFact(
                    name="receipt.transaction.total",
                    value={"amount": 4.65, "currency": "USD"},
                    value_type="money",
                    confidence=0.81,
                    evidence=[
                        EvidenceRef(
                            document_id=str(self.document_id),
                            semantic_annotation_id=str(self.annotation_id),
                            semantic_region_id=str(self.region_id),
                            page_id=str(self.page_id),
                            page_number=1,
                            source_engine="granite_vision_3b",
                            source_text="$4.65",
                            text_span={"start": 8, "end": 13, "basis": "page_text"},
                        )
                    ],
                )
            ],
        )
        return GatewayExtraction(
            schema_name=schema_name,
            schema_version="v1",
            route=ModelRoute(
                source_engine="granite_vision_3b",
                model_name="granite",
                model_version="v1",
                prompt_version="phase8_5-granite-structured-v1",
                route_profile=route_profile,
            ),
            normalized_json={
                "schema_name": "receipt",
                "schema_version": "v1",
                "document_id": str(self.document_id),
                "transaction": {"total": {"amount": 4.65, "currency": "USD"}},
                "confidence": {"overall": 0.81},
            },
            raw_output_json={"modelInvoked": True},
            normalization_json={
                "regionEnvelope": envelope.model_dump(mode="json", exclude_none=True)
            },
        )


def _envelope(
    *,
    document_id: UUID | None = None,
    facts: list[RegionFact] | None = None,
    line_items: list[RegionLineItem] | None = None,
    observations: list[RegionFact] | None = None,
) -> RegionExtractionEnvelope:
    return RegionExtractionEnvelope(
        document_id=str(document_id or uuid4()),
        resolved_document_type="receipt",
        semantic_type="receipt_payment_summary",
        target_schema="receipt",
        model_output_schema_name="granite_receipt_payment_summary.v1",
        facts=facts or [],
        line_items=line_items or [],
        observations=observations or [],
    )


def _fact(name: str, value: Any) -> RegionFact:
    return RegionFact(name=name, value=value, value_type="string")


def _source(*, document_id: UUID) -> ExtractionSourceDocument:
    return ExtractionSourceDocument(
        document_id=document_id,
        household_id=uuid4(),
        title="Receipt",
        original_filename="receipt.pdf",
        mime_type="application/pdf",
        family="receipt",
        subtype=None,
        sensitivity="standard",
        document_date=None,
        counterparty_display=None,
        primary_folder_id=None,
        metadata={},
        pages=[ParsedPageText(page_id=uuid4(), page_number=1, text="Receipt $4.65 total")],
        elements=[],
        tables=[],
    )

from __future__ import annotations

import json
from datetime import date
from uuid import uuid4

import pytest

from lib.extraction.claims import claims_from_region_envelope
from lib.extraction.gateways.routing import ModelRoutingExtractionGateway
from lib.extraction.models import (
    ExtractionSourceDocument,
    GatewayExtraction,
    ModelRoute,
    ParsedElementText,
    ParsedPageText,
)
from lib.extraction.text_lane.eligibility import text_lane_kvp_eligibility
from lib.extraction.text_lane.gateway import TextLaneAbstention
from lib.extraction.text_lane.kvp_extractor import extract_kvp_region
from lib.extraction.text_lane.kvp_gateway import TextLaneKvpExtractionGateway
from lib.extraction.text_lane.span_candidates import (
    MAX_SPANS_PER_PAGE,
    span_candidates_for_page,
)
from lib.extraction.text_lane.span_selection import (
    SpanSelection,
    selection_keys,
    selections_from_payload,
    span_selection_prompt,
    span_selection_schema,
)
from lib.model_runtime.contracts import TextGenerateRequest, TextGenerateResponse
from lib.semantic_annotations.models import SemanticExtractionTask, SemanticGroundingRef

_PAGE_TEXT = (
    "Final Escrow Statement. Loan Number: 1234567890. "
    "Statement Date: 04/29/2024. Escrow balance 2,114.32. "
    "Customer Service: support@example.com or (800) 555-0100."
)


def _element(text: str, ordinal: int, *, bbox: dict[str, float] | None = None) -> ParsedElementText:
    return ParsedElementText(
        element_id=uuid4(),
        page_number=1,
        ordinal=ordinal,
        text=text,
        bbox=bbox,
    )


def _bottomleft(left: float, bottom: float, right: float, top: float) -> dict[str, float]:
    return {"l": left, "b": bottom, "r": right, "t": top, "coord_origin": "BOTTOMLEFT"}


def _source(elements: list[ParsedElementText]) -> ExtractionSourceDocument:
    page_id = uuid4()
    return ExtractionSourceDocument(
        document_id=uuid4(),
        household_id=uuid4(),
        title="Escrow statement",
        original_filename="escrow.pdf",
        mime_type="application/pdf",
        family="mortgage_escrow_statement",
        subtype=None,
        sensitivity="standard",
        document_date=date(2026, 6, 1),
        counterparty_display=None,
        primary_folder_id=None,
        metadata={},
        pages=[
            ParsedPageText(
                page_id=page_id,
                page_number=1,
                text=_PAGE_TEXT,
                has_text_layer=True,
            )
        ],
        elements=elements,
        tables=[],
    )


def _task(
    source: ExtractionSourceDocument,
    *,
    semantic_type: str = "escrow_summary",
    expected: tuple[str, ...] = ("loan_number", "statement_date", "customer_phone"),
) -> SemanticExtractionTask:
    return SemanticExtractionTask(
        region_id=uuid4(),
        annotation_id=uuid4(),
        document_id=source.document_id,
        semantic_type=semantic_type,
        granite_task="kvp",
        target_schema="document_observation",
        expected_fields=expected,
        grounding=SemanticGroundingRef(kind="page", page_id=source.pages[0].page_id),
    )


def _default_elements() -> list[ParsedElementText]:
    return [
        _element("Loan Number: 1234567890", 1),
        _element("Statement Date: 04/29/2024", 2),
        _element("AMOUNT DUE", 3, bbox=_bottomleft(36, 700, 140, 712)),
        _element("$1,860.00", 4, bbox=_bottomleft(150, 700, 240, 712)),
        _element("PROPERTY ADDRESS", 5, bbox=_bottomleft(36, 660, 200, 672)),
        _element("12 Example Way, Springfield", 6, bbox=_bottomleft(36, 640, 260, 652)),
        _element("Questions? Call (800) 555-0100", 7),
        _element("Previous balance was 412.10 as of January.", 8),
    ]


def test_span_candidates_cover_labeled_pairs_and_typed_regexes() -> None:
    source = _source(_default_elements())
    spans = span_candidates_for_page(source, 1)
    assert spans, "expected span candidates"
    by_kind = {span.kind for span in spans}
    assert "label_colon" in by_kind
    assert "label_right_of" in by_kind
    assert "label_below_of" in by_kind
    assert "regex_money" in by_kind
    assert "regex_phone" in by_kind
    loan = next(span for span in spans if span.label_text == "Loan Number")
    assert loan.value_text == "1234567890"
    assert loan.text_span is not None and loan.text_span["basis"] == "element_text"
    assert loan.element_id is not None
    amount = next(span for span in spans if span.kind == "label_right_of")
    assert amount.label_text == "AMOUNT DUE"
    assert amount.value_text == "$1,860.00"
    below = next(span for span in spans if span.kind == "label_below_of")
    assert below.label_text == "PROPERTY ADDRESS"
    assert len(spans) <= MAX_SPANS_PER_PAGE
    # positional ids are stable across rebuilds of the same parse
    again = span_candidates_for_page(_source(_default_elements()), 1)
    assert [span.span_id for span in spans] == [span.span_id for span in again]


def test_selection_schema_is_closed_enum_over_span_ids() -> None:
    source = _source(_default_elements())
    spans = span_candidates_for_page(source, 1)
    keys = selection_keys(("loan_number", "statement_date", "Loan Number"))
    assert keys == ("loan_number", "statement_date")
    schema = span_selection_schema(keys=keys, spans=spans)
    assert schema["additionalProperties"] is False
    assert schema["required"] == list(keys)
    enum = schema["properties"]["loan_number"]["enum"]
    assert enum[-1] is None
    assert set(enum[:-1]) == {span.span_id for span in spans}
    prompt = span_selection_prompt(family="mortgage_escrow_statement", keys=keys, spans=spans)
    assert "loan_number" in prompt
    assert spans[0].span_id in prompt
    assert "null" in prompt


def test_selections_from_payload_drops_unknown_ids() -> None:
    source = _source(_default_elements())
    spans = span_candidates_for_page(source, 1)
    keys = ("loan_number", "statement_date")
    payload = {"loan_number": spans[0].span_id, "statement_date": "s_bogus"}
    selections = selections_from_payload(payload, expected_keys=keys, spans=spans)
    assert selections["loan_number"] == spans[0].span_id
    assert selections["statement_date"] is None


def _selection_for(spans, mapping: dict[str, str | None]) -> SpanSelection:
    return SpanSelection(
        selections=mapping,
        model_name="fake-qwen",
        model_version="t",
        prompt_version="text_lane_span_selection.v1",
    )


def test_kvp_extractor_mints_docling_claims_with_exact_anchors() -> None:
    source = _source(_default_elements())
    task = _task(source)
    spans = span_candidates_for_page(source, 1)
    loan = next(span for span in spans if span.label_text == "Loan Number")
    statement = next(span for span in spans if span.label_text == "Statement Date")
    phone = next(span for span in spans if span.kind == "regex_phone")
    extraction = extract_kvp_region(
        source=source,
        semantic_task=task,
        spans=spans,
        selection=_selection_for(
            spans,
            {
                "loan_number": loan.span_id,
                "statement_date": statement.span_id,
                "customer_phone": phone.span_id,
            },
        ),
        family="mortgage_escrow_statement",
        target_schema="document_observation",
    )
    envelope = extraction.envelope
    assert extraction.fact_count == 0  # unregistered family -> observations only
    assert extraction.observation_count == 3
    claims = claims_from_region_envelope(envelope)
    assert {claim.canonical_key for claim in claims} == {
        "loan_number",
        "statement_date",
        "customer_phone",
    }
    assert {claim.source_engine for claim in claims} == {"docling"}
    loan_claim = next(claim for claim in claims if claim.canonical_key == "loan_number")
    assert loan_claim.raw_value == "1234567890"
    assert loan_claim.anchor.docling_element_ids
    assert loan_claim.anchor.text_span is not None
    date_claim = next(claim for claim in claims if claim.canonical_key == "statement_date")
    assert date_claim.typed_value == "2024-04-29"


def test_registry_keys_mint_family_facts() -> None:
    elements = [
        _element("Subtotal: 100.00", 1),
        _element("Total: 108.25", 2),
        _element("Payment method: VISA ending 1111", 3),
    ]
    source = _source(elements)
    task = _task(
        source,
        semantic_type="receipt_payment_summary",
        expected=("subtotal", "total", "payment_method"),
    )
    spans = span_candidates_for_page(source, 1)
    subtotal = next(span for span in spans if span.label_text == "Subtotal")
    total = next(span for span in spans if span.label_text == "Total")
    method = next(span for span in spans if span.label_text == "Payment method")
    extraction = extract_kvp_region(
        source=source,
        semantic_task=task,
        spans=spans,
        selection=_selection_for(
            spans,
            {
                "subtotal": subtotal.span_id,
                "total": total.span_id,
                "payment_method": method.span_id,
            },
        ),
        family="receipt",
        target_schema="receipt",
    )
    envelope = extraction.envelope
    fact_names = {fact.name for fact in envelope.facts}
    assert fact_names == {"receipt.transaction.subtotal", "receipt.transaction.total"}
    assert {fact.value["amount"] for fact in envelope.facts} == {100.0, 108.25}
    assert [observation.name for observation in envelope.observations] == ["payment_method"]
    claims = claims_from_region_envelope(envelope)
    assert {
        claim.canonical_key for claim in claims if claim.canonical_key.startswith("receipt.")
    } == {"receipt.transaction.subtotal", "receipt.transaction.total"}


def test_kvp_eligibility_screens() -> None:
    source = _source(_default_elements())
    task = _task(source)
    decision = text_lane_kvp_eligibility(source, semantic_task=task)
    assert decision.lane == "text"
    assert decision.reason == "kvp_spans_on_text_page"
    assert decision.page_number == 1
    not_kvp = text_lane_kvp_eligibility(
        source, semantic_task=_task(source, semantic_type="invoice_line_item_table")
    )
    assert not_kvp.reason == "region_not_kvp"
    scan_source = ExtractionSourceDocument(
        document_id=source.document_id,
        household_id=source.household_id,
        title=source.title,
        original_filename=source.original_filename,
        mime_type=source.mime_type,
        family=source.family,
        subtype=None,
        sensitivity="standard",
        document_date=source.document_date,
        counterparty_display=None,
        primary_folder_id=None,
        metadata={},
        pages=[
            ParsedPageText(
                page_id=source.pages[0].page_id,
                page_number=1,
                text="scan",
                has_text_layer=True,
            )
        ],
        elements=source.elements,
        tables=[],
    )
    difficult = text_lane_kvp_eligibility(scan_source, semantic_task=_task(scan_source))
    assert difficult.lane == "vision"
    assert difficult.reason.startswith("difficult_page:")


class _StaticSelector:
    def __init__(self, mapping_factory) -> None:  # noqa: ANN001
        self._factory = mapping_factory
        self.calls = 0

    def select_spans(self, *, family, expected_keys, spans):  # noqa: ANN001, ANN003
        del family
        self.calls += 1
        return _selection_for(spans, self._factory(expected_keys, spans))


class _FakeGranite:
    def __init__(self) -> None:
        self.calls = 0

    def extract(self, source, *, schema_name, route_profile, semantic_task=None):  # noqa: ANN001
        del source, semantic_task
        self.calls += 1
        return GatewayExtraction(
            schema_name=schema_name,
            schema_version="v1",
            route=ModelRoute(
                source_engine="granite_vision_3b",
                model_name="granite",
                model_version="test",
                prompt_version="granite-test",
                route_profile=route_profile,
            ),
            normalized_json={"schema_name": schema_name},
            raw_output_json={},
        )


def test_routing_sends_eligible_kvp_region_to_text_lane() -> None:
    source = _source(_default_elements())
    task = _task(source)

    def _pick(expected_keys, spans):  # noqa: ANN001
        loan = next(span for span in spans if span.label_text == "Loan Number")
        return {key: (loan.span_id if key == "loan_number" else None) for key in expected_keys}

    granite = _FakeGranite()
    gateway = ModelRoutingExtractionGateway(
        deterministic=_FakeGranite(),
        granite=granite,
        text_lane_kvp=TextLaneKvpExtractionGateway(selector=_StaticSelector(_pick)),
    )
    result = gateway.extract(
        source,
        schema_name="document_observation",
        route_profile="docling_plus_structured_extraction",
        semantic_task=task,
    )
    assert granite.calls == 0
    assert result.route.source_engine == "docling"
    assert result.normalization_json["lane"] == "text"
    assert result.normalization_json["laneEligibility"] == "kvp_spans_on_text_page"
    assert result.model_output_schema_name == "text_lane_kvp.v1"


def test_routing_falls_back_to_vision_when_all_keys_unmatched() -> None:
    source = _source(_default_elements())
    task = _task(source)
    granite = _FakeGranite()
    gateway = ModelRoutingExtractionGateway(
        deterministic=_FakeGranite(),
        granite=granite,
        text_lane_kvp=TextLaneKvpExtractionGateway(
            selector=_StaticSelector(lambda keys, spans: {key: None for key in keys})
        ),
    )
    result = gateway.extract(
        source,
        schema_name="document_observation",
        route_profile="docling_plus_structured_extraction",
        semantic_task=task,
    )
    assert granite.calls == 1
    assert result.normalization_json["lane"] == "vision"
    assert str(result.normalization_json["laneEligibility"]).startswith(
        "text_lane_abstained:all_keys_unmatched"
    )


def test_kvp_gateway_abstains_without_expected_fields() -> None:
    source = _source(_default_elements())
    task = _task(source, expected=())
    gateway = TextLaneKvpExtractionGateway(selector=_StaticSelector(lambda keys, spans: {}))
    with pytest.raises(TextLaneAbstention) as excinfo:
        gateway.extract(
            source,
            schema_name="document_observation",
            route_profile="docling_plus_structured_extraction",
            semantic_task=task,
        )
    assert excinfo.value.reason == "no_expected_fields"


def test_selection_cache_dedupes_identical_prompts() -> None:
    from lib.extraction.text_lane.span_selection import (
        LiveSpanSelector,
        clear_span_selection_cache,
    )

    clear_span_selection_cache()
    source = _source(_default_elements())
    spans = span_candidates_for_page(source, 1)

    class _Profile:
        name = "qwen3-vl-8b-fp8-semantic:v1"

    class _Client:
        profile = _Profile()
        calls = 0

        def generate(self, request: TextGenerateRequest) -> TextGenerateResponse:
            type(self).calls += 1
            payload = {"loan_number": spans[0].span_id, "statement_date": None}
            return TextGenerateResponse(
                profile_name=request.profile_name,
                model_name="fake",
                model_version="t",
                source_engine="qwen3_vl_8b",
                prompt_version=request.prompt_version,
                raw_text=json.dumps(payload),
                normalized_json=payload,
                prompt_sha256="0" * 64,
                latency_ms=1,
                structured_output_used=True,
            )

    first = LiveSpanSelector(client=_Client())  # type: ignore[arg-type]
    second = LiveSpanSelector(client=_Client())  # type: ignore[arg-type]
    keys = ("loan_number", "statement_date")
    try:
        initial = first.select_spans(
            family="mortgage_escrow_statement", expected_keys=keys, spans=spans
        )
        cached = second.select_spans(
            family="mortgage_escrow_statement", expected_keys=keys, spans=spans
        )
        assert not initial.from_cache
        assert cached.from_cache
        assert _Client.calls == 1
    finally:
        clear_span_selection_cache()

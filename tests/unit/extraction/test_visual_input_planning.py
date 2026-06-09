from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from io import BytesIO
from uuid import UUID, uuid4

from PIL import Image, ImageDraw

from lib.extraction.gateways.granite_vision import GraniteVisionExtractionGateway
from lib.extraction.models import (
    ExtractionSourceDocument,
    ParsedElementText,
    ParsedPageText,
    ParsedTableText,
)
from lib.extraction.region_envelope import RegionExtractionEnvelope
from lib.extraction.visual_input_planning import (
    is_useful_granite_output,
    plan_granite_visual_inputs,
)
from lib.model_runtime.contracts import VisionGenerateRequest, VisionGenerateResponse
from lib.model_runtime.profiles import GRANITE_VISION_PROFILE
from lib.semantic_annotations.models import SemanticExtractionTask, SemanticGroundingRef
from tests.unit.extraction.model_output_contract_fixtures import (
    invoice_line_items_payload as _invoice_line_items_payload,
)


@dataclass
class SequencedVisionClient:
    payloads: list[dict[str, object]]
    requests: list[VisionGenerateRequest] = field(default_factory=list)

    def generate(self, request: VisionGenerateRequest) -> VisionGenerateResponse:
        self.requests.append(request)
        payload = self.payloads.pop(0)
        return VisionGenerateResponse(
            profile_name=GRANITE_VISION_PROFILE,
            model_name="fake-granite",
            model_version="test",
            source_engine="granite_vision_3b",
            prompt_version=request.prompt_version,
            raw_text="{}",
            normalized_json=payload,
            confidence_json={"overall": 0.8},
            input_sha256=tuple(image.validated_sha256() for image in request.image_inputs),
            latency_ms=1,
        )


def test_shadow_mode_records_element_crop_intent_but_sends_full_page() -> None:
    source, element_id = _source_with_geometry()
    task = _line_item_task(source, element_id=element_id)

    decision = plan_granite_visual_inputs(
        source,
        semantic_task=task,
        max_images=1,
        page_image_loader=lambda page: page.image_bytes,
        mode="shadow_full_page",
    )

    plan = decision.primary_plan
    assert plan is not None
    assert decision.model_inputs[0].content == source.pages[0].image_bytes
    assert plan.intended_scope == "element_crop"
    assert plan.effective_scope == "full_page"
    assert plan.fallback_reason == "shadow_mode_sends_full_page"
    assert plan.bbox_basis == "pdf_points"


def test_page_grounded_task_uses_full_page() -> None:
    source, _element_id = _source_with_geometry()
    task = SemanticExtractionTask(
        region_id=uuid4(),
        annotation_id=uuid4(),
        document_id=source.document_id,
        semantic_type="document_observation",
        granite_task="kvp",
        target_schema="document_observation",
        expected_fields=("seller_name",),
        grounding=SemanticGroundingRef(kind="page", page_id=source.pages[0].page_id),
    )

    decision = plan_granite_visual_inputs(
        source,
        semantic_task=task,
        max_images=1,
        page_image_loader=lambda page: page.image_bytes,
        mode="planned",
    )

    assert decision.primary_plan is not None
    assert decision.primary_plan.effective_scope == "full_page"
    assert decision.model_inputs[0].content == source.pages[0].image_bytes


def test_ambiguous_visual_bbox_hint_falls_back_to_full_page() -> None:
    source, _element_id = _source_with_geometry()
    task = SemanticExtractionTask(
        region_id=uuid4(),
        annotation_id=uuid4(),
        document_id=source.document_id,
        semantic_type="invoice_line_item_table",
        granite_task="tables_json",
        target_schema="invoice",
        expected_fields=("line_items",),
        grounding=SemanticGroundingRef(kind="unmatched_region"),
        metadata={"visual_bbox_hint": [10, 20, 300, 400]},
    )

    decision = plan_granite_visual_inputs(
        source,
        semantic_task=task,
        max_images=1,
        page_image_loader=lambda page: page.image_bytes,
        mode="planned",
    )

    assert decision.primary_plan is not None
    assert decision.primary_plan.effective_scope == "full_page"
    assert decision.primary_plan.fallback_reason == "visual_bbox_hint_untrusted"


def test_planned_mode_sends_crop_when_geometry_is_safe() -> None:
    source, element_id = _source_with_geometry()
    task = _line_item_task(source, element_id=element_id)

    decision = plan_granite_visual_inputs(
        source,
        semantic_task=task,
        max_images=1,
        page_image_loader=lambda page: page.image_bytes,
        mode="planned",
    )

    plan = decision.primary_plan
    assert plan is not None
    assert plan.effective_scope == "expanded_crop"
    assert decision.model_inputs[0].content != source.pages[0].image_bytes
    assert decision.model_inputs[0].validated_sha256() == plan.input_sha256
    assert plan.crop_quality.passed is True
    assert plan.bbox is not None


def test_low_resolution_page_forces_full_page_despite_bbox() -> None:
    source, element_id = _source_with_geometry(width_px=640, height_px=800)
    task = _line_item_task(source, element_id=element_id)

    decision = plan_granite_visual_inputs(
        source,
        semantic_task=task,
        max_images=1,
        page_image_loader=lambda page: page.image_bytes,
        mode="planned",
    )

    assert decision.primary_plan is not None
    assert decision.primary_plan.effective_scope == "full_page"
    assert decision.primary_plan.fallback_reason == "low_resolution_page_requires_full_page"


def test_unknown_rotation_forces_full_page() -> None:
    source, element_id = _source_with_geometry(rotation_degrees=13)
    task = _line_item_task(source, element_id=element_id)

    decision = plan_granite_visual_inputs(
        source,
        semantic_task=task,
        max_images=1,
        page_image_loader=lambda page: page.image_bytes,
        mode="planned",
    )

    assert decision.primary_plan is not None
    assert decision.primary_plan.effective_scope == "full_page"
    assert decision.primary_plan.fallback_reason == "rotation_unresolved"


def test_explicit_rotated_page_falls_back_until_transform_is_proven() -> None:
    source, element_id = _source_with_geometry(rotation_degrees=90)
    task = _line_item_task(source, element_id=element_id)

    decision = plan_granite_visual_inputs(
        source,
        semantic_task=task,
        max_images=1,
        page_image_loader=lambda page: page.image_bytes,
        mode="planned",
    )

    assert decision.primary_plan is not None
    assert decision.primary_plan.rotation_policy == "rotate_90"
    assert decision.primary_plan.effective_scope == "full_page"
    assert decision.primary_plan.fallback_reason == "rotation_unresolved"


def test_explicit_normalized_bbox_hint_can_crop() -> None:
    source, _element_id = _source_with_geometry()
    task = SemanticExtractionTask(
        region_id=uuid4(),
        annotation_id=uuid4(),
        document_id=source.document_id,
        semantic_type="invoice_line_item_table",
        granite_task="tables_json",
        target_schema="invoice",
        expected_fields=("line_items",),
        grounding=SemanticGroundingRef(kind="unmatched_region"),
        metadata={
            "visual_bbox_hint": [160, 260, 850, 620],
            "visual_bbox_basis": "normalized_1000",
            "visual_bbox_confidence": 0.9,
        },
    )

    decision = plan_granite_visual_inputs(
        source,
        semantic_task=task,
        max_images=1,
        page_image_loader=lambda page: page.image_bytes,
        mode="planned",
    )

    assert decision.primary_plan is not None
    assert decision.primary_plan.effective_scope == "expanded_crop"
    assert decision.primary_plan.bbox_basis == "normalized_1000"


def test_oversized_crop_falls_back_to_full_page() -> None:
    source, element_id = _source_with_geometry(bbox=[10, 10, 590, 790])
    task = _line_item_task(source, element_id=element_id)

    decision = plan_granite_visual_inputs(
        source,
        semantic_task=task,
        max_images=1,
        page_image_loader=lambda page: page.image_bytes,
        mode="planned",
    )

    assert decision.primary_plan is not None
    assert decision.primary_plan.effective_scope == "full_page"
    assert decision.primary_plan.fallback_reason == "crop_area_too_large"


def test_blank_crop_falls_back_to_full_page() -> None:
    source, element_id = _source_with_geometry(nonblank=False)
    task = _line_item_task(source, element_id=element_id)

    decision = plan_granite_visual_inputs(
        source,
        semantic_task=task,
        max_images=1,
        page_image_loader=lambda page: page.image_bytes,
        mode="planned",
    )

    assert decision.primary_plan is not None
    assert decision.primary_plan.effective_scope == "full_page"
    assert decision.primary_plan.fallback_reason == "crop_mostly_blank"


def test_table_metadata_bbox_can_drive_table_crop() -> None:
    source, _element_id = _source_with_geometry(table_bbox=[100, 200, 500, 420])
    table_id = source.tables[0].table_id
    task = SemanticExtractionTask(
        region_id=uuid4(),
        annotation_id=uuid4(),
        document_id=source.document_id,
        semantic_type="invoice_line_item_table",
        granite_task="tables_json",
        target_schema="invoice",
        expected_fields=("line_items",),
        grounding=SemanticGroundingRef(kind="table", table_id=table_id),
    )

    decision = plan_granite_visual_inputs(
        source,
        semantic_task=task,
        max_images=1,
        page_image_loader=lambda page: page.image_bytes,
        mode="planned",
    )

    assert decision.primary_plan is not None
    assert decision.primary_plan.effective_scope == "expanded_crop"
    assert decision.primary_plan.intended_scope == "table_crop"


def test_continuation_group_uses_full_page_until_per_page_jobs_exist() -> None:
    source, element_id = _source_with_geometry()
    task = _line_item_task(source, element_id=element_id, metadata={"continuation_group": "a"})

    decision = plan_granite_visual_inputs(
        source,
        semantic_task=task,
        max_images=1,
        page_image_loader=lambda page: page.image_bytes,
        mode="planned",
    )

    assert decision.primary_plan is not None
    assert decision.primary_plan.effective_scope == "full_page"
    assert decision.primary_plan.fallback_reason == "continuation_requires_per_page_visual_plan"


def test_crop_output_empty_line_items_retries_full_page(monkeypatch) -> None:
    monkeypatch.setenv("STRUCTURA_GRANITE_VISUAL_INPUT_MODE", "planned")
    source, element_id = _source_with_geometry()
    task = _line_item_task(source, element_id=element_id)
    client = SequencedVisionClient(
        payloads=[
            _invoice_line_items_payload([]),
            _invoice_line_items_payload([{"description": "600 mile service", "amount": 250.0}]),
        ]
    )

    result = GraniteVisionExtractionGateway(client=client).extract(
        source,
        schema_name="invoice",
        route_profile="docling_plus_granite_structured",
        semantic_task=task,
    )

    assert len(client.requests) == 2
    assert client.requests[0].image_inputs[0].content != source.pages[0].image_bytes
    assert client.requests[1].image_inputs[0].content == source.pages[0].image_bytes
    assert result.raw_output_json["visualInputPlan"]["scope"] == "full_page_retry"
    attempts = result.raw_output_json["visualInputAttempts"]
    assert attempts[0]["useful"] is False
    assert attempts[1]["useful"] is True
    assert result.metadata["visualInputPlan"]["scope"] == "full_page_retry"
    assert result.metadata["visualInputAttempts"] == attempts


def test_usefulness_requires_claims_when_region_envelope_is_present() -> None:
    source, element_id = _source_with_geometry()
    task = _line_item_task(source, element_id=element_id)
    envelope = RegionExtractionEnvelope(
        document_id=str(source.document_id),
        semantic_region_id=str(task.region_id),
        resolved_document_type="invoice",
        semantic_type="invoice_line_item_table",
        target_schema="invoice",
        model_output_schema_name="granite_invoice_line_items.v1",
    )

    assert (
        is_useful_granite_output(
            normalized_json={
                "line_items": [
                    {
                        "description": "Looks like a row but has no anchored Claim",
                        "amount": {"amount": 250.0, "currency": "USD"},
                    }
                ]
            },
            normalization_json={
                "regionEnvelope": envelope.model_dump(mode="json", exclude_none=True)
            },
            semantic_task=task,
        )
        is False
    )


def test_planned_crop_evidence_records_visual_bbox(monkeypatch) -> None:
    monkeypatch.setenv("STRUCTURA_GRANITE_VISUAL_INPUT_MODE", "planned")
    source, element_id = _source_with_geometry()
    task = _line_item_task(source, element_id=element_id)
    client = SequencedVisionClient(
        payloads=[
            _invoice_line_items_payload([{"description": "600 mile service", "amount": 250.0}]),
        ]
    )

    result = GraniteVisionExtractionGateway(client=client).extract(
        source,
        schema_name="invoice",
        route_profile="docling_plus_granite_structured",
        semantic_task=task,
    )

    evidence = result.normalized_json["line_items"][0]["evidence"][0]
    assert evidence["visual_input_scope"] == "expanded_crop"
    assert evidence["bbox"]
    assert evidence["bbox_basis"] == "pdf_points"
    assert evidence["semantic_region_id"] == str(task.region_id)


def _source_with_geometry(
    *,
    width_px: int = 1200,
    height_px: int = 1600,
    bbox: list[float] | None = None,
    rotation_degrees: int = 0,
    nonblank: bool = True,
    table_bbox: list[float] | None = None,
) -> tuple[ExtractionSourceDocument, UUID]:
    page_id = uuid4()
    element_id = uuid4()
    image_bytes = _image_bytes(width_px=width_px, height_px=height_px, nonblank=nonblank)
    return (
        ExtractionSourceDocument(
            document_id=uuid4(),
            household_id=uuid4(),
            title="Invoice",
            original_filename="invoice.pdf",
            mime_type="application/pdf",
            family="invoice",
            subtype=None,
            sensitivity="normal",
            document_date=None,
            counterparty_display=None,
            primary_folder_id=None,
            metadata={},
            pages=[
                ParsedPageText(
                    page_id=page_id,
                    page_number=1,
                    text="Invoice service line",
                    image_bytes=image_bytes,
                    image_mime_type="image/png",
                    image_sha256=hashlib.sha256(image_bytes).hexdigest(),
                    width_points=600,
                    height_points=800,
                    rotation_degrees=rotation_degrees,
                )
            ],
            elements=[
                ParsedElementText(
                    element_id=element_id,
                    page_number=1,
                    ordinal=1,
                    text="600 mile service $250",
                    bbox=bbox or [100, 200, 500, 420],
                    metadata={"bbox_basis": "pdf_points"},
                )
            ],
            tables=[
                ParsedTableText(
                    table_id=uuid4(),
                    page_number=1,
                    table_index=1,
                    table_markdown="600 mile service | $250",
                    element_id=None if table_bbox else element_id,
                    bbox=table_bbox,
                    metadata={"bbox_basis": "pdf_points"} if table_bbox else {},
                )
            ],
        ),
        element_id,
    )


def _line_item_task(
    source: ExtractionSourceDocument,
    *,
    element_id: UUID,
    metadata: dict[str, object] | None = None,
) -> SemanticExtractionTask:
    return SemanticExtractionTask(
        region_id=uuid4(),
        annotation_id=uuid4(),
        document_id=source.document_id,
        semantic_type="invoice_line_item_table",
        granite_task="tables_json",
        target_schema="invoice",
        expected_fields=("line_items",),
        grounding=SemanticGroundingRef(kind="element", element_id=element_id),
        metadata=metadata or {},
    )


def _image_bytes(*, width_px: int, height_px: int, nonblank: bool = True) -> bytes:
    image = Image.new("RGB", (width_px, height_px), "white")
    draw = ImageDraw.Draw(image)
    if nonblank:
        draw.rectangle(
            (180, 360, min(width_px - 40, 1100), min(height_px - 40, 900)),
            fill="black",
        )
    output = BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()

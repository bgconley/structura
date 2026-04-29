from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from uuid import UUID, uuid4

import pytest

from lib.contracts.registry import ContractRegistry
from lib.extraction.models import ExtractionSourceDocument, ParsedPageText
from lib.semantic_annotations.models import (
    DocumentSemanticManifest,
    PageSemanticAnnotation,
    SemanticAnnotationResult,
    SemanticGroundingRef,
    SemanticRegionAnnotation,
)
from lib.semantic_annotations.repository import PersistedSemanticManifest
from lib.semantic_annotations.service import (
    SemanticAnnotationService,
    SemanticAnnotationServiceError,
)


def test_semantic_service_persists_manifest_and_queues_grounded_granite_jobs() -> None:
    document_id = uuid4()
    household_id = uuid4()
    page_id = uuid4()
    annotation_id = uuid4()
    region_id = uuid4()
    source = _source(document_id=document_id, household_id=household_id, page_id=page_id)
    manifest = _manifest(document_id=document_id, household_id=household_id, page_id=page_id)
    jobs = RecordingJobs()

    result = SemanticAnnotationService(
        source_loader=lambda loaded_document_id: source,
        gateway=StaticGateway(manifest),
        manifest_persister=lambda persisted_manifest: PersistedSemanticManifest(
            annotation_id=annotation_id,
            region_ids=(region_id,),
        ),
        jobs=jobs,
    ).annotate_document(document_id, quality_mode="smart", requested_by="system")

    assert result.annotation_id == annotation_id
    assert result.queued_granite_job_ids == (jobs.created_job_id,)
    assert jobs.created[0]["job_type"] == "extract"
    assert jobs.created[0]["queue_name"] == "extraction"
    payload = jobs.created[0]["payload"]
    ContractRegistry.load("contracts").validate_event_instance(
        "extract_document_job.v1.schema.json",
        payload,
    )
    assert payload["job_id"] == str(jobs.created_job_id)
    assert payload["attempt"] == 1
    assert 1 <= payload["priority"] <= 10
    assert payload["route_profile"] == "docling_plus_granite_structured"
    assert payload["target_schema_name"] == "invoice"
    assert payload["semantic_annotation_id"] == str(annotation_id)
    assert payload["semantic_region_id"] == str(region_id)
    assert payload["semantic_granite_task"] == "tables_json"
    assert payload["semantic_expected_fields"] == ["line_items", "total_amount"]
    assert payload["semantic_quality_mode"] == "smart"
    assert payload["allow_8b_rescue"] is False


def test_semantic_service_propagates_explicit_rescue_permission_to_granite_jobs() -> None:
    document_id = uuid4()
    household_id = uuid4()
    page_id = uuid4()
    annotation_id = uuid4()
    region_id = uuid4()
    user_id = uuid4()
    source = _source(document_id=document_id, household_id=household_id, page_id=page_id)
    manifest = _manifest(document_id=document_id, household_id=household_id, page_id=page_id)
    jobs = RecordingJobs()

    SemanticAnnotationService(
        source_loader=lambda loaded_document_id: source,
        gateway=StaticGateway(manifest),
        manifest_persister=lambda persisted_manifest: PersistedSemanticManifest(
            annotation_id=annotation_id,
            region_ids=(region_id,),
        ),
        jobs=jobs,
    ).annotate_document(
        document_id,
        quality_mode="smart",
        requested_by="user",
        allow_8b_rescue=True,
        requested_by_user_id=user_id,
        user_intent_reason="User allowed one 8B rescue.",
    )

    payload = jobs.created[0]["payload"]
    assert payload["semantic_quality_mode"] == "smart"
    assert payload["allow_8b_rescue"] is True
    assert payload["requested_by_user_id"] == str(user_id)
    assert payload["user_intent_reason"] == "User allowed one 8B rescue."


def test_semantic_service_does_not_queue_ignored_or_unmatched_regions() -> None:
    document_id = uuid4()
    household_id = uuid4()
    page_id = uuid4()
    annotation_id = uuid4()
    source = _source(document_id=document_id, household_id=household_id, page_id=page_id)
    manifest = _manifest(
        document_id=document_id,
        household_id=household_id,
        page_id=page_id,
        granite_task="ignore",
    )
    jobs = RecordingJobs()

    result = SemanticAnnotationService(
        source_loader=lambda loaded_document_id: source,
        gateway=StaticGateway(manifest),
        manifest_persister=lambda persisted_manifest: PersistedSemanticManifest(
            annotation_id=annotation_id,
            region_ids=(uuid4(),),
        ),
        jobs=jobs,
    ).annotate_document(document_id, quality_mode="smart", requested_by="system")

    assert result.queued_granite_job_ids == ()
    assert jobs.created == []


def test_semantic_service_caps_high_quality_granite_fanout() -> None:
    document_id = uuid4()
    household_id = uuid4()
    page_id = uuid4()
    annotation_id = uuid4()
    region_ids = tuple(uuid4() for _ in range(12))
    source = _source(document_id=document_id, household_id=household_id, page_id=page_id)
    manifest = _manifest(
        document_id=document_id,
        household_id=household_id,
        page_id=page_id,
        quality_mode="high_quality",
        region_count=12,
    )
    jobs = RecordingJobs()

    result = SemanticAnnotationService(
        source_loader=lambda loaded_document_id: source,
        gateway=StaticGateway(manifest),
        manifest_persister=lambda persisted_manifest: PersistedSemanticManifest(
            annotation_id=annotation_id,
            region_ids=region_ids,
        ),
        jobs=jobs,
    ).annotate_document(document_id, quality_mode="high_quality", requested_by="user")

    assert len(jobs.created) == 8
    assert len(result.queued_granite_job_ids) == 8
    assert (
        [
            job["payload"]["semantic_region_id"]  # type: ignore[index]
            for job in jobs.created
        ]
        == [str(region_id) for region_id in region_ids[:8]]
    )


def test_semantic_service_caps_rescue_granite_fanout_to_single_retry() -> None:
    document_id = uuid4()
    household_id = uuid4()
    page_id = uuid4()
    annotation_id = uuid4()
    region_ids = tuple(uuid4() for _ in range(6))
    source = _source(document_id=document_id, household_id=household_id, page_id=page_id)
    manifest = _manifest(
        document_id=document_id,
        household_id=household_id,
        page_id=page_id,
        quality_mode="rescue",
        region_count=6,
    )
    jobs = RecordingJobs()

    result = SemanticAnnotationService(
        source_loader=lambda loaded_document_id: source,
        gateway=StaticGateway(manifest),
        manifest_persister=lambda persisted_manifest: PersistedSemanticManifest(
            annotation_id=annotation_id,
            region_ids=region_ids,
        ),
        jobs=jobs,
    ).annotate_document(
        document_id,
        quality_mode="rescue",
        requested_by="user",
        allow_8b_rescue=True,
        user_intent_reason="User allowed one 8B rescue.",
    )

    assert len(jobs.created) == 1
    assert result.queued_granite_job_ids == (jobs.created_job_id,)
    assert jobs.created[0]["payload"]["semantic_rescue"] is True  # type: ignore[index]


def test_semantic_service_rejects_rescue_without_persisted_permission() -> None:
    document_id = uuid4()

    with pytest.raises(SemanticAnnotationServiceError, match="persisted user permission"):
        SemanticAnnotationService(
            source_loader=lambda loaded_document_id: _source(
                document_id=loaded_document_id,
                household_id=uuid4(),
                page_id=uuid4(),
            ),
            gateway=StaticGateway(
                _manifest(
                    document_id=document_id,
                    household_id=uuid4(),
                    page_id=uuid4(),
                    quality_mode="rescue",
                )
            ),
        ).annotate_document(document_id, quality_mode="rescue", requested_by="system")


class StaticGateway:
    def __init__(self, manifest: DocumentSemanticManifest) -> None:
        self.manifest = manifest

    def annotate(
        self,
        source: ExtractionSourceDocument,
        *,
        quality_mode: str,
    ) -> SemanticAnnotationResult:
        assert source.document_id == self.manifest.document_id
        assert quality_mode == self.manifest.quality_mode
        return SemanticAnnotationResult(manifest=self.manifest)


class RecordingJobs:
    def __init__(self) -> None:
        self.created: list[dict[str, Any]] = []
        self.created_job_id = uuid4()

    def create_job(self, **kwargs: object) -> SimpleNamespace:
        if "job_id" in kwargs:
            self.created_job_id = kwargs["job_id"]  # type: ignore[assignment]
        self.created.append(kwargs)
        return SimpleNamespace(job_id=self.created_job_id)


def _source(
    *,
    document_id: UUID,
    household_id: UUID,
    page_id: UUID,
) -> ExtractionSourceDocument:
    return ExtractionSourceDocument(
        document_id=document_id,
        household_id=household_id,
        title="Invoice",
        original_filename="invoice.pdf",
        mime_type="application/pdf",
        family="invoice",
        subtype=None,
        sensitivity="standard",
        document_date=None,
        counterparty_display=None,
        primary_folder_id=None,
        metadata={},
        pages=[
            ParsedPageText(
                page_id=page_id,
                page_number=1,
                text="Invoice line items",
                image_bytes=b"fake-image",
                image_mime_type="image/png",
                image_sha256="c" * 64,
            )
        ],
        elements=[],
        tables=[],
    )


def _manifest(
    *,
    document_id: UUID,
    household_id: UUID,
    page_id: UUID,
    granite_task: str = "tables_json",
    quality_mode: str = "smart",
    region_count: int = 1,
) -> DocumentSemanticManifest:
    def expected_fields(index: int) -> tuple[str, ...]:
        if region_count == 1:
            return ("line_items", "total_amount")
        return ("line_items", "total_amount", f"field_{index}")

    regions = [
        SemanticRegionAnnotation(
            semantic_type="invoice_line_item_table",
            priority="high",
            granite_task=granite_task,
            target_schema="invoice",
            expected_fields=expected_fields(index),
            grounding=SemanticGroundingRef(kind="page", page_id=page_id),
            confidence=0.9,
        )
        for index in range(region_count)
    ]
    return DocumentSemanticManifest(
        document_id=document_id,
        household_id=household_id,
        quality_mode=quality_mode,  # type: ignore[arg-type]
        profile_name="qwen3-vl-2b-semantic:v1",
        source_engine="qwen3_vl_2b",
        model_name="Qwen/Qwen3-VL-2B-Instruct",
        model_version="v1",
        prompt_version="phase8_5-semantic-smart-v1",
        pages=[
            PageSemanticAnnotation(
                page_id=page_id,
                page_number=1,
                page_role="invoice_summary",
                has_structured_targets=True,
            )
        ],
        regions=regions,
        confidence={"overall": 0.9},
        manifest={"document_type": "invoice"},
        input_page_hashes=("c" * 64,),
    )

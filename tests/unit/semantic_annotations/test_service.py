from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from uuid import UUID, uuid4

import pytest

from lib.contracts.registry import ContractRegistry
from lib.extraction.models import ExtractionSourceDocument, ParsedPageText, ParsedTableText
from lib.model_runtime.reliability_versions import REGION_ENVELOPE_VERSION
from lib.semantic_annotations.docling_targets import DOCLING_STRUCTURAL_REGION_SOURCE
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
    _granite_extraction_plan,
)


def test_semantic_service_persists_manifest_and_queues_grounded_granite_jobs() -> None:
    document_id = uuid4()
    household_id = uuid4()
    page_id = uuid4()
    annotation_id = uuid4()
    region_id = uuid4()
    source = _source(
        document_id=document_id,
        household_id=household_id,
        page_id=page_id,
        metadata={"hints": {"runId": "phase85-20260604-smoke-001"}},
    )
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
    assert payload["model_output_schema_name"] == "granite_invoice_line_items.v1"
    assert payload["canonical_target_schema"] == "invoice"
    assert payload["compatibility_mode"] == "exact"
    assert payload["extractor_backend"] == "granite_region"
    assert payload["contract_resolution_reason"] == "exact_contract"
    assert payload["region_envelope_version"] == REGION_ENVELOPE_VERSION
    assert payload["semantic_quality_mode"] == "smart"
    assert "allow_8b_rescue" not in payload
    assert "semantic_rescue" not in payload
    assert payload["metadata"]["run_id"] == "phase85-20260604-smoke-001"


def test_semantic_service_rejects_removed_rescue_permission() -> None:
    document_id = uuid4()
    household_id = uuid4()
    page_id = uuid4()
    annotation_id = uuid4()
    user_id = uuid4()
    source = _source(document_id=document_id, household_id=household_id, page_id=page_id)
    manifest = _manifest(document_id=document_id, household_id=household_id, page_id=page_id)
    jobs = RecordingJobs()

    with pytest.raises(SemanticAnnotationServiceError, match="removed"):
        SemanticAnnotationService(
            source_loader=lambda loaded_document_id: source,
            gateway=StaticGateway(manifest),
            manifest_persister=lambda persisted_manifest: _persist_dynamic_manifest(
                persisted_manifest,
                annotation_id=annotation_id,
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

    assert jobs.created == []


def test_semantic_service_prefers_document_family_over_region_target_schema() -> None:
    document_id = uuid4()
    household_id = uuid4()
    page_id = uuid4()
    annotation_id = uuid4()
    source = _source(document_id=document_id, household_id=household_id, page_id=page_id)
    manifest = _manifest(
        document_id=document_id,
        household_id=household_id,
        page_id=page_id,
        target_schema="medical_eob",
    )
    jobs = RecordingJobs()

    SemanticAnnotationService(
        source_loader=lambda loaded_document_id: source,
        gateway=StaticGateway(manifest),
        manifest_persister=lambda persisted_manifest: _persist_dynamic_manifest(
            persisted_manifest,
            annotation_id=annotation_id,
        ),
        jobs=jobs,
    ).annotate_document(document_id, quality_mode="smart", requested_by="system")

    payload = jobs.created[0]["payload"]
    assert payload["target_schema_name"] == "invoice"


def test_semantic_service_corrects_line_item_table_task_before_enqueue() -> None:
    document_id = uuid4()
    household_id = uuid4()
    page_id = uuid4()
    annotation_id = uuid4()
    source = _source(document_id=document_id, household_id=household_id, page_id=page_id)
    manifest = _manifest(
        document_id=document_id,
        household_id=household_id,
        page_id=page_id,
        granite_task="kvp",
        semantic_type="invoice_line_item_table",
        target_schema="invoice",
    )
    jobs = RecordingJobs()

    SemanticAnnotationService(
        source_loader=lambda loaded_document_id: source,
        gateway=StaticGateway(manifest),
        manifest_persister=lambda persisted_manifest: _persist_dynamic_manifest(
            persisted_manifest,
            annotation_id=annotation_id,
        ),
        jobs=jobs,
    ).annotate_document(document_id, quality_mode="smart", requested_by="system")

    payload = jobs.created[0]["payload"]
    assert payload["semantic_granite_task"] == "tables_json"
    assert payload["metadata"]["semantic_task_repair"] == {
        "original_granite_task": "kvp",
        "repaired_granite_task": "tables_json",
        "reason": "line_item_semantic_type_requires_table_task",
    }


def test_semantic_service_uses_qwen_document_type_before_phase4_family() -> None:
    document_id = uuid4()
    household_id = uuid4()
    page_id = uuid4()
    annotation_id = uuid4()
    source = _source(
        document_id=document_id,
        household_id=household_id,
        page_id=page_id,
        family="medical_eob",
        text="Receipt subtotal tax paid amount paid",
        metadata={"phase4": {"classification": {"family": "medical_eob"}}},
    )
    manifest = _manifest(
        document_id=document_id,
        household_id=household_id,
        page_id=page_id,
        semantic_type="payment_summary",
        target_schema="medical_eob",
        document_type="receipt",
    )
    jobs = RecordingJobs()

    SemanticAnnotationService(
        source_loader=lambda loaded_document_id: source,
        gateway=StaticGateway(manifest),
        manifest_persister=lambda persisted_manifest: _persist_dynamic_manifest(
            persisted_manifest,
            annotation_id=annotation_id,
        ),
        jobs=jobs,
    ).annotate_document(document_id, quality_mode="smart", requested_by="system")

    payload = jobs.created[0]["payload"]
    assert payload["target_schema_name"] == "receipt"
    assert payload["metadata"]["schema_fit"]["requested_target_schema"] == "receipt"


def test_semantic_service_blocks_incompatible_qwen_region_target_before_granite() -> None:
    document_id = uuid4()
    household_id = uuid4()
    page_id = uuid4()
    annotation_id = uuid4()
    source = _source(
        document_id=document_id,
        household_id=household_id,
        page_id=page_id,
        family="generic",
        text="Coverage decision denied medical necessity appeal rights member ID",
    )
    manifest = _manifest(
        document_id=document_id,
        household_id=household_id,
        page_id=page_id,
        semantic_type="receipt_line_item_table",
        target_schema="receipt",
        document_type="healthcare_coverage_decision",
    )
    jobs = RecordingJobs()

    SemanticAnnotationService(
        source_loader=lambda loaded_document_id: source,
        gateway=StaticGateway(manifest),
        manifest_persister=lambda persisted_manifest: _persist_dynamic_manifest(
            persisted_manifest,
            annotation_id=annotation_id,
        ),
        jobs=jobs,
    ).annotate_document(document_id, quality_mode="smart", requested_by="system")

    assert jobs.created == []


def test_semantic_service_uses_semantic_type_before_unclassified_family() -> None:
    document_id = uuid4()
    household_id = uuid4()
    page_id = uuid4()
    annotation_id = uuid4()
    source = _source(
        document_id=document_id,
        household_id=household_id,
        page_id=page_id,
        family="medical_eob",
    )
    manifest = _manifest(
        document_id=document_id,
        household_id=household_id,
        page_id=page_id,
        target_schema="medical_eob",
    )
    jobs = RecordingJobs()

    SemanticAnnotationService(
        source_loader=lambda loaded_document_id: source,
        gateway=StaticGateway(manifest),
        manifest_persister=lambda persisted_manifest: _persist_dynamic_manifest(
            persisted_manifest,
            annotation_id=annotation_id,
        ),
        jobs=jobs,
    ).annotate_document(document_id, quality_mode="smart", requested_by="system")

    payload = jobs.created[0]["payload"]
    assert payload["target_schema_name"] == "invoice"


def test_semantic_service_prefers_docling_observation_over_unanchored_eob_guess() -> None:
    document_id = uuid4()
    household_id = uuid4()
    page_id = uuid4()
    annotation_id = uuid4()
    source = _source(
        document_id=document_id,
        household_id=household_id,
        page_id=page_id,
        family="unknown",
        text="UWM escrow shortage statement and mortgage escrow account analysis",
    )
    manifest = _manifest(
        document_id=document_id,
        household_id=household_id,
        page_id=page_id,
        semantic_type="covered_services_line_item_table",
        target_schema="medical_eob",
        document_type="medical_eob",
    )
    jobs = RecordingJobs()

    SemanticAnnotationService(
        source_loader=lambda loaded_document_id: source,
        gateway=StaticGateway(manifest),
        manifest_persister=lambda persisted_manifest: _persist_dynamic_manifest(
            persisted_manifest,
            annotation_id=annotation_id,
        ),
        jobs=jobs,
    ).annotate_document(document_id, quality_mode="smart", requested_by="system")

    payload = jobs.created[0]["payload"]
    assert payload["target_schema_name"] == "document_observation"
    assert payload["semantic_type"] == "escrow_summary"
    assert payload["metadata"]["schema_fit"]["requested_target_schema"] == "document_observation"
    assert payload["metadata"]["schema_fit"]["reason"] == "observation_schema"
    assert payload["metadata"]["docling_structural_target"]["family"] == (
        "mortgage_escrow_statement"
    )


def test_semantic_service_prefers_docling_title_observation_over_weak_receipt_guess() -> None:
    document_id = uuid4()
    household_id = uuid4()
    page_id = uuid4()
    annotation_id = uuid4()
    source = _source(
        document_id=document_id,
        household_id=household_id,
        page_id=page_id,
        family="receipt",
        text=(
            "Phenix Title Seller Information Form seller proceeds payment "
            "instructions and title company wiring details"
        ),
    )
    manifest = _manifest(
        document_id=document_id,
        household_id=household_id,
        page_id=page_id,
        granite_task="kvp",
        semantic_type="receipt_line_item_table",
        target_schema="receipt",
        document_type="receipt",
    )
    jobs = RecordingJobs()

    SemanticAnnotationService(
        source_loader=lambda loaded_document_id: source,
        gateway=StaticGateway(manifest),
        manifest_persister=lambda persisted_manifest: _persist_dynamic_manifest(
            persisted_manifest,
            annotation_id=annotation_id,
        ),
        jobs=jobs,
    ).annotate_document(document_id, quality_mode="smart", requested_by="system")

    payload = jobs.created[0]["payload"]
    assert payload["target_schema_name"] == "document_observation"
    assert payload["semantic_type"] == "seller_information_block"
    assert payload["metadata"]["schema_fit"]["requested_target_schema"] == "document_observation"
    assert payload["metadata"]["schema_fit"]["reason"] == "observation_schema"
    assert payload["metadata"]["docling_structural_target"]["family"] == "real_estate_title"


def test_semantic_service_uses_docling_service_record_targets_when_qwen_emits_no_regions() -> None:
    document_id = uuid4()
    household_id = uuid4()
    page_id = uuid4()
    table_id = uuid4()
    annotation_id = uuid4()
    source = _source(
        document_id=document_id,
        household_id=household_id,
        page_id=page_id,
        family="generic",
        title="BMW CE-04 run in service",
        original_filename="bmw-service.pdf",
        text=(
            "Repair order service labor parts VIN mileage motorcycle "
            "payment received service advisor"
        ),
        tables=[
            ParsedTableText(
                table_id=table_id,
                page_number=1,
                table_index=1,
                table_markdown=(
                    "| Operation | Description | Qty | Amount |\n"
                    "| Run-in service | Labor and parts | 1 | 301.00 |"
                ),
            )
        ],
    )
    manifest = _manifest_with_regions(
        document_id=document_id,
        household_id=household_id,
        page_id=page_id,
        regions=[],
        document_type="generic_form",
    )
    jobs = RecordingJobs()
    persisted_manifests: list[DocumentSemanticManifest] = []

    SemanticAnnotationService(
        source_loader=lambda loaded_document_id: source,
        gateway=StaticGateway(manifest),
        manifest_persister=lambda persisted_manifest: _persist_dynamic_manifest(
            persisted_manifest,
            annotation_id=annotation_id,
            captured=persisted_manifests,
        ),
        jobs=jobs,
    ).annotate_document(document_id, quality_mode="smart", requested_by="system")

    assert len(persisted_manifests) == 1
    persisted_regions = persisted_manifests[0].regions
    assert [region.semantic_type for region in persisted_regions] == [
        "service_record_line_item_table"
    ]
    assert persisted_regions[0].grounding.kind == "table"
    assert persisted_regions[0].grounding.page_id == page_id
    assert persisted_regions[0].grounding.table_id == table_id
    ContractRegistry.load("contracts").validate_schema_instance(
        "semantic_annotation_manifest.v1.schema.json",
        persisted_manifests[0].manifest,
    )

    assert len(jobs.created) == 1
    payload = jobs.created[0]["payload"]
    assert payload["target_schema_name"] == "receipt"
    assert payload["semantic_type"] == "service_record_line_item_table"
    assert payload["semantic_granite_task"] == "tables_json"
    assert payload["model_output_schema_name"] == "granite_service_record_line_items.v1"
    assert payload["canonical_target_schema"] == "service_record"
    assert payload["compatibility_mode"] == "exact"
    assert payload["metadata"]["region_source"] == "docling_structural"


def test_semantic_service_suppresses_weak_docling_table_duplicate_when_qwen_has_type() -> None:
    document_id = uuid4()
    household_id = uuid4()
    page_id = uuid4()
    table_id = uuid4()
    annotation_id = uuid4()
    source = _source(
        document_id=document_id,
        household_id=household_id,
        page_id=page_id,
        family="generic",
        title="BH Photo order",
        original_filename="BH Photo desktop tripod order.pdf",
        text="BH Photo order number ship to item sku quantity",
        tables=[
            ParsedTableText(
                table_id=table_id,
                page_number=1,
                table_index=1,
                table_markdown="| item | total |",
            )
        ],
    )
    manifest = _manifest_with_regions(
        document_id=document_id,
        household_id=household_id,
        page_id=page_id,
        document_type="generic_form",
        regions=[
            SemanticRegionAnnotation(
                semantic_type="retail_order_line_item_table",
                priority="high",
                granite_task="tables_json",
                target_schema="receipt",
                expected_fields=("item_description", "quantity", "line_total"),
                grounding=SemanticGroundingRef(kind="page", page_id=page_id),
                confidence=0.9,
            )
        ],
    )
    jobs = RecordingJobs()

    SemanticAnnotationService(
        source_loader=lambda loaded_document_id: source,
        gateway=StaticGateway(manifest),
        manifest_persister=lambda persisted_manifest: _persist_dynamic_manifest(
            persisted_manifest,
            annotation_id=annotation_id,
        ),
        jobs=jobs,
    ).annotate_document(document_id, quality_mode="smart", requested_by="system")

    payloads = [job["payload"] for job in jobs.created]
    assert len(payloads) == 1
    assert payloads[0]["semantic_type"] == "retail_order_line_item_table"
    assert payloads[0]["metadata"].get("region_source") != "docling_structural"


def test_semantic_service_dedupes_duplicate_page_kvp_regions_before_persistence() -> None:
    document_id = uuid4()
    household_id = uuid4()
    page_id = uuid4()
    annotation_id = uuid4()
    source = _source(
        document_id=document_id,
        household_id=household_id,
        page_id=page_id,
        family="medical_eob",
        title="Anthem denial",
        text="Explanation of benefits claim patient responsibility denial appeal",
    )
    manifest = _manifest_with_regions(
        document_id=document_id,
        household_id=household_id,
        page_id=page_id,
        document_type="medical_eob",
        regions=[
            SemanticRegionAnnotation(
                semantic_type="denial_or_coverage_decision",
                priority="high",
                granite_task="kvp",
                target_schema="medical_eob",
                expected_fields=("request_status", "denial_reason"),
                grounding=SemanticGroundingRef(kind="page", page_id=page_id),
                review_required=True,
                confidence=0.72,
            ),
            SemanticRegionAnnotation(
                semantic_type="denial_or_coverage_decision",
                priority="high",
                granite_task="kvp",
                target_schema="medical_eob",
                expected_fields=("appeal_deadline", "denial_reason"),
                grounding=SemanticGroundingRef(kind="page", page_id=page_id),
                review_required=True,
                confidence=0.66,
            ),
        ],
    )
    jobs = RecordingJobs()
    persisted_manifests: list[DocumentSemanticManifest] = []

    SemanticAnnotationService(
        source_loader=lambda loaded_document_id: source,
        gateway=StaticGateway(manifest),
        manifest_persister=lambda persisted_manifest: _persist_dynamic_manifest(
            persisted_manifest,
            annotation_id=annotation_id,
            captured=persisted_manifests,
        ),
        jobs=jobs,
    ).annotate_document(document_id, quality_mode="smart", requested_by="system")

    persisted_regions = persisted_manifests[0].regions
    assert len(persisted_regions) == 1
    assert persisted_regions[0].semantic_type == "denial_or_coverage_decision"
    assert persisted_regions[0].expected_fields == (
        "appeal_deadline",
        "denial_reason",
        "request_status",
    )
    assert len(jobs.created) == 1


def test_semantic_service_dedupes_element_grounded_page_kvp_regions_before_persistence() -> None:
    document_id = uuid4()
    household_id = uuid4()
    page_id = uuid4()
    annotation_id = uuid4()
    source = _source(
        document_id=document_id,
        household_id=household_id,
        page_id=page_id,
        family="receipt",
        title="Restaurant receipt",
        text="Restaurant receipt subtotal tax tip total amount paid visa payment approval",
    )
    manifest = _manifest_with_regions(
        document_id=document_id,
        household_id=household_id,
        page_id=page_id,
        document_type="receipt",
        regions=[
            SemanticRegionAnnotation(
                semantic_type="receipt_payment_summary",
                priority="high",
                granite_task="kvp",
                target_schema="receipt",
                expected_fields=("subtotal", "tax", "total_amount"),
                grounding=SemanticGroundingRef(
                    kind="element",
                    page_id=page_id,
                    element_id=uuid4(),
                ),
                review_required=True,
                confidence=0.75,
            ),
            SemanticRegionAnnotation(
                semantic_type="receipt_payment_summary",
                priority="high",
                granite_task="kvp",
                target_schema="receipt",
                expected_fields=("payment_method", "tip", "total_amount"),
                grounding=SemanticGroundingRef(
                    kind="element",
                    page_id=page_id,
                    element_id=uuid4(),
                ),
                review_required=True,
                confidence=0.71,
            ),
        ],
    )
    jobs = RecordingJobs()
    persisted_manifests: list[DocumentSemanticManifest] = []

    SemanticAnnotationService(
        source_loader=lambda loaded_document_id: source,
        gateway=StaticGateway(manifest),
        manifest_persister=lambda persisted_manifest: _persist_dynamic_manifest(
            persisted_manifest,
            annotation_id=annotation_id,
            captured=persisted_manifests,
        ),
        jobs=jobs,
    ).annotate_document(document_id, quality_mode="smart", requested_by="system")

    persisted_regions = persisted_manifests[0].regions
    assert len(persisted_regions) == 1
    assert persisted_regions[0].semantic_type == "receipt_payment_summary"
    assert persisted_regions[0].grounding.kind == "page"
    assert persisted_regions[0].grounding.page_id == page_id
    assert persisted_regions[0].expected_fields == (
        "payment_method",
        "subtotal",
        "tax",
        "tip",
        "total_amount",
    )
    assert len(jobs.created) == 1


def test_semantic_service_preserves_generic_kvp_type_for_medical_eob_pages() -> None:
    document_id = uuid4()
    household_id = uuid4()
    page_id = uuid4()
    annotation_id = uuid4()
    source = _source(
        document_id=document_id,
        household_id=household_id,
        page_id=page_id,
        family="medical_eob",
        title="Anthem denial",
        text="Explanation of benefits claim denied appeal grievance rights deadline",
    )
    manifest = _manifest_with_regions(
        document_id=document_id,
        household_id=household_id,
        page_id=page_id,
        document_type="medical_eob",
        regions=[
            SemanticRegionAnnotation(
                semantic_type="generic_form_kvp",
                priority="high",
                granite_task="kvp",
                target_schema="medical_eob",
                expected_fields=("appeal_deadline", "grievance_rights"),
                grounding=SemanticGroundingRef(
                    kind="element",
                    page_id=page_id,
                    element_id=uuid4(),
                ),
                review_required=True,
                confidence=0.69,
            )
        ],
    )
    jobs = RecordingJobs()
    persisted_manifests: list[DocumentSemanticManifest] = []

    SemanticAnnotationService(
        source_loader=lambda loaded_document_id: source,
        gateway=StaticGateway(manifest),
        manifest_persister=lambda persisted_manifest: _persist_dynamic_manifest(
            persisted_manifest,
            annotation_id=annotation_id,
            captured=persisted_manifests,
        ),
        jobs=jobs,
    ).annotate_document(document_id, quality_mode="smart", requested_by="system")

    persisted_region = persisted_manifests[0].regions[0]
    # Family heuristics may not rewrite the model's semantic type; only the
    # structural page-scoped KVP grounding repair applies.
    assert persisted_region.semantic_type == "generic_form_kvp"
    assert persisted_region.grounding.kind == "page"
    assert jobs.created[0]["payload"]["semantic_type"] == "generic_form_kvp"


def test_semantic_service_drops_unanchored_observation_family_region() -> None:
    document_id = uuid4()
    household_id = uuid4()
    page_id = uuid4()
    annotation_id = uuid4()
    source = _source(
        document_id=document_id,
        household_id=household_id,
        page_id=page_id,
        family="generic",
        title="Low text scan",
        original_filename="Scan Apr 8, 2024 at 14.11.pdf",
        text="m xm",
    )
    manifest = _manifest_with_regions(
        document_id=document_id,
        household_id=household_id,
        page_id=page_id,
        document_type="generic_form",
        regions=[
            SemanticRegionAnnotation(
                semantic_type="escrow_summary",
                priority="high",
                granite_task="kvp",
                target_schema="document_observation",
                expected_fields=("loan_number", "escrow_shortage"),
                grounding=SemanticGroundingRef(kind="page", page_id=page_id),
                review_required=True,
                confidence=0.61,
            )
        ],
    )
    jobs = RecordingJobs()
    persisted_manifests: list[DocumentSemanticManifest] = []

    SemanticAnnotationService(
        source_loader=lambda loaded_document_id: source,
        gateway=StaticGateway(manifest),
        manifest_persister=lambda persisted_manifest: _persist_dynamic_manifest(
            persisted_manifest,
            annotation_id=annotation_id,
            captured=persisted_manifests,
        ),
        jobs=jobs,
    ).annotate_document(document_id, quality_mode="smart", requested_by="system")

    assert persisted_manifests[0].regions == []
    assert jobs.created == []


def test_semantic_service_drops_weak_observation_family_false_positive() -> None:
    document_id = uuid4()
    household_id = uuid4()
    page_id = uuid4()
    annotation_id = uuid4()
    source = _source(
        document_id=document_id,
        household_id=household_id,
        page_id=page_id,
        family="generic",
        title="Vehicle registration scan",
        text="seller owner vehicle registration fee amount paid",
    )
    manifest = _manifest_with_regions(
        document_id=document_id,
        household_id=household_id,
        page_id=page_id,
        document_type="generic_form",
        regions=[
            SemanticRegionAnnotation(
                semantic_type="seller_information_block",
                priority="high",
                granite_task="kvp",
                target_schema="document_observation",
                expected_fields=("seller_name", "property_address"),
                grounding=SemanticGroundingRef(
                    kind="element",
                    page_id=page_id,
                    element_id=uuid4(),
                ),
                review_required=True,
                confidence=0.67,
            )
        ],
    )
    jobs = RecordingJobs()
    persisted_manifests: list[DocumentSemanticManifest] = []

    SemanticAnnotationService(
        source_loader=lambda loaded_document_id: source,
        gateway=StaticGateway(manifest),
        manifest_persister=lambda persisted_manifest: _persist_dynamic_manifest(
            persisted_manifest,
            annotation_id=annotation_id,
            captured=persisted_manifests,
        ),
        jobs=jobs,
    ).annotate_document(document_id, quality_mode="smart", requested_by="system")

    assert persisted_manifests[0].regions == []
    assert jobs.created == []


def test_semantic_service_dedupes_supported_observation_family_by_page() -> None:
    document_id = uuid4()
    household_id = uuid4()
    page_id = uuid4()
    annotation_id = uuid4()
    source = _source(
        document_id=document_id,
        household_id=household_id,
        page_id=page_id,
        family="generic",
        title="Dispute form",
        text="dispute transaction charge unauthorized reason for dispute",
    )
    manifest = _manifest_with_regions(
        document_id=document_id,
        household_id=household_id,
        page_id=page_id,
        document_type="generic_form",
        regions=[
            SemanticRegionAnnotation(
                semantic_type="dispute_reason_block",
                priority="high",
                granite_task="kvp",
                target_schema="document_observation",
                expected_fields=("transaction_date", "merchant"),
                grounding=SemanticGroundingRef(
                    kind="element",
                    page_id=page_id,
                    element_id=uuid4(),
                ),
                review_required=True,
                confidence=0.77,
            ),
            SemanticRegionAnnotation(
                semantic_type="dispute_reason_block",
                priority="high",
                granite_task="kvp",
                target_schema="document_observation",
                expected_fields=("amount", "dispute_reason"),
                grounding=SemanticGroundingRef(
                    kind="element",
                    page_id=page_id,
                    element_id=uuid4(),
                ),
                review_required=True,
                confidence=0.74,
            ),
        ],
    )
    jobs = RecordingJobs()
    persisted_manifests: list[DocumentSemanticManifest] = []

    SemanticAnnotationService(
        source_loader=lambda loaded_document_id: source,
        gateway=StaticGateway(manifest),
        manifest_persister=lambda persisted_manifest: _persist_dynamic_manifest(
            persisted_manifest,
            annotation_id=annotation_id,
            captured=persisted_manifests,
        ),
        jobs=jobs,
    ).annotate_document(document_id, quality_mode="smart", requested_by="system")

    persisted_regions = persisted_manifests[0].regions
    assert len(persisted_regions) == 1
    assert persisted_regions[0].semantic_type == "dispute_reason_block"
    assert persisted_regions[0].grounding.kind == "page"
    assert persisted_regions[0].expected_fields == (
        "amount",
        "dispute_reason",
        "merchant",
        "transaction_date",
    )
    assert len(jobs.created) == 1


def test_semantic_service_routes_escrow_docling_tables_as_observations_not_receipts() -> None:
    document_id = uuid4()
    household_id = uuid4()
    page_id = uuid4()
    table_id = uuid4()
    annotation_id = uuid4()
    source = _source(
        document_id=document_id,
        household_id=household_id,
        page_id=page_id,
        family="generic",
        title="UWM Final Escrow Statement",
        original_filename="UWM Final Escrow Statement 4-29-24.pdf",
        text="UWM mortgage escrow shortage surplus paid payment tax statement",
        tables=[
            ParsedTableText(
                table_id=table_id,
                page_number=1,
                table_index=1,
                table_markdown=(
                    "| Escrow item | Amount |\n| Shortage | $120.00 |\n| New payment | $2,100.00 |"
                ),
            )
        ],
    )
    manifest = _manifest_with_regions(
        document_id=document_id,
        household_id=household_id,
        page_id=page_id,
        regions=[],
        document_type="mortgage_escrow_statement",
    )
    jobs = RecordingJobs()

    SemanticAnnotationService(
        source_loader=lambda loaded_document_id: source,
        gateway=StaticGateway(manifest),
        manifest_persister=lambda persisted_manifest: _persist_dynamic_manifest(
            persisted_manifest,
            annotation_id=annotation_id,
        ),
        jobs=jobs,
    ).annotate_document(document_id, quality_mode="smart", requested_by="system")

    assert len(jobs.created) == 2
    payloads = [job["payload"] for job in jobs.created]
    table_payload = next(
        payload for payload in payloads if payload["semantic_granite_task"] == "tables_json"
    )
    observation_payload = next(
        payload for payload in payloads if payload["semantic_granite_task"] == "kvp"
    )
    assert table_payload["target_schema_name"] == "document_observation"
    assert table_payload["semantic_type"] == "generic_form_kvp"
    assert table_payload["metadata"]["region_source"] == "docling_structural"
    assert table_payload["metadata"]["docling_structural_target"]["family"] == "generic_table"
    assert observation_payload["target_schema_name"] == "document_observation"
    assert observation_payload["semantic_type"] == "escrow_summary"
    assert observation_payload["metadata"]["docling_structural_target"]["source"] == (
        "docling_page_anchors"
    )


def test_semantic_service_replaces_qwen_table_escrow_summary_with_docling_targets() -> None:
    document_id = uuid4()
    household_id = uuid4()
    page_id = uuid4()
    table_id = uuid4()
    annotation_id = uuid4()
    source = _source(
        document_id=document_id,
        household_id=household_id,
        page_id=page_id,
        family="mortgage_escrow_statement",
        title="UWM Final Escrow Statement",
        original_filename="UWM Final Escrow Statement 4-29-24.pdf",
        text="UWM mortgage escrow shortage surplus paid payment tax statement",
        tables=[
            ParsedTableText(
                table_id=table_id,
                page_number=1,
                table_index=1,
                table_markdown=(
                    "| Date | Projected payment | Actual payment | Balance |\n"
                    "| 04/29/2024 | $175.73 | $175.73 | $0.04 |"
                ),
            )
        ],
    )
    manifest = _manifest_with_regions(
        document_id=document_id,
        household_id=household_id,
        page_id=page_id,
        regions=[
            SemanticRegionAnnotation(
                semantic_type="escrow_summary",
                priority="high",
                granite_task="tables_json",
                target_schema="document_observation",
                expected_fields=(
                    "date",
                    "projected_payment",
                    "actual_payment",
                    "actual_balance",
                ),
                grounding=SemanticGroundingRef(kind="table", page_id=page_id, table_id=table_id),
                review_required=False,
                confidence=0.98,
            )
        ],
        document_type="mortgage_escrow_statement",
    )
    jobs = RecordingJobs()
    persisted_manifests: list[DocumentSemanticManifest] = []

    SemanticAnnotationService(
        source_loader=lambda loaded_document_id: source,
        gateway=StaticGateway(manifest),
        manifest_persister=lambda persisted_manifest: _persist_dynamic_manifest(
            persisted_manifest,
            annotation_id=annotation_id,
            captured=persisted_manifests,
        ),
        jobs=jobs,
    ).annotate_document(document_id, quality_mode="smart", requested_by="system")

    persisted_signatures = [
        (region.semantic_type, region.granite_task, region.grounding.kind)
        for region in persisted_manifests[0].regions
    ]
    assert persisted_signatures == [
        ("generic_form_kvp", "tables_json", "table"),
        ("escrow_summary", "kvp", "page"),
    ]
    payloads = [job["payload"] for job in jobs.created]
    assert sorted(payload["semantic_type"] for payload in payloads) == [
        "escrow_summary",
        "generic_form_kvp",
    ]
    assert all(
        not (
            payload["semantic_type"] == "escrow_summary"
            and payload["semantic_granite_task"] == "tables_json"
        )
        for payload in payloads
    )


def test_semantic_service_caps_docling_table_fanout_with_page_summary() -> None:
    document_id = uuid4()
    household_id = uuid4()
    page_id = uuid4()
    table_ids = [uuid4() for _ in range(3)]
    annotation_id = uuid4()
    source = _source(
        document_id=document_id,
        household_id=household_id,
        page_id=page_id,
        family="generic",
        title="UWM Final Escrow Statement",
        original_filename="UWM Final Escrow Statement 4-29-24.pdf",
        text="UWM mortgage escrow shortage surplus paid payment tax statement",
        tables=[
            ParsedTableText(
                table_id=table_id,
                page_number=1,
                table_index=index + 1,
                table_markdown=(
                    "| Escrow item | Amount |\n| Shortage | $120.00 |\n| New payment | $2,100.00 |"
                ),
            )
            for index, table_id in enumerate(table_ids)
        ],
    )
    manifest = _manifest_with_regions(
        document_id=document_id,
        household_id=household_id,
        page_id=page_id,
        regions=[
            SemanticRegionAnnotation(
                semantic_type="escrow_summary",
                priority="high",
                granite_task="kvp",
                target_schema="document_observation",
                expected_fields=("loan_number", "payment_amount"),
                grounding=SemanticGroundingRef(kind="page", page_id=page_id),
                confidence=0.92,
            )
        ],
        document_type="mortgage_escrow_statement",
    )
    jobs = RecordingJobs()

    SemanticAnnotationService(
        source_loader=lambda loaded_document_id: source,
        gateway=StaticGateway(manifest),
        manifest_persister=lambda persisted_manifest: _persist_dynamic_manifest(
            persisted_manifest,
            annotation_id=annotation_id,
        ),
        jobs=jobs,
    ).annotate_document(document_id, quality_mode="smart", requested_by="system")

    payloads = [job["payload"] for job in jobs.created]
    assert len(payloads) == 3
    assert sum(payload["semantic_type"] == "escrow_summary" for payload in payloads) == 1
    assert sum(payload["semantic_type"] == "generic_form_kvp" for payload in payloads) == 2


def test_semantic_service_drops_incompatible_docling_structural_target() -> None:
    document_id = uuid4()
    household_id = uuid4()
    page_id = uuid4()
    table_id = uuid4()
    annotation_id = uuid4()
    source = _source(
        document_id=document_id,
        household_id=household_id,
        page_id=page_id,
        family="generic",
        text="receipt subtotal total paid merchant",
    )
    manifest = _manifest_with_regions(
        document_id=document_id,
        household_id=household_id,
        page_id=page_id,
        document_type="receipt",
        regions=[
            SemanticRegionAnnotation(
                semantic_type="invoice_line_item_table",
                priority="critical",
                granite_task="tables_json",
                target_schema="invoice",
                expected_fields=("line_items",),
                grounding=SemanticGroundingRef(kind="table", page_id=page_id, table_id=table_id),
                confidence=0.62,
                metadata={"region_source": DOCLING_STRUCTURAL_REGION_SOURCE},
            )
        ],
    )
    jobs = RecordingJobs()

    SemanticAnnotationService(
        source_loader=lambda loaded_document_id: source,
        gateway=StaticGateway(manifest),
        manifest_persister=lambda persisted_manifest: _persist_dynamic_manifest(
            persisted_manifest,
            annotation_id=annotation_id,
        ),
        jobs=jobs,
    ).annotate_document(document_id, quality_mode="smart", requested_by="system")

    payloads = [job["payload"] for job in jobs.created]
    assert all(payload["semantic_type"] != "invoice_line_item_table" for payload in payloads)
    # Structural-only normalization synthesizes nothing in its place.
    assert payloads == []


def test_semantic_service_uses_docling_observation_targets_when_qwen_emits_no_regions() -> None:
    document_id = uuid4()
    household_id = uuid4()
    page_id = uuid4()
    annotation_id = uuid4()
    source = _source(
        document_id=document_id,
        household_id=household_id,
        page_id=page_id,
        family="receipt",
        title="Phenix Title Seller Info",
        original_filename="Phenix Title Seller Info 032924.pdf",
        text=(
            "Phenix Title Seller Information Form seller proceeds "
            "title company closing settlement wiring details"
        ),
    )
    manifest = _manifest_with_regions(
        document_id=document_id,
        household_id=household_id,
        page_id=page_id,
        regions=[],
        document_type="receipt",
    )
    jobs = RecordingJobs()

    SemanticAnnotationService(
        source_loader=lambda loaded_document_id: source,
        gateway=StaticGateway(manifest),
        manifest_persister=lambda persisted_manifest: _persist_dynamic_manifest(
            persisted_manifest,
            annotation_id=annotation_id,
        ),
        jobs=jobs,
    ).annotate_document(document_id, quality_mode="smart", requested_by="system")

    assert len(jobs.created) == 1
    payload = jobs.created[0]["payload"]
    assert payload["target_schema_name"] == "document_observation"
    assert payload["semantic_type"] == "seller_information_block"
    assert payload["semantic_granite_task"] == "kvp"
    assert payload["metadata"]["region_source"] == "docling_structural"
    assert payload["metadata"]["schema_fit"]["reason"] == "observation_schema"


def test_semantic_service_requires_docling_anchors_for_model_observation_family() -> None:
    document_id = uuid4()
    household_id = uuid4()
    page_id = uuid4()
    annotation_id = uuid4()
    source = _source(
        document_id=document_id,
        household_id=household_id,
        page_id=page_id,
        family="generic",
        title="Vehicle Registration",
        original_filename="Vehicle registration scan.pdf",
        text=(
            "Certificate of title motor vehicle registration owner name mailing address "
            "vin license plate year make model odometer"
        ),
    )
    manifest = _manifest_with_regions(
        document_id=document_id,
        household_id=household_id,
        page_id=page_id,
        document_type="real_estate_title",
        regions=[
            SemanticRegionAnnotation(
                semantic_type="seller_information_block",
                priority="high",
                granite_task="kvp",
                target_schema="document_observation",
                expected_fields=("seller_name", "property_address", "title_company"),
                grounding=SemanticGroundingRef(kind="page", page_id=page_id),
                reason="contains owner name, address, vehicle details, and registration info",
                confidence=0.98,
            )
        ],
    )
    jobs = RecordingJobs()

    SemanticAnnotationService(
        source_loader=lambda loaded_document_id: source,
        gateway=StaticGateway(manifest),
        manifest_persister=lambda persisted_manifest: _persist_dynamic_manifest(
            persisted_manifest,
            annotation_id=annotation_id,
        ),
        jobs=jobs,
    ).annotate_document(document_id, quality_mode="smart", requested_by="system")

    assert jobs.created == []


def test_granite_plan_keeps_unknown_observation_regions_generic_without_anchors() -> None:
    document_id = uuid4()
    household_id = uuid4()
    page_id = uuid4()
    region_id = uuid4()
    source = _source(
        document_id=document_id,
        household_id=household_id,
        page_id=page_id,
        family="generic",
        title="Vehicle Registration",
        original_filename="Vehicle registration scan.pdf",
        text=(
            "Certificate of title motor vehicle registration owner name mailing address "
            "vin license plate year make model odometer"
        ),
    )
    manifest = _manifest_with_regions(
        document_id=document_id,
        household_id=household_id,
        page_id=page_id,
        document_type="real_estate_title",
        regions=[
            SemanticRegionAnnotation(
                semantic_type="vehicle_or_asset_block",
                priority="high",
                granite_task="kvp",
                target_schema="document_observation",
                expected_fields=("owner_name", "vin", "license_plate"),
                grounding=SemanticGroundingRef(kind="page", page_id=page_id),
                reason="contains owner and vehicle details",
                confidence=0.99,
            )
        ],
    )

    plan = _granite_extraction_plan(
        source,
        SemanticAnnotationResult(manifest=manifest),
        PersistedSemanticManifest(annotation_id=uuid4(), region_ids=(region_id,)),
    )

    assert plan.selected == ()
    assert len(plan.dropped) == 1
    assert plan.dropped[0].metadata["resolved_document_type"] == "generic"
    assert plan.dropped[0].contract_resolution_reason == "missing_contract"


def test_semantic_service_uses_only_dominant_docling_observation_family() -> None:
    document_id = uuid4()
    household_id = uuid4()
    page_id = uuid4()
    annotation_id = uuid4()
    source = _source(
        document_id=document_id,
        household_id=household_id,
        page_id=page_id,
        family="receipt",
        title="Phenix Title Seller Info",
        original_filename="Phenix Title Seller Info 032924.pdf",
        text=("Phenix Title seller seller seller title company closing settlement escrow payment"),
    )
    manifest = _manifest_with_regions(
        document_id=document_id,
        household_id=household_id,
        page_id=page_id,
        regions=[],
        document_type="real_estate_title",
    )
    jobs = RecordingJobs()

    SemanticAnnotationService(
        source_loader=lambda loaded_document_id: source,
        gateway=StaticGateway(manifest),
        manifest_persister=lambda persisted_manifest: _persist_dynamic_manifest(
            persisted_manifest,
            annotation_id=annotation_id,
        ),
        jobs=jobs,
    ).annotate_document(document_id, quality_mode="smart", requested_by="system")

    assert len(jobs.created) == 1
    payload = jobs.created[0]["payload"]
    assert payload["semantic_type"] == "seller_information_block"
    assert payload["metadata"]["docling_structural_target"]["family"] == "real_estate_title"


def test_semantic_service_does_not_add_dispute_target_for_restaurant_receipt() -> None:
    document_id = uuid4()
    household_id = uuid4()
    page_id = uuid4()
    annotation_id = uuid4()
    source = _source(
        document_id=document_id,
        household_id=household_id,
        page_id=page_id,
        family="receipt",
        text=(
            "McDonald's receipt transaction subtotal tax total paid "
            "visa charge payment approval code"
        ),
    )
    manifest = _manifest(
        document_id=document_id,
        household_id=household_id,
        page_id=page_id,
        semantic_type="receipt_payment_summary",
        granite_task="kvp",
        target_schema="receipt",
        document_type="receipt",
    )
    jobs = RecordingJobs()

    SemanticAnnotationService(
        source_loader=lambda loaded_document_id: source,
        gateway=StaticGateway(manifest),
        manifest_persister=lambda persisted_manifest: _persist_dynamic_manifest(
            persisted_manifest,
            annotation_id=annotation_id,
        ),
        jobs=jobs,
    ).annotate_document(document_id, quality_mode="smart", requested_by="system")

    semantic_types = [job["payload"].get("semantic_type") for job in jobs.created]
    assert "receipt_payment_summary" in semantic_types
    assert "dispute_reason_block" not in semantic_types


def test_semantic_service_queues_granite_jobs_with_task_budget_attempts() -> None:
    document_id = uuid4()
    household_id = uuid4()
    page_id = uuid4()
    annotation_id = uuid4()
    source = _source(
        document_id=document_id,
        household_id=household_id,
        page_id=page_id,
        family="receipt",
        text="McDonald's receipt subtotal tax total paid",
    )
    manifest = _manifest(
        document_id=document_id,
        household_id=household_id,
        page_id=page_id,
        semantic_type="receipt_line_item_table",
        granite_task="tables_json",
        target_schema="receipt",
        document_type="receipt",
    )
    jobs = RecordingJobs()

    SemanticAnnotationService(
        source_loader=lambda loaded_document_id: source,
        gateway=StaticGateway(manifest),
        manifest_persister=lambda persisted_manifest: _persist_dynamic_manifest(
            persisted_manifest,
            annotation_id=annotation_id,
        ),
        jobs=jobs,
    ).annotate_document(document_id, quality_mode="smart", requested_by="system")

    assert jobs.created[0]["max_attempts"] == 2


def test_semantic_service_dedupes_repeated_regions_before_enqueue() -> None:
    document_id = uuid4()
    household_id = uuid4()
    page_id = uuid4()
    element_id = uuid4()
    annotation_id = uuid4()
    persisted_region_ids: list[UUID] = []
    source = _source(
        document_id=document_id,
        household_id=household_id,
        page_id=page_id,
        family="real_estate_title",
        title="Phenix Title Seller Info",
        original_filename="Phenix Title Seller Info 032924.pdf",
        text="Seller information title company closing settlement property address",
    )
    regions = [
        SemanticRegionAnnotation(
            semantic_type="seller_information_block",
            priority="high",
            granite_task="kvp",
            target_schema="document_observation",
            expected_fields=("seller_name",),
            grounding=SemanticGroundingRef(kind="element", element_id=element_id),
            confidence=0.8 + (index * 0.01),
        )
        for index in range(3)
    ]
    manifest = _manifest_with_regions(
        document_id=document_id,
        household_id=household_id,
        page_id=page_id,
        regions=regions,
        document_type="real_estate_title",
    )
    jobs = RecordingJobs()

    def persist_manifest(persisted_manifest: DocumentSemanticManifest) -> PersistedSemanticManifest:
        persisted = _persist_dynamic_manifest(
            persisted_manifest,
            annotation_id=annotation_id,
        )
        persisted_region_ids.extend(persisted.region_ids)
        return persisted

    SemanticAnnotationService(
        source_loader=lambda loaded_document_id: source,
        gateway=StaticGateway(manifest),
        manifest_persister=persist_manifest,
        jobs=jobs,
    ).annotate_document(document_id, quality_mode="smart", requested_by="system")

    assert len(jobs.created) == 1
    assert UUID(jobs.created[0]["payload"]["semantic_region_id"]) in persisted_region_ids


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


def test_semantic_service_reports_missing_contracts_to_extraction_plan() -> None:
    document_id = uuid4()
    household_id = uuid4()
    page_id = uuid4()
    region_id = uuid4()
    source = _source(
        document_id=document_id,
        household_id=household_id,
        page_id=page_id,
        text="Invoice due date amount due total billing account number",
    )
    manifest = _manifest(
        document_id=document_id,
        household_id=household_id,
        page_id=page_id,
        semantic_type="document_header",
        granite_task="kvp",
        target_schema="invoice",
        document_type="invoice",
    )

    plan = _granite_extraction_plan(
        source,
        SemanticAnnotationResult(manifest=manifest),
        PersistedSemanticManifest(annotation_id=uuid4(), region_ids=(region_id,)),
    )

    assert plan.selected == ()
    assert len(plan.dropped) == 1
    assert plan.summary_counts()["missing_contract_count"] == 1
    assert plan.warnings == (f"granite_plan_missing_contract:{region_id}",)
    assert plan.dropped[0].region_id == region_id
    assert plan.dropped[0].contract_resolution_reason == "missing_contract"


def test_semantic_service_rejects_removed_high_quality_mode() -> None:
    document_id = uuid4()
    household_id = uuid4()
    page_id = uuid4()
    source = _source(document_id=document_id, household_id=household_id, page_id=page_id)
    manifest = _manifest(
        document_id=document_id,
        household_id=household_id,
        page_id=page_id,
        quality_mode="high_quality",
    )
    jobs = RecordingJobs()

    with pytest.raises(SemanticAnnotationServiceError, match="removed"):
        SemanticAnnotationService(
            source_loader=lambda loaded_document_id: source,
            gateway=StaticGateway(manifest),
            jobs=jobs,
        ).annotate_document(document_id, quality_mode="high_quality", requested_by="user")

    assert jobs.created == []


def test_semantic_service_caps_smart_fanout_to_three_regions_on_one_page() -> None:
    document_id = uuid4()
    household_id = uuid4()
    page_id = uuid4()
    annotation_id = uuid4()
    region_ids = tuple(uuid4() for _ in range(10))
    source = _source(document_id=document_id, household_id=household_id, page_id=page_id)
    manifest = _manifest(
        document_id=document_id,
        household_id=household_id,
        page_id=page_id,
        region_count=10,
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
    ).annotate_document(document_id, quality_mode="smart", requested_by="system")

    assert len(jobs.created) == 3
    assert len(result.queued_granite_job_ids) == 3


def test_semantic_service_prioritizes_line_items_over_header_regions() -> None:
    document_id = uuid4()
    household_id = uuid4()
    page_id = uuid4()
    annotation_id = uuid4()
    source = _source(document_id=document_id, household_id=household_id, page_id=page_id)
    regions = [
        SemanticRegionAnnotation(
            semantic_type="document_header",
            priority="high",
            granite_task="kvp",
            target_schema="invoice",
            expected_fields=(f"header_{index}",),
            grounding=SemanticGroundingRef(kind="page", page_id=page_id),
            confidence=0.99,
        )
        for index in range(6)
    ]
    regions.append(
        SemanticRegionAnnotation(
            semantic_type="invoice_line_item_table",
            priority="high",
            granite_task="tables_json",
            target_schema="invoice",
            expected_fields=("line_items",),
            grounding=SemanticGroundingRef(kind="page", page_id=page_id),
            confidence=0.7,
            metadata={
                "coverage_role": "primary",
                "source_signal": "table",
                "requires_full_page_image": True,
            },
        )
    )
    manifest = _manifest_with_regions(
        document_id=document_id,
        household_id=household_id,
        page_id=page_id,
        regions=regions,
    )
    jobs = RecordingJobs()
    persisted_manifests: list[DocumentSemanticManifest] = []

    SemanticAnnotationService(
        source_loader=lambda loaded_document_id: source,
        gateway=StaticGateway(manifest),
        manifest_persister=lambda persisted_manifest: _persist_dynamic_manifest(
            persisted_manifest,
            annotation_id=annotation_id,
            captured=persisted_manifests,
        ),
        jobs=jobs,
    ).annotate_document(document_id, quality_mode="smart", requested_by="system")

    assert [region.semantic_type for region in persisted_manifests[0].regions] == [
        "invoice_line_item_table"
    ]
    assert len(jobs.created) == 1
    payload = jobs.created[0]["payload"]
    assert payload["semantic_type"] == "invoice_line_item_table"
    assert payload["model_output_schema_name"] == "granite_invoice_line_items.v1"


def test_semantic_service_rejects_removed_rescue_mode() -> None:
    document_id = uuid4()
    household_id = uuid4()
    page_id = uuid4()
    source = _source(document_id=document_id, household_id=household_id, page_id=page_id)
    manifest = _manifest(
        document_id=document_id,
        household_id=household_id,
        page_id=page_id,
        quality_mode="rescue",
    )
    jobs = RecordingJobs()

    with pytest.raises(SemanticAnnotationServiceError, match="removed"):
        SemanticAnnotationService(
            source_loader=lambda loaded_document_id: source,
            gateway=StaticGateway(manifest),
            jobs=jobs,
        ).annotate_document(
            document_id,
            quality_mode="rescue",
            requested_by="user",
            allow_8b_rescue=True,
            user_intent_reason="User allowed one 8B rescue.",
        )

    assert jobs.created == []


def test_semantic_service_rejects_rescue_without_persisted_permission() -> None:
    document_id = uuid4()

    with pytest.raises(SemanticAnnotationServiceError, match="removed"):
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


def test_semantic_service_rejects_high_quality_after_legacy_path_removed() -> None:
    document_id = uuid4()

    with pytest.raises(SemanticAnnotationServiceError, match="removed"):
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
                    quality_mode="high_quality",
                )
            ),
        ).annotate_document(document_id, quality_mode="high_quality", requested_by="user")


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
    family: str = "invoice",
    title: str = "Invoice",
    original_filename: str | None = "invoice.pdf",
    text: str = "Invoice line items",
    metadata: dict[str, Any] | None = None,
    tables: list[ParsedTableText] | None = None,
) -> ExtractionSourceDocument:
    return ExtractionSourceDocument(
        document_id=document_id,
        household_id=household_id,
        title=title,
        original_filename=original_filename,
        mime_type="application/pdf",
        family=family,
        subtype=None,
        sensitivity="standard",
        document_date=None,
        counterparty_display=None,
        primary_folder_id=None,
        metadata=metadata or {},
        pages=[
            ParsedPageText(
                page_id=page_id,
                page_number=1,
                text=text,
                image_bytes=b"fake-image",
                image_mime_type="image/png",
                image_sha256="c" * 64,
            )
        ],
        elements=[],
        tables=list(tables or []),
    )


def _source_with_pages(
    *,
    document_id: UUID,
    household_id: UUID,
    family: str,
    title: str,
    original_filename: str | None,
    page_texts: dict[int, str],
    page_ids: dict[int, UUID],
    metadata: dict[str, Any] | None = None,
    tables: list[ParsedTableText] | None = None,
) -> ExtractionSourceDocument:
    return ExtractionSourceDocument(
        document_id=document_id,
        household_id=household_id,
        title=title,
        original_filename=original_filename,
        mime_type="application/pdf",
        family=family,
        subtype=None,
        sensitivity="standard",
        document_date=None,
        counterparty_display=None,
        primary_folder_id=None,
        metadata=metadata or {},
        pages=[
            ParsedPageText(
                page_id=page_ids[page_number],
                page_number=page_number,
                text=text,
                image_bytes=b"fake-image",
                image_mime_type="image/png",
                image_sha256=f"{page_number:064x}"[-64:],
            )
            for page_number, text in sorted(page_texts.items())
        ],
        elements=[],
        tables=list(tables or []),
    )


def _manifest(
    *,
    document_id: UUID,
    household_id: UUID,
    page_id: UUID,
    granite_task: str = "tables_json",
    quality_mode: str = "smart",
    region_count: int = 1,
    target_schema: str = "invoice",
    semantic_type: str = "invoice_line_item_table",
    document_type: str = "invoice",
) -> DocumentSemanticManifest:
    def expected_fields(index: int) -> tuple[str, ...]:
        if region_count == 1:
            return ("line_items", "total_amount")
        return ("line_items", "total_amount", f"field_{index}")

    regions = [
        SemanticRegionAnnotation(
            semantic_type=semantic_type,
            priority="high",
            granite_task=granite_task,
            target_schema=target_schema,
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
        profile_name="qwen3-vl-8b-fp8-semantic:v1",
        source_engine="qwen3_vl_8b",
        model_name="Qwen/Qwen3-VL-8B-Instruct-FP8",
        model_version="v1",
        prompt_version="phase8_5-semantic-smart-v3",
        pages=[
            PageSemanticAnnotation(
                page_id=page_id,
                page_number=1,
                page_role="line_items",
                has_structured_targets=True,
            )
        ],
        regions=regions,
        confidence={"overall": 0.9},
        manifest=_semantic_manifest_payload(
            document_type=document_type,
            page_id=page_id,
            regions=regions,
        ),
        input_page_hashes=("c" * 64,),
    )


def _manifest_with_regions_for_pages(
    *,
    document_id: UUID,
    household_id: UUID,
    page_ids: dict[int, UUID],
    regions: list[SemanticRegionAnnotation],
    document_type: str,
) -> DocumentSemanticManifest:
    pages = [
        PageSemanticAnnotation(
            page_id=page_id,
            page_number=page_number,
            page_role="evidence",
            has_structured_targets=True,
        )
        for page_number, page_id in sorted(page_ids.items())
    ]
    return DocumentSemanticManifest(
        document_id=document_id,
        household_id=household_id,
        quality_mode="smart",
        profile_name="qwen3-vl-8b-fp8-semantic:v1",
        source_engine="qwen3_vl_8b",
        model_name="Qwen/Qwen3-VL-8B-Instruct-FP8",
        model_version="v1",
        prompt_version="phase8_5-semantic-smart-v3",
        pages=pages,
        regions=regions,
        confidence={"overall": 0.9},
        manifest=_semantic_manifest_payload_for_pages(
            document_type=document_type,
            pages=pages,
            regions=regions,
        ),
        input_page_hashes=tuple("c" * 64 for _page in pages),
    )


def _manifest_with_regions(
    *,
    document_id: UUID,
    household_id: UUID,
    page_id: UUID,
    regions: list[SemanticRegionAnnotation],
    document_type: str = "invoice",
) -> DocumentSemanticManifest:
    return DocumentSemanticManifest(
        document_id=document_id,
        household_id=household_id,
        quality_mode="smart",
        profile_name="qwen3-vl-8b-fp8-semantic:v1",
        source_engine="qwen3_vl_8b",
        model_name="Qwen/Qwen3-VL-8B-Instruct-FP8",
        model_version="v1",
        prompt_version="phase8_5-semantic-smart-v3",
        pages=[
            PageSemanticAnnotation(
                page_id=page_id,
                page_number=1,
                page_role="line_items",
                has_structured_targets=True,
            )
        ],
        regions=regions,
        confidence={"overall": 0.9},
        manifest=_semantic_manifest_payload(
            document_type=document_type,
            page_id=page_id,
            regions=regions,
        ),
        input_page_hashes=("c" * 64,),
    )


def _persist_dynamic_manifest(
    manifest: DocumentSemanticManifest,
    *,
    annotation_id: UUID,
    captured: list[DocumentSemanticManifest] | None = None,
) -> PersistedSemanticManifest:
    if captured is not None:
        captured.append(manifest)
    return PersistedSemanticManifest(
        annotation_id=annotation_id,
        region_ids=tuple(uuid4() for _ in manifest.regions),
    )


def _semantic_manifest_payload(
    *,
    document_type: str,
    page_id: UUID,
    regions: list[SemanticRegionAnnotation],
) -> dict[str, Any]:
    return {
        "schema_name": "semantic_annotation_manifest",
        "schema_version": "v1",
        "document_type": document_type,
        "pages": [
            {
                "page_id": str(page_id),
                "page_number": 1,
                "page_role": "line_items",
                "document_type_hint": None,
                "extraction_usefulness": "unknown",
                "is_boilerplate": False,
                "has_structured_targets": True,
                "ambiguous": False,
                "escalation_required": False,
                "escalation_reasons": [],
                "reason": None,
                "confidence": None,
            }
        ],
        "regions": [_region_payload(region) for region in regions],
        "quality_flags": {
            "needs_human_review": False,
            "visual_degradation": False,
        },
        "confidence": {"overall": 0.9},
    }


def _semantic_manifest_payload_for_pages(
    *,
    document_type: str,
    pages: list[PageSemanticAnnotation],
    regions: list[SemanticRegionAnnotation],
) -> dict[str, Any]:
    return {
        "schema_name": "semantic_annotation_manifest",
        "schema_version": "v1",
        "document_type": document_type,
        "pages": [
            {
                "page_id": str(page.page_id),
                "page_number": page.page_number,
                "page_role": page.page_role,
                "document_type_hint": None,
                "extraction_usefulness": "unknown",
                "is_boilerplate": False,
                "has_structured_targets": page.has_structured_targets,
                "ambiguous": False,
                "escalation_required": False,
                "escalation_reasons": [],
                "reason": None,
                "confidence": None,
            }
            for page in pages
        ],
        "regions": [_region_payload(region) for region in regions],
        "quality_flags": {
            "needs_human_review": False,
            "visual_degradation": False,
        },
        "confidence": {"overall": 0.9},
    }


def _region_payload(region: SemanticRegionAnnotation) -> dict[str, Any]:
    return {
        "semantic_type": region.semantic_type,
        "priority": region.priority,
        "granite_task": region.granite_task,
        "target_schema": region.target_schema,
        "expected_fields": list(region.expected_fields),
        "grounding": {
            "kind": region.grounding.kind,
            "page_id": str(region.grounding.page_id) if region.grounding.page_id else None,
            "element_id": (
                str(region.grounding.element_id) if region.grounding.element_id else None
            ),
            "table_id": str(region.grounding.table_id) if region.grounding.table_id else None,
        },
        "review_required": region.review_required,
        "reason": region.reason,
        "confidence": region.confidence,
    }


def test_planning_normalization_never_synthesizes_or_rewrites_model_regions() -> None:
    from lib.semantic_annotations.manifest_normalization import normalize_manifest_for_planning

    document_id = uuid4()
    household_id = uuid4()
    page_id = uuid4()
    source = _source(
        document_id=document_id,
        household_id=household_id,
        page_id=page_id,
        family="medical_eob",
        title="Anthem denial",
        text=(
            "Explanation of benefits claim denied appeal grievance rights deadline "
            "receipt subtotal total tax shipping amount paid seller 1 escrow"
        ),
    )
    model_regions = [
        SemanticRegionAnnotation(
            semantic_type="generic_form_kvp",
            priority="high",
            granite_task="kvp",
            target_schema="medical_eob",
            expected_fields=("appeal_deadline",),
            grounding=SemanticGroundingRef(kind="page", page_id=page_id),
            review_required=True,
            confidence=0.7,
        ),
        SemanticRegionAnnotation(
            semantic_type="covered_services_line_item_table",
            priority="critical",
            granite_task="tables_json",
            target_schema="medical_eob",
            expected_fields=("service_lines",),
            grounding=SemanticGroundingRef(kind="page", page_id=page_id),
            review_required=True,
            confidence=0.8,
        ),
    ]
    manifest = _manifest_with_regions(
        document_id=document_id,
        household_id=household_id,
        page_id=page_id,
        document_type="medical_eob",
        regions=model_regions,
    )

    normalized = normalize_manifest_for_planning(source, manifest)

    # The spec bans synthetic regions and semantic-type rewrites: every output
    # region corresponds to a model-emitted region with its type unchanged.
    assert len(normalized.regions) <= len(model_regions)
    assert {region.semantic_type for region in normalized.regions} <= {
        region.semantic_type for region in model_regions
    }


def test_planning_normalization_preserves_model_payment_summary_on_generic_source() -> None:
    from lib.semantic_annotations.manifest_normalization import normalize_manifest_for_planning

    document_id = uuid4()
    household_id = uuid4()
    page_id = uuid4()
    source = _source(
        document_id=document_id,
        household_id=household_id,
        page_id=page_id,
        family="generic",
        text="quarterly newsletter with no purchase content",
    )
    manifest = _manifest_with_regions(
        document_id=document_id,
        household_id=household_id,
        page_id=page_id,
        document_type="generic_form",
        regions=[
            SemanticRegionAnnotation(
                semantic_type="receipt_payment_summary",
                priority="medium",
                granite_task="kvp",
                target_schema="receipt",
                expected_fields=("total_amount",),
                grounding=SemanticGroundingRef(kind="page", page_id=page_id),
                review_required=False,
                confidence=0.55,
            )
        ],
    )

    normalized = normalize_manifest_for_planning(source, manifest)

    # Model-emitted regions survive normalization; schema-fit gating (not
    # family term lists) decides the eventual contract, and the model-planned
    # payment summary is review-required.
    assert [region.semantic_type for region in normalized.regions] == ["receipt_payment_summary"]
    assert normalized.regions[0].review_required is True

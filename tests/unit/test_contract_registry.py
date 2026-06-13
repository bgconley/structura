import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, ValidationError
from pydantic import TypeAdapter
from pydantic import ValidationError as PydanticValidationError

from lib.contracts import (
    CanonicalField,
    ContractRegistry,
    CreateMagicLinkRequest,
    CreateSessionRequest,
    EvidenceRef,
    FieldCandidate,
    FilingRule,
    PasswordSessionRequest,
    ReviewActionRequest,
    SearchRequest,
    SearchResponse,
    UploadDocumentMultipartRequest,
)
from lib.contracts.registry import _check_structured_output_schema

UUID_1 = "11111111-1111-1111-1111-111111111111"
UUID_2 = "22222222-2222-2222-2222-222222222222"
TIMESTAMP = "2026-04-24T00:00:00Z"


def test_contract_registry_loads_openapi_schemas_and_events() -> None:
    registry = ContractRegistry.load("contracts")
    summary = registry.summary()

    assert summary["openapi_title"] == "Structura API"
    assert summary["path_count"] >= 20
    assert "common_defs.schema.json" in summary["schemas"]
    assert "ingest_document_job.v1.schema.json" in summary["events"]
    assert "granite_invoice_line_items.v1.schema.json" in summary["model_outputs"]


def test_json_schemas_are_valid_draft_2020_12() -> None:
    registry = ContractRegistry.load("contracts")

    registry.check_json_schemas()


def test_model_output_schemas_are_valid_draft_2020_12() -> None:
    for path in sorted(Path("contracts/model_outputs").glob("*.schema.json")):
        Draft202012Validator.check_schema(json.loads(path.read_text(encoding="utf-8")))


def test_model_output_schemas_are_strict_structured_output_contracts() -> None:
    registry = ContractRegistry.load("contracts")

    registry.check_model_output_structured_schemas()


def test_model_output_schema_checker_rejects_empty_root_contracts() -> None:
    with pytest.raises(ValueError, match="require at least one extraction-bearing"):
        _check_structured_output_schema(
            name="empty_model_output.schema.json",
            schema={
                "type": "object",
                "additionalProperties": False,
                "required": ["confidence"],
                "properties": {
                    "confidence": {
                        "type": "object",
                        "additionalProperties": False,
                    }
                },
            },
        )


def test_model_output_schema_checker_rejects_optional_object_properties() -> None:
    with pytest.raises(ValueError, match="must require every declared object property"):
        _check_structured_output_schema(
            name="optional_model_output.schema.json",
            schema={
                "type": "object",
                "additionalProperties": False,
                "required": ["items"],
                "properties": {
                    "items": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "required": ["description"],
                            "properties": {
                                "description": {"type": "string"},
                                "amount": {"type": ["number", "null"]},
                            },
                        },
                    }
                },
            },
        )


def test_model_output_schemas_reject_empty_root_objects() -> None:
    registry = ContractRegistry.load("contracts")

    for name, schema in registry.model_outputs.items():
        required = schema.get("required")
        properties = schema.get("properties") or {}
        assert isinstance(required, list), f"{name} must declare root required keys"
        assert any(key != "confidence" for key in required), (
            f"{name} must require at least one extraction-bearing root key"
        )
        with pytest.raises(ValidationError):
            Draft202012Validator(schema).validate({})
        assert set(required).issubset(properties)


def test_evidence_requires_page_number_and_concrete_locator() -> None:
    registry = ContractRegistry.load("contracts")
    evidence = registry.schemas["common_defs.schema.json"]["$defs"]["evidenceRef"]

    assert "page_number" in evidence["required"]
    assert "source_engine" in evidence["required"]
    assert "anyOf" in evidence
    assert len(evidence["anyOf"]) >= 5


def test_openapi_component_validation_covers_upload_session_and_evidence() -> None:
    registry = ContractRegistry.load("contracts")

    registry.validate_openapi_component(
        "UploadDocumentMultipartRequest",
        {
            "file": "document.pdf",
            "source": "web_upload",
            "suppliedFolderIds": [UUID_1],
            "suppliedTags": ["tax"],
        },
    )
    registry.validate_openapi_component(
        "CreateSessionRequest",
        {"method": "password", "email": "admin@example.com", "password": "minimum8"},
    )
    with pytest.raises(ValidationError):
        registry.validate_openapi_component(
            "PasswordSessionRequest",
            {"method": "password", "email": "not-an-email", "password": "minimum8"},
        )
    registry.validate_openapi_component(
        "EvidenceRef",
        {"pageNumber": 1, "sourceEngine": "docling", "bbox": [0, 0, 1, 1]},
    )

    with pytest.raises(ValidationError):
        registry.validate_openapi_component(
            "EvidenceRef",
            {"pageNumber": 1, "sourceEngine": "docling"},
        )


def test_json_schema_instances_cover_review_candidates_canonical_filing_and_events() -> None:
    registry = ContractRegistry.load("contracts")

    evidence = {"page_number": 1, "source_engine": "docling", "bbox": [0, 0, 1, 1]}
    registry.validate_schema_instance(
        "review_action.v1.schema.json",
        {
            "schema_name": "review_action",
            "schema_version": "v1",
            "document_id": UUID_1,
            "action_type": "confirm_field",
            "actor_type": "human",
            "created_at": TIMESTAMP,
            "evidence_context": [evidence],
        },
    )
    registry.validate_schema_instance(
        "field_candidate.v1.schema.json",
        {
            "schema_name": "field_candidate",
            "schema_version": "field_candidate.v1",
            "document_id": UUID_1,
            "field_path": "invoice.total",
            "value_type": "money",
            "source": {"engine": "docling"},
            "evidence": [evidence],
        },
    )
    registry.validate_schema_instance(
        "canonical_field.v1.schema.json",
        {
            "schema_name": "canonical_field",
            "schema_version": "canonical_field.v1",
            "document_id": UUID_1,
            "field_path": "invoice.total",
            "value_type": "money",
            "value": {"amount": 12.5, "currency": "USD"},
            "source_kind": "candidate",
            "review_status": "user_confirmed",
            "evidence": [evidence],
        },
    )
    registry.validate_schema_instance(
        "filing_rule.v1.schema.json",
        {
            "schema_name": "filing_rule",
            "schema_version": "filing_rule.v1",
            "name": "Paid invoices",
            "enabled": True,
            "conditions": [{"field": "document_type", "op": "eq", "value": "invoice"}],
            "actions": [{"type": "add_tag", "tag": "invoice"}],
        },
    )
    registry.validate_event_instance(
        "ingest_document_job.v1.schema.json",
        {
            "schema_name": "ingest_document_job",
            "schema_version": "v1",
            "job_id": UUID_1,
            "created_at": TIMESTAMP,
            "attempt": 1,
            "priority": 5,
            "source": "web_upload",
            "input_object": {
                "uri": "file:///srv/structura/staging/document.pdf",
                "sha256": "a" * 64,
                "mime_type": "application/pdf",
                "filename": "document.pdf",
            },
        },
    )


def test_review_action_schema_matches_runtime_review_actions() -> None:
    registry = ContractRegistry.load("contracts")
    schema_actions = set(
        registry.schemas["review_action.v1.schema.json"]["properties"]["action_type"]["enum"]
    )
    runtime_actions = {
        "confirm_field",
        "correct_field",
        "reject_field",
        "reclassify_document",
        "rerun_extraction",
        "mark_done",
        "accept_relationship",
        "reject_relationship",
        "accept_observation",
        "reject_observation",
        "accept_line_item",
        "reject_line_item",
    }

    assert schema_actions == runtime_actions
    for action_type in runtime_actions:
        ReviewActionRequest.model_validate(
            {
                "schemaName": "review_action",
                "schemaVersion": "v1",
                "documentId": UUID_1,
                "actionType": action_type,
                "actorType": "human",
                "createdAt": TIMESTAMP,
            }
        )


def test_search_contract_models_match_openapi_phase5_filters_and_response() -> None:
    registry = ContractRegistry.load("contracts")
    registry.validate_openapi_component(
        "SearchRequest",
        {
            "query": "claim ABC123 money owed",
            "mode": "hybrid",
            "families": ["medical_eob"],
            "folderIds": [UUID_1],
            "tags": ["medical"],
            "reviewedOnly": True,
            "dateFrom": "2025-01-01",
            "dateTo": "2026-12-31",
            "amountMin": 1,
            "amountMax": 100,
            "sensitivity": ["normal"],
            "limit": 10,
            "includeDebug": True,
        },
    )
    request = SearchRequest.model_validate(
        {
            "query": "claim ABC123 money owed",
            "mode": "hybrid",
            "families": ["medical_eob"],
            "dateFrom": "2025-01-01",
            "dateTo": "2026-12-31",
            "amountMin": 1,
            "amountMax": 100,
            "includeDebug": True,
        }
    )
    assert request.mode == "hybrid"
    assert request.include_debug is True

    response = SearchResponse.model_validate(
        {
            "items": [
                {
                    "documentId": UUID_1,
                    "title": "Anthem medical EOB",
                    "family": "medical_eob",
                    "rank": 1,
                    "score": 0.19,
                    "snippet": "Claim ABC123 patient responsibility $62.00",
                    "matchedChunkId": UUID_2,
                    "pageNumber": 1,
                    "explanation": "matched by lexical rank 1 and semantic rank 1",
                    "evidence": [
                        {
                            "pageNumber": 1,
                            "sourceEngine": "docling",
                            "sourceText": "Claim ABC123 patient responsibility $62.00",
                        }
                    ],
                }
            ],
            "facets": {"families": {"medical_eob": 1}},
            "debug": {"mode": "hybrid"},
        }
    )
    assert response.items[0].explanation
    with pytest.raises(PydanticValidationError):
        ReviewActionRequest.model_validate(
            {
                "schemaName": "review_action",
                "schemaVersion": "v1",
                "documentId": UUID_1,
                "actionType": "add_tag",
                "actorType": "human",
                "createdAt": TIMESTAMP,
            }
        )


def test_all_job_event_schemas_validate_representative_payloads() -> None:
    registry = ContractRegistry.load("contracts")

    event_payloads = {
        "ingest_document_job.v1.schema.json": {
            "schema_name": "ingest_document_job",
            "schema_version": "v1",
            "job_id": UUID_1,
            "created_at": TIMESTAMP,
            "attempt": 1,
            "priority": 5,
            "source": "web_upload",
            "input_object": {
                "uri": "file:///srv/structura/staging/document.pdf",
                "sha256": "a" * 64,
                "mime_type": "application/pdf",
                "filename": "document.pdf",
            },
        },
        "classify_document_job.v1.schema.json": {
            "schema_name": "classify_document_job",
            "schema_version": "v1",
            "job_id": UUID_1,
            "created_at": TIMESTAMP,
            "attempt": 1,
            "priority": 5,
            "document_id": UUID_2,
        },
        "extract_document_job.v1.schema.json": {
            "schema_name": "extract_document_job",
            "schema_version": "v1",
            "job_id": UUID_1,
            "created_at": TIMESTAMP,
            "attempt": 1,
            "priority": 5,
            "document_id": UUID_2,
            "target_schema_name": "invoice",
            "target_schema_version": "invoice.v1",
            "semantic_annotation_id": UUID_1,
            "semantic_region_id": UUID_2,
            "semantic_granite_task": "tables_json",
            "semantic_type": "invoice_line_item_table",
            "semantic_expected_fields": ["line_items"],
            "semantic_quality_mode": "smart",
            "requested_by_user_id": UUID_1,
            "user_intent_reason": "User requested extraction.",
        },
        "semantic_annotate_document_job.v1.schema.json": {
            "schema_name": "semantic_annotate_document_job",
            "schema_version": "v1",
            "job_id": UUID_1,
            "created_at": TIMESTAMP,
            "document_id": UUID_2,
            "quality_mode": "smart",
            "semantic_quality_mode": "smart",
            "requested_by": "system",
            "requested_by_user_id": UUID_1,
            "user_intent_reason": "Default Smart Parse.",
        },
        "embed_document_job.v1.schema.json": {
            "schema_name": "embed_document_job",
            "schema_version": "v1",
            "job_id": UUID_1,
            "created_at": TIMESTAMP,
            "attempt": 1,
            "priority": 5,
            "document_id": UUID_2,
            "modalities": ["text"],
        },
        "analyze_documents_job.v1.schema.json": {
            "schema_name": "analyze_documents_job",
            "schema_version": "v1",
            "job_id": UUID_1,
            "created_at": TIMESTAMP,
            "attempt": 1,
            "priority": 5,
            "document_ids": [UUID_2],
            "analysis_note_type": "summary",
            "question": "Summarize this document.",
        },
    }

    for schema_name, payload in event_payloads.items():
        registry.validate_event_instance(schema_name, payload)


def test_semantic_annotation_job_contract_is_smart_only() -> None:
    registry = ContractRegistry.load("contracts")
    payload = {
        "schema_name": "semantic_annotate_document_job",
        "schema_version": "v1",
        "job_id": UUID_1,
        "created_at": TIMESTAMP,
        "document_id": UUID_2,
        "quality_mode": "high_quality",
        "semantic_quality_mode": "high_quality",
        "allow_8b_rescue": False,
    }

    with pytest.raises(ValidationError):
        registry.validate_event_instance(
            "semantic_annotate_document_job.v1.schema.json",
            payload,
        )


def test_phase8_5_event_contracts_reject_removed_rescue_fields() -> None:
    registry = ContractRegistry.load("contracts")
    semantic_payload = {
        "schema_name": "semantic_annotate_document_job",
        "schema_version": "v1",
        "job_id": UUID_1,
        "created_at": TIMESTAMP,
        "document_id": UUID_2,
        "quality_mode": "smart",
        "semantic_quality_mode": "smart",
        "allow_8b_rescue": False,
    }
    extract_payload = {
        "schema_name": "extract_document_job",
        "schema_version": "v1",
        "job_id": UUID_1,
        "created_at": TIMESTAMP,
        "attempt": 1,
        "priority": 5,
        "document_id": UUID_2,
        "target_schema_name": "invoice",
        "target_schema_version": "invoice.v1",
        "semantic_quality_mode": "smart",
        "allow_8b_rescue": False,
        "semantic_rescue": False,
    }
    high_quality_extract = {
        **extract_payload,
        "semantic_quality_mode": "high_quality",
    }
    high_quality_extract.pop("allow_8b_rescue")
    high_quality_extract.pop("semantic_rescue")

    for schema_name, payload in (
        ("semantic_annotate_document_job.v1.schema.json", semantic_payload),
        ("extract_document_job.v1.schema.json", extract_payload),
        ("extract_document_job.v1.schema.json", high_quality_extract),
    ):
        with pytest.raises(ValidationError):
            registry.validate_event_instance(schema_name, payload)


def test_extract_document_job_contract_accepts_review_rerun_actor() -> None:
    registry = ContractRegistry.load("contracts")
    payload = {
        "schema_name": "extract_document_job",
        "schema_version": "v1",
        "job_id": UUID_1,
        "created_at": TIMESTAMP,
        "attempt": 1,
        "priority": 5,
        "requested_by": "reviewer",
        "document_id": UUID_2,
        "target_schema_name": "invoice",
        "target_schema_version": "v1",
        "semantic_quality_mode": "smart",
    }

    registry.validate_event_instance("extract_document_job.v1.schema.json", payload)


def test_extract_document_job_contract_accepts_document_orchestration_mode() -> None:
    registry = ContractRegistry.load("contracts")
    payload = {
        "schema_name": "extract_document_job",
        "schema_version": "v1",
        "job_id": UUID_1,
        "created_at": TIMESTAMP,
        "attempt": 1,
        "priority": 5,
        "document_id": UUID_2,
        "target_schema_name": "semantic_document",
        "target_schema_version": "v1",
        "semantic_annotation_id": UUID_1,
        "orchestration_mode": "semantic_document",
        "semantic_quality_mode": "smart",
    }

    registry.validate_event_instance("extract_document_job.v1.schema.json", payload)


def test_phase8_5_semantic_annotation_contract_has_qwen2b_and_response_schema() -> None:
    registry = ContractRegistry.load("contracts")
    common_defs = registry.schemas["common_defs.schema.json"]
    source_engines = common_defs["$defs"]["evidenceRef"]["properties"]["source_engine"]["enum"]
    assert "qwen3_vl_2b" in source_engines

    response_schema = registry.openapi["paths"][
        "/api/v1/documents/{documentId}/semantic-annotations/current"
    ]["get"]["responses"]["200"]["content"]["application/json"]["schema"]
    assert response_schema == {"$ref": "#/components/schemas/SemanticAnnotationCurrentResponse"}

    health_schema = registry.openapi["paths"]["/api/v1/health"]["get"]["responses"]["200"][
        "content"
    ]["application/json"]["schema"]
    assert health_schema == {"$ref": "#/components/schemas/ApiHealthResponse"}


def test_phase_0_contract_models_accept_openapi_shapes_and_reject_loose_evidence() -> None:
    evidence = {"pageNumber": 1, "sourceEngine": "docling", "bbox": [0, 0, 1, 1]}

    UploadDocumentMultipartRequest.model_validate({"file": "document.pdf", "source": "web_upload"})
    PasswordSessionRequest.model_validate(
        {"method": "password", "email": "admin@example.com", "password": "minimum8"}
    )
    CreateMagicLinkRequest.model_validate({"email": "admin@example.com", "purpose": "bootstrap"})
    TypeAdapter(CreateSessionRequest).validate_python(
        {"method": "magic_link", "magicLinkToken": "token"}
    )
    FieldCandidate.model_validate(
        {
            "id": UUID_1,
            "documentId": UUID_2,
            "fieldPath": "invoice.total",
            "valueType": "money",
            "sourceEngine": "docling",
            "evidence": [evidence],
        }
    )
    CanonicalField.model_validate(
        {
            "id": UUID_1,
            "documentId": UUID_2,
            "fieldPath": "invoice.total",
            "valueType": "money",
            "value": {"amount": 12.5, "currency": "USD"},
            "sourceKind": "candidate",
            "reviewStatus": "user_confirmed",
            "evidence": [evidence],
        }
    )
    FilingRule.model_validate(
        {
            "id": UUID_1,
            "name": "Paid invoices",
            "enabled": True,
            "conditions": [{"field": "document_type", "op": "eq", "value": "invoice"}],
            "actions": [{"type": "add_tag", "tag": "invoice"}],
        }
    )

    with pytest.raises(ValueError):
        EvidenceRef.model_validate({"pageNumber": 1, "sourceEngine": "docling"})
    with pytest.raises(PydanticValidationError):
        PasswordSessionRequest.model_validate(
            {"method": "password", "email": "not-an-email", "password": "minimum8"}
        )
    with pytest.raises(PydanticValidationError):
        CreateMagicLinkRequest.model_validate({"email": "not-an-email", "purpose": "bootstrap"})

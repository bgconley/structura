"""Explicit line targets and independent source/canonical decision revisions."""

from datetime import date, datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import AwareDatetime, ConfigDict, Field, field_validator, model_validator

from lib.contracts.document_line_items import ExactDecimal
from lib.contracts.models import ContractModel, EvidenceRef, FieldProjectionRevision

LineItemType = Literal[
    "generic", "receipt_item", "invoice_item", "service_line", "payment", "tax", "adjustment", "fee"
]
Sha256 = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
Ordinal = Annotated[int, Field(strict=True, ge=1, le=2147483647)]


class LineAuthorityModel(ContractModel):
    model_config = ConfigDict(
        extra="forbid", populate_by_name=True, frozen=True, allow_inf_nan=False
    )


class LineEvidenceRef(EvidenceRef):
    # The mapper preserves the actual supported engine identity without relabeling.
    model_config = ConfigDict(
        extra="forbid", populate_by_name=True, frozen=True, allow_inf_nan=False
    )

    @field_validator("page_number", "row_index", "column_index", mode="before")
    @classmethod
    def integer_locator(cls, value):
        if value is not None and type(value) is not int:
            raise ValueError("Evidence indices must be integers.")
        return value

    @field_validator("text_span", mode="before")
    @classmethod
    def integer_span(cls, value):
        if isinstance(value, dict) and any(
            type(value.get(key)) is not int for key in ("start", "end")
        ):
            raise ValueError("Evidence offsets must be integers.")
        return value

    @field_validator("bbox", mode="before")
    @classmethod
    def numeric_bbox(cls, value):
        if value is not None and (
            not isinstance(value, list | tuple)
            or any(type(number) not in (int, float) for number in value)
        ):
            raise ValueError("Evidence coordinates must be numbers.")
        return value

    @field_validator("bbox")
    @classmethod
    def finite_bbox(cls, value: tuple[float, float, float, float] | None):
        import math

        if value is not None and not all(math.isfinite(number) for number in value):
            raise ValueError("Evidence coordinates must be finite.")
        if value is not None and not (
            0 <= value[0] < value[2] <= 1 and 0 <= value[1] < value[3] <= 1
        ):
            raise ValueError("Evidence coordinates must be an ordered page-relative box.")
        return value

    @model_validator(mode="after")
    def usable_locators(self):
        if self.source_text is not None and not self.source_text.strip():
            raise ValueError("Evidence source text must be nonempty.")
        if self.text_span is not None and self.text_span.end <= self.text_span.start:
            raise ValueError("Evidence spans must contain source text.")
        return self


class LineSourceExpectation(LineAuthorityModel):
    candidate_id: UUID = Field(alias="candidateId")
    expected_candidate_version: UUID = Field(alias="expectedCandidateVersion")
    expected_source_snapshot_sha256: Sha256 = Field(alias="expectedSourceSnapshotSha256")
    expected_candidate_decision_revision: UUID | None = Field(
        alias="expectedCandidateDecisionRevision"
    )


class LineSlot(LineAuthorityModel):
    line_item_type: LineItemType = Field(alias="lineItemType")
    ordinal: Ordinal


class VacantLineTarget(LineSlot):
    canonical_line_item_id: None = Field(alias="canonicalLineItemId")
    expected_canonical_updated_at: None = Field(alias="expectedCanonicalUpdatedAt")
    expected_line_decision_revision: None = Field(alias="expectedLineDecisionRevision")


class ExistingLineTarget(LineSlot):
    canonical_line_item_id: UUID = Field(alias="canonicalLineItemId")
    expected_canonical_updated_at: AwareDatetime = Field(alias="expectedCanonicalUpdatedAt")
    expected_line_decision_revision: UUID | None = Field(alias="expectedLineDecisionRevision")


class CreateLineDecision(LineAuthorityModel):
    operation: Literal["create"]
    source: LineSourceExpectation
    target: VacantLineTarget
    comment: str | None = Field(default=None, max_length=2000)


class ReplaceLineDecision(LineAuthorityModel):
    operation: Literal["replace"]
    source: LineSourceExpectation
    target: ExistingLineTarget
    comment: str | None = Field(default=None, max_length=2000)


class RejectSelectedLineDecision(LineAuthorityModel):
    operation: Literal["reject_selected"]
    target: ExistingLineTarget
    comment: str | None = Field(default=None, max_length=2000)


class RejectCandidateLineDecision(LineAuthorityModel):
    operation: Literal["reject_candidate"]
    source: LineSourceExpectation
    comment: str | None = Field(default=None, max_length=2000)


LineDecisionRequest = Annotated[
    CreateLineDecision
    | ReplaceLineDecision
    | RejectSelectedLineDecision
    | RejectCandidateLineDecision,
    Field(discriminator="operation"),
]


class LineSlotDecision(LineAuthorityModel):
    id: UUID
    document_id: UUID = Field(alias="documentId")
    line_item_type: LineItemType = Field(alias="lineItemType")
    ordinal: Ordinal
    canonical_line_item_id: UUID = Field(alias="canonicalLineItemId")
    revision: UUID
    disposition: Literal["confirmed", "corrected", "rejected", "protected_legacy"]
    origin: Literal["live_review", "legacy_current_line"]
    actor_user_id: UUID | None = Field(alias="actorUserId")
    review_event_id: UUID | None = Field(alias="reviewEventId")
    decision_event_id: UUID | None = Field(alias="decisionEventId")
    decided_at: AwareDatetime | None = Field(alias="decidedAt")
    recorded_at: AwareDatetime = Field(alias="recordedAt")


class LineCandidateDecision(LineAuthorityModel):
    id: UUID
    document_id: UUID = Field(alias="documentId")
    source_candidate_id: UUID = Field(alias="sourceCandidateId")
    revision: UUID
    disposition: Literal["accepted", "rejected", "protected_legacy"]
    origin: Literal["live_review", "legacy_current_line"]
    source_snapshot_sha256: Sha256 = Field(alias="sourceSnapshotSha256")
    actor_user_id: UUID | None = Field(alias="actorUserId")
    review_event_id: UUID | None = Field(alias="reviewEventId")
    decided_at: AwareDatetime | None = Field(alias="decidedAt")
    recorded_at: AwareDatetime = Field(alias="recordedAt")


class LineSourceAssignment(LineAuthorityModel):
    source_candidate_id: UUID = Field(alias="sourceCandidateId")
    state: Literal["assigned", "legacy_conflict"]
    canonical_line_item_id: UUID | None = Field(alias="canonicalLineItemId")
    target: LineSlot | None
    currently_selected: bool = Field(alias="currentlySelected")


class LinePublicationEligibility(LineAuthorityModel):
    eligible: bool
    reason: Literal[
        "eligible",
        "source_missing",
        "source_superseded",
        "source_failed",
        "source_binding_invalid",
        "evidence_incomplete",
        "legacy_assignment_conflict",
        "unsupported_candidate_state",
    ]


class LineValidationCheck(LineAuthorityModel):
    code: str = Field(pattern=r"^[A-Za-z0-9_.:-]{1,100}$")
    status: Literal["passed", "failed", "warning", "not_applicable"]


class LineValidationSummary(LineAuthorityModel):
    recorded: bool
    needs_review: bool | None = Field(alias="needsReview")
    checks: list[LineValidationCheck]
    unrepresented_check_count: int = Field(alias="unrepresentedCheckCount", ge=0)


class LineCandidateRead(LineAuthorityModel):
    id: UUID
    document_id: UUID = Field(alias="documentId")
    extraction_id: UUID | None = Field(alias="extractionId")
    line_item_type: LineItemType = Field(alias="lineItemType")
    ordinal: Ordinal
    candidate_group: str | None = Field(alias="candidateGroup")
    candidate_version: UUID = Field(alias="candidateVersion")
    source_snapshot_sha256: Sha256 = Field(alias="sourceSnapshotSha256")
    candidate_decision_revision: UUID | None = Field(alias="candidateDecisionRevision")
    source_engine: str = Field(alias="sourceEngine")
    extraction: "LineExtractionIdentity | None"
    validation: LineValidationSummary
    code: str | None
    code_system: str | None = Field(alias="codeSystem")
    service_date: date | None = Field(alias="serviceDate")
    description: str | None
    quantity: ExactDecimal | None
    unit: str | None
    unit_price: ExactDecimal | None = Field(alias="unitPrice")
    gross_amount: ExactDecimal | None = Field(alias="grossAmount")
    discount_amount: ExactDecimal | None = Field(alias="discountAmount")
    tax_amount: ExactDecimal | None = Field(alias="taxAmount")
    net_amount: ExactDecimal | None = Field(alias="netAmount")
    allowed_amount: ExactDecimal | None = Field(alias="allowedAmount")
    plan_paid_amount: ExactDecimal | None = Field(alias="planPaidAmount")
    currency: str | None
    category_hint: str | None = Field(alias="categoryHint")
    evidence: list[LineEvidenceRef]
    status: str
    publication_eligibility: LinePublicationEligibility = Field(alias="publicationEligibility")
    source_assignment: LineSourceAssignment | None = Field(alias="sourceAssignment")
    suggested_vacant_target: VacantLineTarget | None = Field(alias="suggestedVacantTarget")


class LineCanonicalRead(LineAuthorityModel):
    id: UUID
    document_id: UUID = Field(alias="documentId")
    line_item_type: LineItemType = Field(alias="lineItemType")
    ordinal: int = Field(ge=1)
    selected_candidate_id: UUID | None = Field(alias="selectedCandidateId")
    code: str | None
    code_system: str | None = Field(alias="codeSystem")
    service_date: date | None = Field(alias="serviceDate")
    description: str | None
    quantity: ExactDecimal | None
    unit: str | None
    unit_price: ExactDecimal | None = Field(alias="unitPrice")
    gross_amount: ExactDecimal | None = Field(alias="grossAmount")
    discount_amount: ExactDecimal | None = Field(alias="discountAmount")
    tax_amount: ExactDecimal | None = Field(alias="taxAmount")
    net_amount: ExactDecimal | None = Field(alias="netAmount")
    allowed_amount: ExactDecimal | None = Field(default=None, alias="allowedAmount")
    plan_paid_amount: ExactDecimal | None = Field(default=None, alias="planPaidAmount")
    currency: str | None
    category_hint: str | None = Field(alias="categoryHint")
    source_kind: str = Field(alias="sourceKind")
    review_status: str = Field(alias="reviewStatus")
    evidence: list[LineEvidenceRef]
    validation: dict[str, Any]
    accepted_at: datetime | None = Field(alias="acceptedAt")
    updated_at: datetime = Field(alias="updatedAt")
    selected: bool


class CanonicalLineResponse(LineAuthorityModel):
    authority_version: Literal["line_item_authority.v1"] = Field(alias="authorityVersion")
    document_id: UUID = Field(alias="documentId")
    items: list[LineCanonicalRead]
    decisions: list[LineSlotDecision]
    source_assignments: list[LineSourceAssignment] = Field(alias="sourceAssignments")
    projection: FieldProjectionRevision


class LineDecisionResponse(LineAuthorityModel):
    operation: Literal["create", "replace", "reject_selected", "reject_candidate"]
    event_id: UUID = Field(alias="eventId")
    canonical_item: LineCanonicalRead | None = Field(alias="canonicalItem")
    candidate_decision: LineCandidateDecision | None = Field(alias="candidateDecision")
    line_decision: LineSlotDecision | None = Field(alias="lineDecision")
    projection: FieldProjectionRevision


class LineHistoricalCandidate(LineAuthorityModel):
    id: UUID
    document_id: UUID = Field(alias="documentId")
    extraction_id: UUID | None = Field(alias="extractionId")
    source_engine: str = Field(alias="sourceEngine")
    line_item_type: LineItemType = Field(alias="lineItemType")
    candidate_group: str | None = Field(alias="candidateGroup")
    ordinal: Ordinal
    code: str | None
    code_system: str | None = Field(alias="codeSystem")
    service_date: date | None = Field(alias="serviceDate")
    description: str | None
    quantity: ExactDecimal | None
    unit: str | None
    unit_price: ExactDecimal | None = Field(alias="unitPrice")
    gross_amount: ExactDecimal | None = Field(alias="grossAmount")
    discount_amount: ExactDecimal | None = Field(alias="discountAmount")
    tax_amount: ExactDecimal | None = Field(alias="taxAmount")
    net_amount: ExactDecimal | None = Field(alias="netAmount")
    allowed_amount: ExactDecimal | None = Field(alias="allowedAmount")
    plan_paid_amount: ExactDecimal | None = Field(alias="planPaidAmount")
    currency_code: str | None = Field(alias="currency")
    category_hint: str | None = Field(alias="categoryHint")


class LineExtractionIdentity(LineAuthorityModel):
    id: UUID
    document_id: UUID = Field(alias="documentId")
    schema_name: str = Field(alias="schemaName")
    schema_version: str = Field(alias="schemaVersion")
    source_engine: str = Field(alias="sourceEngine")
    model_name: str | None = Field(alias="modelName")
    model_version: str | None = Field(alias="modelVersion")
    prompt_version: str | None = Field(alias="promptVersion")
    extraction_scope: str = Field(alias="extractionScope")
    semantic_annotation_id: UUID | None = Field(alias="semanticAnnotationId")
    source_semantic_region_id: UUID | None = Field(alias="sourceSemanticRegionId")


class LineOriginalBinding(LineAuthorityModel):
    id: UUID
    sha256: Sha256


class LineSourceSnapshotRead(LineAuthorityModel):
    schema_version: Literal["line_item_source.v1"] = Field(alias="schemaVersion")
    candidate: LineHistoricalCandidate
    extraction: LineExtractionIdentity | None
    original: LineOriginalBinding | None
    evidence: list[LineEvidenceRef]
    validation_sha256: Sha256 = Field(alias="validationSha256")
    stored_evidence_sha256: Sha256 = Field(alias="storedEvidenceSha256")


class LineHistoryValue(LineAuthorityModel):
    canonical: LineCanonicalRead
    source: LineSourceSnapshotRead | None
    source_coverage: Literal["recorded", "legacy_unestablished"] = Field(alias="sourceCoverage")


class LineLegacySummary(LineAuthorityModel):
    description: str | None
    status: str | None
    net_amount: str | None = Field(alias="netAmount")
    precision: Literal["legacy_unestablished"] = "legacy_unestablished"


class LineHistoryEntry(LineAuthorityModel):
    id: UUID
    document_id: UUID = Field(alias="documentId")
    source_candidate_id: UUID | None = Field(alias="sourceCandidateId")
    canonical_line_item_id: UUID | None = Field(alias="canonicalLineItemId")
    operation: str
    coverage: Literal["complete", "legacy_partial"]
    before: LineHistoryValue | None
    after: LineHistoryValue | None
    source: LineSourceSnapshotRead | None
    legacy_summary: LineLegacySummary | None = Field(alias="legacySummary")
    actor_label: str = Field(alias="actorLabel")
    occurred_at: AwareDatetime = Field(alias="occurredAt")
    comment: str | None


class LineHistoryResponse(LineAuthorityModel):
    document_id: UUID = Field(alias="documentId")
    items: list[LineHistoryEntry]
    next_cursor: str | None = Field(alias="nextCursor")


class LineCandidateResponse(LineAuthorityModel):
    authority_version: Literal["line_item_authority.v1"] = Field(alias="authorityVersion")
    document_id: UUID = Field(alias="documentId")
    items: list[LineCandidateRead]

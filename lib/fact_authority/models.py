"""Immutable decision identities, independent revision expectations and read snapshots."""

from __future__ import annotations

from datetime import date
from typing import Annotated, Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator, model_validator


class AuthorityModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)


class FieldIdentity(AuthorityModel):
    document_id: UUID
    field_path: str = Field(min_length=1, pattern=r"\S")
    ordinal: int = Field(strict=True, gt=0, le=2147483647)


class RevisionExpectation(AuthorityModel):
    """Omission permits only a first decision; explicit null asserts absence."""

    supplied: bool = False
    revision: UUID | None = None

    @model_validator(mode="after")
    def consistent_presence(self) -> RevisionExpectation:
        if self.revision is not None and not self.supplied:
            raise ValueError("A revision must be marked as supplied.")
        return self


class CanonicalExpectation(AuthorityModel):
    supplied: bool = False
    updated_at: AwareDatetime | None = None

    @model_validator(mode="after")
    def consistent_presence(self) -> CanonicalExpectation:
        if self.updated_at is not None and not self.supplied:
            raise ValueError("A canonical revision must be marked as supplied.")
        return self


class FieldPreconditions(AuthorityModel):
    canonical: CanonicalExpectation = CanonicalExpectation()
    decision: RevisionExpectation = RevisionExpectation()
    path_guard: RevisionExpectation = RevisionExpectation()


class FieldDecision(AuthorityModel):
    id: UUID
    field: FieldIdentity
    revision: UUID
    disposition: Literal["confirmed", "corrected", "rejected", "protected_legacy"]
    origin: Literal["live_review", "legacy_current_field"]
    canonical_field_id: UUID | None
    review_event_id: UUID | None
    actor_user_id: UUID | None
    decided_at: AwareDatetime | None
    recorded_at: AwareDatetime

    @model_validator(mode="after")
    def live_decision_is_explicit(self) -> FieldDecision:
        if self.origin == "live_review" and (
            self.disposition == "protected_legacy" or self.decided_at is None
        ):
            raise ValueError("A live decision must be explicit.")
        return self


class FieldPathGuard(AuthorityModel):
    id: UUID
    document_id: UUID
    field_path: str = Field(min_length=1, pattern=r"\S")
    revision: UUID
    origin: Literal["legacy_path_rejection"] = "legacy_path_rejection"
    status: Literal["active", "resolved"]
    review_event_id: UUID | None
    actor_user_id: UUID | None


class CanonicalRevision(AuthorityModel):
    id: UUID
    updated_at: AwareDatetime
    human_controlled: bool
    review_status: Literal[
        "unreviewed",
        "auto_accepted",
        "needs_review",
        "user_confirmed",
        "user_corrected",
        "rejected",
    ]


class FieldAuthoritySnapshot(AuthorityModel):
    field: FieldIdentity
    canonical: CanonicalRevision | None
    decision: FieldDecision | None
    path_guard: FieldPathGuard | None

    @model_validator(mode="after")
    def exact_bindings(self) -> FieldAuthoritySnapshot:
        if self.decision and self.decision.field != self.field:
            raise ValueError("The decision must match the exact field identity.")
        if self.path_guard and (
            self.path_guard.document_id != self.field.document_id
            or self.path_guard.field_path != self.field.field_path
        ):
            raise ValueError("The path guard must match the document and path.")
        if (
            self.decision
            and self.decision.canonical_field_id is not None
            and (self.canonical is None or self.decision.canonical_field_id != self.canonical.id)
        ):
            raise ValueError("The decision must reference the selected canonical row.")
        return self


DocumentFamily = Literal[
    "generic",
    "receipt",
    "invoice",
    "medical_eob",
    "medical_bill",
    "insurance_document",
    "legal_contract",
    "legal_notice",
    "tax_document",
    "warranty",
    "identity_document",
    "bank_statement",
    "financial_statement",
    "handwritten_note",
    "typed_note",
    "whitepaper",
    "reference_document",
]


class ManualClassification(AuthorityModel):
    property: Literal["classification"] = "classification"
    family: DocumentFamily
    subtype: str | None


class ManualDocumentDate(AuthorityModel):
    property: Literal["document_date"] = "document_date"
    # Required even when null: clearing a date is a decision, not an omitted edit.
    value: date | None

    @field_validator("value", mode="before")
    @classmethod
    def explicit_calendar_date(cls, value: object) -> object:
        if value is not None and type(value) not in (str, date):
            raise ValueError("A manual date must be an ISO calendar date or an explicit clear.")
        if isinstance(value, str):
            parsed = date.fromisoformat(value)
            if parsed.isoformat() != value:
                raise ValueError("A manual date must use YYYY-MM-DD.")
        return value


ManualMetadataValue = Annotated[
    ManualClassification | ManualDocumentDate, Field(discriminator="property")
]


class MetadataDecision(AuthorityModel):
    id: UUID
    document_id: UUID
    revision: UUID
    value_schema_version: Literal["manual_metadata.v1"] = "manual_metadata.v1"
    value: ManualMetadataValue
    origin: Literal["live_review", "legacy_matching_review", "legacy_matching_filing"]
    review_event_id: UUID | None
    audit_event_id: Annotated[int, Field(strict=True, gt=0)] | None
    actor_user_id: UUID | None
    decided_at: AwareDatetime | None
    recorded_at: AwareDatetime

    @model_validator(mode="after")
    def exact_event_kind(self) -> MetadataDecision:
        if self.origin == "live_review" and self.decided_at is None:
            raise ValueError("A live metadata decision requires its decision time.")
        if self.value.property == "classification" and self.audit_event_id is not None:
            raise ValueError("Classification decisions use review events.")
        if self.value.property == "document_date" and self.review_event_id is not None:
            raise ValueError("Date decisions use organization audit events.")
        return self


Sha256 = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]


class ProjectionRevision(AuthorityModel):
    schema_version: Literal["accepted_fact_projection.v1"] = "accepted_fact_projection.v1"
    document_id: UUID
    state: Literal["unestablished", "current"]
    accepted_fact_revision: int = Field(strict=True, ge=0)
    projection_revision: int = Field(strict=True, ge=0)
    accepted_facts_sha256: Sha256 | None
    indexed_metadata_sha256: Sha256 | None
    accepted_fact_basis_schema_version: Literal[
        "accepted_fields.v1", "accepted_fields_and_lines.v1"
    ] = "accepted_fields.v1"

    @model_validator(mode="after")
    def truthful_revision(self) -> ProjectionRevision:
        if self.state == "unestablished":
            if (
                self.accepted_fact_revision != 0
                or self.projection_revision != 0
                or self.accepted_facts_sha256 is not None
                or self.indexed_metadata_sha256 is not None
            ):
                raise ValueError("Unestablished projections cannot claim a verified revision.")
        elif (
            self.accepted_fact_revision <= 0
            or self.projection_revision < self.accepted_fact_revision
            or self.accepted_facts_sha256 is None
            or self.indexed_metadata_sha256 is None
        ):
            raise ValueError("Current projections require established revisions and hashes.")
        return self

    @property
    def verified_fact_revision(self) -> int | None:
        return self.accepted_fact_revision if self.state == "current" else None

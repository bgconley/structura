from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator

SourceEngine = Literal[
    "docling",
    "qwen3_vl_4b",
    "qwen3_vl_8b",
    "granite_vision_3b",
    "validator",
    "human",
    "system",
]


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class TextSpan(ContractModel):
    start: int = Field(ge=0)
    end: int = Field(ge=0)
    basis: Literal["page_text", "chunk_text", "element_text", "raw_model_output"] | None = None


class EvidenceRef(ContractModel):
    page_number: int = Field(alias="pageNumber", ge=1)
    source_engine: SourceEngine = Field(alias="sourceEngine")
    bbox: tuple[float, float, float, float] | None = None
    element_id: UUID | None = Field(default=None, alias="elementId")
    table_id: UUID | None = Field(default=None, alias="tableId")
    row_index: int | None = Field(default=None, alias="rowIndex", ge=0)
    column_index: int | None = Field(default=None, alias="columnIndex", ge=0)
    source_text: str | None = Field(default=None, alias="sourceText")
    text_span: TextSpan | None = Field(default=None, alias="textSpan")
    confidence: float | None = None

    @model_validator(mode="after")
    def require_concrete_locator(self) -> EvidenceRef:
        has_locator = any(
            [
                self.bbox is not None,
                self.element_id is not None,
                self.table_id is not None and self.row_index is not None,
                self.text_span is not None,
                self.source_text is not None,
            ]
        )
        if not has_locator:
            raise ValueError("EvidenceRef requires a concrete locator")
        return self


class UploadDocumentMultipartRequest(ContractModel):
    file: str
    source: Literal[
        "web_upload",
        "api_upload",
        "mobile_scan",
        "watched_folder",
        "email_import",
        "bulk_import",
    ]
    supplied_title: str | None = Field(default=None, alias="suppliedTitle")
    supplied_folder_ids: list[UUID] | None = Field(default=None, alias="suppliedFolderIds")
    supplied_tags: list[str] | None = Field(default=None, alias="suppliedTags")
    hints_json: str | None = Field(default=None, alias="hintsJson")


class PasswordSessionRequest(ContractModel):
    method: Literal["password"]
    email: EmailStr
    password: str = Field(min_length=8)
    household_id: UUID | None = Field(default=None, alias="householdId")


class MagicLinkSessionRequest(ContractModel):
    method: Literal["magic_link"]
    magic_link_token: str = Field(alias="magicLinkToken", min_length=1)
    household_id: UUID | None = Field(default=None, alias="householdId")


CreateSessionRequest = Annotated[
    PasswordSessionRequest | MagicLinkSessionRequest,
    Field(discriminator="method"),
]


class SessionInfo(ContractModel):
    session_id: UUID = Field(alias="sessionId")
    user_id: UUID = Field(alias="userId")
    is_authenticated: bool = Field(alias="isAuthenticated")
    auth_method: Literal["password", "magic_link", "webauthn"] = Field(alias="authMethod")
    household_id: UUID | None = Field(default=None, alias="householdId")
    display_name: str | None = Field(default=None, alias="displayName")
    email: EmailStr | None = None
    expires_at: datetime | None = Field(default=None, alias="expiresAt")
    password_rotation_required: bool | None = Field(
        default=None,
        alias="passwordRotationRequired",
    )
    session_cookie_name: str = Field(default="structura_session", alias="sessionCookieName")
    csrf_cookie_name: str = Field(default="structura_csrf", alias="csrfCookieName")


class FieldCandidate(ContractModel):
    id: UUID
    document_id: UUID = Field(alias="documentId")
    field_path: str = Field(alias="fieldPath")
    value_type: str = Field(alias="valueType")
    source_engine: SourceEngine = Field(alias="sourceEngine")
    evidence: list[EvidenceRef] = Field(min_length=1)
    extraction_id: UUID | None = Field(default=None, alias="extractionId")
    ordinal: int | None = None
    value: Any = None
    normalized_value: Any = Field(default=None, alias="normalizedValue")
    currency: str | None = None
    confidence: float | None = None
    authority_weight: float | None = Field(default=None, alias="authorityWeight")
    validation: dict[str, Any] | None = None
    status: str | None = None


class CanonicalField(ContractModel):
    id: UUID
    document_id: UUID = Field(alias="documentId")
    field_path: str = Field(alias="fieldPath")
    value_type: str = Field(alias="valueType")
    value: Any
    source_kind: Literal["candidate", "validator", "human", "system"] = Field(alias="sourceKind")
    review_status: str = Field(alias="reviewStatus")
    evidence: list[EvidenceRef] = Field(min_length=1)
    selected_candidate_id: UUID | None = Field(default=None, alias="selectedCandidateId")
    ordinal: int | None = None
    currency: str | None = None
    validation: dict[str, Any] | None = None
    accepted_at: datetime | None = Field(default=None, alias="acceptedAt")


class CanonicalFieldWrite(ContractModel):
    selected_candidate_id: UUID | None = Field(default=None, alias="selectedCandidateId")
    field_path: str = Field(alias="fieldPath")
    ordinal: int = 1
    value_type: str = Field(alias="valueType")
    value: Any
    currency: str | None = None
    source_kind: Literal["candidate", "validator", "human", "system"] = Field(alias="sourceKind")
    evidence: list[EvidenceRef] = Field(min_length=1)
    reason: str | None = None


class ReviewActionRequest(ContractModel):
    schema_name: Literal["review_action"] = Field(default="review_action", alias="schemaName")
    schema_version: Literal["v1"] = Field(default="v1", alias="schemaVersion")
    document_id: UUID = Field(alias="documentId")
    review_task_id: UUID | None = Field(default=None, alias="reviewTaskId")
    action_type: Literal[
        "confirm_field",
        "correct_field",
        "reject_field",
        "reclassify_document",
        "rerun_extraction",
        "mark_done",
    ] = Field(alias="actionType")
    actor_type: Literal["human", "system", "agent"] = Field(default="human", alias="actorType")
    field_path: str | None = Field(default=None, alias="fieldPath")
    old_value: Any = Field(default=None, alias="oldValue")
    new_value: Any = Field(default=None, alias="newValue")
    comment: str | None = None
    evidence_context: list[EvidenceRef] | None = Field(default=None, alias="evidenceContext")
    metadata: dict[str, Any] | None = None
    created_at: datetime | None = Field(default=None, alias="createdAt")


class FilingRule(ContractModel):
    id: UUID
    name: str
    enabled: bool
    conditions: list[dict[str, Any]]
    actions: list[dict[str, Any]]
    priority: int | None = None
    review_required: bool | None = Field(default=None, alias="reviewRequired")


class CreateMagicLinkRequest(ContractModel):
    email: EmailStr
    purpose: Literal["bootstrap", "invite", "recovery"]
    household_id: UUID | None = Field(default=None, alias="householdId")


class ReviewTask(ContractModel):
    id: UUID
    document_id: UUID = Field(alias="documentId")
    task_type: str = Field(alias="taskType")
    status: str
    priority: int
    page_number: int | None = Field(default=None, alias="pageNumber")
    field_path: str | None = Field(default=None, alias="fieldPath")
    rationale: str | None = None


class AcceptedJob(ContractModel):
    job_id: UUID = Field(alias="jobId")
    status: Literal["queued", "running"]


class DocumentSummary(ContractModel):
    id: UUID
    title: str
    family: str
    lifecycle_state: str = Field(alias="lifecycleState")
    review_status: str = Field(alias="reviewStatus")
    created_at: datetime = Field(alias="createdAt")
    document_date: date | None = Field(default=None, alias="documentDate")
    amount_total: float | None = Field(default=None, alias="amountTotal")
    counterparty_display: str | None = Field(default=None, alias="counterpartyDisplay")
    thumbnail_url: str | None = Field(default=None, alias="thumbnailUrl")
    folder_paths: list[str] = Field(default_factory=list, alias="folderPaths")
    tags: list[str] = Field(default_factory=list)


class DocumentAsset(ContractModel):
    id: UUID
    asset_role: str = Field(alias="assetRole")
    mime_type: str = Field(alias="mimeType")
    asset_url: str = Field(alias="assetUrl")
    page_number: int | None = Field(default=None, alias="pageNumber")
    sha256: str | None = None


class DocumentPage(ContractModel):
    page_number: int = Field(alias="pageNumber", ge=1)
    width: float | None = None
    height: float | None = None
    rotation_degrees: int | None = Field(default=None, alias="rotationDegrees")
    text_content: str | None = Field(default=None, alias="textContent")
    image_url: str | None = Field(default=None, alias="imageUrl")


class DocumentDetail(DocumentSummary):
    pages: list[DocumentPage]
    assets: list[DocumentAsset]
    extractions: list[dict[str, Any]]
    relationships: list[dict[str, Any]]
    fields: list[dict[str, Any]]
    line_items: list[dict[str, Any]] = Field(alias="lineItems")
    tags: list[str] = Field(default_factory=list)
    description: str | None = None
    folder_ids: list[UUID] = Field(default_factory=list, alias="folderIds")
    primary_folder_id: UUID | None = Field(default=None, alias="primaryFolderId")
    filing_notes: str | None = Field(default=None, alias="filingNotes")


class SearchRequest(ContractModel):
    query: str = Field(min_length=1, max_length=500)
    mode: Literal["lexical", "semantic", "hybrid"] = "hybrid"
    families: list[str] = Field(default_factory=list)
    folder_ids: list[UUID] = Field(default_factory=list, alias="folderIds")
    tags: list[str] = Field(default_factory=list)
    reviewed_only: bool | None = Field(default=None, alias="reviewedOnly")
    date_from: date | None = Field(default=None, alias="dateFrom")
    date_to: date | None = Field(default=None, alias="dateTo")
    amount_min: Decimal | None = Field(default=None, alias="amountMin")
    amount_max: Decimal | None = Field(default=None, alias="amountMax")
    sensitivity: list[
        Literal["normal", "pii", "financial", "medical", "legal", "highly_sensitive"]
    ] = Field(default_factory=list)
    primary_folder_only: bool = Field(default=False, alias="primaryFolderOnly")
    limit: int = Field(default=25, ge=1, le=100)
    include_debug: bool = Field(default=False, alias="includeDebug")

    @model_validator(mode="after")
    def normalize_search_request(self) -> SearchRequest:
        self.query = self.query.strip()
        if not self.query:
            raise ValueError("query must not be blank")
        self.families = [_trimmed(value) for value in self.families if _trimmed(value)]
        self.tags = [_trimmed(value) for value in self.tags if _trimmed(value)]
        return self


class SearchResult(ContractModel):
    document_id: UUID = Field(alias="documentId")
    title: str
    rank: int = Field(ge=1)
    family: str | None = None
    score: float | None = None
    snippet: str | None = None
    matched_chunk_id: UUID | None = Field(default=None, alias="matchedChunkId")
    page_number: int | None = Field(default=None, alias="pageNumber", ge=1)
    evidence: list[EvidenceRef] = Field(default_factory=list)
    explanation: str | None = None
    counterparty_display: str | None = Field(default=None, alias="counterpartyDisplay")
    document_date: date | None = Field(default=None, alias="documentDate")
    amount_total: float | None = Field(default=None, alias="amountTotal")
    folder_paths: list[str] = Field(default_factory=list, alias="folderPaths")
    tags: list[str] = Field(default_factory=list)


class SearchResponse(ContractModel):
    items: list[SearchResult]
    facets: dict[str, dict[str, int]] = Field(default_factory=dict)
    debug: dict[str, Any] | None = None


class SavedSearch(ContractModel):
    id: UUID
    name: str
    query: str = Field(alias="queryText")
    filters: dict[str, Any] = Field(default_factory=dict)
    sort: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(alias="createdAt")


class SavedSearchWrite(ContractModel):
    name: str = Field(min_length=1, max_length=120)
    query: str = Field(alias="queryText", min_length=1, max_length=500)
    filters: dict[str, Any] = Field(default_factory=dict)
    sort: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def normalize_saved_search(self) -> SavedSearchWrite:
        self.name = self.name.strip()
        self.query = self.query.strip()
        if not self.name:
            raise ValueError("name must not be blank")
        if not self.query:
            raise ValueError("queryText must not be blank")
        return self


def _trimmed(value: str) -> str:
    return value.strip()


class Folder(ContractModel):
    id: UUID
    name: str
    folder_kind: Literal["manual", "smart"] = Field(alias="folderKind")
    parent_id: UUID | None = Field(default=None, alias="parentId")
    path: str | None = None
    saved_query: dict[str, Any] | None = Field(default=None, alias="savedQuery")
    acl_mode: Literal["private", "household", "custom"] | None = Field(
        default=None,
        alias="aclMode",
    )


class FolderWrite(ContractModel):
    name: str = Field(min_length=1, max_length=120)
    folder_kind: Literal["manual", "smart"] = Field(alias="folderKind")
    parent_id: UUID | None = Field(default=None, alias="parentId")
    description: str | None = Field(default=None, max_length=500)
    saved_query: dict[str, Any] | None = Field(default=None, alias="savedQuery")
    acl_mode: Literal["private", "household", "custom"] | None = Field(
        default=None,
        alias="aclMode",
    )


class Tag(ContractModel):
    id: UUID
    name: str
    color_hex: str | None = Field(default=None, alias="colorHex")
    description: str | None = None


class TagWrite(ContractModel):
    name: str = Field(min_length=1, max_length=80)
    color_hex: str | None = Field(default=None, alias="colorHex")
    description: str | None = Field(default=None, max_length=500)


class DocumentOrganizationWrite(ContractModel):
    title: str | None = Field(default=None, min_length=1, max_length=240)
    document_date: date | None = Field(default=None, alias="documentDate")
    folder_ids: list[UUID] | None = Field(default=None, alias="folderIds", max_length=50)
    primary_folder_id: UUID | None = Field(default=None, alias="primaryFolderId")
    tags: list[str] | None = Field(default=None, max_length=50)
    filing_notes: str | None = Field(default=None, alias="filingNotes", max_length=4000)


class JobState(ContractModel):
    job_id: UUID = Field(alias="jobId")
    job_type: str = Field(alias="jobType")
    status: str
    created_at: datetime = Field(alias="createdAt")
    started_at: datetime | None = Field(default=None, alias="startedAt")
    finished_at: datetime | None = Field(default=None, alias="finishedAt")
    error_message: str | None = Field(default=None, alias="errorMessage")
    result: dict[str, Any] | None = None

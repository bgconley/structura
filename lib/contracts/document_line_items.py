"""Read-only canonical line-item values; decimal strings retain database precision."""

from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Any
from uuid import UUID

from pydantic import Field

from lib.contracts.models import ContractModel

ExactDecimal = Annotated[Decimal, Field(max_digits=18, decimal_places=4, allow_inf_nan=False)]


class CanonicalLineItemRead(ContractModel):
    id: UUID
    document_id: UUID = Field(alias="documentId")
    line_item_type: str = Field(alias="lineItemType")
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
    currency: str | None
    category_hint: str | None = Field(alias="categoryHint")
    source_kind: str = Field(alias="sourceKind")
    review_status: str = Field(alias="reviewStatus")
    evidence: list[dict[str, Any]]
    validation: dict[str, Any]
    accepted_at: datetime | None = Field(alias="acceptedAt")
    updated_at: datetime = Field(alias="updatedAt")

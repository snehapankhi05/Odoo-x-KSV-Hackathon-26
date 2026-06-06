from datetime import datetime
from decimal import Decimal
from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


# ── RFQ ITEM SCHEMAS ───────────────────────────────────────────────────
class RFQItemBase(BaseModel):
    item_name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    quantity: Decimal = Field(..., gt=0)
    unit_of_measure: str = Field(..., min_length=1, max_length=30)


class RFQItemCreate(RFQItemBase):
    pass


class RFQItemUpdate(BaseModel):
    item_name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    quantity: Optional[Decimal] = Field(None, gt=0)
    unit_of_measure: Optional[str] = Field(None, min_length=1, max_length=30)


class RFQItemResponse(RFQItemBase):
    rfq_item_id: UUID
    rfq_id: UUID

    model_config = ConfigDict(from_attributes=True)


# ── RFQ VENDOR SCHEMAS ─────────────────────────────────────────────────
class RFQVendorBase(BaseModel):
    rfq_id: UUID
    vendor_id: UUID


class RFQVendorCreate(RFQVendorBase):
    pass


class RFQVendorResponse(RFQVendorBase):
    assigned_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ── RFQ SCHEMAS ────────────────────────────────────────────────────────
class RFQBase(BaseModel):
    status: Literal["draft", "open", "closed", "cancelled"] = "draft"
    deadline: datetime


class RFQCreate(RFQBase):
    created_by_id: UUID
    items: list[RFQItemCreate]


class RFQUpdate(BaseModel):
    status: Optional[Literal["draft", "open", "closed", "cancelled"]] = None
    deadline: Optional[datetime] = None


class RFQResponse(RFQBase):
    rfq_id: UUID
    doc_number: str
    created_by_id: UUID
    created_at: datetime
    updated_at: datetime
    items: list[RFQItemResponse] = []
    vendor_assignments: list[RFQVendorResponse] = []

    model_config = ConfigDict(from_attributes=True)


class RFQListResponse(BaseModel):
    rfqs: list[RFQResponse]
    total: int

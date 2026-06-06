from datetime import datetime
from decimal import Decimal
from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


# ── QUOTATION ITEM SCHEMAS ─────────────────────────────────────────────
class QuotationItemBase(BaseModel):
    rfq_item_id: UUID
    unit_price: Decimal = Field(..., ge=0)
    quantity: Decimal = Field(..., gt=0)
    total_price: Decimal = Field(..., ge=0)


class QuotationItemCreate(QuotationItemBase):
    pass


class QuotationItemUpdate(BaseModel):
    unit_price: Optional[Decimal] = Field(None, ge=0)
    quantity: Optional[Decimal] = Field(None, gt=0)
    total_price: Optional[Decimal] = Field(None, ge=0)


class QuotationItemResponse(QuotationItemBase):
    quotation_item_id: UUID
    quotation_id: UUID

    model_config = ConfigDict(from_attributes=True)


# ── QUOTATION SCHEMAS ──────────────────────────────────────────────────
class QuotationBase(BaseModel):
    status: Literal["draft", "submitted", "selected", "rejected"] = "draft"
    total_amount: Decimal = Field(default=Decimal("0.00"), ge=0)
    delivery_timeline: Optional[str] = Field(None, max_length=100)
    notes: Optional[str] = None


class QuotationCreate(QuotationBase):
    rfq_id: UUID
    vendor_id: UUID
    items: list[QuotationItemCreate]


class QuotationUpdate(BaseModel):
    status: Optional[Literal["draft", "submitted", "selected", "rejected"]] = None
    total_amount: Optional[Decimal] = Field(None, ge=0)
    delivery_timeline: Optional[str] = Field(None, max_length=100)
    notes: Optional[str] = None


class QuotationResponse(QuotationBase):
    quotation_id: UUID
    doc_number: str
    rfq_id: UUID
    vendor_id: UUID
    created_at: datetime
    updated_at: datetime
    items: list[QuotationItemResponse] = []

    model_config = ConfigDict(from_attributes=True)


class QuotationListResponse(BaseModel):
    quotations: list[QuotationResponse]
    total: int

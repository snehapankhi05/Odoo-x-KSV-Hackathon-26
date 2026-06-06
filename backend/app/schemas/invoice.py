from datetime import datetime
from decimal import Decimal
from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


# ── INVOICE ITEM SCHEMAS ───────────────────────────────────────────────
class InvoiceItemBase(BaseModel):
    item_name: str = Field(..., min_length=1, max_length=255)
    quantity: Decimal = Field(..., gt=0)
    unit_price: Decimal = Field(..., ge=0)
    total_price: Decimal = Field(..., ge=0)


class InvoiceItemCreate(InvoiceItemBase):
    pass


class InvoiceItemResponse(InvoiceItemBase):
    invoice_item_id: UUID
    invoice_id: UUID

    model_config = ConfigDict(from_attributes=True)


# ── INVOICE SCHEMAS ────────────────────────────────────────────────────
class InvoiceBase(BaseModel):
    status: Literal["draft", "generated", "sent", "paid", "cancelled", "pending"] = "pending"
    amount_due: Decimal = Field(..., ge=0)
    currency: str = Field(default="USD", min_length=3, max_length=3)
    is_locked: bool = False


class InvoiceCreate(InvoiceBase):
    po_id: UUID
    vendor_id: UUID
    created_by_id: UUID
    items: list[InvoiceItemCreate]


class InvoiceUpdate(BaseModel):
    status: Optional[Literal["draft", "generated", "sent", "paid", "cancelled", "pending"]] = None
    amount_due: Optional[Decimal] = Field(None, ge=0)
    currency: Optional[str] = Field(None, min_length=3, max_length=3)
    is_locked: Optional[bool] = None


class InvoiceResponse(InvoiceBase):
    invoice_id: UUID
    doc_number: str
    po_id: UUID
    vendor_id: UUID
    created_by_id: UUID
    created_at: datetime
    updated_at: datetime
    items: list[InvoiceItemResponse] = []

    model_config = ConfigDict(from_attributes=True)


class InvoiceListResponse(BaseModel):
    invoices: list[InvoiceResponse]
    total: int


class InvoiceCreateRequest(BaseModel):
    po_id: UUID


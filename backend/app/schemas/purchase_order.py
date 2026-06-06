from datetime import datetime
from decimal import Decimal
from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


# ── PURCHASE ORDER ITEM SCHEMAS ────────────────────────────────────────
class PurchaseOrderItemBase(BaseModel):
    item_name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    quantity: Decimal = Field(..., gt=0)
    unit_price: Decimal = Field(..., ge=0)
    total_price: Decimal = Field(..., ge=0)


class PurchaseOrderItemCreate(PurchaseOrderItemBase):
    pass


class PurchaseOrderItemResponse(PurchaseOrderItemBase):
    po_item_id: UUID
    po_id: UUID

    model_config = ConfigDict(from_attributes=True)


# ── PURCHASE ORDER SCHEMAS ─────────────────────────────────────────────
class PurchaseOrderBase(BaseModel):
    status: Literal["generated", "completed", "cancelled"] = "generated"
    total_amount: Decimal = Field(..., ge=0)
    currency: str = Field(default="USD", min_length=3, max_length=3)
    tax_rate: Decimal = Field(default=Decimal("0.00"), ge=0, le=100)
    is_locked: bool = False


class PurchaseOrderCreate(PurchaseOrderBase):
    quotation_id: UUID
    created_by_id: UUID
    items: list[PurchaseOrderItemCreate]


class PurchaseOrderUpdate(BaseModel):
    status: Optional[Literal["generated", "completed", "cancelled"]] = None
    total_amount: Optional[Decimal] = Field(None, ge=0)
    currency: Optional[str] = Field(None, min_length=3, max_length=3)
    tax_rate: Optional[Decimal] = Field(None, ge=0, le=100)
    is_locked: Optional[bool] = None


class PurchaseOrderResponse(PurchaseOrderBase):
    po_id: UUID
    doc_number: str
    quotation_id: UUID
    created_by_id: UUID
    created_at: datetime
    updated_at: datetime
    items: list[PurchaseOrderItemResponse] = []

    model_config = ConfigDict(from_attributes=True)


class PurchaseOrderListResponse(BaseModel):
    purchase_orders: list[PurchaseOrderResponse]
    total: int

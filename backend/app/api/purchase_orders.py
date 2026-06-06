from datetime import datetime, timezone
from decimal import Decimal
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import (
    get_current_user,
    require_officer,
)
from app.models.purchase_order import PurchaseOrder, PurchaseOrderItem
from app.models.quotation import Quotation
from app.models.approval import Approval
from app.models.user import User
from app.models.vendor import Vendor
from app.models.activity_log import ActivityLog
from app.models.notification import Notification
from app.schemas.purchase_order import (
    PurchaseOrderResponse,
    PurchaseOrderListResponse,
    PurchaseOrderCreateRequest,
    PurchaseOrderUpdate,
)

router = APIRouter()


# ── ENDPOINTS IMPLEMENTATION ───────────────────────────────────────────

@router.post(
    "",
    response_model=PurchaseOrderResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Generate a Purchase Order",
    description="Generates a Purchase Order from an approved quotation. Restricted to Officers.",
)
def create_purchase_order(
    payload: PurchaseOrderCreateRequest,
    request: Request,
    current_user: User = Depends(require_officer),
    db: Session = Depends(get_db),
):
    # 1. Verify Quotation exists and is active
    quotation = db.query(Quotation).filter(
        Quotation.quotation_id == payload.quotation_id,
        Quotation.deleted_at.is_(None)
    ).first()
    if not quotation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Quotation not found",
        )

    # 2. Check if Quotation is APPROVED
    approval = db.query(Approval).filter(
        Approval.quotation_id == payload.quotation_id,
        Approval.status == "approved"
    ).first()
    if not approval:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only approved quotations can generate a Purchase Order",
        )

    # 3. Check duplicate PO constraint: One PO per quotation
    existing_po = db.query(PurchaseOrder).filter(
        PurchaseOrder.quotation_id == payload.quotation_id,
        PurchaseOrder.deleted_at.is_(None)
    ).first()
    if existing_po:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A Purchase Order has already been generated for this quotation",
        )

    # 4. Create Purchase Order (doc_number set to "" for DB trigger population)
    po = PurchaseOrder(
        doc_number="",
        quotation_id=payload.quotation_id,
        created_by_id=current_user.user_id,
        status="generated",
        tax_rate=payload.tax_rate,
        currency=payload.currency or "USD",
        total_amount=Decimal("0.00"),  # Calculated below
    )
    db.add(po)
    db.flush()

    # 5. Copy award quotation items to PO items snapshot
    total_amount = Decimal("0.00")
    for item in quotation.items:
        # Resolve item name/description from RFQ item relation
        item_name = item.rfq_item.item_name if item.rfq_item else "Unknown Item"
        description = item.rfq_item.description if item.rfq_item else None
        
        po_item = PurchaseOrderItem(
            po_id=po.po_id,
            item_name=item_name,
            description=description,
            quantity=item.quantity,
            unit_price=item.unit_price,
            total_price=item.total_price,
        )
        db.add(po_item)
        total_amount += item.total_price

    # 6. Apply tax rate calculation to total amount
    tax_multiplier = Decimal("1.00") + (payload.tax_rate / Decimal("100.00"))
    po.total_amount = total_amount * tax_multiplier

    # 7. Log activity: Purchase Order Generated
    log = ActivityLog(
        user_id=current_user.user_id,
        action="Purchase Order Generated",
        entity_name="purchase_orders",
        entity_id=po.po_id,
        ip_address=request.client.host if request.client else None,
    )
    db.add(log)

    db.commit()
    db.refresh(po)
    return po


@router.get(
    "",
    response_model=PurchaseOrderListResponse,
    summary="List and filter Purchase Orders",
    description="Retrieve purchase orders with status filtering, search queries, and pagination. Restricts visibility based on roles.",
)
def list_purchase_orders(
    status_filter: Optional[str] = None,
    search: Optional[str] = None,
    skip: int = 0,
    limit: int = 100,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    query = db.query(PurchaseOrder).filter(PurchaseOrder.deleted_at.is_(None))

    # Vendor role visibility restriction
    if current_user.role == "vendor":
        vendor = db.query(Vendor).filter(Vendor.user_id == current_user.user_id).first()
        if not vendor:
            return PurchaseOrderListResponse(purchase_orders=[], total=0)
        query = query.join(Quotation).filter(Quotation.vendor_id == vendor.vendor_id)

    if status_filter:
        query = query.filter(PurchaseOrder.status == status_filter)

    if search:
        search_query = f"%{search}%"
        # Search by PO doc_number
        query = query.filter(PurchaseOrder.doc_number.ilike(search_query))

    total = query.count()
    purchase_orders = query.offset(skip).limit(limit).all()

    return PurchaseOrderListResponse(purchase_orders=purchase_orders, total=total)


@router.get(
    "/{id}",
    response_model=PurchaseOrderResponse,
    summary="Get Purchase Order details by ID",
    description="Retrieves a single Purchase Order by its UUID. Restricts visibility based on roles.",
)
def get_purchase_order_by_id(
    id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    po = db.query(PurchaseOrder).filter(PurchaseOrder.po_id == id, PurchaseOrder.deleted_at.is_(None)).first()
    if not po:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Purchase Order not found",
        )

    # Vendor validation
    if current_user.role == "vendor":
        vendor = db.query(Vendor).filter(Vendor.user_id == current_user.user_id).first()
        if not vendor or po.quotation.vendor_id != vendor.vendor_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You are not authorized to view this Purchase Order",
            )

    return po


@router.patch(
    "/{id}",
    response_model=PurchaseOrderResponse,
    summary="Update Purchase Order status or details",
    description="Enables Officers to update PO details or status, or Vendors to accept the PO.",
)
def update_purchase_order(
    id: UUID,
    payload: PurchaseOrderUpdate,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    po = db.query(PurchaseOrder).filter(PurchaseOrder.po_id == id, PurchaseOrder.deleted_at.is_(None)).first()
    if not po:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Purchase Order not found",
        )

    # Vendor validation: Can only change status to "accepted"
    if current_user.role == "vendor":
        vendor = db.query(Vendor).filter(Vendor.user_id == current_user.user_id).first()
        if not vendor or po.quotation.vendor_id != vendor.vendor_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You are not authorized to access this Purchase Order",
            )
        
        # Enforce Vendor can ONLY update status and ONLY to "accepted"
        if payload.status != "accepted":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Vendors are only permitted to accept the Purchase Order",
            )
        
        # Vendor accepts PO
        po.status = "accepted"
        
        # Notify Officer
        officer_notif = Notification(
            user_id=po.created_by_id,
            type="info",
            title="Purchase Order Accepted",
            message=f"Vendor {vendor.company_name} has accepted Purchase Order {po.doc_number}.",
        )
        db.add(officer_notif)

    elif current_user.role == "officer":
        # Officer can update status, tax_rate, total_amount, currency, etc.
        if payload.status is not None:
            po.status = payload.status
        if payload.currency is not None:
            po.currency = payload.currency
        if payload.tax_rate is not None:
            po.tax_rate = payload.tax_rate
            # Recalculate total amount if tax_rate changed
            base_amount = sum(item.total_price for item in po.items)
            po.total_amount = base_amount * (Decimal("1.00") + (po.tax_rate / Decimal("100.00")))
        if payload.is_locked is not None:
            po.is_locked = payload.is_locked

    else:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to update this Purchase Order",
        )

    db.commit()
    db.refresh(po)
    return po


@router.patch(
    "/{id}/send",
    response_model=PurchaseOrderResponse,
    summary="Send Purchase Order to vendor",
    description="Updates PO status to 'sent' and notifies the vendor. Officer only.",
)
def send_purchase_order(
    id: UUID,
    request: Request,
    current_user: User = Depends(require_officer),
    db: Session = Depends(get_db),
):
    po = db.query(PurchaseOrder).filter(PurchaseOrder.po_id == id, PurchaseOrder.deleted_at.is_(None)).first()
    if not po:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Purchase Order not found",
        )

    po.status = "sent"

    # Send Notification to Vendor
    vendor = db.query(Vendor).filter(Vendor.vendor_id == po.quotation.vendor_id).first()
    if vendor:
        vendor_notif = Notification(
            user_id=vendor.user_id,
            type="info",
            title="Purchase Order Received",
            message=f"You have received Purchase Order {po.doc_number} for RFQ {po.quotation.rfq.doc_number}.",
        )
        db.add(vendor_notif)

    # Log activity: Purchase Order Sent
    log = ActivityLog(
        user_id=current_user.user_id,
        action="Purchase Order Sent",
        entity_name="purchase_orders",
        entity_id=po.po_id,
        ip_address=request.client.host if request.client else None,
    )
    db.add(log)

    db.commit()
    db.refresh(po)
    return po


@router.patch(
    "/{id}/complete",
    response_model=PurchaseOrderResponse,
    summary="Mark Purchase Order as completed",
    description="Updates PO status to 'completed'. Officer only.",
)
def complete_purchase_order(
    id: UUID,
    request: Request,
    current_user: User = Depends(require_officer),
    db: Session = Depends(get_db),
):
    po = db.query(PurchaseOrder).filter(PurchaseOrder.po_id == id, PurchaseOrder.deleted_at.is_(None)).first()
    if not po:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Purchase Order not found",
        )

    po.status = "completed"

    # Log activity: Purchase Order Completed
    log = ActivityLog(
        user_id=current_user.user_id,
        action="Purchase Order Completed",
        entity_name="purchase_orders",
        entity_id=po.po_id,
        ip_address=request.client.host if request.client else None,
    )
    db.add(log)

    db.commit()
    db.refresh(po)
    return po

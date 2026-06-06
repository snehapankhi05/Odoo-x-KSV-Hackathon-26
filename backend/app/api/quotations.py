import random
from datetime import datetime, timezone
from decimal import Decimal
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import (
    get_current_user,
    require_admin,
    require_manager,
    require_officer,
    require_vendor,
)
from app.models.activity_log import ActivityLog
from app.models.notification import Notification
from app.models.rfq import RFQ, RFQItem, RFQVendor
from app.models.user import User
from app.models.vendor import Vendor
from app.models.quotation import Quotation, QuotationItem
from app.schemas.quotation import (
    QuotationCreate,
    QuotationUpdate,
    QuotationResponse,
    QuotationListResponse,
)

router = APIRouter()


# ── ENDPOINTS IMPLEMENTATION ───────────────────────────────────────────

@router.post(
    "",
    response_model=QuotationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Submit a new bid quotation",
    description="Enables assigned vendors to submit a priced quotation against a published RFQ.",
)
def create_quotation(
    payload: QuotationCreate,
    request: Request,
    current_user: User = Depends(require_vendor),
    db: Session = Depends(get_db),
):
    # 1. Resolve vendor profile and validate owner matches payload
    vendor = db.query(Vendor).filter(Vendor.user_id == current_user.user_id).first()
    if not vendor or vendor.vendor_id != payload.vendor_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Vendor profile mismatch or not authorized",
        )

    # 2. Check RFQ assignment
    assigned = db.query(RFQVendor).filter(
        RFQVendor.rfq_id == payload.rfq_id,
        RFQVendor.vendor_id == vendor.vendor_id
    ).first()
    if not assigned:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Vendor is not assigned to this RFQ",
        )

    # 3. Fetch RFQ and check deadline & status
    rfq = db.query(RFQ).filter(RFQ.rfq_id == payload.rfq_id, RFQ.deleted_at.is_(None)).first()
    if not rfq:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="RFQ not found",
        )

    if rfq.status not in ["published", "open"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Quotation bids can only be submitted for active/published RFQs",
        )

    deadline = rfq.deadline
    if deadline.tzinfo is None:
        deadline = deadline.replace(tzinfo=timezone.utc)
    if datetime.now(timezone.utc) > deadline:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot submit quotation after RFQ deadline",
        )

    # 4. Check one quotation per vendor per RFQ limit
    existing_qtn = db.query(Quotation).filter(
        Quotation.rfq_id == payload.rfq_id,
        Quotation.vendor_id == vendor.vendor_id,
        Quotation.deleted_at.is_(None)
    ).first()
    if existing_qtn:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Quotation already submitted for this RFQ",
        )

    # 5. Check items
    if not payload.items:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one quotation item required",
        )

    # Validate that all items exist on the RFQ
    for item_input in payload.items:
        rfq_item = db.query(RFQItem).filter(
            RFQItem.rfq_item_id == item_input.rfq_item_id,
            RFQItem.rfq_id == rfq.rfq_id
        ).first()
        if not rfq_item:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"RFQ Item {item_input.rfq_item_id} is not part of RFQ {rfq.doc_number}",
            )

    # 6. Generate doc number: QTN-YYYYMMDD-XXXX
    prefix = f"QTN-{datetime.now(timezone.utc).strftime('%Y%m%d')}-"
    while True:
        suffix = "".join(random.choices("0123456789", k=4))
        doc_number = f"{prefix}{suffix}"
        exists = db.query(Quotation).filter(Quotation.doc_number == doc_number).first()
        if not exists:
            break

    # 7. Create Quotation
    quotation = Quotation(
        doc_number=doc_number,
        rfq_id=payload.rfq_id,
        vendor_id=payload.vendor_id,
        status=payload.status,
        delivery_timeline=payload.delivery_timeline,
        notes=payload.notes,
        total_amount=Decimal("0.00"),
    )
    db.add(quotation)
    db.flush()

    # 8. Create QuotationItems and calculate total
    total_amount = Decimal("0.00")
    for item_input in payload.items:
        total_price = Decimal(str(item_input.quantity)) * Decimal(str(item_input.unit_price))
        qtn_item = QuotationItem(
            quotation_id=quotation.quotation_id,
            rfq_item_id=item_input.rfq_item_id,
            unit_price=item_input.unit_price,
            quantity=item_input.quantity,
            total_price=total_price,
        )
        db.add(qtn_item)
        total_amount += total_price

    quotation.total_amount = total_amount

    # 9. Log activity
    action_log = "Quotation Submitted" if payload.status == "submitted" else "Quotation Created"
    log = ActivityLog(
        user_id=current_user.user_id,
        action=action_log,
        entity_name="quotations",
        entity_id=quotation.quotation_id,
        ip_address=request.client.host if request.client else None,
    )
    db.add(log)

    # 10. Send notification to Officer
    notif = Notification(
        user_id=rfq.created_by_id,
        type="info",
        title="Quotation Submitted",
        message=f"Vendor {vendor.company_name} has submitted a quotation for RFQ {rfq.doc_number}.",
    )
    db.add(notif)

    db.commit()
    db.refresh(quotation)
    return quotation


@router.get(
    "",
    response_model=QuotationListResponse,
    summary="List and filter bids",
    description="Lists all active quotations. Enforces role-based visibility restrictions.",
)
def list_quotations(
    rfq_id: Optional[UUID] = None,
    status_filter: Optional[str] = None,
    skip: int = 0,
    limit: int = 100,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    query = db.query(Quotation).filter(Quotation.deleted_at.is_(None))

    # Vendor visibility constraint
    if current_user.role == "vendor":
        vendor = db.query(Vendor).filter(Vendor.user_id == current_user.user_id).first()
        if not vendor:
            return QuotationListResponse(quotations=[], total=0)
        query = query.filter(Quotation.vendor_id == vendor.vendor_id)

    if rfq_id:
        query = query.filter(Quotation.rfq_id == rfq_id)
    if status_filter:
        query = query.filter(Quotation.status == status_filter)

    total = query.count()
    quotations = query.offset(skip).limit(limit).all()

    return QuotationListResponse(quotations=quotations, total=total)


@router.get(
    "/rfq/{rfq_id}",
    response_model=QuotationListResponse,
    summary="Get quotations for a specific RFQ",
    description="Retrieve bid submissions for an RFQ. Vendors only retrieve their own bid.",
)
def get_quotations_by_rfq(
    rfq_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    query = db.query(Quotation).filter(Quotation.rfq_id == rfq_id, Quotation.deleted_at.is_(None))

    if current_user.role == "vendor":
        vendor = db.query(Vendor).filter(Vendor.user_id == current_user.user_id).first()
        if not vendor:
            return QuotationListResponse(quotations=[], total=0)
        query = query.filter(Quotation.vendor_id == vendor.vendor_id)

    total = query.count()
    quotations = query.all()
    return QuotationListResponse(quotations=quotations, total=total)


@router.get(
    "/{id}",
    response_model=QuotationResponse,
    summary="Get quotation details by ID",
    description="Retrieves a single quotation. Vendors must own the quotation to read it.",
)
def get_quotation_by_id(
    id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    quotation = db.query(Quotation).filter(Quotation.quotation_id == id, Quotation.deleted_at.is_(None)).first()
    if not quotation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Quotation not found",
        )

    # Vendor visibility constraint
    if current_user.role == "vendor":
        vendor = db.query(Vendor).filter(Vendor.user_id == current_user.user_id).first()
        if not vendor or quotation.vendor_id != vendor.vendor_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You are not authorized to view this quotation.",
            )

    return quotation


@router.patch(
    "/{id}",
    response_model=QuotationResponse,
    summary="Update draft quotation",
    description="Enables vendors to update pricing, delivery timeline, or notes before the RFQ deadline.",
)
def update_quotation(
    id: UUID,
    payload: QuotationUpdate,
    request: Request,
    current_user: User = Depends(require_vendor),
    db: Session = Depends(get_db),
):
    quotation = db.query(Quotation).filter(Quotation.quotation_id == id, Quotation.deleted_at.is_(None)).first()
    if not quotation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Quotation not found",
        )

    vendor = db.query(Vendor).filter(Vendor.user_id == current_user.user_id).first()
    if not vendor or quotation.vendor_id != vendor.vendor_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not authorized to edit this quotation.",
        )

    # Check RFQ deadline
    rfq = db.query(RFQ).filter(RFQ.rfq_id == quotation.rfq_id).first()
    deadline = rfq.deadline
    if deadline.tzinfo is None:
        deadline = deadline.replace(tzinfo=timezone.utc)
    if datetime.now(timezone.utc) > deadline:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot edit quotation after RFQ deadline",
        )

    # Update simple fields
    if payload.delivery_timeline is not None:
        quotation.delivery_timeline = payload.delivery_timeline
    if payload.notes is not None:
        quotation.notes = payload.notes

    status_changed_to_submitted = False
    if payload.status is not None:
        if quotation.status != "submitted" and payload.status == "submitted":
            status_changed_to_submitted = True
        quotation.status = payload.status

    # Log activity
    action_log = "Quotation Submitted" if status_changed_to_submitted else "Quotation Updated"
    log = ActivityLog(
        user_id=current_user.user_id,
        action=action_log,
        entity_name="quotations",
        entity_id=quotation.quotation_id,
        ip_address=request.client.host if request.client else None,
    )
    db.add(log)

    # Notify Officer if submitted
    if status_changed_to_submitted:
        notif = Notification(
            user_id=rfq.created_by_id,
            type="info",
            title="Quotation Updated",
            message=f"Vendor {vendor.company_name} has finalized and submitted quotation {quotation.doc_number}.",
        )
        db.add(notif)

    db.commit()
    db.refresh(quotation)
    return quotation


@router.delete(
    "/{id}",
    status_code=status.HTTP_200_OK,
    summary="Soft-delete quotation",
    description="Soft-deletes a quotation. Restricted to the submitting vendor before the RFQ deadline.",
)
def delete_quotation(
    id: UUID,
    current_user: User = Depends(require_vendor),
    db: Session = Depends(get_db),
):
    quotation = db.query(Quotation).filter(Quotation.quotation_id == id, Quotation.deleted_at.is_(None)).first()
    if not quotation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Quotation not found",
        )

    vendor = db.query(Vendor).filter(Vendor.user_id == current_user.user_id).first()
    if not vendor or quotation.vendor_id != vendor.vendor_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not authorized to delete this quotation.",
        )

    # Check RFQ deadline
    rfq = db.query(RFQ).filter(RFQ.rfq_id == quotation.rfq_id).first()
    deadline = rfq.deadline
    if deadline.tzinfo is None:
        deadline = deadline.replace(tzinfo=timezone.utc)
    if datetime.now(timezone.utc) > deadline:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete quotation after RFQ deadline",
        )

    # Soft delete
    quotation.deleted_at = datetime.now(timezone.utc)
    db.commit()

    return {"detail": "Quotation has been successfully soft-deleted"}

from datetime import datetime, timezone
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import (
    get_current_user,
    require_manager,
)
from app.models.approval import Approval
from app.models.quotation import Quotation
from app.models.user import User
from app.models.vendor import Vendor
from app.models.rfq import RFQ
from app.models.activity_log import ActivityLog
from app.models.notification import Notification
from app.schemas.approval import ApprovalResponse, ApprovalListResponse

router = APIRouter()


# ── REQUEST SCHEMAS ───────────────────────────────────────────────────
class ProcessApprovalRequest(BaseModel):
    remarks: str = Field(..., min_length=1, description="Reason or remarks for the decision")


# ── ENDPOINTS IMPLEMENTATION ───────────────────────────────────────────

@router.get(
    "",
    response_model=ApprovalListResponse,
    summary="List and filter approval decisions",
    description="Lists all approval decisions. Restricts visibility based on roles.",
)
def list_approvals(
    status_filter: Optional[str] = None,
    skip: int = 0,
    limit: int = 100,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    query = db.query(Approval)

    # Vendor role visibility restriction
    if current_user.role == "vendor":
        vendor = db.query(Vendor).filter(Vendor.user_id == current_user.user_id).first()
        if not vendor:
            return ApprovalListResponse(approvals=[], total=0)
        query = query.join(Quotation).filter(Quotation.vendor_id == vendor.vendor_id)

    if status_filter:
        query = query.filter(Approval.status == status_filter)

    total = query.count()
    approvals = query.offset(skip).limit(limit).all()

    return ApprovalListResponse(approvals=approvals, total=total)


@router.get(
    "/{id}",
    response_model=ApprovalResponse,
    summary="Get approval record details by ID",
    description="Retrieves a single approval record by its UUID.",
)
def get_approval_by_id(
    id: UUID,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    approval = db.query(Approval).filter(Approval.approval_id == id).first()
    if not approval:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Approval record not found",
        )

    # Vendor validation
    if current_user.role == "vendor":
        vendor = db.query(Vendor).filter(Vendor.user_id == current_user.user_id).first()
        if not vendor or approval.quotation.vendor_id != vendor.vendor_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You are not authorized to view this approval record",
            )

    # Log activity: Approval Viewed
    log = ActivityLog(
        user_id=current_user.user_id,
        action="Approval Viewed",
        entity_name="approvals",
        entity_id=approval.approval_id,
        ip_address=request.client.host if request.client else None,
    )
    db.add(log)
    db.commit()

    return approval


@router.patch(
    "/{id}/approve",
    response_model=ApprovalResponse,
    summary="Approve quotation",
    description="Approves a pending quotation request. Restricted to Managers.",
)
def approve_quotation(
    id: UUID,
    payload: ProcessApprovalRequest,
    request: Request,
    current_user: User = Depends(require_manager),
    db: Session = Depends(get_db),
):
    approval = db.query(Approval).filter(Approval.approval_id == id).first()
    if not approval:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Approval record not found",
        )

    # Enforce only pending status can be processed
    if approval.status != "pending":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Only pending approvals can be processed. Current status: {approval.status}",
        )

    # Process approval
    approval.status = "approved"
    approval.manager_id = current_user.user_id
    approval.remarks = payload.remarks

    # Fetch quotation and RFQ for notifications
    quotation = approval.quotation
    rfq = db.query(RFQ).filter(RFQ.rfq_id == quotation.rfq_id).first()

    # Trigger notifications
    # 1. Notify Officer who created the RFQ
    if rfq:
        officer_notif = Notification(
            user_id=rfq.created_by_id,
            type="info",
            title="Quotation Approved",
            message=f"Quotation {quotation.doc_number} for RFQ {rfq.doc_number} has been approved by Manager {current_user.first_name} {current_user.last_name}.",
        )
        db.add(officer_notif)

    # 2. Notify Vendor who submitted the bid
    vendor = db.query(Vendor).filter(Vendor.vendor_id == quotation.vendor_id).first()
    if vendor:
        vendor_notif = Notification(
            user_id=vendor.user_id,
            type="success",
            title="Quotation Approved",
            message=f"Your quotation {quotation.doc_number} for RFQ {rfq.doc_number if rfq else ''} has been approved.",
        )
        db.add(vendor_notif)

    # Log activity: Quotation Approved
    log = ActivityLog(
        user_id=current_user.user_id,
        action="Quotation Approved",
        entity_name="quotations",
        entity_id=quotation.quotation_id,
        ip_address=request.client.host if request.client else None,
    )
    db.add(log)

    db.commit()
    db.refresh(approval)
    return approval


@router.patch(
    "/{id}/reject",
    response_model=ApprovalResponse,
    summary="Reject quotation",
    description="Rejects a pending quotation request. Restricted to Managers.",
)
def reject_quotation(
    id: UUID,
    payload: ProcessApprovalRequest,
    request: Request,
    current_user: User = Depends(require_manager),
    db: Session = Depends(get_db),
):
    approval = db.query(Approval).filter(Approval.approval_id == id).first()
    if not approval:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Approval record not found",
        )

    # Enforce only pending status can be processed
    if approval.status != "pending":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Only pending approvals can be processed. Current status: {approval.status}",
        )

    # Process rejection
    approval.status = "rejected"
    approval.manager_id = current_user.user_id
    approval.remarks = payload.remarks

    # Update corresponding Quotation status to rejected
    quotation = approval.quotation
    quotation.status = "rejected"

    # Fetch RFQ for notification details
    rfq = db.query(RFQ).filter(RFQ.rfq_id == quotation.rfq_id).first()

    # Trigger notifications
    # 1. Notify Officer
    if rfq:
        officer_notif = Notification(
            user_id=rfq.created_by_id,
            type="info",
            title="Quotation Rejected",
            message=f"Quotation {quotation.doc_number} for RFQ {rfq.doc_number} has been rejected by Manager {current_user.first_name} {current_user.last_name}.",
        )
        db.add(officer_notif)

    # 2. Notify Vendor
    vendor = db.query(Vendor).filter(Vendor.vendor_id == quotation.vendor_id).first()
    if vendor:
        vendor_notif = Notification(
            user_id=vendor.user_id,
            type="warning",
            title="Quotation Rejected",
            message=f"Your quotation {quotation.doc_number} for RFQ {rfq.doc_number if rfq else ''} has been rejected.",
        )
        db.add(vendor_notif)

    # Log activity: Quotation Rejected
    log = ActivityLog(
        user_id=current_user.user_id,
        action="Quotation Rejected",
        entity_name="quotations",
        entity_id=quotation.quotation_id,
        ip_address=request.client.host if request.client else None,
    )
    db.add(log)

    db.commit()
    db.refresh(approval)
    return approval

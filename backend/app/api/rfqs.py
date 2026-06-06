import random
import uuid
from datetime import datetime, timedelta, timezone
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
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
from app.schemas.rfq import (
    RFQCreate,
    RFQItemCreate,
    RFQListResponse,
    RFQResponse,
    RFQUpdate,
)

router = APIRouter()


# ── LOCAL REQUEST MODELS ──────────────────────────────────────────────
class AssignVendorsRequest(BaseModel):
    vendor_ids: List[UUID] = Field(..., description="List of vendor IDs to assign")


# ── ENDPOINTS IMPLEMENTATION ───────────────────────────────────────────

@router.post(
    "",
    response_model=RFQResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new RFQ (Request For Quotation)",
    description="Enables Procurement Officers to create a new RFQ sourcing document in draft status.",
)
def create_rfq(
    payload: RFQCreate,
    request: Request,
    current_user: User = Depends(require_officer),
    db: Session = Depends(get_db),
):
    # 1. Validate deadline
    deadline = payload.deadline
    if deadline.tzinfo is None:
        deadline = deadline.replace(tzinfo=timezone.utc)
    if deadline <= datetime.now(timezone.utc):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Deadline must be a future date",
        )

    # 2. Validate items
    if not payload.items:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one RFQ item required",
        )

    # 3. Generate unique doc_number: RFQ-YYYYMMDD-XXXX
    prefix = f"RFQ-{datetime.now(timezone.utc).strftime('%Y%m%d')}-"
    while True:
        suffix = "".join(random.choices("0123456789", k=4))
        doc_number = f"{prefix}{suffix}"
        exists = db.query(RFQ).filter(RFQ.doc_number == doc_number).first()
        if not exists:
            break

    # 4. Create RFQ
    rfq = RFQ(
        doc_number=doc_number,
        created_by_id=current_user.user_id,
        status="draft",
        deadline=deadline,
    )
    db.add(rfq)
    db.flush()

    # 5. Create Items
    for item_data in payload.items:
        rfq_item = RFQItem(
            rfq_id=rfq.rfq_id,
            item_name=item_data.item_name,
            description=item_data.description,
            quantity=item_data.quantity,
            unit_of_measure=item_data.unit_of_measure,
        )
        db.add(rfq_item)

    # 6. Create Activity Log
    log = ActivityLog(
        user_id=current_user.user_id,
        action="RFQ Created",
        entity_name="rfqs",
        entity_id=rfq.rfq_id,
        ip_address=request.client.host if request.client else None,
    )
    db.add(log)

    db.commit()
    db.refresh(rfq)
    return rfq


@router.get(
    "",
    response_model=RFQListResponse,
    summary="List, search, and filter RFQs",
    description="Lists all active RFQs. Admin, Officer, Manager can view all. Vendors can only view their assigned RFQs.",
)
def list_rfqs(
    q: Optional[str] = None,
    status_filter: Optional[str] = None,
    skip: int = 0,
    limit: int = 100,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    query = db.query(RFQ).filter(RFQ.deleted_at.is_(None))

    # Vendor role restriction: view only assigned RFQs
    if current_user.role == "vendor":
        vendor = db.query(Vendor).filter(Vendor.user_id == current_user.user_id).first()
        if not vendor:
            return RFQListResponse(rfqs=[], total=0)
        query = query.join(RFQVendor).filter(RFQVendor.vendor_id == vendor.vendor_id)

    if status_filter:
        query = query.filter(RFQ.status == status_filter)

    if q:
        query = query.filter(
            or_(
                RFQ.doc_number.ilike(f"%{q}%"),
                RFQ.status.ilike(f"%{q}%"),
            )
        )

    total = query.count()
    rfqs = query.offset(skip).limit(limit).all()

    return RFQListResponse(rfqs=rfqs, total=total)


@router.get(
    "/analytics",
    summary="Get RFQ sourcing analytics",
    description="Returns high-level statistics and metadata. Restricted to Administrators.",
)
def get_rfq_analytics(
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    total_rfqs = db.query(RFQ).filter(RFQ.deleted_at.is_(None)).count()
    status_counts = {}
    for s in [
        "draft",
        "published",
        "quotation_open",
        "quotation_closed",
        "under_review",
        "approved",
        "cancelled",
        "completed",
    ]:
        status_counts[s] = db.query(RFQ).filter(RFQ.status == s, RFQ.deleted_at.is_(None)).count()

    total_assigned_vendors = db.query(RFQVendor.vendor_id).distinct().count()
    total_items = db.query(RFQItem).join(RFQ).filter(RFQ.deleted_at.is_(None)).count()

    return {
        "total_rfqs": total_rfqs,
        "status_counts": status_counts,
        "total_assigned_vendors": total_assigned_vendors,
        "total_items": total_items,
    }


@router.get(
    "/{id}",
    response_model=RFQResponse,
    summary="Get RFQ details by ID",
    description="Retrieve details of a single RFQ. Vendors must be assigned to the RFQ to read it.",
)
def get_rfq_by_id(
    id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    rfq = db.query(RFQ).filter(RFQ.rfq_id == id, RFQ.deleted_at.is_(None)).first()
    if not rfq:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="RFQ not found",
        )

    # Vendor visibility check
    if current_user.role == "vendor":
        vendor = db.query(Vendor).filter(Vendor.user_id == current_user.user_id).first()
        if not vendor:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You are not authorized to view this RFQ.",
            )
        assigned = (
            db.query(RFQVendor)
            .filter(RFQVendor.rfq_id == id, RFQVendor.vendor_id == vendor.vendor_id)
            .first()
        )
        if not assigned:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You are not authorized to view this RFQ.",
            )

    return rfq


@router.patch(
    "/{id}",
    response_model=RFQResponse,
    summary="Update RFQ details",
    description="Allows Procurement Officers to update details of a draft RFQ.",
)
def update_rfq(
    id: UUID,
    payload: RFQUpdate,
    request: Request,
    current_user: User = Depends(require_officer),
    db: Session = Depends(get_db),
):
    rfq = db.query(RFQ).filter(RFQ.rfq_id == id, RFQ.deleted_at.is_(None)).first()
    if not rfq:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="RFQ not found",
        )

    # Validate that status is draft
    if rfq.status != "draft":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot edit published RFQ",
        )

    if payload.deadline is not None:
        deadline = payload.deadline
        if deadline.tzinfo is None:
            deadline = deadline.replace(tzinfo=timezone.utc)
        if deadline <= datetime.now(timezone.utc):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Deadline must be a future date",
            )
        rfq.deadline = deadline

    if payload.status is not None:
        rfq.status = payload.status

    # Log RFQ Update activity
    log = ActivityLog(
        user_id=current_user.user_id,
        action="RFQ Updated",
        entity_name="rfqs",
        entity_id=rfq.rfq_id,
        ip_address=request.client.host if request.client else None,
    )
    db.add(log)

    db.commit()
    db.refresh(rfq)
    return rfq


@router.delete(
    "/{id}",
    status_code=status.HTTP_200_OK,
    summary="Soft-delete RFQ",
    description="Soft-deletes an RFQ document. Restricted to Procurement Officers.",
)
def delete_rfq(
    id: UUID,
    request: Request,
    current_user: User = Depends(require_officer),
    db: Session = Depends(get_db),
):
    rfq = db.query(RFQ).filter(RFQ.rfq_id == id, RFQ.deleted_at.is_(None)).first()
    if not rfq:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="RFQ not found",
        )

    # Soft delete setting deleted_at
    rfq.deleted_at = datetime.now(timezone.utc)

    # Log RFQ Deleted activity
    log = ActivityLog(
        user_id=current_user.user_id,
        action="RFQ Deleted",
        entity_name="rfqs",
        entity_id=rfq.rfq_id,
        ip_address=request.client.host if request.client else None,
    )
    db.add(log)

    db.commit()
    return {"detail": "RFQ has been successfully soft-deleted"}


@router.patch(
    "/{id}/publish",
    response_model=RFQResponse,
    summary="Publish RFQ",
    description="Publishes a draft RFQ. Triggers notifications to assigned vendors.",
)
def publish_rfq(
    id: UUID,
    request: Request,
    current_user: User = Depends(require_officer),
    db: Session = Depends(get_db),
):
    rfq = db.query(RFQ).filter(RFQ.rfq_id == id, RFQ.deleted_at.is_(None)).first()
    if not rfq:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="RFQ not found",
        )

    if rfq.status != "draft":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="RFQ is already published, closed, or cancelled",
        )

    # Check that at least one vendor is assigned
    vendors_assigned_count = db.query(RFQVendor).filter(RFQVendor.rfq_id == id).count()
    if vendors_assigned_count == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one vendor required",
        )

    # Validate deadline is in the future
    if rfq.deadline <= datetime.now(timezone.utc):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Deadline must be a future date",
        )

    # Set status
    rfq.status = "published"

    # Notify all assigned vendors
    assignments = db.query(RFQVendor).filter(RFQVendor.rfq_id == id).all()
    for assignment in assignments:
        vendor = db.query(Vendor).filter(Vendor.vendor_id == assignment.vendor_id).first()
        if vendor:
            # Generate Notification for assigned vendor
            notif = Notification(
                user_id=vendor.user_id,
                type="info",
                title="RFQ Published",
                message=f"RFQ {rfq.doc_number} has been published. Please submit your quotation.",
            )
            db.add(notif)

    # Log RFQ Published activity
    log = ActivityLog(
        user_id=current_user.user_id,
        action="RFQ Published",
        entity_name="rfqs",
        entity_id=rfq.rfq_id,
        ip_address=request.client.host if request.client else None,
    )
    db.add(log)

    db.commit()
    db.refresh(rfq)
    return rfq


@router.patch(
    "/{id}/close",
    response_model=RFQResponse,
    summary="Close RFQ",
    description="Closes an active RFQ from receiving further quotations.",
)
def close_rfq(
    id: UUID,
    request: Request,
    current_user: User = Depends(require_officer),
    db: Session = Depends(get_db),
):
    rfq = db.query(RFQ).filter(RFQ.rfq_id == id, RFQ.deleted_at.is_(None)).first()
    if not rfq:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="RFQ not found",
        )

    if rfq.status not in ["published", "open"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only active/published RFQs can be closed",
        )

    # Set status to closed / quotation_closed
    rfq.status = "quotation_closed"

    # Notify all assigned vendors
    assignments = db.query(RFQVendor).filter(RFQVendor.rfq_id == id).all()
    for assignment in assignments:
        vendor = db.query(Vendor).filter(Vendor.vendor_id == assignment.vendor_id).first()
        if vendor:
            notif = Notification(
                user_id=vendor.user_id,
                type="warning",
                title="RFQ Closed",
                message=f"RFQ {rfq.doc_number} has been closed.",
            )
            db.add(notif)

    # Log RFQ Closed activity
    log = ActivityLog(
        user_id=current_user.user_id,
        action="RFQ Closed",
        entity_name="rfqs",
        entity_id=rfq.rfq_id,
        ip_address=request.client.host if request.client else None,
    )
    db.add(log)

    db.commit()
    db.refresh(rfq)
    return rfq


@router.post(
    "/{id}/assign-vendors",
    response_model=RFQResponse,
    summary="Assign vendors to RFQ",
    description="Assigns multiple vendors to a draft RFQ document.",
)
def assign_vendors(
    id: UUID,
    payload: AssignVendorsRequest,
    request: Request,
    current_user: User = Depends(require_officer),
    db: Session = Depends(get_db),
):
    rfq = db.query(RFQ).filter(RFQ.rfq_id == id, RFQ.deleted_at.is_(None)).first()
    if not rfq:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="RFQ not found",
        )

    # Validate that status is draft
    if rfq.status != "draft":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot edit published RFQ",
        )

    # Validate non-empty vendors
    if not payload.vendor_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one vendor required",
        )

    # Validate no duplicate vendors
    if len(payload.vendor_ids) != len(set(payload.vendor_ids)):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No duplicate vendors allowed",
        )

    # Verify each vendor exists and is active/verified
    for v_id in payload.vendor_ids:
        vendor = db.query(Vendor).filter(Vendor.vendor_id == v_id).first()
        if not vendor:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Vendor with ID {v_id} does not exist",
            )
        if vendor.status != "active":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Vendor with ID {v_id} is not verified/active",
            )

    # Clean existing assignments
    db.query(RFQVendor).filter(RFQVendor.rfq_id == id).delete()

    # Create new assignments and notifications
    for v_id in payload.vendor_ids:
        assignment = RFQVendor(rfq_id=id, vendor_id=v_id)
        db.add(assignment)

        vendor = db.query(Vendor).filter(Vendor.vendor_id == v_id).first()
        notif = Notification(
            user_id=vendor.user_id,
            type="info",
            title="Vendor Assigned",
            message=f"You have been assigned to RFQ {rfq.doc_number}.",
        )
        db.add(notif)

    # Log Vendor Assigned activity
    log = ActivityLog(
        user_id=current_user.user_id,
        action="Vendor Assigned",
        entity_name="rfqs",
        entity_id=rfq.rfq_id,
        ip_address=request.client.host if request.client else None,
    )
    db.add(log)

    db.commit()
    db.refresh(rfq)
    return rfq


@router.post(
    "/deadline-reminders",
    status_code=status.HTTP_200_OK,
    summary="Trigger deadline reminders manually",
    description="Sends deadline reminder notifications to assigned vendors for active RFQs closing in < 24 hours.",
)
def trigger_deadline_reminders(
    current_user: User = Depends(require_officer),
    db: Session = Depends(get_db),
):
    now = datetime.now(timezone.utc)
    tomorrow = now + timedelta(hours=24)
    upcoming_rfqs = (
        db.query(RFQ)
        .filter(
            RFQ.status == "published",
            RFQ.deadline > now,
            RFQ.deadline <= tomorrow,
            RFQ.deleted_at.is_(None),
        )
        .all()
    )

    for rfq in upcoming_rfqs:
        assignments = db.query(RFQVendor).filter(RFQVendor.rfq_id == rfq.rfq_id).all()
        for assignment in assignments:
            vendor = db.query(Vendor).filter(Vendor.vendor_id == assignment.vendor_id).first()
            if vendor:
                notif = Notification(
                    user_id=vendor.user_id,
                    type="warning",
                    title="Deadline Reminder",
                    message=f"Reminder: RFQ {rfq.doc_number} deadline is approaching on {rfq.deadline.strftime('%Y-%m-%d %H:%M:%S')}.",
                )
                db.add(notif)

    db.commit()
    return {"detail": "Deadline reminders processed successfully"}

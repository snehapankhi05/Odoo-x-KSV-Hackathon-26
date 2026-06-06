import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import get_current_user, require_admin
from app.core.security import hash_password
from app.models.activity_log import ActivityLog
from app.models.user import User
from app.models.vendor import Vendor, VendorVerificationToken
from app.schemas.vendor import VendorResponse

router = APIRouter()


# ── LOCAL REQUEST MODELS ──────────────────────────────────────────────
class VendorCreateRequest(BaseModel):
    # User Profile Fields
    email: EmailStr
    first_name: str = Field(..., min_length=1, max_length=100)
    last_name: str = Field(..., min_length=1, max_length=100)
    phone_number: str = Field(..., min_length=10, max_length=30)
    password: str = Field(..., min_length=8, max_length=100)
    # Vendor Company Fields
    company_name: str = Field(..., min_length=1, max_length=255)
    contact_person: str = Field(..., min_length=1, max_length=150)
    gst_number: str = Field(..., min_length=15, max_length=15)
    category: str = Field(..., min_length=1, max_length=100)
    address: str = Field(..., min_length=1)


class VendorUpdateRequest(BaseModel):
    # Optional Vendor profile updates
    contact_person: Optional[str] = Field(None, min_length=1, max_length=150)
    category: Optional[str] = Field(None, min_length=1, max_length=100)
    address: Optional[str] = Field(None, min_length=1)
    # Optional Company/GST fields (Admin-only validation checks in endpoint)
    company_name: Optional[str] = Field(None, min_length=1, max_length=255)
    gst_number: Optional[str] = Field(None, min_length=15, max_length=15)
    # Optional linked User profile updates
    first_name: Optional[str] = Field(None, min_length=1, max_length=100)
    last_name: Optional[str] = Field(None, min_length=1, max_length=100)
    phone_number: Optional[str] = Field(None, min_length=10, max_length=30)
    email: Optional[EmailStr] = None


# ── VENDORS ROUTER ENDPOINTS ──────────────────────────────────────────

@router.post(
    "",
    response_model=VendorResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new Vendor profile",
    description="Enables Admins to register a new vendor. Creates user credentials, vendor profile, and generates verification tokens.",
)
def create_vendor(
    payload: VendorCreateRequest,
    request: Request,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    # Validate uniqueness constraints
    existing_email = db.query(User).filter(
        User.email == payload.email, 
        User.deleted_at.is_(None)
    ).first()
    if existing_email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email is already taken",
        )

    existing_gst = db.query(Vendor).filter(
        Vendor.gst_number == payload.gst_number, 
        Vendor.deleted_at.is_(None)
    ).first()
    if existing_gst:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="GST number is already registered",
        )

    # 1. Create linked User login profile
    new_user = User(
        first_name=payload.first_name,
        last_name=payload.last_name,
        email=payload.email,
        phone_number=payload.phone_number,
        password_hash=hash_password(payload.password),
        role="vendor",
        created_by_id=current_user.user_id,
        is_active=False,  # Inactive until token verification is complete
    )
    db.add(new_user)
    db.flush()  # Retrieve new_user.user_id

    # 2. Create Vendor profile
    new_vendor = Vendor(
        user_id=new_user.user_id,
        company_name=payload.company_name,
        contact_person=payload.contact_person,
        gst_number=payload.gst_number,
        category=payload.category,
        address=payload.address,
        status="pending",
        created_by_id=current_user.user_id,
    )
    db.add(new_vendor)
    db.flush()  # Retrieve new_vendor.vendor_id

    # 3. Create Verification Token
    token_str = secrets.token_urlsafe(32)
    new_token = VendorVerificationToken(
        vendor_id=new_vendor.vendor_id,
        token_string=token_str,
        expires_at=datetime.now(timezone.utc) + timedelta(days=2),
    )
    db.add(new_token)

    # 4. Activity Log
    log = ActivityLog(
        user_id=current_user.user_id,
        action="create-vendor",
        entity_name="vendors",
        entity_id=new_vendor.vendor_id,
        ip_address=request.client.host if request.client else None,
    )
    db.add(log)
    db.commit()

    # Simulate email dispatch
    print(f"\n[EMAIL SIMULATION] Verification email sent to {payload.email}!")
    print(f"[EMAIL SIMULATION] Verification Link: http://localhost:8000/api/v1/auth/verify?token={token_str}\n")

    db.refresh(new_vendor)
    return new_vendor


@router.get(
    "",
    response_model=list[VendorResponse],
    summary="List, search and filter vendors",
    description="Enables Admins, Officers, and Managers to query and filter active vendor directory profiles.",
)
def list_vendors(
    q: Optional[str] = None,
    status: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if current_user.role not in ["admin", "officer", "manager"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Vendor accounts are not permitted to list all vendors.",
        )

    query = db.query(Vendor).filter(Vendor.deleted_at.is_(None))

    if status:
        query = query.filter(Vendor.status == status)

    if q:
        query = query.filter(
            or_(
                Vendor.company_name.ilike(f"%{q}%"),
                Vendor.contact_person.ilike(f"%{q}%"),
                Vendor.gst_number.ilike(f"%{q}%"),
            )
        )

    return query.all()


@router.get(
    "/{id}",
    response_model=VendorResponse,
    summary="Get vendor profile details by ID",
    description="Allows internal staff to view any vendor profile. Vendors can only query their own profiles.",
)
def get_vendor_by_id(
    id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    vendor = db.query(Vendor).filter(
        Vendor.vendor_id == id, 
        Vendor.deleted_at.is_(None)
    ).first()
    if not vendor:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Vendor not found",
        )

    # Vendor isolation checks
    if current_user.role == "vendor" and current_user.user_id != vendor.user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not authorized to view this vendor profile.",
        )

    return vendor


@router.patch(
    "/{id}",
    response_model=VendorResponse,
    summary="Update vendor profile details",
    description="Admin can update any vendor. Vendors can update their own contact details (cannot update GST or Company Name).",
)
def update_vendor(
    id: UUID,
    payload: VendorUpdateRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    vendor = db.query(Vendor).filter(
        Vendor.vendor_id == id, 
        Vendor.deleted_at.is_(None)
    ).first()
    if not vendor:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Vendor profile not found",
        )

    user = db.query(User).filter(User.user_id == vendor.user_id).first()

    # Vendor validation limits
    if current_user.role == "vendor":
        if current_user.user_id != vendor.user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You are not permitted to update other vendor profiles.",
            )
        # Block updating GST/Company Name for vendors
        if payload.company_name or payload.gst_number:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Vendors are not permitted to change GST numbers or company name settings.",
            )

    # 1. Update Vendor specific fields
    if payload.contact_person:
        vendor.contact_person = payload.contact_person
    if payload.category:
        vendor.category = payload.category
    if payload.address:
        vendor.address = payload.address

    # Admin only profile controls
    if current_user.role == "admin":
        if payload.company_name:
            vendor.company_name = payload.company_name
        if payload.gst_number and payload.gst_number != vendor.gst_number:
            existing_gst = db.query(Vendor).filter(
                Vendor.gst_number == payload.gst_number,
                Vendor.deleted_at.is_(None)
            ).first()
            if existing_gst:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="GST number is already in use by another vendor",
                )
            vendor.gst_number = payload.gst_number

    # 2. Update linked login User fields
    if user:
        if payload.first_name:
            user.first_name = payload.first_name
        if payload.last_name:
            user.last_name = payload.last_name
        if payload.phone_number:
            user.phone_number = payload.phone_number
        if payload.email and payload.email != user.email:
            existing_email = db.query(User).filter(
                User.email == payload.email, 
                User.deleted_at.is_(None)
            ).first()
            if existing_email:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Email is already taken",
                )
            user.email = payload.email

    db.commit()
    db.refresh(vendor)

    # Activity Log
    log = ActivityLog(
        user_id=current_user.user_id,
        action="update-vendor",
        entity_name="vendors",
        entity_id=vendor.vendor_id,
        ip_address=request.client.host if request.client else None,
    )
    db.add(log)
    db.commit()

    return vendor


@router.delete(
    "/{id}",
    status_code=status.HTTP_200_OK,
    summary="Soft delete a vendor profile",
    description="Enables Admins to soft-delete vendor profiles and deactivate their linked user login credential records.",
)
def delete_vendor(
    id: UUID,
    request: Request,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    vendor = db.query(Vendor).filter(
        Vendor.vendor_id == id, 
        Vendor.deleted_at.is_(None)
    ).first()
    if not vendor:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Vendor profile not found or already deleted",
        )

    # Soft Delete both Vendor and linked User login records
    vendor.deleted_at = datetime.now()
    vendor.status = "blocked"

    user = db.query(User).filter(User.user_id == vendor.user_id).first()
    if user:
        user.deleted_at = datetime.now()
        user.is_active = False

    db.commit()

    # Activity Log
    log = ActivityLog(
        user_id=current_user.user_id,
        action="delete-vendor",
        entity_name="vendors",
        entity_id=id,
        ip_address=request.client.host if request.client else None,
    )
    db.add(log)
    db.commit()

    return {"detail": "Vendor profile has been successfully soft-deleted"}


@router.patch(
    "/{id}/block",
    response_model=VendorResponse,
    summary="Block a vendor profile",
    description="Blocks a vendor profile and deactivates their login credentials immediately.",
)
def block_vendor(
    id: UUID,
    request: Request,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    vendor = db.query(Vendor).filter(
        Vendor.vendor_id == id, 
        Vendor.deleted_at.is_(None)
    ).first()
    if not vendor:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Vendor profile not found",
        )

    vendor.status = "blocked"

    user = db.query(User).filter(User.user_id == vendor.user_id).first()
    if user:
        user.is_active = False

    db.commit()
    db.refresh(vendor)

    # Activity Log
    log = ActivityLog(
        user_id=current_user.user_id,
        action="block-vendor",
        entity_name="vendors",
        entity_id=id,
        ip_address=request.client.host if request.client else None,
    )
    db.add(log)
    db.commit()

    return vendor


@router.patch(
    "/{id}/activate",
    response_model=VendorResponse,
    summary="Activate a vendor profile",
    description="Sets a vendor profile status to active and reactivates login credentials.",
)
def activate_vendor(
    id: UUID,
    request: Request,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    vendor = db.query(Vendor).filter(
        Vendor.vendor_id == id, 
        Vendor.deleted_at.is_(None)
    ).first()
    if not vendor:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Vendor profile not found",
        )

    vendor.status = "active"

    user = db.query(User).filter(User.user_id == vendor.user_id).first()
    if user:
        user.is_active = True

    db.commit()
    db.refresh(vendor)

    # Activity Log
    log = ActivityLog(
        user_id=current_user.user_id,
        action="activate-vendor",
        entity_name="vendors",
        entity_id=id,
        ip_address=request.client.host if request.client else None,
    )
    db.add(log)
    db.commit()

    return vendor


@router.post(
    "/{id}/send-verification",
    status_code=status.HTTP_200_OK,
    summary="Generate and dispatch vendor verification link",
    description="Admin can trigger a new activation link for pending vendor accounts.",
)
def send_vendor_verification(
    id: UUID,
    request: Request,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    vendor = db.query(Vendor).filter(
        Vendor.vendor_id == id, 
        Vendor.deleted_at.is_(None)
    ).first()
    if not vendor:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Vendor profile not found",
        )

    # Generate a new token
    token_str = secrets.token_urlsafe(32)
    new_token = VendorVerificationToken(
        vendor_id=vendor.vendor_id,
        token_string=token_str,
        expires_at=datetime.now(timezone.utc) + timedelta(days=2),
    )
    db.add(new_token)

    # Reset vendor status to pending
    vendor.status = "pending"

    # Activity Log
    log = ActivityLog(
        user_id=current_user.user_id,
        action="send-verification-token",
        entity_name="vendors",
        entity_id=id,
        ip_address=request.client.host if request.client else None,
    )
    db.add(log)
    db.commit()

    # Simulate email dispatch
    user = db.query(User).filter(User.user_id == vendor.user_id).first()
    email_dest = user.email if user else "vendor"
    print(f"\n[EMAIL SIMULATION] Re-verification link sent to {email_dest}!")
    print(f"[EMAIL SIMULATION] Verification Link: http://localhost:8000/api/v1/auth/verify?token={token_str}\n")

    return {"message": "Verification link has been successfully generated and dispatched"}

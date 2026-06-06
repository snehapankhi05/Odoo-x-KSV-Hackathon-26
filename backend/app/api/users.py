from datetime import datetime
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
from app.schemas.user import UserResponse

router = APIRouter()


# ── LOCAL REQUEST MODELS ──────────────────────────────────────────────
class ManagerCreateRequest(BaseModel):
    first_name: str = Field(..., min_length=1, max_length=100)
    last_name: str = Field(..., min_length=1, max_length=100)
    email: EmailStr
    phone_number: str = Field(..., min_length=10, max_length=30)
    password: str = Field(..., min_length=8, max_length=100)


class UserUpdateRequest(BaseModel):
    first_name: Optional[str] = Field(None, min_length=1, max_length=100)
    last_name: Optional[str] = Field(None, min_length=1, max_length=100)
    email: Optional[EmailStr] = None
    phone_number: Optional[str] = Field(None, min_length=10, max_length=30)
    password: Optional[str] = Field(None, min_length=8, max_length=100)


# ── USER ROUTER ENDPOINTS ─────────────────────────────────────────────

@router.get(
    "",
    response_model=list[UserResponse],
    summary="List, search and filter users",
    description="Allows administrators to retrieve and filter all active users. Supports keyword search.",
)
def list_users(
    q: Optional[str] = None,
    role: Optional[str] = None,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    query = db.query(User).filter(User.deleted_at.is_(None))

    if role:
        query = query.filter(User.role == role)

    if q:
        query = query.filter(
            or_(
                User.first_name.ilike(f"%{q}%"),
                User.last_name.ilike(f"%{q}%"),
                User.email.ilike(f"%{q}%"),
            )
        )

    return query.all()


@router.post(
    "/manager",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new Manager account",
    description="Enables Admins to provision new Manager users. Managers can evaluate quotations and approve POs.",
)
def create_manager(
    payload: ManagerCreateRequest,
    request: Request,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    # Check if email is already taken
    existing_user = db.query(User).filter(
        User.email == payload.email, 
        User.deleted_at.is_(None)
    ).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email is already registered",
        )

    new_manager = User(
        first_name=payload.first_name,
        last_name=payload.last_name,
        email=payload.email,
        phone_number=payload.phone_number,
        password_hash=hash_password(payload.password),
        role="manager",
        created_by_id=current_user.user_id,
        is_active=True,
    )
    db.add(new_manager)
    db.commit()
    db.refresh(new_manager)

    # Activity Log
    log = ActivityLog(
        user_id=current_user.user_id,
        action="create-manager",
        entity_name="users",
        entity_id=new_manager.user_id,
        ip_address=request.client.host if request.client else None,
    )
    db.add(log)
    db.commit()

    return new_manager


@router.get(
    "/{id}",
    response_model=UserResponse,
    summary="Get user details by ID",
    description="Admin can view any user details. Regular users can only query their own details.",
)
def get_user_by_id(
    id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if current_user.role != "admin" and current_user.user_id != id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not authorized to view this user's profile details.",
        )

    user = db.query(User).filter(User.user_id == id, User.deleted_at.is_(None)).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    return user


@router.patch(
    "/{id}",
    response_model=UserResponse,
    summary="Update user details",
    description="Allows Admins to edit any user profile. Or allows users to update their own contact information.",
)
def update_user(
    id: UUID,
    payload: UserUpdateRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if current_user.role != "admin" and current_user.user_id != id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not authorized to update this profile.",
        )

    user = db.query(User).filter(User.user_id == id, User.deleted_at.is_(None)).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    # Validate email uniqueness if changing email
    if payload.email and payload.email != user.email:
        existing_user = db.query(User).filter(
            User.email == payload.email, 
            User.deleted_at.is_(None)
        ).first()
        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email is already taken",
            )
        user.email = payload.email

    if payload.first_name:
        user.first_name = payload.first_name
    if payload.last_name:
        user.last_name = payload.last_name
    if payload.phone_number:
        user.phone_number = payload.phone_number
    if payload.password:
        user.password_hash = hash_password(payload.password)

    db.commit()
    db.refresh(user)

    # Activity Log
    log = ActivityLog(
        user_id=current_user.user_id,
        action="update-user",
        entity_name="users",
        entity_id=user.user_id,
        ip_address=request.client.host if request.client else None,
    )
    db.add(log)
    db.commit()

    return user


@router.delete(
    "/{id}",
    status_code=status.HTTP_200_OK,
    summary="Soft delete a user account",
    description="Enables Admins to soft-delete manager or officer accounts. Prevents deleting self.",
)
def delete_user(
    id: UUID,
    request: Request,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    if current_user.user_id == id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Administrators cannot delete their own profiles.",
        )

    user = db.query(User).filter(User.user_id == id, User.deleted_at.is_(None)).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found or already deleted",
        )

    user.deleted_at = datetime.now()
    user.is_active = False
    db.commit()

    # Activity Log
    log = ActivityLog(
        user_id=current_user.user_id,
        action="delete-user",
        entity_name="users",
        entity_id=id,
        ip_address=request.client.host if request.client else None,
    )
    db.add(log)
    db.commit()

    return {"detail": "User has been successfully soft-deleted"}


@router.patch(
    "/{id}/block",
    response_model=UserResponse,
    summary="Block a user account",
    description="Deactivates a user account to block login permissions immediately.",
)
def block_user(
    id: UUID,
    request: Request,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.user_id == id, User.deleted_at.is_(None)).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    user.is_active = False
    db.commit()
    db.refresh(user)

    # Activity Log
    log = ActivityLog(
        user_id=current_user.user_id,
        action="block-user",
        entity_name="users",
        entity_id=id,
        ip_address=request.client.host if request.client else None,
    )
    db.add(log)
    db.commit()

    return user


@router.patch(
    "/{id}/unblock",
    response_model=UserResponse,
    summary="Unblock a user account",
    description="Re-activates a user account to restore login access.",
)
def unblock_user(
    id: UUID,
    request: Request,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.user_id == id, User.deleted_at.is_(None)).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    user.is_active = True
    db.commit()
    db.refresh(user)

    # Activity Log
    log = ActivityLog(
        user_id=current_user.user_id,
        action="unblock-user",
        entity_name="users",
        entity_id=id,
        ip_address=request.client.host if request.client else None,
    )
    db.add(log)
    db.commit()

    return user

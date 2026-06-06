from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.activity_log import ActivityLog
from app.models.notification import Notification
from app.models.user import User
from app.schemas.user import UserCreate, UserResponse
from app.services.auth_service import AuthService

router = APIRouter()


# ── LOCAL APIS REQUEST & RESPONSE SCHEMAS ─────────────────────────────
class AdminSignupRequest(BaseModel):
    first_name: str = Field(..., min_length=1, max_length=100)
    last_name: str = Field(..., min_length=1, max_length=100)
    email: EmailStr
    phone_number: str = Field(..., min_length=10, max_length=30)
    password: str = Field(..., min_length=8, max_length=100)


class OfficerSignupRequest(BaseModel):
    first_name: str = Field(..., min_length=1, max_length=100)
    last_name: str = Field(..., min_length=1, max_length=100)
    email: EmailStr
    phone_number: str = Field(..., min_length=10, max_length=30)
    password: str = Field(..., min_length=8, max_length=100)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class LoginResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str
    user: UserResponse


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str = Field(..., min_length=8, max_length=100)


class RefreshTokenRequest(BaseModel):
    refresh_token: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str


# ── ENDPOINTS IMPLEMENTATION ───────────────────────────────────────────

@router.post(
    "/signup/admin",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Admin self-service registration",
    description="Registers a new system administrator. Has permission to onboard Managers and Vendors.",
)
def signup_admin(
    payload: AdminSignupRequest, request: Request, db: Session = Depends(get_db)
):
    user_create = UserCreate(
        first_name=payload.first_name,
        last_name=payload.last_name,
        email=payload.email,
        phone_number=payload.phone_number,
        password=payload.password,
        role="admin",
    )
    new_user = AuthService.register_user(db, user_create)

    # 1. Audit Log
    log = ActivityLog(
        user_id=new_user.user_id,
        action="signup",
        entity_name="users",
        entity_id=new_user.user_id,
        ip_address=request.client.host if request.client else None,
    )
    db.add(log)

    # 2. Welcome Notification
    notif = Notification(
        user_id=new_user.user_id,
        type="info",
        title="Admin Profile Created",
        message=f"Welcome to VendorBridge, Admin {new_user.first_name}!",
    )
    db.add(notif)
    db.commit()

    return new_user


@router.post(
    "/signup/officer",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Officer self-service registration",
    description="Registers a new procurement officer. Has permission to draft RFQs and issue Purchase Orders.",
)
def signup_officer(
    payload: OfficerSignupRequest, request: Request, db: Session = Depends(get_db)
):
    user_create = UserCreate(
        first_name=payload.first_name,
        last_name=payload.last_name,
        email=payload.email,
        phone_number=payload.phone_number,
        password=payload.password,
        role="officer",
    )
    new_user = AuthService.register_user(db, user_create)

    # 1. Audit Log
    log = ActivityLog(
        user_id=new_user.user_id,
        action="signup",
        entity_name="users",
        entity_id=new_user.user_id,
        ip_address=request.client.host if request.client else None,
    )
    db.add(log)

    # 2. Welcome Notification
    notif = Notification(
        user_id=new_user.user_id,
        type="info",
        title="Officer Profile Created",
        message=f"Welcome to VendorBridge, Officer {new_user.first_name}!",
    )
    db.add(notif)
    db.commit()

    return new_user


@router.post(
    "/login",
    response_model=LoginResponse,
    status_code=status.HTTP_200_OK,
    summary="User credentials authentication",
    description="Logs in users using email and password. Validates account status and activation for all roles.",
)
def login(payload: LoginRequest, request: Request, db: Session = Depends(get_db)):
    auth_data = AuthService.authenticate_user(db, payload.email, payload.password)
    user = db.query(User).filter(User.email == payload.email).first()

    # Log login activity
    log = ActivityLog(
        user_id=user.user_id if user else None,
        action="login",
        entity_name="users",
        entity_id=user.user_id if user else UUID("00000000-0000-0000-0000-000000000000"),
        ip_address=request.client.host if request.client else None,
    )
    db.add(log)
    db.commit()

    return {
        "access_token": auth_data["access_token"],
        "refresh_token": auth_data["refresh_token"],
        "token_type": auth_data["token_type"],
        "user": user,
    }


@router.post(
    "/forgot-password",
    status_code=status.HTTP_200_OK,
    summary="Request a password reset link",
    description="Statelessly generates a secure, short-lived JWT reset token. Always returns a generic success message.",
)
def forgot_password(
    payload: ForgotPasswordRequest, request: Request, db: Session = Depends(get_db)
):
    response = AuthService.request_password_reset(db, payload.email)
    user = db.query(User).filter(User.email == payload.email).first()

    # Log password reset request activity
    log = ActivityLog(
        user_id=user.user_id if user else None,
        action="forgot-password",
        entity_name="users",
        entity_id=user.user_id if user else UUID("00000000-0000-0000-0000-000000000000"),
        ip_address=request.client.host if request.client else None,
    )
    db.add(log)
    db.commit()

    return response


@router.post(
    "/reset-password",
    status_code=status.HTTP_200_OK,
    summary="Submit password reset confirmation",
    description="Validates the short-lived reset token, verifies password strength, and updates credentials.",
)
def reset_password(
    payload: ResetPasswordRequest, request: Request, db: Session = Depends(get_db)
):
    response = AuthService.reset_password(db, payload.token, payload.new_password)

    # Resolve user from token for logging (optional, handles gracefully if invalid)
    try:
        from jose import jwt
        from app.core.config import settings
        token_payload = jwt.decode(
            payload.token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM]
        )
        user_id = token_payload.get("user_id")
        user_uuid = UUID(user_id) if user_id else None
    except Exception:
        user_uuid = None

    # Log password update activity
    log = ActivityLog(
        user_id=user_uuid,
        action="reset-password",
        entity_name="users",
        entity_id=user_uuid if user_uuid else UUID("00000000-0000-0000-0000-000000000000"),
        ip_address=request.client.host if request.client else None,
    )
    db.add(log)

    # Notify user of password change
    if user_uuid:
        notif = Notification(
            user_id=user_uuid,
            type="warning",
            title="Password Changed",
            message="Your account password was updated successfully. If this wasn't you, contact support.",
        )
        db.add(notif)

    db.commit()
    return response


@router.post(
    "/refresh-token",
    response_model=TokenResponse,
    status_code=status.HTTP_200_OK,
    summary="Renew access token using refresh token",
    description="Validates the refresh token and issues a new access token.",
)
def refresh_token(payload: RefreshTokenRequest, db: Session = Depends(get_db)):
    return AuthService.refresh_token(db, payload.refresh_token)


@router.post(
    "/logout",
    status_code=status.HTTP_200_OK,
    summary="Invalidate user session",
    description="Logs out the current authenticated user and creates an audit activity log entry.",
)
def logout(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # Create logout activity log
    log = ActivityLog(
        user_id=current_user.user_id,
        action="logout",
        entity_name="users",
        entity_id=current_user.user_id,
        ip_address=request.client.host if request.client else None,
    )
    db.add(log)
    db.commit()

    return {"detail": "Successfully logged out"}

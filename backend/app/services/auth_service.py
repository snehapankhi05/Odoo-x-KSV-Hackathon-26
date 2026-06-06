from datetime import datetime, timedelta, timezone
from typing import Dict

from fastapi import HTTPException, status
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import (
    create_access_token,
    create_refresh_token,
    hash_password,
    verify_password,
)
from app.models.user import User
from app.models.vendor import Vendor, VendorVerificationToken
from app.schemas.user import UserCreate


class AuthService:
    @staticmethod
    def register_user(db: Session, user_data: UserCreate) -> User:
        """
        Self-service registration for Admins and Officers.
        Managers and Vendors cannot register via self-service.
        """
        if user_data.role not in ["admin", "officer"]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{user_data.role}' accounts cannot self-register.",
            )

        # Check for existing email
        existing_user = db.query(User).filter(
            User.email == user_data.email, 
            User.deleted_at.is_(None)
        ).first()
        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email is already registered",
            )

        new_user = User(
            first_name=user_data.first_name,
            last_name=user_data.last_name,
            email=user_data.email,
            phone_number=user_data.phone_number,
            password_hash=hash_password(user_data.password),
            role=user_data.role,
            created_by_id=user_data.created_by_id,
            is_active=True,
        )

        db.add(new_user)
        db.commit()
        db.refresh(new_user)
        return new_user

    @staticmethod
    def authenticate_user(db: Session, email: str, password: str) -> Dict[str, str]:
        """
        Authenticate user login request.
        For vendors, checks status is active (requires verification).
        """
        user = db.query(User).filter(
            User.email == email, 
            User.deleted_at.is_(None)
        ).first()

        invalid_credentials_exception = HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )

        if not user or not verify_password(password, user.password_hash):
            raise invalid_credentials_exception

        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User account is deactivated",
            )

        # Extra checks for Vendor profiles
        if user.role == "vendor":
            vendor = db.query(Vendor).filter(Vendor.user_id == user.user_id).first()
            if not vendor:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Vendor profile not found",
                )
            if vendor.status == "pending":
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Please verify your vendor account first",
                )
            elif vendor.status == "blocked":
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Vendor account is blocked",
                )

        # Generate tokens
        token_data = {
            "user_id": str(user.user_id),
            "email": user.email,
            "role": user.role,
        }

        return {
            "access_token": create_access_token(token_data),
            "refresh_token": create_refresh_token(token_data),
            "token_type": "bearer",
        }

    @staticmethod
    def refresh_token(db: Session, refresh_token: str) -> Dict[str, str]:
        """Verify the refresh token and return a new access token."""
        credentials_exception = HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
        )

        try:
            payload = jwt.decode(
                refresh_token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM]
            )
            user_id: str = payload.get("user_id")
            token_type: str = payload.get("type")

            if user_id is None or token_type != "refresh":
                raise credentials_exception
        except JWTError:
            raise credentials_exception

        user = db.query(User).filter(
            User.user_id == user_id, 
            User.deleted_at.is_(None)
        ).first()

        if not user or not user.is_active:
            raise credentials_exception

        token_data = {
            "user_id": str(user.user_id),
            "email": user.email,
            "role": user.role,
        }

        return {
            "access_token": create_access_token(token_data),
            "token_type": "bearer",
        }

    @staticmethod
    def request_password_reset(db: Session, email: str) -> Dict[str, str]:
        """
        Request password reset link/token.
        Always returns generic message to prevent user enumeration.
        """
        user = db.query(User).filter(
            User.email == email, 
            User.deleted_at.is_(None)
        ).first()

        # Secure reset token (stateless signed JWT, 15-minute expiration)
        if user:
            reset_payload = {
                "user_id": str(user.user_id),
                "email": user.email,
                "type": "reset",
                "exp": datetime.now(timezone.utc) + timedelta(minutes=15),
            }
            token = jwt.encode(
                reset_payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM
            )
            # In production, send this token via email (e.g. print/log for local development)
            # Print reset link for local debug purposes
            print(f"\n[DEBUG] Password reset token for {email}: {token}\n")

        return {
            "message": "If the email is registered, a password reset link has been sent."
        }

    @staticmethod
    def reset_password(db: Session, token: str, new_password: str) -> Dict[str, str]:
        """Verify the password reset token and update user password."""
        try:
            payload = jwt.decode(
                token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM]
            )
            user_id: str = payload.get("user_id")
            token_type: str = payload.get("type")

            if user_id is None or token_type != "reset":
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid or expired reset token",
                )
        except JWTError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid or expired reset token",
            )

        user = db.query(User).filter(
            User.user_id == user_id, 
            User.deleted_at.is_(None)
        ).first()

        if not user or not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
            )

        user.password_hash = hash_password(new_password)
        db.commit()

        return {"message": "Password has been successfully updated"}

    @staticmethod
    def verify_vendor_account(db: Session, token_string: str) -> Dict[str, str]:
        """Consume verification token to activate a vendor profile."""
        token = db.query(VendorVerificationToken).filter(
            VendorVerificationToken.token_string == token_string
        ).first()

        if not token:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid verification token",
            )

        if token.used_at is not None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Token has already been used",
            )

        # Check expiration
        now = datetime.now(timezone.utc)
        # Handle offset-naive vs offset-aware datetime matching
        expires_at = token.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)

        if now > expires_at:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Verification token has expired",
            )

        # Mark token as used
        token.used_at = now

        # Update vendor profile status to active
        vendor = db.query(Vendor).filter(Vendor.vendor_id == token.vendor_id).first()
        if not vendor:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Vendor profile not found",
            )

        vendor.status = "active"
        vendor.verified_at = now

        # Make sure user login identity is enabled
        user = db.query(User).filter(User.user_id == vendor.user_id).first()
        if user:
            user.is_active = True

        db.commit()

        return {"message": "Vendor account has been successfully verified"}

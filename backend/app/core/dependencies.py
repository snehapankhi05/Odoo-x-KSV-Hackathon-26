from typing import Annotated

from fastapi import Depends, HTTPException, status
from jose import JWTError
from sqlalchemy.orm import Session

from app.core.auth import oauth2_scheme
from app.core.database import get_db
from app.core.security import decode_token
from app.models.user import User


def get_current_user(
    db: Session = Depends(get_db), token: str = Depends(oauth2_scheme)
) -> User:
    """
    Dependency to fetch the authenticated user from the JWT token.
    Validates token format, expiration, user existence, and operational state.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication credentials were not provided",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        payload = decode_token(token)
        user_id_str: str = payload.get("user_id")
        token_type: str = payload.get("type")

        if user_id_str is None or token_type != "access":
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    # Query the user record
    user = db.query(User).filter(User.user_id == user_id_str, User.deleted_at.is_(None)).first()
    if user is None:
        raise credentials_exception

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is deactivated",
        )

    return user


# Reusable dependency shortcuts
CurrentUser = Annotated[User, Depends(get_current_user)]


def require_admin(current_user: CurrentUser) -> User:
    """Assert current authenticated user is an Admin."""
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Operation requires Admin privileges",
        )
    return current_user


def require_officer(current_user: CurrentUser) -> User:
    """Assert current authenticated user is an Officer."""
    if current_user.role != "officer":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Operation requires Officer privileges",
        )
    return current_user


def require_manager(current_user: CurrentUser) -> User:
    """Assert current authenticated user is a Manager."""
    if current_user.role != "manager":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Operation requires Manager privileges",
        )
    return current_user


def require_vendor(current_user: CurrentUser) -> User:
    """Assert current authenticated user is a Vendor."""
    if current_user.role != "vendor":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Operation requires Vendor privileges",
        )
    return current_user

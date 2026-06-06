from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.notification import Notification
from app.models.user import User
from app.schemas.notification import (
    NotificationResponse,
    NotificationListResponse,
)

router = APIRouter()


# ── ENDPOINTS IMPLEMENTATION ───────────────────────────────────────────

@router.get(
    "",
    response_model=NotificationListResponse,
    summary="List all notifications",
    description="Retrieves a paginated list of notifications and the total unread count. Admins view all; others view only their own.",
)
def list_notifications(
    skip: int = 0,
    limit: int = 100,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    query = db.query(Notification)

    # Visibility constraints
    if current_user.role != "admin":
        query = query.filter(Notification.user_id == current_user.user_id)

    # Order by newest first
    query = query.order_by(Notification.created_at.desc())

    total = query.count()
    notifications = query.offset(skip).limit(limit).all()

    # Calculate unread count under the same visibility constraints
    unread_query = db.query(Notification).filter(Notification.is_read == False)
    if current_user.role != "admin":
        unread_query = unread_query.filter(Notification.user_id == current_user.user_id)
    unread_count = unread_query.count()

    return NotificationListResponse(
        notifications=notifications,
        total=total,
        unread_count=unread_count,
    )


@router.patch(
    "/{id}/read",
    response_model=NotificationResponse,
    summary="Mark a notification as read",
    description="Updates a notification's status to read.",
)
def mark_as_read(
    id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    notification = db.query(Notification).filter(Notification.notification_id == id).first()
    if not notification:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notification not found",
        )

    # Restrict users to only mark their own notifications as read
    if current_user.role != "admin" and notification.user_id != current_user.user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not authorized to access this notification",
        )

    notification.is_read = True
    db.commit()
    db.refresh(notification)
    return notification


@router.patch(
    "/read-all",
    summary="Mark all notifications as read",
    description="Marks all pending notifications as read.",
)
def mark_all_as_read(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    query = db.query(Notification).filter(Notification.is_read == False)

    # Filter by user if not admin
    if current_user.role != "admin":
        query = query.filter(Notification.user_id == current_user.user_id)

    unread_notifications = query.all()
    for notif in unread_notifications:
        notif.is_read = True

    db.commit()
    return {"detail": f"Successfully marked {len(unread_notifications)} notifications as read"}

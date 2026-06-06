from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import require_admin
from app.models.activity_log import ActivityLog
from app.models.user import User
from app.schemas.activity_log import ActivityLogListResponse

router = APIRouter()


@router.get(
    "",
    response_model=ActivityLogListResponse,
    summary="List all activity logs",
    description="Retrieves a paginated list of audit activity logs. Restricted to Admin users only.",
)
def list_activity_logs(
    search: Optional[str] = Query(None, description="Search term matching action or entity_name"),
    action: Optional[str] = Query(None, description="Filter logs by exact action"),
    entity_name: Optional[str] = Query(None, description="Filter logs by exact entity type"),
    user_id: Optional[UUID] = Query(None, description="Filter logs by performing user ID"),
    skip: int = Query(0, ge=0, description="Number of items to skip"),
    limit: int = Query(100, ge=1, le=1000, description="Number of items to return"),
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    query = db.query(ActivityLog)

    # Filtering by user_id
    if user_id:
        query = query.filter(ActivityLog.user_id == user_id)

    # Filtering by exact action
    if action:
        query = query.filter(ActivityLog.action == action)

    # Filtering by exact entity_name
    if entity_name:
        query = query.filter(ActivityLog.entity_name == entity_name)

    # Fuzzy search case-insensitively on action or entity_name
    if search:
        search_filter = or_(
            ActivityLog.action.ilike(f"%{search}%"),
            ActivityLog.entity_name.ilike(f"%{search}%"),
        )
        query = query.filter(search_filter)

    # Order by newest first
    query = query.order_by(ActivityLog.created_at.desc())

    total = query.count()
    logs = query.offset(skip).limit(limit).all()

    return ActivityLogListResponse(logs=logs, total=total)

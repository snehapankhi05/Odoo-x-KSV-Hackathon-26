from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ActivityLogBase(BaseModel):
    action: str = Field(..., min_length=1, max_length=100)
    entity_name: str = Field(..., min_length=1, max_length=100)
    entity_id: UUID
    ip_address: Optional[str] = Field(None, max_length=45)


class ActivityLogCreate(ActivityLogBase):
    user_id: Optional[UUID] = None


class ActivityLogResponse(ActivityLogBase):
    log_id: UUID
    user_id: Optional[UUID] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ActivityLogListResponse(BaseModel):
    logs: list[ActivityLogResponse]
    total: int

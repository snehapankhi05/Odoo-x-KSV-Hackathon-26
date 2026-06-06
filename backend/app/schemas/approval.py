from datetime import datetime
from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ApprovalBase(BaseModel):
    quotation_id: UUID
    status: Literal["pending", "approved", "rejected"] = "pending"
    remarks: str = Field(..., min_length=1)


class ApprovalCreate(ApprovalBase):
    manager_id: UUID


class ApprovalUpdate(BaseModel):
    status: Optional[Literal["pending", "approved", "rejected"]] = None
    remarks: Optional[str] = Field(None, min_length=1)


class ApprovalResponse(ApprovalBase):
    approval_id: UUID
    manager_id: UUID
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ApprovalListResponse(BaseModel):
    approvals: list[ApprovalResponse]
    total: int

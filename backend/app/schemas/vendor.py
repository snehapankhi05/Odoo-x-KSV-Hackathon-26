from datetime import datetime
from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.user import UserResponse


class VendorBase(BaseModel):
    company_name: str = Field(..., min_length=1, max_length=255)
    contact_person: str = Field(..., min_length=1, max_length=150)
    gst_number: str = Field(..., min_length=15, max_length=15)
    category: str = Field(..., min_length=1, max_length=100)
    address: str = Field(..., min_length=1)


class VendorCreate(VendorBase):
    user_id: UUID
    created_by_id: Optional[UUID] = None


class VendorUpdate(BaseModel):
    company_name: Optional[str] = Field(None, min_length=1, max_length=255)
    contact_person: Optional[str] = Field(None, min_length=1, max_length=150)
    gst_number: Optional[str] = Field(None, min_length=15, max_length=15)
    category: Optional[str] = Field(None, min_length=1, max_length=100)
    address: Optional[str] = Field(None, min_length=1)
    status: Optional[Literal["pending", "active", "blocked"]] = None


class VendorResponse(VendorBase):
    vendor_id: UUID
    user_id: UUID
    status: Literal["pending", "active", "blocked"]
    created_by_id: Optional[UUID] = None
    verified_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    user: Optional[UserResponse] = None

    model_config = ConfigDict(from_attributes=True)


class VendorListResponse(BaseModel):
    vendors: list[VendorResponse]
    total: int


class VendorVerificationTokenBase(BaseModel):
    vendor_id: UUID
    expires_at: datetime


class VendorVerificationTokenCreate(VendorVerificationTokenBase):
    pass


class VendorVerificationTokenResponse(VendorVerificationTokenBase):
    token_id: UUID
    token_string: str
    used_at: Optional[datetime] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

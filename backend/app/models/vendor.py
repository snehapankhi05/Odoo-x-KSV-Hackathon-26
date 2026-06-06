import uuid
from datetime import datetime
from typing import List, Optional

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class Vendor(Base):
    """
    Supplier company profile.
    Has a strict 1:1 link to a User account (user_id, UNIQUE).
    created_by_id tracks the Admin/Officer who onboarded this vendor.
    Two separate FKs to users require explicit foreign_keys on both relationships.
    """

    __tablename__ = "vendors"

    vendor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.user_id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    company_name: Mapped[str] = mapped_column(String(255), nullable=False)
    contact_person: Mapped[str] = mapped_column(String(150), nullable=False)
    gst_number: Mapped[str] = mapped_column(String(15), nullable=False, unique=True)
    category: Mapped[str] = mapped_column(String(100), nullable=False)
    address: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        String(50), nullable=False, default="pending"
    )  # CHECK: pending | active | blocked
    created_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.user_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    verified_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
    deleted_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # ── The user account that is this vendor's login identity (1:1) ────────
    user: Mapped["User"] = relationship(
        "User",
        foreign_keys=[user_id],
        back_populates="vendor_profile",
    )

    # ── The admin/officer who created this vendor record ───────────────────
    created_by: Mapped[Optional["User"]] = relationship(
        "User",
        foreign_keys=[created_by_id],
        back_populates="created_vendors",
    )

    # ── Account verification tokens (1:N, cascade delete) ─────────────────
    verification_tokens: Mapped[List["VendorVerificationToken"]] = relationship(
        "VendorVerificationToken",
        back_populates="vendor",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    # ── RFQ assignment bridge rows (1:N, cascade delete) ───────────────────
    rfq_assignments: Mapped[List["RFQVendor"]] = relationship(
        "RFQVendor",
        back_populates="vendor",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    # ── Quotations submitted by this vendor (1:N) ──────────────────────────
    quotations: Mapped[List["Quotation"]] = relationship(
        "Quotation",
        back_populates="vendor",
    )

    # ── Invoices billed by this vendor (1:N) ───────────────────────────────
    invoices: Mapped[List["Invoice"]] = relationship(
        "Invoice",
        foreign_keys="[Invoice.vendor_id]",
        back_populates="vendor",
    )


class VendorVerificationToken(Base):
    """
    One-time email verification tokens for vendor account activation.
    Deleted when the parent vendor is deleted (ON DELETE CASCADE).
    """

    __tablename__ = "vendor_verification_tokens"

    token_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    vendor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("vendors.vendor_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    token_string: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    # ── Parent vendor ──────────────────────────────────────────────────────
    vendor: Mapped["Vendor"] = relationship(
        "Vendor", back_populates="verification_tokens"
    )

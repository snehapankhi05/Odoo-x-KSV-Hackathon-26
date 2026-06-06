import uuid
from datetime import datetime
from typing import List, Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class User(Base):
    """
    Unified authentication and profile table.
    Supports all four roles: admin, officer, manager, vendor.
    Self-references via created_by_id to track who provisioned each account.
    """

    __tablename__ = "users"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    email: Mapped[str] = mapped_column(
        String(255), nullable=False, unique=True, index=True
    )
    phone_number: Mapped[str] = mapped_column(String(30), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # CHECK: admin | officer | manager | vendor
    created_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.user_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
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

    # ── Self-referencing: who created this account ─────────────────────────
    # remote_side tells SQLAlchemy that user_id is the "one" side (the parent PK).
    creator: Mapped[Optional["User"]] = relationship(
        "User",
        foreign_keys="[User.created_by_id]",
        remote_side="[User.user_id]",
        back_populates="created_accounts",
    )
    created_accounts: Mapped[List["User"]] = relationship(
        "User",
        foreign_keys="[User.created_by_id]",
        back_populates="creator",
    )

    # ── Vendor: the linked supplier profile for this user account (1:1) ────
    # Disambiguation required: Vendor has two FKs to users (user_id & created_by_id).
    vendor_profile: Mapped[Optional["Vendor"]] = relationship(
        "Vendor",
        foreign_keys="[Vendor.user_id]",
        back_populates="user",
        uselist=False,
    )

    # ── Vendors this user administratively created (1:N) ───────────────────
    created_vendors: Mapped[List["Vendor"]] = relationship(
        "Vendor",
        foreign_keys="[Vendor.created_by_id]",
        back_populates="created_by",
    )

    # ── RFQs this officer created (1:N) ────────────────────────────────────
    created_rfqs: Mapped[List["RFQ"]] = relationship(
        "RFQ",
        foreign_keys="[RFQ.created_by_id]",
        back_populates="created_by",
    )

    # ── Approvals this manager actioned (1:N) ──────────────────────────────
    managed_approvals: Mapped[List["Approval"]] = relationship(
        "Approval",
        foreign_keys="[Approval.manager_id]",
        back_populates="manager",
    )

    # ── Purchase Orders this officer generated (1:N) ────────────────────────
    created_purchase_orders: Mapped[List["PurchaseOrder"]] = relationship(
        "PurchaseOrder",
        foreign_keys="[PurchaseOrder.created_by_id]",
        back_populates="created_by",
    )

    # ── Invoices this officer processed (1:N) ──────────────────────────────
    created_invoices: Mapped[List["Invoice"]] = relationship(
        "Invoice",
        foreign_keys="[Invoice.created_by_id]",
        back_populates="created_by",
    )

    # ── Notifications delivered to this user (1:N) ─────────────────────────
    # Cascade: DB enforces ON DELETE CASCADE; passive_deletes avoids redundant SELECTs.
    notifications: Mapped[List["Notification"]] = relationship(
        "Notification",
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    # ── Audit events triggered by this user (1:N) ─────────────────────────
    activity_logs: Mapped[List["ActivityLog"]] = relationship(
        "ActivityLog",
        back_populates="user",
    )

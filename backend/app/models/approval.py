import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class Approval(Base):
    """
    Manager's decision record on a submitted quotation.
    Strictly 1:1 with Quotation (UNIQUE constraint on quotation_id).
    Status lifecycle: pending → approved | rejected
    Remarks are mandatory — the Manager must always justify the decision.
    """

    __tablename__ = "approvals"

    approval_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    quotation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("quotations.quotation_id", ondelete="RESTRICT"),
        nullable=False,
        unique=True,
        index=True,
    )
    manager_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.user_id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    status: Mapped[str] = mapped_column(
        String(50), nullable=False, default="pending"
    )  # CHECK: pending | approved | rejected
    remarks: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    # ── The quotation being evaluated (1:1 back-reference) ─────────────────
    quotation: Mapped["Quotation"] = relationship(
        "Quotation", back_populates="approval"
    )

    # ── The manager who made the decision ──────────────────────────────────
    manager: Mapped["User"] = relationship(
        "User",
        foreign_keys=[manager_id],
        back_populates="managed_approvals",
    )

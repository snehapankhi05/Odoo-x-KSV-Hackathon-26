import uuid
from datetime import datetime
from decimal import Decimal
from typing import List, Optional

from sqlalchemy import DateTime, ForeignKey, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class RFQ(Base):
    """
    Request For Quotation — the sourcing document created by an Officer.
    Contains line items and is dispatched to multiple vendors via rfq_vendors.
    Status lifecycle: draft → open → closed | cancelled
    """

    __tablename__ = "rfqs"

    rfq_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    doc_number: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    created_by_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.user_id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    status: Mapped[str] = mapped_column(
        String(50), nullable=False, default="draft"
    )  # CHECK: draft | open | closed | cancelled
    deadline: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
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

    # ── Officer who created this RFQ ───────────────────────────────────────
    created_by: Mapped["User"] = relationship(
        "User",
        foreign_keys=[created_by_id],
        back_populates="created_rfqs",
    )

    # ── Line items within this RFQ (1:N, cascade delete) ──────────────────
    items: Mapped[List["RFQItem"]] = relationship(
        "RFQItem",
        back_populates="rfq",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    # ── Vendor assignment bridge records (M2M, cascade delete) ─────────────
    vendor_assignments: Mapped[List["RFQVendor"]] = relationship(
        "RFQVendor",
        back_populates="rfq",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    # ── Quotations submitted against this RFQ (1:N) ────────────────────────
    quotations: Mapped[List["Quotation"]] = relationship(
        "Quotation",
        back_populates="rfq",
    )


class RFQItem(Base):
    """
    Individual line item within an RFQ specifying what is needed.
    Referenced by QuotationItem when a vendor prices each line.
    Deleted when parent RFQ is deleted (ON DELETE CASCADE).
    """

    __tablename__ = "rfq_items"

    rfq_item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    rfq_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("rfqs.rfq_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    item_name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    quantity: Mapped[Decimal] = mapped_column(Numeric(15, 4), nullable=False)
    unit_of_measure: Mapped[str] = mapped_column(String(30), nullable=False)

    # ── Parent RFQ ─────────────────────────────────────────────────────────
    rfq: Mapped["RFQ"] = relationship("RFQ", back_populates="items")

    # ── Quotation items that price this line (1:N) ─────────────────────────
    quotation_items: Mapped[List["QuotationItem"]] = relationship(
        "QuotationItem",
        back_populates="rfq_item",
    )


class RFQVendor(Base):
    """
    Many-to-Many association between RFQs and Vendors.
    Composite primary key: (rfq_id, vendor_id).
    Has an extra column (assigned_at) so it is an explicit model, not a simple Table().
    """

    __tablename__ = "rfq_vendors"

    rfq_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("rfqs.rfq_id", ondelete="CASCADE"),
        primary_key=True,
    )
    vendor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("vendors.vendor_id", ondelete="CASCADE"),
        primary_key=True,
    )
    assigned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    # ── Parent RFQ ─────────────────────────────────────────────────────────
    rfq: Mapped["RFQ"] = relationship("RFQ", back_populates="vendor_assignments")

    # ── Assigned vendor ────────────────────────────────────────────────────
    vendor: Mapped["Vendor"] = relationship("Vendor", back_populates="rfq_assignments")

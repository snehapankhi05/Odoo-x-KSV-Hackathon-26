import uuid
from datetime import datetime
from decimal import Decimal
from typing import List, Optional

from sqlalchemy import DateTime, ForeignKey, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class Quotation(Base):
    """
    Bid submitted by a Vendor in response to an RFQ.
    UNIQUE(rfq_id, vendor_id) enforced at DB level — only one bid per vendor per RFQ.
    Status lifecycle: draft → submitted → selected | rejected
    Converts 1:1 to a PurchaseOrder after Manager approval.
    """

    __tablename__ = "quotations"

    quotation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    doc_number: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    rfq_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("rfqs.rfq_id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    vendor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("vendors.vendor_id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    status: Mapped[str] = mapped_column(
        String(50), nullable=False, default="draft"
    )  # CHECK: draft | submitted | selected | rejected
    total_amount: Mapped[Decimal] = mapped_column(
        Numeric(15, 2), nullable=False, default=Decimal("0.00")
    )
    delivery_timeline: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
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

    # ── Parent RFQ ─────────────────────────────────────────────────────────
    rfq: Mapped["RFQ"] = relationship("RFQ", back_populates="quotations")

    # ── Submitting vendor ──────────────────────────────────────────────────
    vendor: Mapped["Vendor"] = relationship("Vendor", back_populates="quotations")

    # ── Bid line items (1:N, cascade delete) ───────────────────────────────
    items: Mapped[List["QuotationItem"]] = relationship(
        "QuotationItem",
        back_populates="quotation",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    # ── Manager approval record (1:1, optional until reviewed) ────────────
    approval: Mapped[Optional["Approval"]] = relationship(
        "Approval",
        back_populates="quotation",
        uselist=False,
    )

    # ── Purchase Order generated from this quotation (1:1) ─────────────────
    purchase_order: Mapped[Optional["PurchaseOrder"]] = relationship(
        "PurchaseOrder",
        back_populates="quotation",
        uselist=False,
    )


class QuotationItem(Base):
    """
    Vendor's priced bid for a specific RFQ line item.
    References the original rfq_item_id for traceability.
    DB CHECK enforces: total_price = quantity * unit_price.
    """

    __tablename__ = "quotation_items"

    quotation_item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    quotation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("quotations.quotation_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    rfq_item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("rfq_items.rfq_item_id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    unit_price: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(15, 4), nullable=False)
    total_price: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)

    # ── Parent quotation ───────────────────────────────────────────────────
    quotation: Mapped["Quotation"] = relationship("Quotation", back_populates="items")

    # ── The RFQ line item this bid is pricing ──────────────────────────────
    rfq_item: Mapped["RFQItem"] = relationship(
        "RFQItem", back_populates="quotation_items"
    )

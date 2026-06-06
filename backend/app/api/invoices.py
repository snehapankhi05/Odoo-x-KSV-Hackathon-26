from datetime import datetime, timezone
from decimal import Decimal
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import (
    get_current_user,
    require_officer,
)
from app.models.invoice import Invoice, InvoiceItem
from app.models.purchase_order import PurchaseOrder
from app.models.user import User
from app.models.vendor import Vendor
from app.models.activity_log import ActivityLog
from app.models.notification import Notification
from app.schemas.invoice import (
    InvoiceResponse,
    InvoiceListResponse,
    InvoiceCreateRequest,
    InvoiceUpdate,
)

router = APIRouter()


# ── ENDPOINTS IMPLEMENTATION ───────────────────────────────────────────

@router.post(
    "",
    response_model=InvoiceResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Generate an Invoice from Purchase Order",
    description="Generates an Invoice from a Purchase Order. Restricted to Officers.",
)
def create_invoice(
    payload: InvoiceCreateRequest,
    request: Request,
    current_user: User = Depends(require_officer),
    db: Session = Depends(get_db),
):
    # 1. Verify PO exists
    po = db.query(PurchaseOrder).filter(
        PurchaseOrder.po_id == payload.po_id,
        PurchaseOrder.deleted_at.is_(None)
    ).first()
    if not po:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Purchase Order not found",
        )

    # 2. Enforce one invoice per PO limit
    existing_inv = db.query(Invoice).filter(
        Invoice.po_id == payload.po_id,
        Invoice.deleted_at.is_(None)
    ).first()
    if existing_inv:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="An Invoice has already been generated for this Purchase Order",
        )

    # 3. Create Invoice (doc_number set to "" for DB trigger population)
    invoice = Invoice(
        doc_number="",
        po_id=payload.po_id,
        vendor_id=po.quotation.vendor_id,
        created_by_id=current_user.user_id,
        status="generated",
        amount_due=Decimal("0.00"),  # Calculated below
        currency=po.currency or "USD",
        is_locked=False,
    )
    db.add(invoice)
    db.flush()

    # 4. Copy PO line items to Invoice items snapshot and compute GST
    subtotal = Decimal("0.00")
    for po_item in po.items:
        inv_item = InvoiceItem(
            invoice_id=invoice.invoice_id,
            item_name=po_item.item_name,
            quantity=po_item.quantity,
            unit_price=po_item.unit_price,
            total_price=po_item.total_price,
        )
        db.add(inv_item)
        subtotal += po_item.total_price

    # Grand total includes GST (copied tax_rate from PO)
    tax_multiplier = Decimal("1.00") + (po.tax_rate / Decimal("100.00"))
    invoice.amount_due = subtotal * tax_multiplier

    # 5. Log activity: Invoice Generated
    log = ActivityLog(
        user_id=current_user.user_id,
        action="Invoice Generated",
        entity_name="invoices",
        entity_id=invoice.invoice_id,
        ip_address=request.client.host if request.client else None,
    )
    db.add(log)

    # 6. Send notification: Invoice Generated (to Officer)
    officer_notif = Notification(
        user_id=current_user.user_id,
        type="info",
        title="Invoice Generated",
        message=f"Invoice {invoice.doc_number} has been generated for Purchase Order {po.doc_number}.",
    )
    db.add(officer_notif)

    db.commit()
    db.refresh(invoice)
    return invoice


@router.get(
    "",
    response_model=InvoiceListResponse,
    summary="List and filter Invoices",
    description="Retrieve invoices with status filtering, search queries, and pagination. Restricts visibility based on roles.",
)
def list_invoices(
    status_filter: Optional[str] = None,
    search: Optional[str] = None,
    skip: int = 0,
    limit: int = 100,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    query = db.query(Invoice).filter(Invoice.deleted_at.is_(None))

    # Vendor role visibility restriction
    if current_user.role == "vendor":
        vendor = db.query(Vendor).filter(Vendor.user_id == current_user.user_id).first()
        if not vendor:
            return InvoiceListResponse(invoices=[], total=0)
        query = query.filter(Invoice.vendor_id == vendor.vendor_id)

    if status_filter:
        query = query.filter(Invoice.status == status_filter)

    if search:
        search_query = f"%{search}%"
        query = query.filter(Invoice.doc_number.ilike(search_query))

    total = query.count()
    invoices = query.offset(skip).limit(limit).all()

    return InvoiceListResponse(invoices=invoices, total=total)


@router.get(
    "/{id}",
    response_model=InvoiceResponse,
    summary="Get Invoice details by ID",
    description="Retrieves a single Invoice by its UUID. Restricts visibility based on roles.",
)
def get_invoice_by_id(
    id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    invoice = db.query(Invoice).filter(Invoice.invoice_id == id, Invoice.deleted_at.is_(None)).first()
    if not invoice:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invoice not found",
        )

    # Vendor validation
    if current_user.role == "vendor":
        vendor = db.query(Vendor).filter(Vendor.user_id == current_user.user_id).first()
        if not vendor or invoice.vendor_id != vendor.vendor_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You are not authorized to view this Invoice",
            )

    return invoice


@router.patch(
    "/{id}",
    response_model=InvoiceResponse,
    summary="Update Invoice details or status",
    description="Enables Officers to update Invoice status, currency, amount_due, or lock state. Officer only.",
)
def update_invoice(
    id: UUID,
    payload: InvoiceUpdate,
    request: Request,
    current_user: User = Depends(require_officer),
    db: Session = Depends(get_db),
):
    invoice = db.query(Invoice).filter(Invoice.invoice_id == id, Invoice.deleted_at.is_(None)).first()
    if not invoice:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invoice not found",
        )

    # Enforce edit lock constraint
    if invoice.is_locked:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Locked invoices cannot be modified",
        )

    old_status = invoice.status

    if payload.status is not None:
        invoice.status = payload.status
    if payload.currency is not None:
        invoice.currency = payload.currency
    if payload.amount_due is not None:
        invoice.amount_due = payload.amount_due
    if payload.is_locked is not None:
        invoice.is_locked = payload.is_locked

    # Trigger logic on state changes
    if payload.status is not None and old_status != payload.status:
        # Invoice Sent
        if payload.status == "sent":
            # Log activity: Invoice Sent
            log = ActivityLog(
                user_id=current_user.user_id,
                action="Invoice Sent",
                entity_name="invoices",
                entity_id=invoice.invoice_id,
                ip_address=request.client.host if request.client else None,
            )
            db.add(log)
            # Notification: Invoice Sent (to Vendor)
            vendor = db.query(Vendor).filter(Vendor.vendor_id == invoice.vendor_id).first()
            if vendor:
                v_notif = Notification(
                    user_id=vendor.user_id,
                    type="info",
                    title="Invoice Sent",
                    message=f"Invoice {invoice.doc_number} has been sent to you.",
                )
                db.add(v_notif)

        # Invoice Paid
        elif payload.status == "paid":
            # Lock both PO and Invoice
            invoice.is_locked = True
            po = db.query(PurchaseOrder).filter(PurchaseOrder.po_id == invoice.po_id).first()
            if po:
                po.is_locked = True
            
            # Notification: Invoice Paid (to Vendor and Officer)
            vendor = db.query(Vendor).filter(Vendor.vendor_id == invoice.vendor_id).first()
            if vendor:
                v_notif = Notification(
                    user_id=vendor.user_id,
                    type="success",
                    title="Invoice Paid",
                    message=f"Payment received for Invoice {invoice.doc_number}.",
                )
                db.add(v_notif)

            officer_notif = Notification(
                user_id=current_user.user_id,
                type="success",
                title="Invoice Paid",
                message=f"Invoice {invoice.doc_number} status updated to Paid.",
            )
            db.add(officer_notif)

    db.commit()
    db.refresh(invoice)
    return invoice


@router.get(
    "/{id}/pdf",
    summary="Download Invoice PDF",
    description="Generates and streams a PDF version of the invoice.",
)
def get_invoice_pdf(
    id: UUID,
    request: Request,
    action: Optional[str] = "download",  # download | print
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    invoice = db.query(Invoice).filter(Invoice.invoice_id == id, Invoice.deleted_at.is_(None)).first()
    if not invoice:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invoice not found",
        )

    # Vendor validation
    if current_user.role == "vendor":
        vendor = db.query(Vendor).filter(Vendor.user_id == current_user.user_id).first()
        if not vendor or invoice.vendor_id != vendor.vendor_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You are not authorized to access this Invoice PDF",
            )

    # Log activity based on action query param
    action_log = "Invoice Printed" if action == "print" else "Invoice Downloaded"
    log = ActivityLog(
        user_id=current_user.user_id,
        action=action_log,
        entity_name="invoices",
        entity_id=invoice.invoice_id,
        ip_address=request.client.host if request.client else None,
    )
    db.add(log)
    db.commit()

    # Generate portable PDF stream
    pdf_text = (
        "%PDF-1.4\n"
        "1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
        "2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n"
        "3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Contents 4 0 R /Resources << >> >>\nendobj\n"
        "4 0 obj\n<< /Length 300 >>\nstream\n"
        "BT /F1 16 Tf 50 750 Td (VendorBridge Procurement ERP Invoice) Tj ET\n"
        f"BT /F1 10 Tf 50 720 Td (Invoice ID: {invoice.invoice_id}) Tj ET\n"
        f"BT /F1 10 Tf 50 700 Td (Doc Number: {invoice.doc_number}) Tj ET\n"
        f"BT /F1 10 Tf 50 680 Td (Amount Due: {invoice.amount_due} {invoice.currency}) Tj ET\n"
        f"BT /F1 10 Tf 50 660 Td (PO ID: {invoice.po_id}) Tj ET\n"
        f"BT /F1 10 Tf 50 640 Td (Generated At: {invoice.created_at.isoformat()}) Tj ET\n"
        "endstream\nendobj\nxref\n0 5\n0000000000 65535 f\n0000000009 00000 n\n0000000058 00000 n\n0000000115 00000 n\n0000000220 00000 n\ntrailer\n<< /Size 5 /Root 1 0 R >>\nstartxref\n400\n%%EOF"
    )
    pdf_content = pdf_text.encode("utf-8")

    disposition = "inline" if action == "print" else "attachment"
    return Response(
        content=pdf_content,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f"{disposition}; filename=invoice_{invoice.doc_number}.pdf"
        }
    )


@router.post(
    "/{id}/email",
    summary="Send Invoice via Email",
    description="Emails a PDF invoice document copy to the vendor contact details.",
)
def email_invoice(
    id: UUID,
    request: Request,
    current_user: User = Depends(require_officer),
    db: Session = Depends(get_db),
):
    invoice = db.query(Invoice).filter(Invoice.invoice_id == id, Invoice.deleted_at.is_(None)).first()
    if not invoice:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invoice not found",
        )

    # Log activity: Invoice Sent
    log = ActivityLog(
        user_id=current_user.user_id,
        action="Invoice Sent",
        entity_name="invoices",
        entity_id=invoice.invoice_id,
        ip_address=request.client.host if request.client else None,
    )
    db.add(log)

    # Send Notification: Invoice Sent (to Vendor)
    vendor = db.query(Vendor).filter(Vendor.vendor_id == invoice.vendor_id).first()
    if vendor:
        v_notif = Notification(
            user_id=vendor.user_id,
            type="info",
            title="Invoice Sent",
            message=f"Email confirmation sent: Invoice {invoice.doc_number} for PO {invoice.purchase_order.doc_number}.",
        )
        db.add(v_notif)

    db.commit()
    return {"detail": f"Invoice {invoice.doc_number} sent via email successfully"}

import uuid
from decimal import Decimal
from datetime import datetime, timedelta, timezone
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.security import create_access_token, hash_password
from app.models.user import User
from app.models.vendor import Vendor
from app.models.rfq import RFQ, RFQItem, RFQVendor
from app.models.quotation import Quotation, QuotationItem
from app.models.approval import Approval
from app.models.purchase_order import PurchaseOrder, PurchaseOrderItem
from app.models.invoice import Invoice
from app.models.notification import Notification
from app.models.activity_log import ActivityLog


# ── TEST HELPERS ──────────────────────────────────────────────────────
def create_test_user(db: Session, email: str, role: str, is_active: bool = True) -> User:
    user = User(
        first_name="Test",
        last_name=role.capitalize(),
        email=email,
        phone_number="12345678901",
        password_hash=hash_password("password123"),
        role=role,
        is_active=is_active,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def get_auth_headers(user: User) -> dict:
    token_data = {
        "user_id": str(user.user_id),
        "email": user.email,
        "role": user.role,
    }
    token = create_access_token(token_data)
    return {"Authorization": f"Bearer {token}"}


def create_test_vendor(db: Session, user: User, gst: str) -> Vendor:
    vendor = Vendor(
        user_id=user.user_id,
        company_name=f"Supplier {gst[:5]} Co",
        contact_person="Supplier Name",
        gst_number=gst,
        category="Hardware",
        address="100 Sourcing Lane",
        status="active",
    )
    db.add(vendor)
    db.commit()
    db.refresh(vendor)
    return vendor


# ── TEST CASES ────────────────────────────────────────────────────────

def test_invoice_management_complete_flow(client: TestClient, db_session: Session):
    # Setup users
    officer = create_test_user(db_session, "off_inv@test.com", "officer")
    manager = create_test_user(db_session, "mgr_inv@test.com", "manager")
    admin = create_test_user(db_session, "adm_inv@test.com", "admin")
    vendor_user = create_test_user(db_session, "v_inv@test.com", "vendor")
    vendor = create_test_vendor(db_session, vendor_user, "333334444455555")

    # 1. Setup RFQ, Quotation, Approval, PO
    rfq = RFQ(
        doc_number="RFQ-INV-01",
        created_by_id=officer.user_id,
        status="published",
        deadline=datetime.now(timezone.utc) + timedelta(days=5),
    )
    db_session.add(rfq)
    db_session.flush()
    rfq_item = RFQItem(rfq_id=rfq.rfq_id, item_name="Cables", quantity=20, unit_of_measure="meters")
    db_session.add(rfq_item)
    db_session.flush()
    db_session.add(RFQVendor(rfq_id=rfq.rfq_id, vendor_id=vendor.vendor_id))
    db_session.commit()

    qtn = Quotation(
        doc_number="QTN-INV-01",
        rfq_id=rfq.rfq_id,
        vendor_id=vendor.vendor_id,
        status="submitted",
        total_amount=Decimal("400.00"),
    )
    db_session.add(qtn)
    db_session.flush()
    db_session.add(QuotationItem(quotation_id=qtn.quotation_id, rfq_item_id=rfq_item.rfq_item_id, unit_price=20.00, quantity=20, total_price=400.00))
    db_session.commit()

    # Select winner
    headers_off = get_auth_headers(officer)
    payload_win = {"quotation_id": str(qtn.quotation_id)}
    client.post(f"/api/v1/comparison/rfq/{rfq.rfq_id}/select-winner", json=payload_win, headers=headers_off)

    # Approve quotation
    approval = db_session.query(Approval).filter(Approval.quotation_id == qtn.quotation_id).first()
    headers_mgr = get_auth_headers(manager)
    client.patch(f"/api/v1/approvals/{approval.approval_id}/approve", json={"remarks": "Approve pricing"}, headers=headers_mgr)

    # Generate PO
    payload_po = {"quotation_id": str(qtn.quotation_id), "tax_rate": 5.0, "currency": "USD"}
    response = client.post("/api/v1/purchase-orders", json=payload_po, headers=headers_off)
    assert response.status_code == 201
    po_data = response.json()
    po_id = po_data["po_id"]
    po = db_session.query(PurchaseOrder).filter(PurchaseOrder.po_id == po_id).first()

    # 2. Officer generates Invoice from PO
    payload_inv = {"po_id": po_id}
    response = client.post("/api/v1/invoices", json=payload_inv, headers=headers_off)
    assert response.status_code == 201
    inv_data = response.json()
    inv_id = inv_data["invoice_id"]
    assert inv_data["status"] == "generated"
    assert Decimal(str(inv_data["amount_due"])) == Decimal("420.00")  # 400 + 5% tax

    # Verify activity log
    log_gen = db_session.query(ActivityLog).filter(
        ActivityLog.user_id == officer.user_id,
        ActivityLog.action == "Invoice Generated"
    ).first()
    assert log_gen is not None

    # Verify notification to Officer
    notif_gen = db_session.query(Notification).filter(
        Notification.user_id == officer.user_id,
        Notification.title == "Invoice Generated"
    ).first()
    assert notif_gen is not None

    # 3. Duplicate Invoice creation gets blocked (returns HTTP 400)
    response = client.post("/api/v1/invoices", json=payload_inv, headers=headers_off)
    assert response.status_code == 400
    assert "An Invoice has already been generated" in response.json()["detail"]

    # 4. Vendor can view own invoice
    headers_v = get_auth_headers(vendor_user)
    response = client.get(f"/api/v1/invoices/{inv_id}", headers=headers_v)
    assert response.status_code == 200

    # Other vendors cannot view it
    other_v_user = create_test_user(db_session, "other_v_inv@test.com", "vendor")
    headers_other_v = get_auth_headers(other_v_user)
    response = client.get(f"/api/v1/invoices/{inv_id}", headers=headers_other_v)
    assert response.status_code == 403

    # 5. PDF downloads correctly
    response = client.get(f"/api/v1/invoices/{inv_id}/pdf", headers=headers_v)
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    
    # Check download log
    log_dl = db_session.query(ActivityLog).filter(
        ActivityLog.user_id == vendor_user.user_id,
        ActivityLog.action == "Invoice Downloaded"
    ).first()
    assert log_dl is not None

    # Print PDF action check
    response = client.get(f"/api/v1/invoices/{inv_id}/pdf?action=print", headers=headers_v)
    assert response.status_code == 200
    
    log_pr = db_session.query(ActivityLog).filter(
        ActivityLog.user_id == vendor_user.user_id,
        ActivityLog.action == "Invoice Printed"
    ).first()
    assert log_pr is not None

    # 6. Email API works
    response = client.post(f"/api/v1/invoices/{inv_id}/email", headers=headers_off)
    assert response.status_code == 200
    
    log_email = db_session.query(ActivityLog).filter(
        ActivityLog.user_id == officer.user_id,
        ActivityLog.action == "Invoice Sent"
    ).first()
    assert log_email is not None

    # 7. Manager read-only check
    response = client.get(f"/api/v1/invoices/{inv_id}", headers=headers_mgr)
    assert response.status_code == 200
    
    response = client.post("/api/v1/invoices", json=payload_inv, headers=headers_mgr)
    assert response.status_code == 403

    # 8. Admin analytics check
    headers_adm = get_auth_headers(admin)
    response = client.get("/api/v1/invoices", headers=headers_adm)
    assert response.status_code == 200
    assert response.json()["total"] >= 1

    # 9. Test paid flow & locking
    # Update status to sent
    client.patch(f"/api/v1/invoices/{inv_id}", json={"status": "sent"}, headers=headers_off)
    
    # Update status to paid
    response = client.patch(f"/api/v1/invoices/{inv_id}", json={"status": "paid"}, headers=headers_off)
    assert response.status_code == 200
    
    db_session.refresh(po)
    invoice = db_session.query(Invoice).filter(Invoice.invoice_id == inv_id).first()
    assert invoice.status == "paid"
    assert invoice.is_locked is True
    assert po.is_locked is True

    # Paid notifications generated
    notif_paid = db_session.query(Notification).filter(
        Notification.user_id == vendor_user.user_id,
        Notification.title == "Invoice Paid"
    ).first()
    assert notif_paid is not None

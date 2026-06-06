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
from app.models.purchase_order import PurchaseOrder
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

def test_purchase_orders_complete_flow(client: TestClient, db_session: Session):
    officer = create_test_user(db_session, "off_po@test.com", "officer")
    manager = create_test_user(db_session, "mgr_po@test.com", "manager")
    admin = create_test_user(db_session, "adm_po@test.com", "admin")
    vendor_user = create_test_user(db_session, "v_po@test.com", "vendor")
    vendor = create_test_vendor(db_session, vendor_user, "222223333344444")
    
    # 1. Setup RFQ and Quotation
    rfq = RFQ(
        doc_number="RFQ-PO-01",
        created_by_id=officer.user_id,
        status="published",
        deadline=datetime.now(timezone.utc) + timedelta(days=5),
    )
    db_session.add(rfq)
    db_session.flush()
    rfq_item = RFQItem(rfq_id=rfq.rfq_id, item_name="Laptop", quantity=5, unit_of_measure="units")
    db_session.add(rfq_item)
    db_session.flush()
    db_session.add(RFQVendor(rfq_id=rfq.rfq_id, vendor_id=vendor.vendor_id))
    db_session.commit()

    qtn = Quotation(
        doc_number="QTN-PO-01",
        rfq_id=rfq.rfq_id,
        vendor_id=vendor.vendor_id,
        status="submitted",
        total_amount=Decimal("5000.00"),
    )
    db_session.add(qtn)
    db_session.flush()
    db_session.add(QuotationItem(quotation_id=qtn.quotation_id, rfq_item_id=rfq_item.rfq_item_id, unit_price=1000.00, quantity=5, total_price=5000.00))
    db_session.commit()

    # 2. Select quotation winner
    headers_off = get_auth_headers(officer)
    payload_win = {"quotation_id": str(qtn.quotation_id)}
    client.post(f"/api/v1/comparison/rfq/{rfq.rfq_id}/select-winner", json=payload_win, headers=headers_off)

    approval = db_session.query(Approval).filter(Approval.quotation_id == qtn.quotation_id).first()
    assert approval is not None

    # 3. Generating PO is blocked if quotation is NOT approved yet
    response = client.post("/api/v1/purchase-orders", json={"quotation_id": str(qtn.quotation_id)}, headers=headers_off)
    assert response.status_code == 400
    assert "Only approved quotations can generate" in response.json()["detail"]

    # 4. Manager approves quotation
    headers_mgr = get_auth_headers(manager)
    client.patch(f"/api/v1/approvals/{approval.approval_id}/approve", json={"remarks": "Approved by manager"}, headers=headers_mgr)

    # 5. Officer generates PO from approved quotation
    payload_po = {
        "quotation_id": str(qtn.quotation_id),
        "tax_rate": 10.0,
        "currency": "USD"
    }
    response = client.post("/api/v1/purchase-orders", json=payload_po, headers=headers_off)
    assert response.status_code == 201
    po_data = response.json()
    po_id = po_data["po_id"]
    assert po_data["status"] == "generated"
    assert Decimal(str(po_data["total_amount"])) == Decimal("5500.00")  # 5000 + 10% tax
    assert len(po_data["items"]) == 1
    assert po_data["items"][0]["item_name"] == "Laptop"
    assert Decimal(str(po_data["items"][0]["quantity"])) == Decimal("5.0000")
    assert Decimal(str(po_data["items"][0]["unit_price"])) == Decimal("1000.00")

    # Verify activity log
    gen_log = db_session.query(ActivityLog).filter(
        ActivityLog.user_id == officer.user_id,
        ActivityLog.action == "Purchase Order Generated"
    ).first()
    assert gen_log is not None

    # 6. Duplicate PO is blocked
    response = client.post("/api/v1/purchase-orders", json=payload_po, headers=headers_off)
    assert response.status_code == 400
    assert "A Purchase Order has already been generated" in response.json()["detail"]

    # 7. Visibility permissions check
    # Manager read-only
    response = client.get(f"/api/v1/purchase-orders/{po_id}", headers=headers_mgr)
    assert response.status_code == 200
    
    # Manager cannot create PO
    response = client.post("/api/v1/purchase-orders", json=payload_po, headers=headers_mgr)
    assert response.status_code == 403

    # Vendor can view own PO
    headers_v = get_auth_headers(vendor_user)
    response = client.get(f"/api/v1/purchase-orders/{po_id}", headers=headers_v)
    assert response.status_code == 200

    # Other vendors cannot view it
    other_vendor_user = create_test_user(db_session, "other_v@test.com", "vendor")
    headers_other_v = get_auth_headers(other_vendor_user)
    response = client.get(f"/api/v1/purchase-orders/{po_id}", headers=headers_other_v)
    assert response.status_code == 403

    # Admin read-only analytics/listing
    headers_adm = get_auth_headers(admin)
    response = client.get("/api/v1/purchase-orders", headers=headers_adm)
    assert response.status_code == 200
    assert response.json()["total"] >= 1

    # 8. Officer sends PO to vendor
    response = client.patch(f"/api/v1/purchase-orders/{po_id}/send", headers=headers_off)
    assert response.status_code == 200
    assert response.json()["status"] == "sent"

    # Verify vendor notification
    v_notif = db_session.query(Notification).filter(
        Notification.user_id == vendor_user.user_id,
        Notification.title == "Purchase Order Received"
    ).first()
    assert v_notif is not None

    # Verify send activity log
    send_log = db_session.query(ActivityLog).filter(
        ActivityLog.user_id == officer.user_id,
        ActivityLog.action == "Purchase Order Sent"
    ).first()
    assert send_log is not None

    # 9. Vendor accepts PO
    response = client.patch(f"/api/v1/purchase-orders/{po_id}", json={"status": "accepted"}, headers=headers_v)
    assert response.status_code == 200
    assert response.json()["status"] == "accepted"

    # Verify officer notification
    off_notif = db_session.query(Notification).filter(
        Notification.user_id == officer.user_id,
        Notification.title == "Purchase Order Accepted"
    ).first()
    assert off_notif is not None

    # 10. Officer marks PO as completed
    response = client.patch(f"/api/v1/purchase-orders/{po_id}/complete", headers=headers_off)
    assert response.status_code == 200
    assert response.json()["status"] == "completed"

    # Verify complete activity log
    comp_log = db_session.query(ActivityLog).filter(
        ActivityLog.user_id == officer.user_id,
        ActivityLog.action == "Purchase Order Completed"
    ).first()
    assert comp_log is not None

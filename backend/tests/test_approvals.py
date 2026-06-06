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

def test_approvals_workflow_lifecycle(client: TestClient, db_session: Session):
    # Setup users
    officer = create_test_user(db_session, "off_appr@test.com", "officer")
    manager = create_test_user(db_session, "mgr_appr@test.com", "manager")
    vendor_user = create_test_user(db_session, "v_appr@test.com", "vendor")
    vendor = create_test_vendor(db_session, vendor_user, "111112222233333")
    
    # 1. Setup RFQ and Quotation
    rfq = RFQ(
        doc_number="RFQ-APPR-01",
        created_by_id=officer.user_id,
        status="published",
        deadline=datetime.now(timezone.utc) + timedelta(days=5),
    )
    db_session.add(rfq)
    db_session.flush()
    rfq_item = RFQItem(rfq_id=rfq.rfq_id, item_name="Screws", quantity=100, unit_of_measure="units")
    db_session.add(rfq_item)
    db_session.flush()
    db_session.add(RFQVendor(rfq_id=rfq.rfq_id, vendor_id=vendor.vendor_id))
    db_session.commit()

    qtn = Quotation(
        doc_number="QTN-APPR-01",
        rfq_id=rfq.rfq_id,
        vendor_id=vendor.vendor_id,
        status="submitted",
        total_amount=Decimal("500.00"),
    )
    db_session.add(qtn)
    db_session.flush()
    db_session.add(QuotationItem(quotation_id=qtn.quotation_id, rfq_item_id=rfq_item.rfq_item_id, unit_price=5.00, quantity=100, total_price=500.00))
    db_session.commit()

    # 2. Select quotation winner as Officer (this triggers automatic creation of pending approval record)
    headers_off = get_auth_headers(officer)
    payload_win = {"quotation_id": str(qtn.quotation_id)}
    response = client.post(f"/api/v1/comparison/rfq/{rfq.rfq_id}/select-winner", json=payload_win, headers=headers_off)
    assert response.status_code == 200

    # Verify pending Approval record was automatically created via SQL event listener
    approval = db_session.query(Approval).filter(Approval.quotation_id == qtn.quotation_id).first()
    assert approval is not None
    assert approval.status == "pending"
    assert approval.remarks == "Pending manager review"

    # 3. Verify Manager can retrieve approval and logs "Approval Viewed"
    headers_mgr = get_auth_headers(manager)
    response = client.get(f"/api/v1/approvals/{approval.approval_id}", headers=headers_mgr)
    assert response.status_code == 200
    
    view_log = db_session.query(ActivityLog).filter(
        ActivityLog.user_id == manager.user_id,
        ActivityLog.action == "Approval Viewed"
    ).first()
    assert view_log is not None

    # 4. Officer and Vendor cannot approve or reject
    # Try with Officer
    response = client.patch(f"/api/v1/approvals/{approval.approval_id}/approve", json={"remarks": "Officer approve"}, headers=headers_off)
    assert response.status_code == 403
    
    # Try with Vendor
    headers_v = get_auth_headers(vendor_user)
    response = client.patch(f"/api/v1/approvals/{approval.approval_id}/approve", json={"remarks": "Vendor approve"}, headers=headers_v)
    assert response.status_code == 403

    # 5. Remarks are mandatory (min_length=1)
    response = client.patch(f"/api/v1/approvals/{approval.approval_id}/approve", json={"remarks": ""}, headers=headers_mgr)
    assert response.status_code == 422

    # 6. Manager approves quotation
    response = client.patch(f"/api/v1/approvals/{approval.approval_id}/approve", json={"remarks": "Approved: Pricing fits within budget."}, headers=headers_mgr)
    assert response.status_code == 200
    assert response.json()["status"] == "approved"
    assert response.json()["remarks"] == "Approved: Pricing fits within budget."

    # Verify database updates
    db_session.refresh(approval)
    assert approval.status == "approved"
    assert approval.manager_id == manager.user_id

    # Verify notifications generated
    # Officer notified
    off_notif = db_session.query(Notification).filter(
        Notification.user_id == officer.user_id,
        Notification.title == "Quotation Approved"
    ).first()
    assert off_notif is not None

    # Vendor notified
    v_notif = db_session.query(Notification).filter(
        Notification.user_id == vendor_user.user_id,
        Notification.title == "Quotation Approved"
    ).first()
    assert v_notif is not None

    # Verify activity log
    appr_log = db_session.query(ActivityLog).filter(
        ActivityLog.user_id == manager.user_id,
        ActivityLog.action == "Quotation Approved"
    ).first()
    assert appr_log is not None

    # 7. Approved quotation cannot be processed or rejected later
    response = client.patch(f"/api/v1/approvals/{approval.approval_id}/reject", json={"remarks": "Reject now?"}, headers=headers_mgr)
    assert response.status_code == 400
    assert "Only pending approvals can be processed" in response.json()["detail"]


def test_approvals_rejection_workflow(client: TestClient, db_session: Session):
    officer = create_test_user(db_session, "off_rej@test.com", "officer")
    manager = create_test_user(db_session, "mgr_rej@test.com", "manager")
    vendor_user = create_test_user(db_session, "v_rej@test.com", "vendor")
    vendor = create_test_vendor(db_session, vendor_user, "444445555566666")
    
    rfq = RFQ(
        doc_number="RFQ-REJ-01",
        created_by_id=officer.user_id,
        status="published",
        deadline=datetime.now(timezone.utc) + timedelta(days=5),
    )
    db_session.add(rfq)
    db_session.flush()
    rfq_item = RFQItem(rfq_id=rfq.rfq_id, item_name="Cables", quantity=10, unit_of_measure="meters")
    db_session.add(rfq_item)
    db_session.flush()
    db_session.add(RFQVendor(rfq_id=rfq.rfq_id, vendor_id=vendor.vendor_id))
    db_session.commit()

    qtn = Quotation(
        doc_number="QTN-REJ-01",
        rfq_id=rfq.rfq_id,
        vendor_id=vendor.vendor_id,
        status="submitted",
        total_amount=Decimal("200.00"),
    )
    db_session.add(qtn)
    db_session.flush()
    db_session.add(QuotationItem(quotation_id=qtn.quotation_id, rfq_item_id=rfq_item.rfq_item_id, unit_price=20.00, quantity=10, total_price=200.00))
    db_session.commit()

    # Officer selects winner -> creates pending approval
    headers_off = get_auth_headers(officer)
    payload_win = {"quotation_id": str(qtn.quotation_id)}
    client.post(f"/api/v1/comparison/rfq/{rfq.rfq_id}/select-winner", json=payload_win, headers=headers_off)

    approval = db_session.query(Approval).filter(Approval.quotation_id == qtn.quotation_id).first()
    assert approval is not None

    # Manager rejects approval
    headers_mgr = get_auth_headers(manager)
    response = client.patch(f"/api/v1/approvals/{approval.approval_id}/reject", json={"remarks": "Pricing is too high."}, headers=headers_mgr)
    assert response.status_code == 200
    assert response.json()["status"] == "rejected"

    db_session.refresh(approval)
    db_session.refresh(qtn)
    assert approval.status == "rejected"
    assert qtn.status == "rejected"

    # Verify rejection notifications
    off_notif = db_session.query(Notification).filter(
        Notification.user_id == officer.user_id,
        Notification.title == "Quotation Rejected"
    ).first()
    assert off_notif is not None

    v_notif = db_session.query(Notification).filter(
        Notification.user_id == vendor_user.user_id,
        Notification.title == "Quotation Rejected"
    ).first()
    assert v_notif is not None

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
from app.models.notification import Notification
from app.models.activity_log import ActivityLog


# ── TEST HELPERS ──────────────────────────────────────────────────────
def create_test_user(db: Session, email: str, role: str, is_active: bool = True) -> User:
    """Helper to create a user."""
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
    """Generate auth headers for simulated JWT login."""
    token_data = {
        "user_id": str(user.user_id),
        "email": user.email,
        "role": user.role,
    }
    token = create_access_token(token_data)
    return {"Authorization": f"Bearer {token}"}


def create_test_vendor(db: Session, user: User, gst: str) -> Vendor:
    """Helper to create a verified vendor profile."""
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

def test_officer_compares_and_selects_winner(client: TestClient, db_session: Session):
    """
    Test Case:
    1. Create RFQ and assign 2 Vendors.
    2. Vendors submit 2 separate quotations with different pricing and timelines.
    3. Officer views side-by-side comparison, verifies lowest price highlight and delivery timeline.
    4. Officer selects the winner quotation.
    5. Verify status transitions (winning to selected, other to rejected, RFQ to approved).
    6. Verify that notifications are generated for both vendors.
    """
    officer = create_test_user(db_session, "off_comp@test.com", "officer")
    headers_off = get_auth_headers(officer)

    # 1. Setup RFQ
    rfq = RFQ(
        doc_number="RFQ-COMP-01",
        created_by_id=officer.user_id,
        status="published",
        deadline=datetime.now(timezone.utc) + timedelta(days=5),
    )
    db_session.add(rfq)
    db_session.flush()
    rfq_item = RFQItem(rfq_id=rfq.rfq_id, item_name="Hard Drive", quantity=10, unit_of_measure="units")
    db_session.add(rfq_item)
    db_session.flush()

    # Setup 2 Vendors
    v1_user = create_test_user(db_session, "v1_comp@test.com", "vendor")
    v1 = create_test_vendor(db_session, v1_user, "123451234512345")
    v2_user = create_test_user(db_session, "v2_comp@test.com", "vendor")
    v2 = create_test_vendor(db_session, v2_user, "678906789067890")

    db_session.add(RFQVendor(rfq_id=rfq.rfq_id, vendor_id=v1.vendor_id))
    db_session.add(RFQVendor(rfq_id=rfq.rfq_id, vendor_id=v2.vendor_id))
    db_session.commit()

    # 2. Submit 2 Quotations
    # Quotation 1 (Higher price, faster delivery)
    q1 = Quotation(
        doc_number="QTN-COMP-01", rfq_id=rfq.rfq_id, vendor_id=v1.vendor_id,
        status="submitted", delivery_timeline="2 days", total_amount=Decimal("1500.00")
    )
    db_session.add(q1)
    db_session.flush()
    db_session.add(QuotationItem(quotation_id=q1.quotation_id, rfq_item_id=rfq_item.rfq_item_id, unit_price=150.00, quantity=10, total_price=1500.00))

    # Quotation 2 (Lower price, slower delivery)
    q2 = Quotation(
        doc_number="QTN-COMP-02", rfq_id=rfq.rfq_id, vendor_id=v2.vendor_id,
        status="submitted", delivery_timeline="7 days", total_amount=Decimal("1200.00")
    )
    db_session.add(q2)
    db_session.flush()
    db_session.add(QuotationItem(quotation_id=q2.quotation_id, rfq_item_id=rfq_item.rfq_item_id, unit_price=120.00, quantity=10, total_price=1200.00))
    db_session.commit()

    # 3. Officer views comparison
    response = client.get(f"/api/v1/comparison/rfq/{rfq.rfq_id}", headers=headers_off)
    assert response.status_code == 200
    comp_data = response.json()
    assert len(comp_data["quotations"]) == 2

    # Check lowest price highlight and timeline
    qtns = comp_data["quotations"]
    qtn_map = {q["doc_number"]: q for q in qtns}
    assert qtn_map["QTN-COMP-02"]["is_lowest_price"] is True
    assert qtn_map["QTN-COMP-01"]["is_lowest_price"] is False
    assert qtn_map["QTN-COMP-01"]["delivery_timeline"] == "2 days"
    assert qtn_map["QTN-COMP-02"]["delivery_timeline"] == "7 days"
    assert qtn_map["QTN-COMP-01"]["price_calculation_verified"] is True

    # 4. Officer selects winner
    payload_win = {"quotation_id": str(q2.quotation_id)}
    response = client.post(f"/api/v1/comparison/rfq/{rfq.rfq_id}/select-winner", json=payload_win, headers=headers_off)
    assert response.status_code == 200

    # 5. Verify status transitions
    db_session.refresh(q1)
    db_session.refresh(q2)
    db_session.refresh(rfq)
    assert q2.status == "selected"
    assert q1.status == "rejected"
    assert rfq.status == "approved"

    # 6. Verify Notifications
    # Notification to winner
    win_notif = db_session.query(Notification).filter(
        Notification.user_id == v2_user.user_id,
        Notification.title == "Winning Vendor Selected"
    ).first()
    assert win_notif is not None

    # Notification to rejected vendor
    rej_notif = db_session.query(Notification).filter(
        Notification.user_id == v1_user.user_id,
        Notification.title == "Other Vendors Notified"
    ).first()
    assert rej_notif is not None

    # Verify Activity Log
    log = db_session.query(ActivityLog).filter(
        ActivityLog.user_id == officer.user_id,
        ActivityLog.action == "Winning Quotation Selected"
    ).first()
    assert log is not None


def test_manager_readonly_vendor_denied(client: TestClient, db_session: Session):
    """
    Test Case:
    1. Setup RFQ and 2 Quotations.
    2. Manager reads comparison (Expects 200).
    3. Manager attempts to select winner (Expects 403).
    4. Vendor attempts to read comparison (Expects 403).
    5. Vendor attempts to select winner (Expects 403).
    """
    officer = create_test_user(db_session, "off_denied@test.com", "officer")
    manager = create_test_user(db_session, "mgr_denied@test.com", "manager")
    vendor_user = create_test_user(db_session, "v_denied@test.com", "vendor")
    vendor1 = create_test_vendor(db_session, vendor_user, "111110000011111")
    vendor2_user = create_test_user(db_session, "v2_denied@test.com", "vendor")
    vendor2 = create_test_vendor(db_session, vendor2_user, "222220000022222")

    # Setup RFQ and Quotations
    rfq = RFQ(
        doc_number="RFQ-DENIED-TEST",
        created_by_id=officer.user_id,
        status="published",
        deadline=datetime.now(timezone.utc) + timedelta(days=5),
    )
    db_session.add(rfq)
    db_session.flush()
    rfq_item = RFQItem(rfq_id=rfq.rfq_id, item_name="Cable", quantity=5, unit_of_measure="units")
    db_session.add(rfq_item)
    db_session.flush()
    db_session.add(RFQVendor(rfq_id=rfq.rfq_id, vendor_id=vendor1.vendor_id))
    db_session.add(RFQVendor(rfq_id=rfq.rfq_id, vendor_id=vendor2.vendor_id))
    db_session.commit()

    q1 = Quotation(doc_number="QTN-D-1", rfq_id=rfq.rfq_id, vendor_id=vendor1.vendor_id, status="submitted", total_amount=Decimal("100.00"))
    db_session.add(q1)
    db_session.flush()
    db_session.add(QuotationItem(quotation_id=q1.quotation_id, rfq_item_id=rfq_item.rfq_item_id, unit_price=20.00, quantity=5, total_price=100.00))

    q2 = Quotation(doc_number="QTN-D-2", rfq_id=rfq.rfq_id, vendor_id=vendor2.vendor_id, status="submitted", total_amount=Decimal("120.00"))
    db_session.add(q2)
    db_session.flush()
    db_session.add(QuotationItem(quotation_id=q2.quotation_id, rfq_item_id=rfq_item.rfq_item_id, unit_price=24.00, quantity=5, total_price=120.00))
    db_session.commit()

    # 2. Manager reads comparison (Expects 200)
    headers_mgr = get_auth_headers(manager)
    response = client.get(f"/api/v1/comparison/rfq/{rfq.rfq_id}", headers=headers_mgr)
    assert response.status_code == 200

    # 3. Manager tries to select winner (Expects 403)
    payload_win = {"quotation_id": str(q1.quotation_id)}
    response = client.post(f"/api/v1/comparison/rfq/{rfq.rfq_id}/select-winner", json=payload_win, headers=headers_mgr)
    assert response.status_code == 403

    # 4. Vendor tries to read comparison (Expects 403)
    headers_v = get_auth_headers(vendor_user)
    response = client.get(f"/api/v1/comparison/rfq/{rfq.rfq_id}", headers=headers_v)
    assert response.status_code == 403

    # 5. Vendor tries to select winner (Expects 403)
    response = client.post(f"/api/v1/comparison/rfq/{rfq.rfq_id}/select-winner", json=payload_win, headers=headers_v)
    assert response.status_code == 403

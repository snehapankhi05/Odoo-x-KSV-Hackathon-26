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
        company_name="Test Supplier Co",
        contact_person="Supplier Name",
        gst_number=gst,
        category="Logistics",
        address="789 Sourcing Lane",
        status="active",
    )
    db.add(vendor)
    db.commit()
    db.refresh(vendor)
    return vendor


# ── TEST CASES ────────────────────────────────────────────────────────

def test_quotation_lifecycle_and_deadline_checks(client: TestClient, db_session: Session):
    """
    Test Case:
    1. Create an RFQ and assign Vendor 1. Publish RFQ.
    2. Vendor 1 submits a quotation (verifies automatic price calculations, notes, delivery timeline).
    3. Vendor 1 tries to submit a duplicate quotation (Expects 400).
    4. Vendor 1 edits quotation before deadline (Expects 200).
    5. Setup an RFQ with past deadline. Vendor 1 tries to submit (Expects 400).
    """
    # Setup users
    officer = create_test_user(db_session, "off_q_life@test.com", "officer")
    vendor_user = create_test_user(db_session, "v_q_life@test.com", "vendor")
    vendor = create_test_vendor(db_session, vendor_user, "999998888877777")
    headers_v = get_auth_headers(vendor_user)

    # 1. Setup RFQ and publish
    rfq = RFQ(
        doc_number="RFQ-Q-LIFE-01",
        created_by_id=officer.user_id,
        status="draft",
        deadline=datetime.now(timezone.utc) + timedelta(days=5),
    )
    db_session.add(rfq)
    db_session.flush()
    rfq_item = RFQItem(rfq_id=rfq.rfq_id, item_name="Processor", quantity=10, unit_of_measure="units")
    db_session.add(rfq_item)
    db_session.flush()
    db_session.add(RFQVendor(rfq_id=rfq.rfq_id, vendor_id=vendor.vendor_id))
    db_session.commit()

    # Publish RFQ
    headers_off = get_auth_headers(officer)
    client.patch(f"/api/v1/rfqs/{rfq.rfq_id}/publish", headers=headers_off)

    # 2. Vendor 1 submits quotation
    payload = {
        "rfq_id": str(rfq.rfq_id),
        "vendor_id": str(vendor.vendor_id),
        "status": "draft",
        "delivery_timeline": "5 days",
        "notes": "Premium quality",
        "items": [
            {
                "rfq_item_id": str(rfq_item.rfq_item_id),
                "unit_price": 250.00,
                "quantity": 10.0,
                "total_price": 0.00  # Will be auto-calculated
            }
        ]
    }
    response = client.post("/api/v1/quotations", json=payload, headers=headers_v)
    assert response.status_code == 201
    qtn_data = response.json()
    assert qtn_data["status"] == "draft"
    assert qtn_data["delivery_timeline"] == "5 days"
    assert qtn_data["notes"] == "Premium quality"
    assert Decimal(str(qtn_data["total_amount"])) == Decimal("2500.00")

    # 3. Duplicate submission check
    response = client.post("/api/v1/quotations", json=payload, headers=headers_v)
    assert response.status_code == 400
    assert "Quotation already submitted for this RFQ" in response.json()["detail"]

    # 4. Edit quotation before deadline
    qtn_id = qtn_data["quotation_id"]
    payload_edit = {
        "status": "submitted",
        "notes": "Premium quality - updated notes"
    }
    response = client.patch(f"/api/v1/quotations/{qtn_id}", json=payload_edit, headers=headers_v)
    assert response.status_code == 200
    assert response.json()["status"] == "submitted"
    assert response.json()["notes"] == "Premium quality - updated notes"

    # Verify notification generated for Officer
    notif = db_session.query(Notification).filter(
        Notification.user_id == officer.user_id,
        Notification.title == "Quotation Updated"
    ).first()
    assert notif is not None

    # 5. Blocked after deadline test
    rfq_past = RFQ(
        doc_number="RFQ-Q-PAST-01",
        created_by_id=officer.user_id,
        status="published",
        deadline=datetime.now(timezone.utc) - timedelta(hours=1),
    )
    db_session.add(rfq_past)
    db_session.flush()
    rfq_past_item = RFQItem(rfq_id=rfq_past.rfq_id, item_name="Cooler", quantity=5, unit_of_measure="units")
    db_session.add(rfq_past_item)
    db_session.add(RFQVendor(rfq_id=rfq_past.rfq_id, vendor_id=vendor.vendor_id))
    db_session.commit()

    payload_past = {
        "rfq_id": str(rfq_past.rfq_id),
        "vendor_id": str(vendor.vendor_id),
        "status": "submitted",
        "items": [
            {
                "rfq_item_id": str(rfq_past_item.rfq_item_id),
                "unit_price": 50.00,
                "quantity": 5.0,
                "total_price": 250.00
            }
        ]
    }
    response = client.post("/api/v1/quotations", json=payload_past, headers=headers_v)
    assert response.status_code == 400
    assert "Cannot submit quotation after RFQ deadline" in response.json()["detail"]


def test_officer_manager_admin_roles(client: TestClient, db_session: Session):
    """
    Test Case:
    1. Setup a quotation.
    2. Officer lists all quotations (Expects 200).
    3. Officer views details of the quotation (Expects 200).
    4. Manager reads quotation details (Expects 200).
    5. Manager tries to edit quotation (Expects 403).
    6. Admin can list all quotations (Expects 200).
    """
    officer = create_test_user(db_session, "off_roles@test.com", "officer")
    manager = create_test_user(db_session, "mgr_roles@test.com", "manager")
    admin = create_test_user(db_session, "adm_roles@test.com", "admin")
    vendor_user = create_test_user(db_session, "v_roles@test.com", "vendor")
    vendor = create_test_vendor(db_session, vendor_user, "000001111122222")

    # Setup RFQ and Quotation
    rfq = RFQ(
        doc_number="RFQ-ROLE-TEST",
        created_by_id=officer.user_id,
        status="published",
        deadline=datetime.now(timezone.utc) + timedelta(days=5),
    )
    db_session.add(rfq)
    db_session.flush()
    rfq_item = RFQItem(rfq_id=rfq.rfq_id, item_name="Hardware", quantity=1, unit_of_measure="units")
    db_session.add(rfq_item)
    db_session.flush()
    db_session.add(RFQVendor(rfq_id=rfq.rfq_id, vendor_id=vendor.vendor_id))
    db_session.commit()

    # Create Quotation
    qtn = Quotation(
        doc_number="QTN-ROLE-TEST-01",
        rfq_id=rfq.rfq_id,
        vendor_id=vendor.vendor_id,
        status="submitted",
        total_amount=Decimal("150.00"),
    )
    db_session.add(qtn)
    db_session.flush()
    db_session.add(QuotationItem(quotation_id=qtn.quotation_id, rfq_item_id=rfq_item.rfq_item_id, unit_price=150.00, quantity=1, total_price=150.00))
    db_session.commit()

    # 2. Officer lists all quotations
    headers_off = get_auth_headers(officer)
    response = client.get("/api/v1/quotations", headers=headers_off)
    assert response.status_code == 200
    assert response.json()["total"] >= 1

    # 3. Officer views details
    response = client.get(f"/api/v1/quotations/{qtn.quotation_id}", headers=headers_off)
    assert response.status_code == 200

    # 4. Manager reads details
    headers_mgr = get_auth_headers(manager)
    response = client.get(f"/api/v1/quotations/{qtn.quotation_id}", headers=headers_mgr)
    assert response.status_code == 200

    # 5. Manager tries to edit (Expects 403 - restricted to Vendor only)
    payload_edit = {"delivery_timeline": "Immediate"}
    response = client.patch(f"/api/v1/quotations/{qtn.quotation_id}", json=payload_edit, headers=headers_mgr)
    assert response.status_code == 403

    # 6. Admin lists quotations
    headers_adm = get_auth_headers(admin)
    response = client.get("/api/v1/quotations", headers=headers_adm)
    assert response.status_code == 200
    assert response.json()["total"] >= 1

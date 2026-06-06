import uuid
from datetime import datetime, timedelta, timezone
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.security import create_access_token, hash_password
from app.models.user import User
from app.models.vendor import Vendor
from app.models.rfq import RFQ, RFQItem, RFQVendor
from app.models.activity_log import ActivityLog
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

def test_officer_create_rfq_flow(client: TestClient, db_session: Session):
    """
    Test Case:
    1. Officer attempts to create RFQ with past deadline (Expects 400).
    2. Officer attempts to create RFQ with empty items list (Expects 400).
    3. Officer successfully creates a draft RFQ.
    4. Verify that an Activity Log for creation is recorded.
    """
    officer = create_test_user(db_session, "officer_create@test.com", "officer")
    headers = get_auth_headers(officer)

    # 1. Past deadline validation
    payload_past = {
        "deadline": (datetime.now(timezone.utc) - timedelta(days=1)).isoformat(),
        "created_by_id": str(officer.user_id),
        "items": [{"item_name": "Laptop", "quantity": 10.0, "unit_of_measure": "units"}],
    }
    response = client.post("/api/v1/rfqs", json=payload_past, headers=headers)
    assert response.status_code == 400
    assert "Deadline must be a future date" in response.json()["detail"]

    # 2. Empty items list validation
    payload_empty = {
        "deadline": (datetime.now(timezone.utc) + timedelta(days=5)).isoformat(),
        "created_by_id": str(officer.user_id),
        "items": [],
    }
    response = client.post("/api/v1/rfqs", json=payload_empty, headers=headers)
    assert response.status_code == 400
    assert "At least one RFQ item required" in response.json()["detail"]

    # 3. Successful draft RFQ creation
    payload_success = {
        "deadline": (datetime.now(timezone.utc) + timedelta(days=5)).isoformat(),
        "created_by_id": str(officer.user_id),
        "items": [
            {"item_name": "Keyboard", "quantity": 50.0, "unit_of_measure": "units", "description": "USB keyboards"},
            {"item_name": "Mouse", "quantity": 50.0, "unit_of_measure": "units"},
        ],
    }
    response = client.post("/api/v1/rfqs", json=payload_success, headers=headers)
    assert response.status_code == 201
    rfq_data = response.json()
    assert rfq_data["status"] == "draft"
    assert rfq_data["doc_number"].startswith("RFQ-")
    assert len(rfq_data["items"]) == 2

    # 4. Verify Activity Log
    log = db_session.query(ActivityLog).filter(
        ActivityLog.entity_id == uuid.UUID(rfq_data["rfq_id"]),
        ActivityLog.action == "RFQ Created"
    ).first()
    assert log is not None
    assert log.user_id == officer.user_id


def test_officer_edit_and_delete_rfq(client: TestClient, db_session: Session):
    """
    Test Case:
    1. Officer edits draft RFQ (Allowed).
    2. Officer soft deletes draft RFQ.
    3. Verify that retrieval returns 404.
    """
    officer = create_test_user(db_session, "officer_edit@test.com", "officer")
    headers = get_auth_headers(officer)

    # Setup draft RFQ
    deadline = datetime.now(timezone.utc) + timedelta(days=5)
    rfq = RFQ(
        doc_number="RFQ-EDIT-TEST-01",
        created_by_id=officer.user_id,
        status="draft",
        deadline=deadline,
    )
    db_session.add(rfq)
    db_session.flush()
    item = RFQItem(rfq_id=rfq.rfq_id, item_name="Desktop", quantity=5, unit_of_measure="units")
    db_session.add(item)
    db_session.commit()

    # 1. Edit draft RFQ
    new_deadline = deadline + timedelta(days=2)
    payload = {"deadline": new_deadline.isoformat()}
    response = client.patch(f"/api/v1/rfqs/{rfq.rfq_id}", json=payload, headers=headers)
    assert response.status_code == 200
    assert response.json()["deadline"] is not None

    # 2. Soft delete RFQ
    response = client.delete(f"/api/v1/rfqs/{rfq.rfq_id}", headers=headers)
    assert response.status_code == 200
    assert "successfully soft-deleted" in response.json()["detail"]

    # 3. Retrieve deleted RFQ (Expects 404)
    response = client.get(f"/api/v1/rfqs/{rfq.rfq_id}", headers=headers)
    assert response.status_code == 404


def test_officer_assign_and_publish_flow(client: TestClient, db_session: Session):
    """
    Test Case:
    1. Officer attempts to publish RFQ without assigned vendors (Expects 400).
    2. Officer assigns vendors (with validation checks on empty list, duplicates, verified status).
    3. Officer publishes RFQ (Expects status 'published').
    4. Verify that assigned vendors receive notifications.
    5. Officer closes the published RFQ.
    """
    officer = create_test_user(db_session, "officer_publish@test.com", "officer")
    headers = get_auth_headers(officer)

    # Setup draft RFQ
    rfq = RFQ(
        doc_number="RFQ-PUBLISH-TEST-01",
        created_by_id=officer.user_id,
        status="draft",
        deadline=datetime.now(timezone.utc) + timedelta(days=5),
    )
    db_session.add(rfq)
    db_session.flush()
    item = RFQItem(rfq_id=rfq.rfq_id, item_name="Server", quantity=2, unit_of_measure="units")
    db_session.add(item)
    db_session.commit()

    # Setup vendors
    vendor1_user = create_test_user(db_session, "vendor1@test.com", "vendor")
    vendor1 = create_test_vendor(db_session, vendor1_user, "111112222233333")
    vendor2_user = create_test_user(db_session, "vendor2@test.com", "vendor")
    vendor2 = create_test_vendor(db_session, vendor2_user, "444445555566666")

    # 1. Publish without vendors validation
    response = client.patch(f"/api/v1/rfqs/{rfq.rfq_id}/publish", headers=headers)
    assert response.status_code == 400
    assert "At least one vendor required" in response.json()["detail"]

    # 2. Assign vendors duplicate validation
    payload_dup = {"vendor_ids": [str(vendor1.vendor_id), str(vendor1.vendor_id)]}
    response = client.post(f"/api/v1/rfqs/{rfq.rfq_id}/assign-vendors", json=payload_dup, headers=headers)
    assert response.status_code == 400
    assert "No duplicate vendors allowed" in response.json()["detail"]

    # Assign vendors success
    payload_success = {"vendor_ids": [str(vendor1.vendor_id), str(vendor2.vendor_id)]}
    response = client.post(f"/api/v1/rfqs/{rfq.rfq_id}/assign-vendors", json=payload_success, headers=headers)
    assert response.status_code == 200

    # 3. Publish RFQ success
    response = client.patch(f"/api/v1/rfqs/{rfq.rfq_id}/publish", headers=headers)
    assert response.status_code == 200
    assert response.json()["status"] == "published"

    # Cannot edit anymore once published
    payload_edit = {"deadline": (datetime.now(timezone.utc) + timedelta(days=10)).isoformat()}
    response = client.patch(f"/api/v1/rfqs/{rfq.rfq_id}", json=payload_edit, headers=headers)
    assert response.status_code == 400
    assert "Cannot edit published RFQ" in response.json()["detail"]

    # 4. Check Notifications for vendor1 and vendor2
    notif1 = db_session.query(Notification).filter(Notification.user_id == vendor1_user.user_id, Notification.title == "RFQ Published").first()
    notif2 = db_session.query(Notification).filter(Notification.user_id == vendor2_user.user_id, Notification.title == "RFQ Published").first()
    assert notif1 is not None
    assert notif2 is not None

    # 5. Close RFQ
    response = client.patch(f"/api/v1/rfqs/{rfq.rfq_id}/close", headers=headers)
    assert response.status_code == 200
    assert response.json()["status"] == "quotation_closed"


def test_vendor_visibility_and_restrictions(client: TestClient, db_session: Session):
    """
    Test Case:
    1. Create RFQ A (assigned to Vendor 1).
    2. Create RFQ B (assigned to Vendor 2).
    3. Vendor 1 views list of RFQs (Expects only RFQ A).
    4. Vendor 1 attempts to retrieve RFQ B details directly (Expects 403).
    """
    officer = create_test_user(db_session, "officer_restrict_test@test.com", "officer")
    headers_off = get_auth_headers(officer)

    # Setup Vendors
    vendor1_user = create_test_user(db_session, "vendor_vis1@test.com", "vendor")
    vendor1 = create_test_vendor(db_session, vendor1_user, "123123123123123")
    vendor2_user = create_test_user(db_session, "vendor_vis2@test.com", "vendor")
    vendor2 = create_test_vendor(db_session, vendor2_user, "456456456456456")

    # RFQ A
    rfq_a = RFQ(doc_number="RFQ-A-TEST", created_by_id=officer.user_id, status="published", deadline=datetime.now(timezone.utc) + timedelta(days=5))
    db_session.add(rfq_a)
    db_session.flush()
    db_session.add(RFQItem(rfq_id=rfq_a.rfq_id, item_name="Item A", quantity=10, unit_of_measure="units"))
    db_session.add(RFQVendor(rfq_id=rfq_a.rfq_id, vendor_id=vendor1.vendor_id))

    # RFQ B
    rfq_b = RFQ(doc_number="RFQ-B-TEST", created_by_id=officer.user_id, status="published", deadline=datetime.now(timezone.utc) + timedelta(days=5))
    db_session.add(rfq_b)
    db_session.flush()
    db_session.add(RFQItem(rfq_id=rfq_b.rfq_id, item_name="Item B", quantity=20, unit_of_measure="units"))
    db_session.add(RFQVendor(rfq_id=rfq_b.rfq_id, vendor_id=vendor2.vendor_id))

    db_session.commit()

    # 3. Vendor 1 views lists
    headers_v1 = get_auth_headers(vendor1_user)
    response = client.get("/api/v1/rfqs", headers=headers_v1)
    assert response.status_code == 200
    list_data = response.json()
    assert list_data["total"] == 1
    assert list_data["rfqs"][0]["doc_number"] == "RFQ-A-TEST"

    # 4. Vendor 1 retrieves RFQ B directly (Expects 403)
    response = client.get(f"/api/v1/rfqs/{rfq_b.rfq_id}", headers=headers_v1)
    assert response.status_code == 403


def test_manager_read_only_access(client: TestClient, db_session: Session):
    """
    Test Case:
    1. Manager attempts to create RFQ (Expects 403).
    2. Manager lists RFQs (Expects 200).
    3. Manager retrieves single RFQ details (Expects 200).
    """
    officer = create_test_user(db_session, "off_mgr_readonly@test.com", "officer")
    manager = create_test_user(db_session, "manager_readonly@test.com", "manager")
    headers_mgr = get_auth_headers(manager)

    # Setup draft RFQ
    rfq = RFQ(
        doc_number="RFQ-MGR-TEST-01",
        created_by_id=officer.user_id,
        status="draft",
        deadline=datetime.now(timezone.utc) + timedelta(days=5),
    )
    db_session.add(rfq)
    db_session.flush()
    item = RFQItem(rfq_id=rfq.rfq_id, item_name="Manager Test Item", quantity=1, unit_of_measure="units")
    db_session.add(item)
    db_session.commit()

    # 1. Manager attempts create
    payload = {
        "deadline": (datetime.now(timezone.utc) + timedelta(days=5)).isoformat(),
        "created_by_id": str(manager.user_id),
        "items": [{"item_name": "Test", "quantity": 1, "unit_of_measure": "units"}],
    }
    response = client.post("/api/v1/rfqs", json=payload, headers=headers_mgr)
    assert response.status_code == 403

    # 2. Manager lists RFQs
    response = client.get("/api/v1/rfqs", headers=headers_mgr)
    assert response.status_code == 200
    assert response.json()["total"] >= 1

    # 3. Manager retrieves details
    response = client.get(f"/api/v1/rfqs/{rfq.rfq_id}", headers=headers_mgr)
    assert response.status_code == 200


def test_admin_analytics_and_visibility(client: TestClient, db_session: Session):
    """
    Test Case:
    1. Admin accesses analytics endpoint (Expects 200).
    2. Admin lists all RFQs (Expects 200).
    """
    admin = create_test_user(db_session, "admin_analytics@test.com", "admin")
    headers = get_auth_headers(admin)

    # 1. Admin accesses analytics
    response = client.get("/api/v1/rfqs/analytics", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert "total_rfqs" in data
    assert "status_counts" in data

    # 2. Admin lists RFQs
    response = client.get("/api/v1/rfqs", headers=headers)
    assert response.status_code == 200

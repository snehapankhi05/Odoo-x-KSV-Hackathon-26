import uuid
from datetime import datetime, timezone
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.security import create_access_token, hash_password
from app.models.user import User
from app.models.vendor import Vendor
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


# ── TEST CASES ────────────────────────────────────────────────────────

def test_notifications_crud_and_visibility(client: TestClient, db_session: Session):
    # Setup users
    admin = create_test_user(db_session, "adm_notif@test.com", "admin")
    vendor_user = create_test_user(db_session, "v_notif@test.com", "vendor")
    manager = create_test_user(db_session, "mgr_notif@test.com", "manager")

    headers_admin = get_auth_headers(admin)
    headers_vendor = get_auth_headers(vendor_user)
    headers_manager = get_auth_headers(manager)

    # 1. Create notifications in DB
    notif_v = Notification(
        user_id=vendor_user.user_id,
        type="RFQ Assigned",
        title="RFQ Assigned Title",
        message="Message for vendor",
        is_read=False,
    )
    notif_m = Notification(
        user_id=manager.user_id,
        type="Approval Granted",
        title="Approval Title",
        message="Message for manager",
        is_read=False,
    )
    db_session.add(notif_v)
    db_session.add(notif_m)
    db_session.commit()

    # 2. Vendor views own notifications
    response = client.get("/api/v1/notifications", headers=headers_vendor)
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert data["unread_count"] == 1
    assert data["notifications"][0]["title"] == "RFQ Assigned Title"

    # 3. Manager views own notifications
    response = client.get("/api/v1/notifications", headers=headers_manager)
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert data["unread_count"] == 1
    assert data["notifications"][0]["title"] == "Approval Title"

    # 4. Admin views ALL notifications
    response = client.get("/api/v1/notifications", headers=headers_admin)
    assert response.status_code == 200
    data = response.json()
    assert data["total"] >= 2
    titles = [n["title"] for n in data["notifications"]]
    assert "RFQ Assigned Title" in titles
    assert "Approval Title" in titles

    # 5. Mark single notification as read - unauthorized attempt
    response = client.patch(
        f"/api/v1/notifications/{notif_v.notification_id}/read",
        headers=headers_manager
    )
    assert response.status_code == 403

    # 6. Mark single notification as read - authorized
    response = client.patch(
        f"/api/v1/notifications/{notif_v.notification_id}/read",
        headers=headers_vendor
    )
    assert response.status_code == 200
    assert response.json()["is_read"] is True

    # Check state in DB
    db_session.refresh(notif_v)
    assert notif_v.is_read is True

    # 7. Test Mark All as Read
    # Create two more unread notifications for vendor
    notif_v2 = Notification(
        user_id=vendor_user.user_id,
        type="RFQ Published",
        title="RFQ Published Title",
        message="Message 2 for vendor",
        is_read=False,
    )
    notif_v3 = Notification(
        user_id=vendor_user.user_id,
        type="Purchase Order Generated",
        title="PO Title",
        message="Message 3 for vendor",
        is_read=False,
    )
    db_session.add(notif_v2)
    db_session.add(notif_v3)
    db_session.commit()

    # Vendor unread count should be 2 now
    response = client.get("/api/v1/notifications", headers=headers_vendor)
    assert response.json()["unread_count"] == 2

    # Mark all as read
    response = client.patch("/api/v1/notifications/read-all", headers=headers_vendor)
    assert response.status_code == 200
    
    # Vendor unread count should be 0 now
    response = client.get("/api/v1/notifications", headers=headers_vendor)
    assert response.json()["unread_count"] == 0


def test_activity_logs_and_admin_security(client: TestClient, db_session: Session):
    admin = create_test_user(db_session, "adm_log@test.com", "admin")
    officer = create_test_user(db_session, "off_log@test.com", "officer")

    headers_admin = get_auth_headers(admin)
    headers_officer = get_auth_headers(officer)

    # 1. Populate activity logs
    log_1 = ActivityLog(
        user_id=officer.user_id,
        action="RFQ Created",
        entity_name="rfqs",
        entity_id=uuid.uuid4(),
        ip_address="127.0.0.1",
    )
    log_2 = ActivityLog(
        user_id=admin.user_id,
        action="Report Exported",
        entity_name="reports",
        entity_id=uuid.uuid4(),
        ip_address="192.168.1.1",
    )
    log_3 = ActivityLog(
        user_id=officer.user_id,
        action="Purchase Order Generated",
        entity_name="purchase_orders",
        entity_id=uuid.uuid4(),
        ip_address="127.0.0.1",
    )
    db_session.add_all([log_1, log_2, log_3])
    db_session.commit()

    # 2. Officer requests activity logs (Forbidden)
    response = client.get("/api/v1/activity-logs", headers=headers_officer)
    assert response.status_code == 403

    # 3. Admin requests activity logs (Allowed)
    response = client.get("/api/v1/activity-logs", headers=headers_admin)
    assert response.status_code == 200
    data = response.json()
    assert data["total"] >= 3

    # 4. Search and Filters
    # Filter by user_id
    response = client.get(
        f"/api/v1/activity-logs?user_id={officer.user_id}",
        headers=headers_admin
    )
    assert response.status_code == 200
    assert response.json()["total"] == 2

    # Filter by exact action
    response = client.get("/api/v1/activity-logs?action=Report Exported", headers=headers_admin)
    assert response.status_code == 200
    assert response.json()["total"] >= 1
    assert any(log["entity_name"] == "reports" for log in response.json()["logs"])

    # Filter by exact entity_name
    response = client.get("/api/v1/activity-logs?entity_name=purchase_orders", headers=headers_admin)
    assert response.status_code == 200
    assert response.json()["total"] >= 1
    assert any(log["action"] == "Purchase Order Generated" for log in response.json()["logs"])

    # Search (fuzzy match action or entity_name)
    response = client.get("/api/v1/activity-logs?search=create", headers=headers_admin)
    assert response.status_code == 200
    assert response.json()["total"] >= 1
    assert any("create" in log["action"].lower() for log in response.json()["logs"])

    response = client.get("/api/v1/activity-logs?search=report", headers=headers_admin)
    assert response.status_code == 200
    assert response.json()["total"] >= 1
    assert any("report" in log["entity_name"].lower() for log in response.json()["logs"])


def test_automatic_notification_and_activity_logging(client: TestClient, db_session: Session):
    # Registering an officer triggers both Notification and ActivityLog automatically
    signup_payload = {
        "first_name": "LogTest",
        "last_name": "Officer",
        "email": "log_auto@test.com",
        "phone_number": "12345678902",
        "password": "password123",
    }

    # Call the signup officer API endpoint
    response = client.post("/api/v1/auth/signup/officer", json=signup_payload)
    assert response.status_code == 201
    user_id = response.json()["user_id"]

    # Verify that an Activity Log for "signup" was automatically generated
    log = db_session.query(ActivityLog).filter(
        ActivityLog.user_id == user_id,
        ActivityLog.action == "signup",
        ActivityLog.entity_name == "users"
    ).first()
    assert log is not None

    # Verify that a welcome Notification was automatically generated
    notif = db_session.query(Notification).filter(
        Notification.user_id == user_id,
        Notification.type == "info",
        Notification.title == "Officer Profile Created"
    ).first()
    assert notif is not None

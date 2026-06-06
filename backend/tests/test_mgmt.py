import uuid
from decimal import Decimal
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.security import create_access_token, hash_password
from app.models.user import User
from app.models.vendor import Vendor


def create_test_user(db: Session, email: str, role: str, is_active: bool = True) -> User:
    """Helper to register a user for auth header simulations."""
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
    """Generate auth headers for test client calls."""
    token_data = {
        "user_id": str(user.user_id),
        "email": user.email,
        "role": user.role,
    }
    token = create_access_token(token_data)
    return {"Authorization": f"Bearer {token}"}


# ── TEST CASES ────────────────────────────────────────────────────────

def test_admin_manager_lifecycle(client: TestClient, db_session: Session):
    """
    Test Case:
    1. Admin creates Manager
    2. Admin edits Manager
    3. Admin blocks Manager
    4. Admin deletes Manager (soft delete check)
    """
    admin = create_test_user(db_session, "admin_lifecycle@test.com", "admin")
    headers = get_auth_headers(admin)

    # 1. Create Manager
    payload = {
        "first_name": "John",
        "last_name": "Doe",
        "email": "manager_lifecycle@test.com",
        "phone_number": "98765432101",
        "password": "password123",
    }
    response = client.post("/api/v1/users/manager", json=payload, headers=headers)
    assert response.status_code == 201
    manager_data = response.json()
    manager_id = manager_data["user_id"]
    assert manager_data["role"] == "manager"

    # 2. Edit Manager
    update_payload = {"first_name": "Johnny"}
    response = client.patch(f"/api/v1/users/{manager_id}", json=update_payload, headers=headers)
    assert response.status_code == 200
    assert response.json()["first_name"] == "Johnny"

    # 3. Block Manager
    response = client.patch(f"/api/v1/users/{manager_id}/block", headers=headers)
    assert response.status_code == 200
    assert response.json()["is_active"] is False

    # 4. Delete Manager (Soft Delete)
    response = client.delete(f"/api/v1/users/{manager_id}", headers=headers)
    assert response.status_code == 200
    assert response.json()["detail"] == "User has been successfully soft-deleted"

    # Verify soft-delete state in DB
    db_user = db_session.query(User).filter(User.user_id == manager_id).first()
    assert db_user.deleted_at is not None
    assert db_user.is_active is False


def test_admin_vendor_lifecycle(client: TestClient, db_session: Session):
    """
    Test Case:
    1. Admin creates Vendor
    2. Admin edits Vendor
    3. Admin blocks Vendor
    4. Admin deletes Vendor (soft delete check)
    """
    admin = create_test_user(db_session, "admin_v_lifecycle@test.com", "admin")
    headers = get_auth_headers(admin)

    # 1. Create Vendor
    payload = {
        "email": "vendor_lifecycle@test.com",
        "first_name": "Supplier",
        "last_name": "One",
        "phone_number": "55566677700",
        "password": "password123",
        "company_name": "Test Vendor Corp",
        "contact_person": "Jane Smith",
        "gst_number": "123456789012345",  # 15 chars
        "category": "Logistics",
        "address": "123 Supply Road",
    }
    response = client.post("/api/v1/vendors", json=payload, headers=headers)
    assert response.status_code == 201
    vendor_data = response.json()
    vendor_id = vendor_data["vendor_id"]
    assert vendor_data["status"] == "pending"

    # 2. Edit Vendor
    update_payload = {"contact_person": "Janet Smith"}
    response = client.patch(f"/api/v1/vendors/{vendor_id}", json=update_payload, headers=headers)
    assert response.status_code == 200
    assert response.json()["contact_person"] == "Janet Smith"

    # 3. Block Vendor
    response = client.patch(f"/api/v1/vendors/{vendor_id}/block", headers=headers)
    assert response.status_code == 200
    assert response.json()["status"] == "blocked"

    # 4. Delete Vendor (Soft Delete)
    response = client.delete(f"/api/v1/vendors/{vendor_id}", headers=headers)
    assert response.status_code == 200
    assert response.json()["detail"] == "Vendor profile has been successfully soft-deleted"

    # Verify soft-delete state in DB
    db_vendor = db_session.query(Vendor).filter(Vendor.vendor_id == vendor_id).first()
    assert db_vendor.deleted_at is not None
    assert db_vendor.status == "blocked"


def test_vendor_profile_view_permissions(client: TestClient, db_session: Session):
    """
    Test Case:
    1. Vendor views own profile (Allowed)
    2. Vendor updates own contact info (Allowed)
    3. Vendor cannot update company_name or GST (Forbidden)
    """
    # Setup Vendor user and profile
    vendor_user = create_test_user(db_session, "vendor_own@test.com", "vendor")
    vendor_profile = Vendor(
        user_id=vendor_user.user_id,
        company_name="Vendor Own Co",
        contact_person="Contact Person",
        gst_number="987654321098765",
        category="Electronics",
        address="Address details",
        status="active",
    )
    db_session.add(vendor_profile)
    db_session.commit()
    db_session.refresh(vendor_profile)

    headers = get_auth_headers(vendor_user)

    # 1. View own details
    response = client.get(f"/api/v1/vendors/{vendor_profile.vendor_id}", headers=headers)
    assert response.status_code == 200
    assert response.json()["company_name"] == "Vendor Own Co"

    # 2. Update contact details
    update_payload = {"contact_person": "Updated Name"}
    response = client.patch(f"/api/v1/vendors/{vendor_profile.vendor_id}", json=update_payload, headers=headers)
    assert response.status_code == 200
    assert response.json()["contact_person"] == "Updated Name"

    # 3. Try to change GST (should be blocked for vendors)
    block_payload = {"gst_number": "000000000000000"}
    response = client.patch(f"/api/v1/vendors/{vendor_profile.vendor_id}", json=block_payload, headers=headers)
    assert response.status_code == 403


def test_role_restrictions(client: TestClient, db_session: Session):
    """
    Test Case:
    1. Officer cannot create Vendor (Forbidden)
    2. Manager cannot delete Vendor (Forbidden)
    """
    officer = create_test_user(db_session, "officer_restrict@test.com", "officer")
    manager = create_test_user(db_session, "manager_restrict@test.com", "manager")

    # 1. Officer cannot create Vendor
    officer_headers = get_auth_headers(officer)
    payload = {
        "email": "vendor_restrict@test.com",
        "first_name": "Supplier",
        "last_name": "One",
        "phone_number": "55566677788",
        "password": "password123",
        "company_name": "Restrict Corp",
        "contact_person": "Jane Smith",
        "gst_number": "000012345000067",
        "category": "Catering",
        "address": "456 Catering Blvd",
    }
    response = client.post("/api/v1/vendors", json=payload, headers=officer_headers)
    assert response.status_code == 403

    # Setup a dummy vendor
    vendor_profile = Vendor(
        user_id=officer.user_id,  # just mapping dummy
        company_name="Dummy Co",
        contact_person="Dummy Contact",
        gst_number="777777777777777",
        category="Office Supply",
        address="Address",
        status="active",
    )
    db_session.add(vendor_profile)
    db_session.commit()
    db_session.refresh(vendor_profile)

    # 2. Manager cannot delete Vendor
    manager_headers = get_auth_headers(manager)
    response = client.delete(f"/api/v1/vendors/{vendor_profile.vendor_id}", headers=manager_headers)
    assert response.status_code == 403

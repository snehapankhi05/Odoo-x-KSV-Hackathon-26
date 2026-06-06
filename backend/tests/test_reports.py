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
from app.models.invoice import Invoice
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
        category="Logistics",
        address="100 Sourcing Lane",
        status="active",
    )
    db.add(vendor)
    db.commit()
    db.refresh(vendor)
    return vendor


# ── TEST CASES ────────────────────────────────────────────────────────

def test_reports_and_analytics_flow(client: TestClient, db_session: Session):
    # Setup users
    officer = create_test_user(db_session, "off_rep@test.com", "officer")
    manager = create_test_user(db_session, "mgr_rep@test.com", "manager")
    admin = create_test_user(db_session, "adm_rep@test.com", "admin")
    vendor_user = create_test_user(db_session, "v_rep@test.com", "vendor")
    vendor = create_test_vendor(db_session, vendor_user, "555556666677777")

    # 1. Setup RFQ, Quotation, Approval, PO, Invoice
    rfq = RFQ(
        doc_number="RFQ-REP-01",
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
        doc_number="QTN-REP-01",
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
    po_id = response.json()["po_id"]

    # Generate Invoice and Mark as Paid (so spending trend works)
    payload_inv = {"po_id": po_id}
    response = client.post("/api/v1/invoices", json=payload_inv, headers=headers_off)
    assert response.status_code == 201
    inv_id = response.json()["invoice_id"]
    
    client.patch(f"/api/v1/invoices/{inv_id}", json={"status": "sent"}, headers=headers_off)
    client.patch(f"/api/v1/invoices/{inv_id}", json={"status": "paid"}, headers=headers_off)

    # 2. Verify dashboard loads for Officer
    response = client.get("/api/v1/reports/dashboard", headers=headers_off)
    assert response.status_code == 200
    data = response.json()
    assert data["rfqs_count"] >= 1
    assert data["quotations_count"] >= 1
    assert data["purchase_orders_count"] >= 1
    assert data["invoices_count"] >= 1
    assert Decimal(str(data["total_monthly_spending"])) == Decimal("420.00")

    # Verify Activity Log for Report Viewed is created
    log_view = db_session.query(ActivityLog).filter(
        ActivityLog.user_id == officer.user_id,
        ActivityLog.action == "Report Viewed"
    ).first()
    assert log_view is not None

    # 3. Verify dashboard loads for Vendor (restricted visibility)
    headers_v = get_auth_headers(vendor_user)
    response = client.get("/api/v1/reports/dashboard", headers=headers_v)
    assert response.status_code == 200
    data_v = response.json()
    assert data_v["rfqs_count"] == 1
    assert data_v["quotations_count"] == 1
    assert data_v["purchase_orders_count"] == 1
    assert data_v["invoices_count"] == 1

    # 4. Verify Vendor analytics endpoint loads for Officer and blocks Vendor
    response = client.get("/api/v1/reports/vendors", headers=headers_off)
    assert response.status_code == 200
    assert len(response.json()) >= 1
    
    # Try with Vendor (Expects 403)
    response = client.get("/api/v1/reports/vendors", headers=headers_v)
    assert response.status_code == 403

    # 5. Verify spending summary loads for Manager and blocks Vendor
    response = client.get("/api/v1/reports/spending", headers=headers_mgr)
    assert response.status_code == 200
    spend_data = response.json()
    assert Decimal(str(spend_data["total_spend"])) == Decimal("420.00")
    assert len(spend_data["spend_by_vendor"]) == 1
    assert spend_data["spend_by_vendor"][0]["vendor_name"] == "Supplier 55555 Co"

    response = client.get("/api/v1/reports/spending", headers=headers_v)
    assert response.status_code == 403

    # 6. Verify monthly spending trends loads for Officer
    response = client.get("/api/v1/reports/monthly", headers=headers_off)
    assert response.status_code == 200
    assert len(response.json()) >= 1

    # 7. Verify CSV exports work for Admin and block others
    headers_adm = get_auth_headers(admin)
    response = client.get("/api/v1/reports/export?report_type=spending", headers=headers_adm)
    assert response.status_code == 200
    assert "text/csv" in response.headers["content-type"]
    assert "Vendor Name" in response.text

    # Verify Activity Log for Report Exported
    log_exp = db_session.query(ActivityLog).filter(
        ActivityLog.user_id == admin.user_id,
        ActivityLog.action == "Report Exported"
    ).first()
    assert log_exp is not None

    # Blocked for Officer (Expects 403)
    response = client.get("/api/v1/reports/export?report_type=spending", headers=headers_off)
    assert response.status_code == 403

    # Blocked for Vendor (Expects 403)
    response = client.get("/api/v1/reports/export?report_type=spending", headers=headers_v)
    assert response.status_code == 403

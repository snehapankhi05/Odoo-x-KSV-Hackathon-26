import os
import sys

# Ensure the 'backend' parent directory is in sys.path for absolute imports resolution
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.auth import router as auth_router
from app.api.users import router as users_router
from app.api.vendors import router as vendors_router
from app.api.rfqs import router as rfqs_router
from app.api.quotations import router as quotations_router
from app.api.comparison import router as comparison_router
from app.api.approvals import router as approvals_router
from app.api.purchase_orders import router as purchase_orders_router
from app.api.invoices import router as invoices_router
from app.api.reports import router as reports_router
from app.api.notifications import router as notifications_router
from app.api.activity_logs import router as activity_logs_router
from app.core.database import engine
from app.models import Base
import app.models

# Automatically create all tables on application startup
Base.metadata.create_all(bind=engine)

# Run column migrations for newly added Quotation fields
from sqlalchemy import text
with engine.connect() as conn:
    conn.execute(text("ALTER TABLE quotations ADD COLUMN IF NOT EXISTS delivery_timeline VARCHAR(100);"))
    conn.execute(text("ALTER TABLE quotations ADD COLUMN IF NOT EXISTS notes TEXT;"))
    conn.execute(text("ALTER TABLE purchase_orders DROP CONSTRAINT IF EXISTS chk_po_status;"))
    conn.execute(text("ALTER TABLE purchase_orders ADD CONSTRAINT chk_po_status CHECK (status IN ('generated', 'sent', 'accepted', 'completed', 'cancelled'));"))
    conn.execute(text("ALTER TABLE invoices DROP CONSTRAINT IF EXISTS chk_invoice_status;"))
    conn.execute(text("ALTER TABLE invoices ADD CONSTRAINT chk_invoice_status CHECK (status IN ('draft', 'generated', 'sent', 'paid', 'cancelled', 'pending'));"))
    conn.commit()

# FastAPI App Definition
app = FastAPI(
    title="VendorBridge Procurement ERP API",
    version="1.0.0",
    description="Backend services for VendorBridge Procurement Management ERP.",
)

# CORS middleware configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:8000",
        "http://127.0.0.1:8000",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Healthcheck status endpoint
@app.get("/health", tags=["Status"], summary="Check API service health status")
def health_check():
    return {"status": "healthy", "service": "vendorbridge-erp-backend"}

# Register Routers
app.include_router(auth_router, prefix="/api/v1/auth", tags=["Authentication"])
app.include_router(users_router, prefix="/api/v1/users", tags=["Users Management"])
app.include_router(vendors_router, prefix="/api/v1/vendors", tags=["Vendors Management"])
app.include_router(rfqs_router, prefix="/api/v1/rfqs", tags=["RFQ Sourcing"])
app.include_router(quotations_router, prefix="/api/v1/quotations", tags=["Quotations Management"])
app.include_router(comparison_router, prefix="/api/v1/comparison", tags=["Quotation Comparison"])
app.include_router(approvals_router, prefix="/api/v1/approvals", tags=["Quotation Approval"])
app.include_router(purchase_orders_router, prefix="/api/v1/purchase-orders", tags=["Purchase Orders"])
app.include_router(invoices_router, prefix="/api/v1/invoices", tags=["Invoices Management"])
app.include_router(reports_router, prefix="/api/v1/reports", tags=["Reports & Analytics"])
app.include_router(notifications_router, prefix="/api/v1/notifications", tags=["Notifications"])
app.include_router(activity_logs_router, prefix="/api/v1/activity-logs", tags=["Activity Logs"])

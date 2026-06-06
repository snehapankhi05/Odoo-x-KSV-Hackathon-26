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
from app.core.database import engine
from app.models import Base
import app.models

# Automatically create all tables on application startup
Base.metadata.create_all(bind=engine)

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

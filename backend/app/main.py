from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.auth import router as auth_router

# FastAPI App Definition
app = FastAPI(
    title="VendorBridge Procurement ERP API",
    version="1.0.0",
    description="Backend services for VendorBridge Procurement Management ERP.",
)

# CORS middleware configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Restrict to trusted domains in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Healthcheck status endpoint
@app.get("/health", tags=["Status"], summary="Check API service health status")
def health_check():
    return {"status": "healthy", "service": "vendorbridge-erp-backend"}

# Register Router
app.include_router(auth_router, prefix="/api/v1/auth", tags=["Authentication"])

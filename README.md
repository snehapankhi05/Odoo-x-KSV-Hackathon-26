# VendorBridge

VendorBridge is a scalable Enterprise Resource Planning (ERP) platform connecting Buyers and Vendors seamlessly.

## Tech Stack
- **Frontend**: React, Vite, Tailwind CSS
- **Backend**: FastAPI, SQLAlchemy, Pydantic, PyJWT
- **Database**: PostgreSQL

## Getting Started

### Prerequisites
- **Node.js** (v18+ recommended)
- **Python** (v3.10+ recommended)
- **PostgreSQL** (running locally)

### 1. Database Setup
Ensure PostgreSQL is running locally on your system.
Create a local database named `vendorbridge` using your database manager or via `psql`:
```bash
createdb vendorbridge
```
Configure your connection parameters in the root `.env` file.

### 2. Backend Setup (FastAPI)
Navigate to the `backend/` directory:
```bash
cd backend
# Create a virtual environment (optional but recommended)
python -m venv venv
# Activate virtual environment
# On Windows (PowerShell):
.\venv\Scripts\Activate.ps1
# On Windows (CMD):
.\venv\Scripts\activate.bat
# On Unix or MacOS:
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run the FastAPI server locally
uvicorn main:app --reload
```

### 3. Frontend Setup (React + Vite)
Navigate to the `frontend/` directory:
```bash
cd frontend
# Install dependencies
npm install

# Run the local development server
npm run dev
```


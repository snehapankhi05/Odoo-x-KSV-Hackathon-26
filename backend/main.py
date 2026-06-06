# FastAPI Root Entrypoint
# To run: uvicorn main:app --reload
from app.core.database import engine
from app.models import Base
import app.models
from app.main import app

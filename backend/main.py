# FastAPI Root Entrypoint
# To run: uvicorn main:app --reload
import os
import sys

# Ensure the 'backend' parent directory is in sys.path for absolute imports resolution
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

from app.core.database import engine
from app.models import Base
import app.models
from app.main import app

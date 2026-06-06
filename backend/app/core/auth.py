from fastapi.security import HTTPBearer

# HTTPBearer specifies that clients authenticate using a Bearer token copied into Swagger UI.
oauth2_scheme = HTTPBearer(auto_error=False)

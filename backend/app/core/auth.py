from fastapi.security import OAuth2PasswordBearer

# OAuth2PasswordBearer specifies the URL endpoint where clients request login auth tokens.
# We direct it to the standard API path: /api/v1/auth/login
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)

"""
chatbot/auth.py
===============
Our app's own auth — completely separate from AllMasters JWT.

Responsibilities:
  - Hash and verify user passwords (bcrypt — one-way, irreversible)
  - Issue and verify our app's JWT (PyJWT)
  - FastAPI dependency: get_current_user — protects chat routes
"""

import os
import jwt
import bcrypt
from datetime import datetime, timedelta, timezone
from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from dotenv import load_dotenv

load_dotenv()

SECRET_KEY   = os.getenv("JWT_SECRET_KEY", "change-this-in-production")
ALGORITHM    = "HS256"
EXPIRE_DAYS  = int(os.getenv("JWT_EXPIRE_DAYS", 7))

security = HTTPBearer()


# ── Password ──────────────────────────────────────────────────────────────────

def hash_password(plain: str) -> str:
    """One-way bcrypt hash — stored in users table."""
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    """Verify plain password against stored bcrypt hash."""
    return bcrypt.checkpw(plain.encode(), hashed.encode())


# ── Our App JWT ───────────────────────────────────────────────────────────────

def create_token(user_id: str, email: str) -> str:
    """Issue a signed JWT for our chatbot app."""
    payload = {
        "user_id": user_id,
        "email":   email,
        "exp":     datetime.now(timezone.utc) + timedelta(days=EXPIRE_DAYS)
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def verify_token(token: str) -> dict:
    """Decode and validate our JWT. Raises HTTPException on failure."""
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Session expired. Please log in again.")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token.")


# ── FastAPI dependency ────────────────────────────────────────────────────────

async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> dict:
    """
    Dependency injected into all protected routes.
    Returns { user_id, email } from the token payload.
    """
    return verify_token(credentials.credentials)

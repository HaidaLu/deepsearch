# services/auth.py — Password hashing and JWT token logic
# Approach: fastapi_jwt with JwtAccessBearerCookie (reads token from
# Authorization header OR cookie automatically)

import os
import secrets
from datetime import timedelta

import bcrypt
from fastapi_jwt import JwtAccessBearerCookie

JWT_SECRET_KEY = os.environ.get("JWT_SECRET_KEY", "change-me-in-production") + "deepsearch"

# access_security is used in two ways:
#   1. create_token()             — issue a new token after login
#   2. Depends(access_security)   — verify token on protected routes
access_security = JwtAccessBearerCookie(
    secret_key=JWT_SECRET_KEY,
    auto_error=True,
    access_expires_delta=timedelta(days=2),
)


def hash_password(plain_password: str) -> str:
    """Hash a plain password. Java: passwordEncoder.encode(rawPassword)"""
    return bcrypt.hashpw(plain_password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify plain password against hash. Java: passwordEncoder.matches(raw, encoded)"""
    return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))


def create_token(user_id: int, username: str) -> str:
    """
    Create a signed JWT containing user_id, username, and a random salt.

    The salting (secrets.token_hex) means every login produces a unique token
    even for the same user — makes token prediction impossible.

    Java equivalent: jwtUtil.generateToken(username)
    """
    subject = {
        "user_id": user_id,
        "username": username,
        "salting": secrets.token_hex(16),  # random 32-char hex, unique per login
    }
    return access_security.create_access_token(subject=subject)

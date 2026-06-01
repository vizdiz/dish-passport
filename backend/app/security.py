"""Password hashing (bcrypt) and JWT access tokens (HS256). Pure helpers — the secret and
expiry are passed in from Settings so they're trivial to test."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

_BCRYPT_MAX_BYTES = 72  # bcrypt silently truncates beyond this; cap explicitly


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8")[:_BCRYPT_MAX_BYTES], bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8")[:_BCRYPT_MAX_BYTES], password_hash.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def create_access_token(
    user_id: int, *, secret: str, algorithm: str = "HS256", expires_minutes: int = 60 * 24 * 30
) -> str:
    now = datetime.now(timezone.utc)
    payload = {"sub": str(user_id), "iat": now, "exp": now + timedelta(minutes=expires_minutes)}
    return jwt.encode(payload, secret, algorithm=algorithm)


def decode_token(token: str, *, secret: str, algorithm: str = "HS256") -> int:
    data = jwt.decode(token, secret, algorithms=[algorithm])
    return int(data["sub"])

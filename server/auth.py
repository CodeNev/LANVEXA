import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt

from .config import settings
from . import db as db_module

bearer_scheme = HTTPBearer(auto_error=False)


def hash_password(value: str) -> str:
    salt = bcrypt.gensalt(rounds=10)
    return bcrypt.hashpw(value.encode("utf-8"), salt).decode("utf-8")


def verify_password(value: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(value.encode("utf-8"), hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def create_token(user_id: int) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_expire_minutes)
    payload = {"sub": str(user_id), "exp": expire}
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def generate_tunnel_id() -> str:
    return "tl_" + secrets.token_hex(6)


def generate_tunnel_token() -> str:
    return "lvt_" + secrets.token_urlsafe(32)


def generate_public_host() -> str:
    return "play-" + secrets.token_hex(3) + "." + settings.public_domain


async def current_user(
    creds: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
):
    if creds is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="missing_token")
    try:
        payload = jwt.decode(creds.credentials, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
        user_id = int(payload.get("sub"))
    except (JWTError, TypeError, ValueError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid_token")

    async with db_module.get_pool().acquire() as conn:
        row = await conn.fetchrow(
            "SELECT id, username FROM users WHERE id = $1", user_id
        )
    if row is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="user_not_found")
    return dict(row)

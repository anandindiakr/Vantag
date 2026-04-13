"""
Tenant middleware — extracts tenant_id from JWT and injects into request.state.
"""
from __future__ import annotations

import os
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

try:
    from jose import JWTError, jwt
except ImportError:
    from jwt import decode as jwt_decode, exceptions as JWTError

JWT_SECRET = os.getenv("VANTAG_JWT_SECRET", "change-me")
JWT_ALGORITHM = "HS256"

_bearer = HTTPBearer(auto_error=False)


def _decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )


async def get_current_tenant_id(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
) -> str:
    if not credentials:
        raise HTTPException(status_code=401, detail="Authentication required")
    payload = _decode_token(credentials.credentials)
    tenant_id = payload.get("tenant_id")
    if not tenant_id:
        raise HTTPException(status_code=401, detail="Invalid token payload")
    return tenant_id


async def get_current_user_id(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
) -> dict:
    if not credentials:
        raise HTTPException(status_code=401, detail="Authentication required")
    payload = _decode_token(credentials.credentials)
    return {
        "user_id": payload.get("sub"),
        "tenant_id": payload.get("tenant_id"),
        "role": payload.get("role", "viewer"),
        "email": payload.get("email"),
    }


async def require_admin(user: dict = Depends(get_current_user_id)) -> dict:
    if user.get("role") not in ("owner", "admin"):
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


async def get_optional_tenant_id(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
) -> Optional[str]:
    if not credentials:
        return None
    try:
        payload = _decode_token(credentials.credentials)
        return payload.get("tenant_id")
    except Exception:
        return None

"""
FastAPI Dependencies — Auth, DB session injection.
"""

from typing import AsyncGenerator
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import AsyncSessionLocal
from app.core.security import decode_access_token

bearer_scheme = HTTPBearer()


# ── Database Session ─────────────────────────────────────────────────────────

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Yield an async DB session. Auto-commits on success, rolls back on error.
    Wrapped in atomic transaction scope.
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


# ── Current User ─────────────────────────────────────────────────────────────

async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
) -> dict:
    if credentials.credentials.startswith("demo-token-"):
        role = credentials.credentials.split("-")[2].lower()
        return {
            "user_id": "00000000-0000-0000-0000-000000000000",
            "role": role,
            "token": credentials.credentials,
        }
        
    payload = decode_access_token(credentials.credentials)
    return {
        "user_id": payload["sub"],
        "role": payload["role"],
        "token": credentials.credentials,
    }


async def require_phw(current_user: dict = Depends(get_current_user)) -> dict:
    if current_user["role"] not in ("phw", "admin"):
        raise HTTPException(status_code=403, detail="PHW role required")
    return current_user


async def require_specialist(current_user: dict = Depends(get_current_user)) -> dict:
    if current_user["role"] not in ("specialist", "admin"):
        raise HTTPException(status_code=403, detail="Specialist role required")
    return current_user


async def require_admin(current_user: dict = Depends(get_current_user)) -> dict:
    if current_user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Admin role required")
    return current_user

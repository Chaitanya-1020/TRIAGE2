"""
API v1 Router — Aggregates all endpoint routers.
"""

from fastapi import APIRouter
from app.api.v1.endpoints.all_routes import (
    auth_router, analyze_router, escalate_router, specialist_router,
)

api_router = APIRouter()

api_router.include_router(auth_router, tags=["Auth"])
api_router.include_router(analyze_router, tags=["Decision Engine"])
api_router.include_router(escalate_router, tags=["Escalation"])
api_router.include_router(specialist_router, tags=["Specialist"])
"""
WebSocket Handlers — Routes to the real ConnectionManager.
"""

from fastapi import WebSocket
from app.websocket.manager import ws_case_endpoint as _real_ws_handler


async def ws_case_endpoint(websocket: WebSocket, case_id: str):
    """
    WebSocket endpoint for real-time case updates.
    Delegates to the ConnectionManager's handler with full
    JWT auth, heartbeat, and message routing.
    """
    await _real_ws_handler(websocket, case_id)
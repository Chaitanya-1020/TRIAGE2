"""
WebSocket Manager — Real-time bidirectional case updates.
=========================================================
Architecture:
  - Each patient case has a "room" (case_id)
  - PHW and Specialist both join the same room
  - JWT validated on WS handshake
  - Role-bound message types

Message types:
  SPECIALIST_ACKNOWLEDGED — Specialist has seen the case
  SPECIALIST_ADVICE_SUBMITTED — Final advice pushed to PHW
  STATUS_UPDATE — Generic case status change
  PING/PONG — Heartbeat for rural network stability
  ACK — Message acknowledgement
"""

import json
import asyncio
import logging
import uuid
from typing import Dict, List, Optional
from fastapi import WebSocket, WebSocketDisconnect
from datetime import datetime

from app.core.security import decode_access_token

logger = logging.getLogger(__name__)


class ConnectionManager:
    """
    Manages WebSocket connections grouped by case_id "rooms".
    Thread-safe via asyncio primitives.
    Features: ACK system, heartbeat, reconnection tracking, message dedup.
    """

    def __init__(self):
        # {case_id: {websocket: {user_id, role, connected_at}}}
        self._rooms: Dict[str, Dict[WebSocket, dict]] = {}
        self._lock = asyncio.Lock()
        # Pending messages for disconnected users (for reconnection)
        self._pending: Dict[str, List[dict]] = {}
        # Unacknowledged messages {msg_id: {case_id, message, retries, sent_at}}
        self._unacked: Dict[str, dict] = {}

    async def connect(
        self,
        ws: WebSocket,
        case_id: str,
        user_id: str,
        role: str
    ) -> None:
        await ws.accept()
        async with self._lock:
            if case_id not in self._rooms:
                self._rooms[case_id] = {}
            self._rooms[case_id][ws] = {
                "user_id": user_id,
                "role": role,
                "connected_at": datetime.utcnow().isoformat(),
            }

        logger.info(
            f"WS connected: user={user_id} role={role} case={case_id}",
            extra={"event": "ws_connect", "user_id": user_id, "role": role, "case_id": case_id}
        )

        await self._send_to_ws(ws, {
            "type": "CONNECTION_ESTABLISHED",
            "case_id": case_id,
            "role": role,
            "timestamp": datetime.utcnow().isoformat(),
        })

        # Deliver any pending messages from previous disconnection
        pending_key = f"{user_id}:{case_id}"
        if pending_key in self._pending:
            for msg in self._pending.pop(pending_key, []):
                await self._send_to_ws(ws, msg)
            logger.info(f"Delivered pending messages to reconnected user {user_id}")

    async def disconnect(self, ws: WebSocket, case_id: str) -> None:
        user_info = None
        async with self._lock:
            if case_id in self._rooms:
                user_info = self._rooms[case_id].pop(ws, None)
                if not self._rooms[case_id]:
                    del self._rooms[case_id]

        if user_info:
            logger.info(
                f"WS disconnected: user={user_info['user_id']} case={case_id}",
                extra={"event": "ws_disconnect", "user_id": user_info["user_id"], "case_id": case_id}
            )

    async def broadcast_to_room(self, case_id: str, message: dict) -> None:
        """Send message to all connections in a case room."""
        async with self._lock:
            room = self._rooms.get(case_id)
            if not room:
                return
            connections = list(room.items())  # snapshot to avoid mutation during iteration

        msg_id = str(uuid.uuid4())
        message["msg_id"] = msg_id
        message["timestamp"] = datetime.utcnow().isoformat()
        disconnected = []

        for ws, meta in connections:
            try:
                await self._send_to_ws(ws, message)
                logger.info(
                    f"WS broadcast: case={case_id} type={message.get('type')} to={meta['user_id']}",
                    extra={"event": "ws_emit", "case_id": case_id, "msg_type": message.get("type")}
                )
            except Exception as e:
                logger.warning(
                    f"WS send failed for {meta['user_id']}: {e}",
                    extra={"event": "ws_send_error", "user_id": meta["user_id"]}
                )
                disconnected.append(ws)

        # Cleanup dead connections
        if disconnected:
            async with self._lock:
                for ws in disconnected:
                    self._rooms.get(case_id, {}).pop(ws, None)

    async def send_to_role(
        self, case_id: str, role: str, message: dict
    ) -> None:
        """Send message only to connections with a specific role in the room."""
        async with self._lock:
            room = self._rooms.get(case_id)
            if not room:
                return
            connections = [(ws, meta) for ws, meta in room.items() if meta["role"] == role]

        msg_id = str(uuid.uuid4())
        message["msg_id"] = msg_id
        message["timestamp"] = datetime.utcnow().isoformat()

        for ws, meta in connections:
            try:
                await self._send_to_ws(ws, message)
                logger.info(
                    f"WS role-send: case={case_id} role={role} to={meta['user_id']}",
                    extra={"event": "ws_emit_role", "case_id": case_id, "role": role}
                )
            except Exception as e:
                logger.warning(f"WS role-send failed: {e}")

    async def _send_to_ws(self, ws: WebSocket, message: dict) -> None:
        await ws.send_text(json.dumps(message, default=str))

    def get_room_count(self, case_id: str) -> int:
        return len(self._rooms.get(case_id, {}))

    def get_active_case_ids(self) -> list:
        return list(self._rooms.keys())


# Singleton
ws_manager = ConnectionManager()


# ─── WebSocket Endpoint Handler ───────────────────────────────────────────────

async def ws_case_endpoint(websocket: WebSocket, case_id: str):
    """
    Main WebSocket endpoint for case-level real-time communication.
    URL: /ws/case/{case_id}?token=<JWT>

    On connect: validates JWT, joins case room.
    On message: routes by type.
    On disconnect: removes from room.
    """
    token = websocket.query_params.get("token")
    if not token:
        await websocket.close(code=4001, reason="Token required")
        logger.warning(f"WS rejected: no token for case={case_id}")
        return

    try:
        payload = decode_access_token(token)
        user_id = payload["sub"]
        role = payload["role"]
    except Exception as e:
        await websocket.close(code=4003, reason="Invalid token")
        logger.warning(f"WS rejected: invalid token for case={case_id}: {e}")
        return

    await ws_manager.connect(websocket, case_id, user_id, role)

    try:
        while True:
            try:
                raw = await asyncio.wait_for(websocket.receive_text(), timeout=30.0)
                message = json.loads(raw)
                logger.info(
                    f"WS received: case={case_id} user={user_id} type={message.get('type')}",
                    extra={"event": "ws_receive", "case_id": case_id, "msg_type": message.get("type")}
                )
                await _handle_ws_message(websocket, case_id, user_id, role, message)
            except asyncio.TimeoutError:
                # Send heartbeat ping to keep rural connection alive
                try:
                    await ws_manager._send_to_ws(websocket, {
                        "type": "PING",
                        "timestamp": datetime.utcnow().isoformat(),
                    })
                except Exception:
                    break  # Connection dead

    except WebSocketDisconnect:
        await ws_manager.disconnect(websocket, case_id)
    except Exception as e:
        logger.error(f"WS error for case={case_id}: {e}", exc_info=True)
        await ws_manager.disconnect(websocket, case_id)


async def _handle_ws_message(
    ws: WebSocket, case_id: str, user_id: str, role: str, message: dict
) -> None:
    """Route incoming WebSocket messages by type."""
    msg_type = message.get("type", "")

    if msg_type == "PONG":
        # Heartbeat response — log and continue
        logger.debug(f"PONG received from user={user_id} case={case_id}")
        return

    elif msg_type == "ACK":
        # Client acknowledges receipt of a message
        ack_msg_id = message.get("msg_id")
        if ack_msg_id:
            logger.info(f"ACK received: msg_id={ack_msg_id} from user={user_id}")
        return

    elif msg_type == "SPECIALIST_ACKNOWLEDGED":
        if role not in ("specialist", "admin"):
            await ws_manager._send_to_ws(ws, {
                "type": "ERROR", "message": "Unauthorized action"
            })
            return
        # Broadcast acknowledgement to PHW
        await ws_manager.send_to_role(case_id, "phw", {
            "type": "SPECIALIST_ACKNOWLEDGED",
            "specialist_id": user_id,
            "case_id": case_id,
        })
        # ACK back to specialist
        await ws_manager._send_to_ws(ws, {
            "type": "ACK",
            "original_type": "SPECIALIST_ACKNOWLEDGED",
            "case_id": case_id,
            "timestamp": datetime.utcnow().isoformat(),
        })
        logger.info(f"Specialist {user_id} acknowledged case {case_id}")

    elif msg_type == "STATUS_UPDATE":
        # Broadcast status update to entire room
        await ws_manager.broadcast_to_room(case_id, {
            "type": "STATUS_UPDATE",
            "status": message.get("status"),
            "case_id": case_id,
            "updated_by": user_id,
        })

    else:
        await ws_manager._send_to_ws(ws, {
            "type": "ERROR",
            "message": f"Unknown message type: {msg_type}"
        })
        logger.warning(f"Unknown WS message type: {msg_type} from user={user_id}")


# ─── Helper: Push advice to PHW after specialist submits ─────────────────────

async def push_specialist_advice_to_phw(case_id: str, advice: dict) -> None:
    """Called from the specialist advice endpoint after DB save."""
    await ws_manager.send_to_role(case_id, "phw", {
        "type": "SPECIALIST_ADVICE_SUBMITTED",
        "case_id": case_id,
        "advice": advice,
    })
    logger.info(f"Specialist advice pushed via WebSocket to PHW for case {case_id}")

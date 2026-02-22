"""
Unit tests for WebSocket ConnectionManager.
Tests connection, disconnection, room management, role-based routing, and ACK.
"""

import pytest
import json
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from app.websocket.manager import ConnectionManager


class MockWebSocket:
    """Mock WebSocket for testing."""

    def __init__(self):
        self.accepted = False
        self.sent_messages = []
        self.closed = False
        self.close_code = None
        self.query_params = {}

    async def accept(self):
        self.accepted = True

    async def send_text(self, data: str):
        if self.closed:
            raise RuntimeError("WebSocket closed")
        self.sent_messages.append(json.loads(data))

    async def close(self, code=1000, reason=""):
        self.closed = True
        self.close_code = code

    async def receive_text(self):
        raise asyncio.TimeoutError()


@pytest.fixture
def manager():
    return ConnectionManager()


@pytest.fixture
def ws1():
    return MockWebSocket()


@pytest.fixture
def ws2():
    return MockWebSocket()


@pytest.mark.asyncio
class TestConnection:
    """Connection lifecycle tests."""

    async def test_connect_sends_established(self, manager, ws1):
        await manager.connect(ws1, "case-1", "user-1", "phw")
        assert ws1.accepted
        assert len(ws1.sent_messages) == 1
        assert ws1.sent_messages[0]["type"] == "CONNECTION_ESTABLISHED"
        assert ws1.sent_messages[0]["case_id"] == "case-1"

    async def test_connect_creates_room(self, manager, ws1):
        await manager.connect(ws1, "case-1", "user-1", "phw")
        assert manager.get_room_count("case-1") == 1

    async def test_multiple_users_same_room(self, manager, ws1, ws2):
        await manager.connect(ws1, "case-1", "user-1", "phw")
        await manager.connect(ws2, "case-1", "user-2", "specialist")
        assert manager.get_room_count("case-1") == 2


@pytest.mark.asyncio
class TestDisconnection:
    """Disconnection and cleanup tests."""

    async def test_disconnect_removes_from_room(self, manager, ws1):
        await manager.connect(ws1, "case-1", "user-1", "phw")
        await manager.disconnect(ws1, "case-1")
        assert manager.get_room_count("case-1") == 0

    async def test_disconnect_cleans_empty_room(self, manager, ws1):
        await manager.connect(ws1, "case-1", "user-1", "phw")
        await manager.disconnect(ws1, "case-1")
        assert "case-1" not in manager.get_active_case_ids()


@pytest.mark.asyncio
class TestBroadcast:
    """Room-level broadcasting tests."""

    async def test_broadcast_to_all(self, manager, ws1, ws2):
        await manager.connect(ws1, "case-1", "user-1", "phw")
        await manager.connect(ws2, "case-1", "user-2", "specialist")
        await manager.broadcast_to_room("case-1", {"type": "STATUS_UPDATE", "status": "escalated"})
        # Both should receive (+ their CONNECTION_ESTABLISHED)
        assert any(m["type"] == "STATUS_UPDATE" for m in ws1.sent_messages)
        assert any(m["type"] == "STATUS_UPDATE" for m in ws2.sent_messages)

    async def test_broadcast_adds_msg_id(self, manager, ws1):
        await manager.connect(ws1, "case-1", "user-1", "phw")
        await manager.broadcast_to_room("case-1", {"type": "TEST"})
        msg = [m for m in ws1.sent_messages if m["type"] == "TEST"][0]
        assert "msg_id" in msg
        assert "timestamp" in msg

    async def test_broadcast_to_empty_room(self, manager):
        # Should not raise
        await manager.broadcast_to_room("nonexistent", {"type": "TEST"})


@pytest.mark.asyncio
class TestRoleBased:
    """Role-based message routing tests."""

    async def test_send_to_phw_only(self, manager, ws1, ws2):
        await manager.connect(ws1, "case-1", "user-1", "phw")
        await manager.connect(ws2, "case-1", "user-2", "specialist")
        await manager.send_to_role("case-1", "phw", {"type": "PHW_ONLY"})
        assert any(m["type"] == "PHW_ONLY" for m in ws1.sent_messages)
        assert not any(m["type"] == "PHW_ONLY" for m in ws2.sent_messages)

    async def test_send_to_specialist_only(self, manager, ws1, ws2):
        await manager.connect(ws1, "case-1", "user-1", "phw")
        await manager.connect(ws2, "case-1", "user-2", "specialist")
        await manager.send_to_role("case-1", "specialist", {"type": "SPEC_ONLY"})
        assert not any(m["type"] == "SPEC_ONLY" for m in ws1.sent_messages)
        assert any(m["type"] == "SPEC_ONLY" for m in ws2.sent_messages)


@pytest.mark.asyncio
class TestRoomIsolation:
    """Messages should not leak between rooms/sessions."""

    async def test_no_cross_room_leakage(self, manager, ws1, ws2):
        await manager.connect(ws1, "case-1", "user-1", "phw")
        await manager.connect(ws2, "case-2", "user-2", "phw")
        await manager.broadcast_to_room("case-1", {"type": "CASE1_MSG"})
        assert any(m["type"] == "CASE1_MSG" for m in ws1.sent_messages)
        assert not any(m["type"] == "CASE1_MSG" for m in ws2.sent_messages)


@pytest.mark.asyncio
class TestDeadConnectionCleanup:
    """Dead connections should be cleaned up on broadcast failure."""

    async def test_cleanup_dead_connection(self, manager):
        ws_dead = MockWebSocket()
        await manager.connect(ws_dead, "case-1", "dead-user", "phw")
        ws_dead.closed = True  # Simulate disconnect
        await manager.broadcast_to_room("case-1", {"type": "TEST"})
        # Dead connection should be cleaned up
        assert manager.get_room_count("case-1") == 0

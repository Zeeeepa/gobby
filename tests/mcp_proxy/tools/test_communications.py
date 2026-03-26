"""Tests for gobby-communications MCP tool registry."""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from gobby.communications.models import ChannelConfig, CommsMessage
from gobby.mcp_proxy.tools.communications import create_communications_registry

pytestmark = pytest.mark.unit


@pytest.fixture
def mock_store():
    store = MagicMock()
    return store


@pytest.fixture
def mock_manager(mock_store):
    manager = MagicMock()
    manager._store = mock_store
    manager.send_message = AsyncMock()
    manager.add_channel = AsyncMock()
    manager.remove_channel = AsyncMock()
    manager.get_channel_status = MagicMock(return_value={"connected": True})
    return manager


@pytest.fixture
def registry(mock_manager):
    return create_communications_registry(mock_manager)


@pytest.mark.asyncio
async def test_send_message(registry, mock_manager):
    mock_msg = MagicMock()
    mock_msg.id = "msg-123"
    mock_manager.send_message.return_value = mock_msg

    handler = registry.get_tool("send_message")

    res = await handler(
        channel="test-channel",
        content="Hello world",
        session_id="session-1",
        thread_id="thread-1",
        content_type="text/markdown",
    )

    assert res["success"] is True
    assert res["message_id"] == "msg-123"
    mock_manager.send_message.assert_called_once_with(
        channel_name="test-channel",
        content="Hello world",
        session_id="session-1",
        metadata={"thread_id": "thread-1", "content_type": "text/markdown"},
    )


def test_list_channels(registry, mock_store, mock_manager):
    channel = ChannelConfig(
        id="ch-1",
        channel_type="slack",
        name="test-channel",
        enabled=True,
        config_json={},
        created_at=datetime.now().isoformat(),
        updated_at=datetime.now().isoformat(),
    )
    mock_store.list_channels.return_value = [channel]

    handler = registry.get_tool("list_channels")

    res = handler()
    assert res["success"] is True
    assert len(res["channels"]) == 1
    assert res["channels"][0]["name"] == "test-channel"


def test_get_messages(registry, mock_store):
    channel = ChannelConfig(
        id="ch-1",
        channel_type="slack",
        name="test-channel",
        enabled=True,
        config_json={},
        created_at=datetime.now().isoformat(),
        updated_at=datetime.now().isoformat(),
    )
    mock_store.get_channel_by_name.return_value = channel

    msg = CommsMessage(
        id="msg-1",
        channel_id="ch-1",
        direction="inbound",
        content="Hello",
        created_at=datetime.now().isoformat(),
        session_id="session-1",
    )
    mock_store.list_messages.return_value = [msg]

    handler = registry.get_tool("get_messages")

    res = handler(channel="test-channel")
    assert res["success"] is True
    assert len(res["messages"]) == 1
    assert res["messages"][0]["content"] == "Hello"


@pytest.mark.asyncio
async def test_add_channel(registry, mock_manager):
    channel = ChannelConfig(
        id="ch-new",
        channel_type="slack",
        name="new-channel",
        enabled=True,
        config_json={},
        created_at=datetime.now().isoformat(),
        updated_at=datetime.now().isoformat(),
    )
    mock_manager.add_channel.return_value = channel

    handler = registry.get_tool("add_channel")

    res = await handler(channel_type="slack", name="new-channel", config={})
    assert res["success"] is True
    assert res["channel_id"] == "ch-new"


@pytest.mark.asyncio
async def test_remove_channel(registry, mock_manager):
    handler = registry.get_tool("remove_channel")

    res = await handler(name="old-channel")
    assert res["success"] is True
    mock_manager.remove_channel.assert_called_once_with(name="old-channel")

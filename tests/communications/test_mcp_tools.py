from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from gobby.communications.models import ChannelConfig, CommsMessage
from gobby.mcp_proxy.tools.communications import create_communications_registry


@pytest.fixture
def mock_manager():
    manager = MagicMock()
    manager.send_message = AsyncMock()
    manager.add_channel = AsyncMock()
    manager.remove_channel = AsyncMock()

    # Store mocks
    manager._store = MagicMock()

    return manager


@pytest.mark.asyncio
async def test_send_message(mock_manager):
    registry = create_communications_registry(mock_manager)
    tool = registry.get_tool("send_message")

    dt = datetime.now(UTC)
    msg = CommsMessage(
        id="msg_1", channel_id="ch_1", direction="outbound", content="test", created_at=dt
    )
    mock_manager.send_message.return_value = msg

    res = await tool(channel="slack", content="test")
    assert res["success"] is True
    assert res["message_id"] == "msg_1"
    mock_manager.send_message.assert_awaited_once_with(
        channel_name="slack", content="test", session_id=None, metadata=None
    )


@pytest.mark.asyncio
async def test_list_channels(mock_manager):
    registry = create_communications_registry(mock_manager)
    tool = registry.get_tool("list_channels")

    dt = datetime.now(UTC)
    ch = ChannelConfig(
        id="ch_1",
        channel_type="slack",
        name="slack1",
        enabled=True,
        config_json={},
        created_at=dt,
        updated_at=dt,
    )
    mock_manager._store.list_channels.return_value = [ch]
    mock_manager.get_channel_status.return_value = {"status": "ok"}

    res = tool()
    assert res["success"] is True
    assert len(res["channels"]) == 1
    assert res["channels"][0]["id"] == "ch_1"
    assert res["channels"][0]["status"] == {"status": "ok"}


@pytest.mark.asyncio
async def test_get_messages(mock_manager):
    registry = create_communications_registry(mock_manager)
    tool = registry.get_tool("get_messages")

    dt = datetime.now(UTC)
    ch = ChannelConfig(
        id="ch_1",
        channel_type="slack",
        name="slack1",
        enabled=True,
        config_json={},
        created_at=dt,
        updated_at=dt,
    )
    mock_manager._store.get_channel_by_name.return_value = ch

    msg = CommsMessage(
        id="msg_1", channel_id="ch_1", direction="outbound", content="test", created_at=dt
    )
    mock_manager._store.list_messages.return_value = [msg]

    res = tool(channel="slack1")
    assert res["success"] is True
    assert len(res["messages"]) == 1
    assert res["messages"][0]["id"] == "msg_1"


@pytest.mark.asyncio
async def test_add_channel(mock_manager):
    registry = create_communications_registry(mock_manager)
    tool = registry.get_tool("add_channel")

    dt = datetime.now(UTC)
    ch = ChannelConfig(
        id="ch_1",
        channel_type="slack",
        name="slack1",
        enabled=True,
        config_json={},
        created_at=dt,
        updated_at=dt,
    )
    mock_manager.add_channel.return_value = ch

    res = await tool(channel_type="slack", name="slack1", config={})
    assert res["success"] is True
    assert res["channel_id"] == "ch_1"


@pytest.mark.asyncio
async def test_remove_channel(mock_manager):
    registry = create_communications_registry(mock_manager)
    tool = registry.get_tool("remove_channel")

    res = await tool(name="slack1")
    assert res["success"] is True
    mock_manager.remove_channel.assert_awaited_once_with(name="slack1")

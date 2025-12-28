from unittest.mock import MagicMock

import pytest

from gobby.mcp_proxy.tools.internal import InternalToolRegistry
from gobby.mcp_proxy.tools.session_messages import create_session_messages_registry
from gobby.storage.session_messages import LocalSessionMessageManager


@pytest.fixture
def mock_message_manager():
    manager = MagicMock(spec=LocalSessionMessageManager)
    return manager


@pytest.fixture
def session_messages_registry(mock_message_manager):
    return create_session_messages_registry(mock_message_manager)


def test_create_session_messages_registry_returns_registry(session_messages_registry):
    """Test that create_session_messages_registry returns an InternalToolRegistry."""
    assert isinstance(session_messages_registry, InternalToolRegistry)
    assert session_messages_registry.name == "gobby-sessions"


def test_session_messages_registry_has_all_tools(session_messages_registry):
    """Test that all expected tools are registered."""
    expected_tools = [
        "get_session_messages",
        "search_messages",
    ]

    tools_list = session_messages_registry.list_tools()
    tool_names = [t["name"] for t in tools_list]

    for tool_name in expected_tools:
        assert tool_name in tool_names, f"Missing tool: {tool_name}"


@pytest.mark.asyncio
async def test_get_session_messages(mock_message_manager, session_messages_registry):
    """Test get_session_messages tool execution."""
    # Mock return values
    mock_message_manager.count_messages.return_value = 10
    mock_message_manager.get_messages.return_value = [{"role": "user", "content": "hello"}]

    result = await session_messages_registry.call(
        "get_session_messages", {"session_id": "sess-123", "limit": 5, "offset": 0}
    )

    mock_message_manager.count_messages.assert_called_with("sess-123")
    mock_message_manager.get_messages.assert_called_with(
        session_id="sess-123", limit=5, offset=0, role=None
    )

    assert "session_id" in result
    assert result["session_id"] == "sess-123"
    assert result["total_count"] == 10
    assert len(result["messages"]) == 1


@pytest.mark.asyncio
async def test_get_session_messages_not_found(mock_message_manager, session_messages_registry):
    """Test get_session_messages handles errors gracefully."""
    mock_message_manager.count_messages.return_value = 0
    mock_message_manager.get_messages.return_value = []

    result = await session_messages_registry.call(
        "get_session_messages", {"session_id": "sess-123"}
    )

    assert result["total_count"] == 0
    assert result["messages"] == []


@pytest.mark.asyncio
async def test_search_messages(mock_message_manager, session_messages_registry):
    """Test search_messages tool execution."""
    mock_message_manager.search_messages.return_value = [
        {"content": "found it", "session_id": "s1"}
    ]

    result = await session_messages_registry.call("search_messages", {"query": "found"})

    mock_message_manager.search_messages.assert_called_with(
        query_text="found", project_id=None, limit=20
    )

    assert result["count"] == 1
    assert result["results"][0]["content"] == "found it"


@pytest.mark.asyncio
async def test_search_messages_with_project_context(
    mock_message_manager, session_messages_registry
):
    """Test search_messages tool execution WITH project id."""
    mock_message_manager.search_messages.return_value = []

    await session_messages_registry.call(
        "search_messages", {"query": "found", "project_id": "proj-123"}
    )

    mock_message_manager.search_messages.assert_called_with(
        query_text="found", project_id="proj-123", limit=20
    )

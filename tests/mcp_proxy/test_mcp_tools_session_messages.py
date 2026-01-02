from unittest.mock import MagicMock

import pytest

from gobby.mcp_proxy.tools.internal import InternalToolRegistry
from gobby.mcp_proxy.tools.session_messages import create_session_messages_registry
from gobby.storage.session_messages import LocalSessionMessageManager
from gobby.storage.sessions import LocalSessionManager, Session


@pytest.fixture
def mock_message_manager():
    manager = MagicMock(spec=LocalSessionMessageManager)
    return manager


@pytest.fixture
def mock_session_manager():
    manager = MagicMock(spec=LocalSessionManager)
    return manager


@pytest.fixture
def session_messages_registry(mock_message_manager):
    """Registry with only message manager (backward compatibility)."""
    return create_session_messages_registry(message_manager=mock_message_manager)


@pytest.fixture
def full_sessions_registry(mock_message_manager, mock_session_manager):
    """Registry with both message and session managers."""
    return create_session_messages_registry(
        message_manager=mock_message_manager,
        session_manager=mock_session_manager,
    )


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


# --- Session CRUD Tool Tests ---


def test_full_registry_has_session_tools(full_sessions_registry):
    """Test that full registry has all session and handoff tools."""
    expected_tools = [
        "get_session_messages",
        "search_messages",
        "get_session",
        "get_current_session",
        "list_sessions",
        "session_stats",
        "get_handoff_context",
        "create_handoff",
    ]

    tools_list = full_sessions_registry.list_tools()
    tool_names = [t["name"] for t in tools_list]

    for tool_name in expected_tools:
        assert tool_name in tool_names, f"Missing tool: {tool_name}"


def test_registry_without_session_manager_lacks_crud_tools(session_messages_registry):
    """Test that registry without session_manager doesn't have CRUD tools."""
    tools_list = session_messages_registry.list_tools()
    tool_names = [t["name"] for t in tools_list]

    # Should have message tools
    assert "get_session_messages" in tool_names
    assert "search_messages" in tool_names

    # Should NOT have session CRUD tools
    assert "get_session" not in tool_names
    assert "list_sessions" not in tool_names


def _make_mock_session(session_id: str = "sess-123", **kwargs) -> MagicMock:
    """Helper to create a mock Session object."""
    session = MagicMock(spec=Session)
    session.id = session_id
    session.to_dict.return_value = {
        "id": session_id,
        "status": kwargs.get("status", "active"),
        "source": kwargs.get("source", "claude_code"),
        "project_id": kwargs.get("project_id", "proj-123"),
        "title": kwargs.get("title"),
        "created_at": "2025-01-01T00:00:00Z",
        "updated_at": "2025-01-01T00:00:00Z",
    }
    return session


@pytest.mark.asyncio
async def test_get_session(mock_session_manager, full_sessions_registry):
    """Test get_session tool execution."""
    mock_session = _make_mock_session("sess-abc")
    mock_session_manager.get.return_value = mock_session

    result = await full_sessions_registry.call("get_session", {"session_id": "sess-abc"})

    mock_session_manager.get.assert_called_with("sess-abc")
    assert result["found"] is True
    assert result["id"] == "sess-abc"


@pytest.mark.asyncio
async def test_get_session_not_found(mock_session_manager, full_sessions_registry):
    """Test get_session returns error when not found."""
    mock_session_manager.get.return_value = None
    mock_session_manager.list.return_value = []

    result = await full_sessions_registry.call("get_session", {"session_id": "nonexistent"})

    assert "error" in result
    assert result["found"] is False


@pytest.mark.asyncio
async def test_get_session_prefix_match(mock_session_manager, full_sessions_registry):
    """Test get_session supports prefix matching."""
    mock_session = _make_mock_session("sess-abc123")
    mock_session_manager.get.return_value = None  # Direct lookup fails
    mock_session_manager.list.return_value = [mock_session]  # But prefix match works

    result = await full_sessions_registry.call("get_session", {"session_id": "sess-abc"})

    assert result["found"] is True
    assert result["id"] == "sess-abc123"


@pytest.mark.asyncio
async def test_get_current_session(mock_session_manager, full_sessions_registry):
    """Test get_current_session tool execution."""
    mock_session = _make_mock_session("sess-active", status="active")
    mock_session_manager.list.return_value = [mock_session]

    result = await full_sessions_registry.call("get_current_session", {})

    mock_session_manager.list.assert_called_with(
        project_id=None, status="active", limit=1
    )
    assert result["found"] is True
    assert result["status"] == "active"


@pytest.mark.asyncio
async def test_get_current_session_none(mock_session_manager, full_sessions_registry):
    """Test get_current_session when no active session."""
    mock_session_manager.list.return_value = []

    result = await full_sessions_registry.call("get_current_session", {"project_id": "proj-123"})

    assert result["found"] is False
    assert result["project_id"] == "proj-123"


@pytest.mark.asyncio
async def test_list_sessions(mock_session_manager, full_sessions_registry):
    """Test list_sessions tool execution."""
    mock_sessions = [
        _make_mock_session("sess-1"),
        _make_mock_session("sess-2"),
    ]
    mock_session_manager.list.return_value = mock_sessions
    mock_session_manager.count.return_value = 2

    result = await full_sessions_registry.call("list_sessions", {"limit": 10})

    mock_session_manager.list.assert_called_with(
        project_id=None, status=None, source=None, limit=10
    )
    assert result["count"] == 2
    assert result["total"] == 2
    assert len(result["sessions"]) == 2


@pytest.mark.asyncio
async def test_list_sessions_with_filters(mock_session_manager, full_sessions_registry):
    """Test list_sessions with status and source filters."""
    mock_session_manager.list.return_value = []
    mock_session_manager.count.return_value = 0

    result = await full_sessions_registry.call(
        "list_sessions",
        {"status": "active", "source": "claude_code", "project_id": "proj-123"},
    )

    mock_session_manager.list.assert_called_with(
        project_id="proj-123", status="active", source="claude_code", limit=20
    )
    assert result["filters"]["status"] == "active"
    assert result["filters"]["source"] == "claude_code"


@pytest.mark.asyncio
async def test_session_stats(mock_session_manager, full_sessions_registry):
    """Test session_stats tool execution."""
    mock_session_manager.count.return_value = 10
    mock_session_manager.count_by_status.return_value = {
        "active": 3,
        "expired": 7,
    }

    result = await full_sessions_registry.call("session_stats", {})

    assert result["total"] == 10
    assert result["by_status"]["active"] == 3
    assert result["by_status"]["expired"] == 7


# --- Handoff Tool Tests ---


@pytest.mark.asyncio
async def test_get_handoff_context(mock_session_manager, full_sessions_registry):
    """Test get_handoff_context tool execution."""
    mock_session = _make_mock_session("sess-abc")
    mock_session.compact_markdown = "## Continuation Context\n\nTest handoff content"
    mock_session_manager.get.return_value = mock_session

    result = await full_sessions_registry.call("get_handoff_context", {"session_id": "sess-abc"})

    mock_session_manager.get.assert_called_with("sess-abc")
    assert result["session_id"] == "sess-abc"
    assert result["has_context"] is True
    assert "Test handoff content" in result["compact_markdown"]


@pytest.mark.asyncio
async def test_get_handoff_context_not_found(mock_session_manager, full_sessions_registry):
    """Test get_handoff_context when session not found."""
    mock_session_manager.get.return_value = None

    result = await full_sessions_registry.call("get_handoff_context", {"session_id": "nonexistent"})

    assert "error" in result
    assert result["found"] is False


@pytest.mark.asyncio
async def test_get_handoff_context_no_context(mock_session_manager, full_sessions_registry):
    """Test get_handoff_context when session has no handoff context."""
    mock_session = _make_mock_session("sess-abc")
    mock_session.compact_markdown = None
    mock_session_manager.get.return_value = mock_session

    result = await full_sessions_registry.call("get_handoff_context", {"session_id": "sess-abc"})

    assert result["has_context"] is False
    assert result["compact_markdown"] is None


@pytest.mark.asyncio
async def test_create_handoff_no_session(mock_session_manager, full_sessions_registry):
    """Test create_handoff when no session is found."""
    mock_session_manager.get.return_value = None
    mock_session_manager.list.return_value = []

    result = await full_sessions_registry.call("create_handoff", {})

    assert "error" in result
    assert "No session found" in result["error"]


@pytest.mark.asyncio
async def test_create_handoff_no_transcript(mock_session_manager, full_sessions_registry):
    """Test create_handoff when session has no transcript path."""
    mock_session = _make_mock_session("sess-abc")
    mock_session.jsonl_path = None
    mock_session_manager.get.return_value = mock_session

    result = await full_sessions_registry.call("create_handoff", {"session_id": "sess-abc"})

    assert "error" in result
    assert "No transcript path" in result["error"]

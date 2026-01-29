"""
Tests for gobby.mcp_proxy.tools.agent_messaging module.

Tests the inter-agent messaging MCP tools:
- send_to_parent
- send_to_child
- poll_messages
- mark_message_read
- broadcast_to_children
"""

from dataclasses import dataclass
from unittest.mock import MagicMock

import pytest

from gobby.mcp_proxy.tools.internal import InternalToolRegistry

pytestmark = pytest.mark.unit

class MockInterSessionMessage:
    """Mock inter-session message object for tests."""

    def __init__(
        self,
        id: str = "msg-123",
        from_session: str = "session-parent",
        to_session: str = "session-child",
        content: str = "Test message content",
        priority: str = "normal",
        sent_at: str = "2026-01-22T12:00:00Z",
        read_at: str | None = None,
    ):
        self.id = id
        self.from_session = from_session
        self.to_session = to_session
        self.content = content
        self.priority = priority
        self.sent_at = sent_at
        self.read_at = read_at

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "from_session": self.from_session,
            "to_session": self.to_session,
            "content": self.content,
            "priority": self.priority,
            "sent_at": self.sent_at,
            "read_at": self.read_at,
        }


@dataclass
class MockSession:
    """Mock session object for tests."""

    id: str
    parent_session_id: str | None = None
    status: str = "active"


@pytest.fixture
def mock_message_manager():
    """Create a mock inter-session message manager."""
    manager = MagicMock()
    manager.create_message = MagicMock(return_value=MockInterSessionMessage())
    manager.get_messages = MagicMock(return_value=[MockInterSessionMessage()])
    manager.mark_read = MagicMock(
        return_value=MockInterSessionMessage(read_at="2026-01-22T12:05:00Z")
    )
    return manager


@pytest.fixture
def mock_session_manager():
    """Create a mock session manager."""
    manager = MagicMock()
    # Default: return None for any get() call
    manager.get = MagicMock(return_value=None)
    # Default: return empty list for find_children()
    manager.find_children = MagicMock(return_value=[])
    # resolve_session_reference returns input unchanged by default
    manager.resolve_session_reference = MagicMock(side_effect=lambda ref, project_id=None: ref)
    return manager


@pytest.fixture
def messaging_registry(mock_message_manager, mock_session_manager):
    """Create a registry with messaging tools."""
    from gobby.mcp_proxy.tools.agent_messaging import add_messaging_tools

    registry = InternalToolRegistry(
        name="gobby-agents",
        description="Agent spawning and messaging",
    )
    add_messaging_tools(
        registry=registry,
        message_manager=mock_message_manager,
        session_manager=mock_session_manager,
    )
    return registry


@pytest.mark.unit
class TestAddMessagingTools:
    """Tests for add_messaging_tools function."""

    def test_adds_all_expected_tools(self, messaging_registry) -> None:
        """Test that all messaging tools are registered."""
        tools = messaging_registry.list_tools()
        tool_names = [t["name"] for t in tools]

        assert "send_to_parent" in tool_names
        assert "send_to_child" in tool_names
        assert "broadcast_to_children" in tool_names
        assert "poll_messages" in tool_names
        assert "mark_message_read" in tool_names


@pytest.mark.unit
class TestSendToParent:
    """Tests for send_to_parent tool."""

    @pytest.mark.asyncio
    async def test_send_to_parent_success(
        self, messaging_registry, mock_message_manager, mock_session_manager
    ):
        """Test successful message send to parent."""
        # Setup: session exists in database with parent relationship
        mock_session_manager.get.return_value = MockSession(
            id="session-child",
            parent_session_id="session-parent",
        )

        result = await messaging_registry.call(
            "send_to_parent",
            {
                "session_id": "session-child",
                "content": "Hello parent!",
                "priority": "normal",
            },
        )

        assert result["success"] is True
        assert "message" in result
        assert result["parent_session_id"] == "session-parent"
        mock_message_manager.create_message.assert_called_once_with(
            from_session="session-child",
            to_session="session-parent",
            content="Hello parent!",
            priority="normal",
        )

    @pytest.mark.asyncio
    async def test_send_to_parent_session_not_found(self, messaging_registry, mock_session_manager):
        """Test send_to_parent when session is not found in database."""
        mock_session_manager.get.return_value = None

        result = await messaging_registry.call(
            "send_to_parent",
            {
                "session_id": "unknown-session",
                "content": "Hello?",
            },
        )

        assert result["success"] is False
        assert "not found" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_send_to_parent_no_parent(self, messaging_registry, mock_session_manager):
        """Test send_to_parent when session has no parent."""
        # Session exists but has no parent
        mock_session_manager.get.return_value = MockSession(
            id="session-orphan",
            parent_session_id=None,
        )

        result = await messaging_registry.call(
            "send_to_parent",
            {
                "session_id": "session-orphan",
                "content": "Hello?",
            },
        )

        assert result["success"] is False
        assert "no parent" in result["error"].lower()


@pytest.mark.unit
class TestSendToChild:
    """Tests for send_to_child tool."""

    @pytest.mark.asyncio
    async def test_send_to_child_success(
        self, messaging_registry, mock_message_manager, mock_session_manager
    ):
        """Test successful message send to child."""
        # Setup: child session exists in database with correct parent
        mock_session_manager.get.return_value = MockSession(
            id="session-child",
            parent_session_id="session-parent",
        )

        result = await messaging_registry.call(
            "send_to_child",
            {
                "parent_session_id": "session-parent",
                "child_session_id": "session-child",
                "content": "Hello child!",
                "priority": "urgent",
            },
        )

        assert result["success"] is True
        assert "message" in result
        mock_message_manager.create_message.assert_called_once_with(
            from_session="session-parent",
            to_session="session-child",
            content="Hello child!",
            priority="urgent",
        )

    @pytest.mark.asyncio
    async def test_send_to_child_not_found(self, messaging_registry, mock_session_manager):
        """Test send_to_child when child session is not found."""
        mock_session_manager.get.return_value = None

        result = await messaging_registry.call(
            "send_to_child",
            {
                "parent_session_id": "session-parent",
                "child_session_id": "unknown-child",
                "content": "Hello?",
            },
        )

        assert result["success"] is False
        assert "not found" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_send_to_child_wrong_parent(self, messaging_registry, mock_session_manager):
        """Test send_to_child when parent doesn't match."""
        # Child exists but has different parent
        mock_session_manager.get.return_value = MockSession(
            id="session-child",
            parent_session_id="session-actual-parent",
        )

        result = await messaging_registry.call(
            "send_to_child",
            {
                "parent_session_id": "session-wrong-parent",
                "child_session_id": "session-child",
                "content": "Hello?",
            },
        )

        assert result["success"] is False
        assert "not a child of" in result["error"].lower()


@pytest.mark.unit
class TestPollMessages:
    """Tests for poll_messages tool."""

    @pytest.mark.asyncio
    async def test_poll_messages_success(self, messaging_registry, mock_message_manager):
        """Test successful message polling."""
        mock_message_manager.get_messages.return_value = [
            MockInterSessionMessage(id="msg-1", content="Message 1"),
            MockInterSessionMessage(id="msg-2", content="Message 2"),
        ]

        result = await messaging_registry.call(
            "poll_messages",
            {
                "session_id": "session-child",
            },
        )

        assert result["success"] is True
        assert "messages" in result
        assert len(result["messages"]) == 2
        mock_message_manager.get_messages.assert_called_once_with(
            to_session="session-child",
            unread_only=True,
        )

    @pytest.mark.asyncio
    async def test_poll_messages_all(self, messaging_registry, mock_message_manager):
        """Test polling all messages (not just unread)."""
        result = await messaging_registry.call(
            "poll_messages",
            {
                "session_id": "session-child",
                "unread_only": False,
            },
        )

        assert result["success"] is True
        mock_message_manager.get_messages.assert_called_once_with(
            to_session="session-child",
            unread_only=False,
        )

    @pytest.mark.asyncio
    async def test_poll_messages_empty(self, messaging_registry, mock_message_manager):
        """Test polling when no messages exist."""
        mock_message_manager.get_messages.return_value = []

        result = await messaging_registry.call(
            "poll_messages",
            {
                "session_id": "session-child",
            },
        )

        assert result["success"] is True
        assert result["messages"] == []
        assert result["count"] == 0


@pytest.mark.unit
class TestMarkMessageRead:
    """Tests for mark_message_read tool."""

    @pytest.mark.asyncio
    async def test_mark_message_read_success(self, messaging_registry, mock_message_manager):
        """Test successful message mark as read."""
        mock_message_manager.mark_read.return_value = MockInterSessionMessage(
            id="msg-123",
            read_at="2026-01-22T12:05:00Z",
        )

        result = await messaging_registry.call(
            "mark_message_read",
            {
                "message_id": "msg-123",
            },
        )

        assert result["success"] is True
        assert result["message"]["read_at"] is not None
        mock_message_manager.mark_read.assert_called_once_with("msg-123")

    @pytest.mark.asyncio
    async def test_mark_message_read_not_found(self, messaging_registry, mock_message_manager):
        """Test marking non-existent message as read."""
        mock_message_manager.mark_read.side_effect = ValueError("Message not found")

        result = await messaging_registry.call(
            "mark_message_read",
            {
                "message_id": "nonexistent",
            },
        )

        assert result["success"] is False
        assert "not found" in result["error"].lower()


@pytest.mark.unit
class TestBroadcastToChildren:
    """Tests for broadcast_to_children tool."""

    @pytest.mark.asyncio
    async def test_broadcast_to_children_success(
        self, messaging_registry, mock_message_manager, mock_session_manager
    ):
        """Test broadcasting message to all active children."""
        # Setup: 3 active children in database
        mock_session_manager.find_children.return_value = [
            MockSession(id="session-child-0", parent_session_id="session-parent", status="active"),
            MockSession(id="session-child-1", parent_session_id="session-parent", status="active"),
            MockSession(id="session-child-2", parent_session_id="session-parent", status="active"),
        ]

        result = await messaging_registry.call(
            "broadcast_to_children",
            {
                "parent_session_id": "session-parent",
                "content": "Hello all children!",
            },
        )

        assert result["success"] is True
        assert result["sent_count"] == 3
        assert mock_message_manager.create_message.call_count == 3

    @pytest.mark.asyncio
    async def test_broadcast_to_children_filters_inactive(
        self, messaging_registry, mock_message_manager, mock_session_manager
    ):
        """Test that broadcast filters out inactive children."""
        # Setup: 2 active, 1 paused child
        mock_session_manager.find_children.return_value = [
            MockSession(id="session-child-0", parent_session_id="session-parent", status="active"),
            MockSession(id="session-child-1", parent_session_id="session-parent", status="paused"),
            MockSession(id="session-child-2", parent_session_id="session-parent", status="active"),
        ]

        result = await messaging_registry.call(
            "broadcast_to_children",
            {
                "parent_session_id": "session-parent",
                "content": "Hello active children!",
            },
        )

        assert result["success"] is True
        assert result["sent_count"] == 2
        assert result["total_children"] == 2

    @pytest.mark.asyncio
    async def test_broadcast_to_children_no_children(
        self, messaging_registry, mock_session_manager
    ):
        """Test broadcasting when no children exist."""
        mock_session_manager.find_children.return_value = []

        result = await messaging_registry.call(
            "broadcast_to_children",
            {
                "parent_session_id": "session-parent",
                "content": "Hello?",
            },
        )

        assert result["success"] is True
        assert result["sent_count"] == 0


@pytest.mark.unit
class TestErrorHandling:
    """Tests for error handling in messaging tools."""

    @pytest.mark.asyncio
    async def test_send_to_parent_manager_error(
        self, messaging_registry, mock_message_manager, mock_session_manager
    ):
        """Test error handling when message manager fails."""
        # Setup: session exists with parent
        mock_session_manager.get.return_value = MockSession(
            id="session-child",
            parent_session_id="session-parent",
        )

        mock_message_manager.create_message.side_effect = Exception("Database error")

        result = await messaging_registry.call(
            "send_to_parent",
            {
                "session_id": "session-child",
                "content": "This will fail",
            },
        )

        assert result["success"] is False
        assert "error" in result

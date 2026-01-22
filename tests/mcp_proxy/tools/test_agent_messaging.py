"""
Tests for gobby.mcp_proxy.tools.agent_messaging module.

Tests the inter-agent messaging MCP tools:
- send_to_parent
- send_to_child
- poll_messages
- mark_message_read
"""

from unittest.mock import MagicMock

import pytest

from gobby.agents.registry import RunningAgent, RunningAgentRegistry
from gobby.mcp_proxy.tools.internal import InternalToolRegistry


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
def mock_agent_registry():
    """Create a mock running agent registry."""
    registry = RunningAgentRegistry()
    return registry


@pytest.fixture
def messaging_registry(mock_message_manager, mock_agent_registry):
    """Create a registry with messaging tools."""
    from gobby.mcp_proxy.tools.agent_messaging import add_messaging_tools

    registry = InternalToolRegistry(
        name="gobby-agents",
        description="Agent spawning and messaging",
    )
    add_messaging_tools(
        registry=registry,
        message_manager=mock_message_manager,
        agent_registry=mock_agent_registry,
    )
    return registry


class TestAddMessagingTools:
    """Tests for add_messaging_tools function."""

    def test_adds_all_expected_tools(self, messaging_registry):
        """Test that all messaging tools are registered."""
        tools = messaging_registry.list_tools()
        tool_names = [t["name"] for t in tools]

        assert "send_to_parent" in tool_names
        assert "send_to_child" in tool_names
        assert "broadcast_to_children" in tool_names
        assert "poll_messages" in tool_names
        assert "mark_message_read" in tool_names


class TestSendToParent:
    """Tests for send_to_parent tool."""

    @pytest.mark.asyncio
    async def test_send_to_parent_success(
        self, messaging_registry, mock_message_manager, mock_agent_registry
    ):
        """Test successful message send to parent."""
        # Register a running agent with parent relationship
        child_agent = RunningAgent(
            run_id="run-123",
            session_id="session-child",
            parent_session_id="session-parent",
            mode="terminal",
        )
        mock_agent_registry.add(child_agent)

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
        mock_message_manager.create_message.assert_called_once_with(
            from_session="session-child",
            to_session="session-parent",
            content="Hello parent!",
            priority="normal",
        )

    @pytest.mark.asyncio
    async def test_send_to_parent_no_running_agent(
        self, messaging_registry, mock_agent_registry
    ):
        """Test send_to_parent when session is not in running registry."""
        result = await messaging_registry.call(
            "send_to_parent",
            {
                "session_id": "unknown-session",
                "content": "Hello?",
            },
        )

        assert result["success"] is False
        assert "not found" in result["error"].lower()

    def test_send_to_parent_no_parent(self):
        """Test send_to_parent when agent has no parent.

        This test is skipped because RunningAgent dataclass requires parent_session_id.
        All spawned agents in practice have parents, so this edge case cannot occur.
        """
        pytest.skip("RunningAgent requires parent_session_id - edge case cannot occur")


class TestSendToChild:
    """Tests for send_to_child tool."""

    @pytest.mark.asyncio
    async def test_send_to_child_success(
        self, messaging_registry, mock_message_manager, mock_agent_registry
    ):
        """Test successful message send to child."""
        # Register a running agent as a child
        child_agent = RunningAgent(
            run_id="run-456",
            session_id="session-child",
            parent_session_id="session-parent",
            mode="terminal",
        )
        mock_agent_registry.add(child_agent)

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
    async def test_send_to_child_not_running(
        self, messaging_registry, mock_agent_registry
    ):
        """Test send_to_child when child is not running."""
        result = await messaging_registry.call(
            "send_to_child",
            {
                "parent_session_id": "session-parent",
                "child_session_id": "unknown-child",
                "content": "Hello?",
            },
        )

        assert result["success"] is False
        assert "not found" in result["error"].lower() or "not running" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_send_to_child_wrong_parent(
        self, messaging_registry, mock_agent_registry
    ):
        """Test send_to_child when parent doesn't match."""
        child_agent = RunningAgent(
            run_id="run-789",
            session_id="session-child",
            parent_session_id="session-actual-parent",
            mode="terminal",
        )
        mock_agent_registry.add(child_agent)

        result = await messaging_registry.call(
            "send_to_child",
            {
                "parent_session_id": "session-wrong-parent",
                "child_session_id": "session-child",
                "content": "Hello?",
            },
        )

        assert result["success"] is False
        assert "parent" in result["error"].lower()


class TestPollMessages:
    """Tests for poll_messages tool."""

    @pytest.mark.asyncio
    async def test_poll_messages_success(
        self, messaging_registry, mock_message_manager
    ):
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
    async def test_poll_messages_all(
        self, messaging_registry, mock_message_manager
    ):
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
    async def test_poll_messages_empty(
        self, messaging_registry, mock_message_manager
    ):
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


class TestMarkMessageRead:
    """Tests for mark_message_read tool."""

    @pytest.mark.asyncio
    async def test_mark_message_read_success(
        self, messaging_registry, mock_message_manager
    ):
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
    async def test_mark_message_read_not_found(
        self, messaging_registry, mock_message_manager
    ):
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


class TestBroadcastToChildren:
    """Tests for broadcast_to_children tool (optional extension)."""

    @pytest.mark.asyncio
    async def test_broadcast_to_children_success(
        self, messaging_registry, mock_message_manager, mock_agent_registry
    ):
        """Test broadcasting message to all children."""
        # Register multiple children
        for i in range(3):
            child_agent = RunningAgent(
                run_id=f"run-{i}",
                session_id=f"session-child-{i}",
                parent_session_id="session-parent",
                mode="terminal",
            )
            mock_agent_registry.add(child_agent)

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
    async def test_broadcast_to_children_no_children(
        self, messaging_registry, mock_agent_registry
    ):
        """Test broadcasting when no children exist."""
        result = await messaging_registry.call(
            "broadcast_to_children",
            {
                "parent_session_id": "session-parent",
                "content": "Hello?",
            },
        )

        assert result["success"] is True
        assert result["sent_count"] == 0


class TestErrorHandling:
    """Tests for error handling in messaging tools."""

    @pytest.mark.asyncio
    async def test_send_to_parent_manager_error(
        self, messaging_registry, mock_message_manager, mock_agent_registry
    ):
        """Test error handling when message manager fails."""
        child_agent = RunningAgent(
            run_id="run-err",
            session_id="session-child",
            parent_session_id="session-parent",
            mode="terminal",
        )
        mock_agent_registry.add(child_agent)

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

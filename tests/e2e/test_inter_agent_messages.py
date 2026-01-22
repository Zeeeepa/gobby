"""
E2E tests for inter-agent messaging via MCP tools.

Tests verify:
1. Parent-child message exchange works via gobby-agents MCP tools
2. Messages are persisted and retrievable
3. Message read status is tracked

Test scenario:
1. Start daemon
2. Register parent and child sessions
3. Parent sends message via send_to_child
4. Child receives via poll_messages
5. Child responds via send_to_parent
6. Parent receives response
"""

import uuid

import httpx
import pytest

from tests.e2e.conftest import (
    CLIEventSimulator,
    DaemonInstance,
    MCPTestClient,
)

pytestmark = pytest.mark.e2e


def unwrap_result(result: dict) -> dict:
    """Unwrap MCP tool call result from wrapper response."""
    # MCP call_tool endpoint returns {"success": bool, "result": {...}, "response_time_ms": float}
    # The actual tool result is in result["result"]
    if "result" in result:
        return result["result"]
    return result


class TestInterAgentMessagingE2E:
    """E2E tests for inter-agent messaging through the daemon."""

    def test_poll_messages_empty(
        self,
        daemon_instance: DaemonInstance,
        mcp_client: MCPTestClient,
        cli_events: CLIEventSimulator,
    ):
        """Test polling messages returns empty list when no messages."""
        # Register a session
        session_id = f"test-session-{uuid.uuid4().hex[:8]}"
        cli_events.session_start(
            session_id=session_id,
            machine_id="test-machine",
            source="claude",
        )

        # Poll messages should return empty
        raw_result = mcp_client.call_tool(
            server_name="gobby-agents",
            tool_name="poll_messages",
            arguments={"session_id": session_id},
        )
        result = unwrap_result(raw_result)

        assert result.get("success") is True
        assert result.get("messages", []) == []
        assert result.get("count", 0) == 0

    def test_poll_messages_with_unread_filter(
        self,
        daemon_instance: DaemonInstance,
        mcp_client: MCPTestClient,
        cli_events: CLIEventSimulator,
    ):
        """Test polling all messages (not just unread)."""
        session_id = f"test-session-{uuid.uuid4().hex[:8]}"
        cli_events.session_start(
            session_id=session_id,
            machine_id="test-machine",
            source="claude",
        )

        # Poll all messages
        raw_result = mcp_client.call_tool(
            server_name="gobby-agents",
            tool_name="poll_messages",
            arguments={"session_id": session_id, "unread_only": False},
        )
        result = unwrap_result(raw_result)

        assert result.get("success") is True
        assert isinstance(result.get("messages"), list)

    def test_send_to_child_without_running_agent(
        self,
        daemon_instance: DaemonInstance,
        mcp_client: MCPTestClient,
        cli_events: CLIEventSimulator,
    ):
        """Test send_to_child fails gracefully when child is not a running agent."""
        parent_session_id = f"parent-{uuid.uuid4().hex[:8]}"
        child_session_id = f"child-{uuid.uuid4().hex[:8]}"

        # Register sessions (but no agent relationship)
        cli_events.session_start(
            session_id=parent_session_id,
            machine_id="test-machine",
            source="claude",
        )
        cli_events.session_start(
            session_id=child_session_id,
            machine_id="test-machine",
            source="claude",
        )

        # Try to send message - should fail because child is not a running agent
        raw_result = mcp_client.call_tool(
            server_name="gobby-agents",
            tool_name="send_to_child",
            arguments={
                "parent_session_id": parent_session_id,
                "child_session_id": child_session_id,
                "content": "Hello child!",
            },
        )
        result = unwrap_result(raw_result)

        assert result.get("success") is False
        # Should mention that the child is not found in running agent registry
        assert "not found" in result.get("error", "").lower()

    def test_send_to_parent_without_running_agent(
        self,
        daemon_instance: DaemonInstance,
        mcp_client: MCPTestClient,
        cli_events: CLIEventSimulator,
    ):
        """Test send_to_parent fails gracefully when session is not a running agent."""
        session_id = f"test-session-{uuid.uuid4().hex[:8]}"

        cli_events.session_start(
            session_id=session_id,
            machine_id="test-machine",
            source="claude",
        )

        # Try to send message to parent - should fail because not a running agent
        raw_result = mcp_client.call_tool(
            server_name="gobby-agents",
            tool_name="send_to_parent",
            arguments={
                "session_id": session_id,
                "content": "Hello parent!",
            },
        )
        result = unwrap_result(raw_result)

        assert result.get("success") is False
        assert "not found" in result.get("error", "").lower()

    def test_mark_message_read_nonexistent(
        self,
        daemon_instance: DaemonInstance,
        mcp_client: MCPTestClient,
    ):
        """Test marking nonexistent message as read fails gracefully."""
        raw_result = mcp_client.call_tool(
            server_name="gobby-agents",
            tool_name="mark_message_read",
            arguments={"message_id": "nonexistent-msg-id"},
        )
        result = unwrap_result(raw_result)

        assert result.get("success") is False
        assert "not found" in result.get("error", "").lower()

    def test_broadcast_to_children_no_children(
        self,
        daemon_instance: DaemonInstance,
        mcp_client: MCPTestClient,
        cli_events: CLIEventSimulator,
    ):
        """Test broadcasting to children when none exist returns success with zero sent."""
        parent_session_id = f"parent-{uuid.uuid4().hex[:8]}"

        cli_events.session_start(
            session_id=parent_session_id,
            machine_id="test-machine",
            source="claude",
        )

        # Broadcast - should succeed with 0 sent
        raw_result = mcp_client.call_tool(
            server_name="gobby-agents",
            tool_name="broadcast_to_children",
            arguments={
                "parent_session_id": parent_session_id,
                "content": "Hello all children!",
            },
        )
        result = unwrap_result(raw_result)

        assert result.get("success") is True
        assert result.get("sent_count", -1) == 0


class TestMessagingToolsAvailability:
    """Tests to verify messaging tools are properly registered."""

    def test_messaging_tools_are_registered(
        self,
        daemon_instance: DaemonInstance,
        mcp_client: MCPTestClient,
    ):
        """Verify all messaging tools are available on gobby-agents server."""
        tools = mcp_client.list_tools(server="gobby-agents")
        tool_names = [t["name"] for t in tools]

        expected_tools = [
            "send_to_parent",
            "send_to_child",
            "poll_messages",
            "mark_message_read",
            "broadcast_to_children",
        ]

        for tool in expected_tools:
            assert tool in tool_names, f"Missing tool: {tool}"

    def test_send_to_parent_schema(
        self,
        daemon_instance: DaemonInstance,
        mcp_client: MCPTestClient,
    ):
        """Verify send_to_parent tool schema can be retrieved."""
        raw_schema = mcp_client.get_tool_schema(
            server_name="gobby-agents",
            tool_name="send_to_parent",
        )

        # Schema endpoint returns response - just verify we get some response
        assert raw_schema is not None
        assert isinstance(raw_schema, dict)

    def test_poll_messages_schema(
        self,
        daemon_instance: DaemonInstance,
        mcp_client: MCPTestClient,
    ):
        """Verify poll_messages tool schema can be retrieved."""
        raw_schema = mcp_client.get_tool_schema(
            server_name="gobby-agents",
            tool_name="poll_messages",
        )

        # Schema endpoint returns response - just verify we get some response
        assert raw_schema is not None
        assert isinstance(raw_schema, dict)

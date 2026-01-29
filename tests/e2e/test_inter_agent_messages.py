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

    def test_parent_child_message_exchange(
        self,
        daemon_instance: DaemonInstance,
        mcp_client: MCPTestClient,
        cli_events: CLIEventSimulator,
    ) -> None:
        """Test complete parent↔child message exchange via MCP tools.

        This test verifies the full messaging flow:
        1. Parent sends message via send_to_child
        2. Child receives via poll_messages
        3. Child responds via send_to_parent
        4. Parent receives response via poll_messages
        """
        # Setup: Create parent and child sessions using register_session
        # (which creates entries in the sessions DB table)
        parent_external_id = f"parent-{uuid.uuid4().hex[:8]}"
        child_external_id = f"child-{uuid.uuid4().hex[:8]}"
        run_id = f"run-{uuid.uuid4().hex[:8]}"

        # First, register the project in the database (required for FK constraint)
        project_result = cli_events.register_test_project(
            project_id="e2e-test-project",
            name="E2E Test Project",
            repo_path=str(daemon_instance.project_dir),
        )
        assert project_result["status"] in ["success", "already_exists"]

        # Register parent session first and get internal ID
        parent_result = cli_events.register_session(
            external_id=parent_external_id,
            machine_id="test-machine",
            source="Claude Code",
            cwd=str(daemon_instance.project_dir),
        )
        parent_session_id = parent_result["id"]  # Internal session ID

        # Register child session with parent relationship
        child_result = cli_events.register_session(
            external_id=child_external_id,
            machine_id="test-machine",
            source="Claude Code",
            parent_session_id=parent_session_id,
            cwd=str(daemon_instance.project_dir),
        )
        child_session_id = child_result["id"]  # Internal session ID

        # Register the child as a running agent in the agent registry
        register_result = cli_events.register_test_agent(
            run_id=run_id,
            session_id=child_session_id,
            parent_session_id=parent_session_id,
            mode="terminal",
        )
        assert register_result["status"] == "success"

        # Step 1: Parent sends message to child via send_to_child
        raw_result = mcp_client.call_tool(
            server_name="gobby-agents",
            tool_name="send_to_child",
            arguments={
                "parent_session_id": parent_session_id,
                "child_session_id": child_session_id,
                "content": "Hello child, please process this task!",
            },
        )
        result = unwrap_result(raw_result)
        assert result.get("success") is True, f"send_to_child failed: {result}"
        assert "message" in result, f"No message in result: {result}"
        parent_to_child_msg_id = result["message"]["id"]
        assert parent_to_child_msg_id is not None

        # Step 2: Child receives message via poll_messages
        raw_result = mcp_client.call_tool(
            server_name="gobby-agents",
            tool_name="poll_messages",
            arguments={"session_id": child_session_id, "unread_only": True},
        )
        result = unwrap_result(raw_result)
        assert result.get("success") is True, f"poll_messages failed: {result}"
        messages = result.get("messages", [])
        assert len(messages) >= 1, "Child should have received at least 1 message"

        # Find the message from parent by filtering on content and from_session
        received_msg = next(
            (
                m
                for m in messages
                if m["from_session"] == parent_session_id
                and m["content"] == "Hello child, please process this task!"
            ),
            None,
        )
        assert received_msg is not None, f"Expected message from parent not found in: {messages}"

        # Step 3: Child marks message as read
        raw_result = mcp_client.call_tool(
            server_name="gobby-agents",
            tool_name="mark_message_read",
            arguments={"message_id": received_msg["id"]},
        )
        result = unwrap_result(raw_result)
        assert result.get("success") is True, f"mark_message_read failed: {result}"

        # Step 4: Child responds to parent via send_to_parent
        raw_result = mcp_client.call_tool(
            server_name="gobby-agents",
            tool_name="send_to_parent",
            arguments={
                "session_id": child_session_id,
                "content": "Task completed successfully, parent!",
            },
        )
        result = unwrap_result(raw_result)
        assert result.get("success") is True, f"send_to_parent failed: {result}"
        assert "message" in result, f"No message in result: {result}"
        child_to_parent_msg_id = result["message"]["id"]
        assert child_to_parent_msg_id is not None

        # Step 5: Parent receives response via poll_messages
        raw_result = mcp_client.call_tool(
            server_name="gobby-agents",
            tool_name="poll_messages",
            arguments={"session_id": parent_session_id, "unread_only": True},
        )
        result = unwrap_result(raw_result)
        assert result.get("success") is True, f"poll_messages (parent) failed: {result}"
        parent_messages = result.get("messages", [])
        assert len(parent_messages) >= 1, "Parent should have received at least 1 message"

        # Find the response message from child by filtering on content and from_session
        response_msg = next(
            (
                m
                for m in parent_messages
                if m["from_session"] == child_session_id
                and m["content"] == "Task completed successfully, parent!"
            ),
            None,
        )
        assert response_msg is not None, (
            f"Expected response from child not found in: {parent_messages}"
        )

        # Cleanup: Unregister the test agent
        cli_events.unregister_test_agent(run_id)

    def test_poll_messages_empty(
        self,
        daemon_instance: DaemonInstance,
        mcp_client: MCPTestClient,
        cli_events: CLIEventSimulator,
    ) -> None:
        """Test polling messages returns empty list when no messages."""
        # First, register the project in the database (required for FK constraint)
        project_result = cli_events.register_test_project(
            project_id="e2e-test-project",
            name="E2E Test Project",
            repo_path=str(daemon_instance.project_dir),
        )
        assert project_result["status"] in ["success", "already_exists"]

        # Register a session via register_session to get internal ID
        external_id = f"test-session-{uuid.uuid4().hex[:8]}"
        session_result = cli_events.register_session(
            external_id=external_id,
            machine_id="test-machine",
            source="Claude Code",
            cwd=str(daemon_instance.project_dir),
        )
        session_id = session_result["id"]

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
    ) -> None:
        """Test polling all messages (not just unread)."""
        # First, register the project in the database (required for FK constraint)
        project_result = cli_events.register_test_project(
            project_id="e2e-test-project",
            name="E2E Test Project",
            repo_path=str(daemon_instance.project_dir),
        )
        assert project_result["status"] in ["success", "already_exists"]

        # Register a session via register_session to get internal ID
        external_id = f"test-session-{uuid.uuid4().hex[:8]}"
        session_result = cli_events.register_session(
            external_id=external_id,
            machine_id="test-machine",
            source="Claude Code",
            cwd=str(daemon_instance.project_dir),
        )
        session_id = session_result["id"]

        # Poll all messages
        raw_result = mcp_client.call_tool(
            server_name="gobby-agents",
            tool_name="poll_messages",
            arguments={"session_id": session_id, "unread_only": False},
        )
        result = unwrap_result(raw_result)

        assert result.get("success") is True
        assert isinstance(result.get("messages"), list)

    def test_send_to_child_without_parent_relationship(
        self,
        daemon_instance: DaemonInstance,
        mcp_client: MCPTestClient,
        cli_events: CLIEventSimulator,
    ) -> None:
        """Test send_to_child fails when child has no parent relationship in DB."""
        parent_external_id = f"parent-{uuid.uuid4().hex[:8]}"
        child_external_id = f"child-{uuid.uuid4().hex[:8]}"

        # First, register the project in the database (required for FK constraint)
        project_result = cli_events.register_test_project(
            project_id="e2e-test-project",
            name="E2E Test Project",
            repo_path=str(daemon_instance.project_dir),
        )
        assert project_result["status"] in ["success", "already_exists"]

        # Register sessions via register_session to get internal IDs
        # (no parent-child relationship - child has no parent_session_id)
        parent_result = cli_events.register_session(
            external_id=parent_external_id,
            machine_id="test-machine",
            source="Claude Code",
            cwd=str(daemon_instance.project_dir),
        )
        parent_session_id = parent_result["id"]

        child_result = cli_events.register_session(
            external_id=child_external_id,
            machine_id="test-machine",
            source="Claude Code",
            cwd=str(daemon_instance.project_dir),
            # Note: no parent_session_id - child is not linked to parent
        )
        child_session_id = child_result["id"]

        # Try to send message - should fail because child doesn't have this parent
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
        # Should mention that the session is not a child of the parent
        assert "not a child of" in result.get("error", "").lower()

    def test_send_to_parent_without_parent_relationship(
        self,
        daemon_instance: DaemonInstance,
        mcp_client: MCPTestClient,
        cli_events: CLIEventSimulator,
    ) -> None:
        """Test send_to_parent fails gracefully when session has no parent in DB."""
        external_id = f"test-session-{uuid.uuid4().hex[:8]}"

        # First, register the project in the database (required for FK constraint)
        project_result = cli_events.register_test_project(
            project_id="e2e-test-project",
            name="E2E Test Project",
            repo_path=str(daemon_instance.project_dir),
        )
        assert project_result["status"] in ["success", "already_exists"]

        # Register session via register_session to get internal ID
        # (no parent_session_id set)
        result = cli_events.register_session(
            external_id=external_id,
            machine_id="test-machine",
            source="Claude Code",
            cwd=str(daemon_instance.project_dir),
        )
        session_id = result["id"]

        # Try to send message to parent - should fail because session has no parent_session_id
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
        assert "no parent" in result.get("error", "").lower()

    def test_mark_message_read_nonexistent(
        self,
        daemon_instance: DaemonInstance,
        mcp_client: MCPTestClient,
    ) -> None:
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
    ) -> None:
        """Test broadcasting to children when none exist returns success with zero sent."""
        # First, register the project in the database (required for FK constraint)
        project_result = cli_events.register_test_project(
            project_id="e2e-test-project",
            name="E2E Test Project",
            repo_path=str(daemon_instance.project_dir),
        )
        assert project_result["status"] in ["success", "already_exists"]

        # Register parent session via register_session to get internal ID
        parent_external_id = f"parent-{uuid.uuid4().hex[:8]}"
        parent_result = cli_events.register_session(
            external_id=parent_external_id,
            machine_id="test-machine",
            source="Claude Code",
            cwd=str(daemon_instance.project_dir),
        )
        parent_session_id = parent_result["id"]

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
    ) -> None:
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
    ) -> None:
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
    ) -> None:
        """Verify poll_messages tool schema can be retrieved."""
        raw_schema = mcp_client.get_tool_schema(
            server_name="gobby-agents",
            tool_name="poll_messages",
        )

        # Schema endpoint returns response - just verify we get some response
        assert raw_schema is not None
        assert isinstance(raw_schema, dict)

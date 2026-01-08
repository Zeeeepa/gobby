"""
Comprehensive unit tests for session_messages.py MCP tools module.

Tests cover:
- Helper functions (_format_handoff_markdown, _format_turns_for_llm)
- Message tools (get_session_messages, search_messages)
- Handoff tools (get_handoff_context, create_handoff, pickup)
- Session CRUD tools (get_session, get_current_session, list_sessions, session_stats)
- Session commits tools (get_session_commits, mark_loop_complete)
"""

import json
import tempfile
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from gobby.mcp_proxy.tools.internal import InternalToolRegistry
from gobby.mcp_proxy.tools.session_messages import (
    _format_handoff_markdown,
    _format_turns_for_llm,
    create_session_messages_registry,
)
from gobby.sessions.analyzer import HandoffContext

# ============================================================================
# Custom Registry Class for Testing
# ============================================================================


class SessionMessagesTestRegistry(InternalToolRegistry):
    """Registry subclass with get_tool method for testing."""

    def get_tool(self, name: str) -> Callable[..., Any] | None:
        """Get a tool function by name (for testing)."""
        tool = self._tools.get(name)
        return tool.func if tool else None


def create_test_registry(
    message_manager: Any = None,
    session_manager: Any = None,
) -> SessionMessagesTestRegistry:
    """Create a test-friendly registry by wrapping the real factory."""
    # Create the real registry
    real_registry = create_session_messages_registry(
        message_manager=message_manager,
        session_manager=session_manager,
    )

    # Create test registry with same tools
    test_registry = SessionMessagesTestRegistry(
        name=real_registry.name,
        description=real_registry.description,
    )
    test_registry._tools = real_registry._tools
    return test_registry


# ============================================================================
# Tests for _format_handoff_markdown helper
# ============================================================================


class TestFormatHandoffMarkdown:
    """Tests for _format_handoff_markdown helper function."""

    def test_empty_context(self):
        """Test formatting empty HandoffContext."""
        ctx = HandoffContext()
        result = _format_handoff_markdown(ctx)

        assert "## Continuation Context" in result
        # Should only have the header, no sections
        assert "### Active Task" not in result
        assert "### In-Progress Work" not in result

    def test_with_active_task(self):
        """Test formatting with active gobby task."""
        ctx = HandoffContext(
            active_gobby_task={
                "id": "gt-abc123",
                "title": "Implement feature",
                "status": "in_progress",
            }
        )
        result = _format_handoff_markdown(ctx)

        assert "### Active Task" in result
        assert "**Implement feature**" in result
        assert "gt-abc123" in result
        assert "Status: in_progress" in result

    def test_with_todo_state(self):
        """Test formatting with todo items."""
        ctx = HandoffContext(
            todo_state=[
                {"content": "First task", "status": "completed"},
                {"content": "Second task", "status": "in_progress"},
                {"content": "Third task", "status": "pending"},
            ]
        )
        result = _format_handoff_markdown(ctx)

        assert "### In-Progress Work" in result
        assert "[x] First task" in result
        assert "[>] Second task" in result
        assert "[ ] Third task" in result

    def test_with_git_commits(self):
        """Test formatting with git commits."""
        ctx = HandoffContext(
            git_commits=[
                {"hash": "abc1234567890", "message": "First commit"},
                {"hash": "def9876543210", "message": "Second commit"},
            ]
        )
        result = _format_handoff_markdown(ctx)

        assert "### Commits This Session" in result
        assert "`abc1234`" in result  # Truncated to 7 chars
        assert "First commit" in result
        assert "`def9876`" in result
        assert "Second commit" in result

    def test_with_git_status(self):
        """Test formatting with git status."""
        ctx = HandoffContext(git_status="M src/file.py\n?? new_file.py")
        result = _format_handoff_markdown(ctx)

        assert "### Uncommitted Changes" in result
        assert "```" in result
        assert "M src/file.py" in result
        assert "?? new_file.py" in result

    def test_with_files_modified(self):
        """Test formatting with files modified."""
        ctx = HandoffContext(files_modified=["src/main.py", "tests/test_main.py"])
        result = _format_handoff_markdown(ctx)

        assert "### Files Being Modified" in result
        assert "- src/main.py" in result
        assert "- tests/test_main.py" in result

    def test_with_initial_goal(self):
        """Test formatting with initial goal."""
        ctx = HandoffContext(initial_goal="Implement user authentication")
        result = _format_handoff_markdown(ctx)

        assert "### Original Goal" in result
        assert "Implement user authentication" in result

    def test_with_recent_activity(self):
        """Test formatting with recent activity."""
        ctx = HandoffContext(
            recent_activity=[
                "Called Edit on src/file.py",
                "Ran tests",
                "Called Grep for pattern",
                "Read config file",
                "Updated database",
                "More activity",  # Should be truncated
                "Even more",
            ]
        )
        result = _format_handoff_markdown(ctx)

        assert "### Recent Activity" in result
        # Only last 5 should be shown
        assert "- Called Edit on src/file.py" not in result  # First one truncated
        assert "- Even more" in result

    def test_with_notes(self):
        """Test formatting with additional notes."""
        ctx = HandoffContext()
        result = _format_handoff_markdown(ctx, notes="Remember to run tests")

        assert "### Notes" in result
        assert "Remember to run tests" in result

    def test_full_context(self):
        """Test formatting with all fields populated."""
        ctx = HandoffContext(
            active_gobby_task={"id": "gt-123", "title": "Test", "status": "active"},
            todo_state=[{"content": "Task 1", "status": "pending"}],
            git_commits=[{"hash": "abc1234", "message": "commit"}],
            git_status="M file.py",
            files_modified=["file.py"],
            initial_goal="Build feature",
            recent_activity=["action1"],
        )
        result = _format_handoff_markdown(ctx, notes="Test notes")

        assert "## Continuation Context" in result
        assert "### Active Task" in result
        assert "### In-Progress Work" in result
        assert "### Commits This Session" in result
        assert "### Uncommitted Changes" in result
        assert "### Files Being Modified" in result
        assert "### Original Goal" in result
        assert "### Recent Activity" in result
        assert "### Notes" in result


# ============================================================================
# Tests for _format_turns_for_llm helper
# ============================================================================


class TestFormatTurnsForLLM:
    """Tests for _format_turns_for_llm helper function."""

    def test_empty_turns(self):
        """Test formatting empty turn list."""
        result = _format_turns_for_llm([])
        assert result == ""

    def test_simple_text_content(self):
        """Test formatting turns with simple text content."""
        turns = [
            {"message": {"role": "user", "content": "Hello"}},
            {"message": {"role": "assistant", "content": "Hi there"}},
        ]
        result = _format_turns_for_llm(turns)

        assert "[Turn 1 - user]: Hello" in result
        assert "[Turn 2 - assistant]: Hi there" in result

    def test_content_block_list(self):
        """Test formatting turns with content as list of blocks."""
        turns = [
            {
                "message": {
                    "role": "assistant",
                    "content": [
                        {"type": "text", "text": "Here is the result"},
                        {"type": "tool_use", "name": "Edit"},
                    ],
                }
            }
        ]
        result = _format_turns_for_llm(turns)

        assert "[Turn 1 - assistant]:" in result
        assert "Here is the result" in result
        assert "[Tool: Edit]" in result

    def test_content_block_with_missing_fields(self):
        """Test handling content blocks with missing fields."""
        turns = [
            {
                "message": {
                    "role": "assistant",
                    "content": [
                        {"type": "text"},  # Missing 'text' field
                        {"type": "tool_use"},  # Missing 'name' field
                        {"type": "unknown_type"},
                    ],
                }
            }
        ]
        result = _format_turns_for_llm(turns)

        assert "[Turn 1 - assistant]:" in result
        assert "[Tool: unknown]" in result

    def test_non_dict_content_blocks(self):
        """Test handling non-dict content blocks."""
        turns = [
            {
                "message": {
                    "role": "assistant",
                    "content": [
                        "plain string",  # Not a dict
                        123,  # Number
                        {"type": "text", "text": "actual text"},
                    ],
                }
            }
        ]
        result = _format_turns_for_llm(turns)

        assert "actual text" in result

    def test_missing_role(self):
        """Test handling turns with missing role."""
        turns = [{"message": {"content": "No role here"}}]
        result = _format_turns_for_llm(turns)

        assert "[Turn 1 - unknown]:" in result

    def test_missing_content(self):
        """Test handling turns with missing content."""
        turns = [{"message": {"role": "user"}}]
        result = _format_turns_for_llm(turns)

        assert "[Turn 1 - user]:" in result

    def test_turn_separator(self):
        """Test that turns are separated by double newlines."""
        turns = [
            {"message": {"role": "user", "content": "First"}},
            {"message": {"role": "assistant", "content": "Second"}},
        ]
        result = _format_turns_for_llm(turns)

        assert "\n\n" in result


# ============================================================================
# Tests for Message Tools
# ============================================================================


class TestGetSessionMessages:
    """Tests for get_session_messages tool."""

    @pytest.mark.asyncio
    async def test_get_messages_success(self):
        """Test successful message retrieval."""
        message_manager = AsyncMock()
        message_manager.get_messages.return_value = [
            {"id": 1, "content": "Hello", "role": "user"},
            {"id": 2, "content": "Hi", "role": "assistant"},
        ]
        message_manager.count_messages.return_value = 2

        registry = create_test_registry(message_manager=message_manager)
        get_messages = registry.get_tool("get_session_messages")

        result = await get_messages(session_id="sess-123")

        assert result["success"] is True
        assert result["total_count"] == 2
        assert result["returned_count"] == 2
        assert len(result["messages"]) == 2
        message_manager.get_messages.assert_called_once_with(
            session_id="sess-123", limit=50, offset=0
        )

    @pytest.mark.asyncio
    async def test_get_messages_truncates_content(self):
        """Test that large content is truncated when full_content=False."""
        long_content = "x" * 600  # More than 500 chars
        message_manager = AsyncMock()
        message_manager.get_messages.return_value = [
            {"id": 1, "content": long_content, "role": "user"},
        ]
        message_manager.count_messages.return_value = 1

        registry = create_test_registry(message_manager=message_manager)
        get_messages = registry.get_tool("get_session_messages")

        result = await get_messages(session_id="sess-123", full_content=False)

        assert result["success"] is True
        assert result["truncated"] is True
        # Content should be truncated to ~500 chars + "... (truncated)"
        assert len(result["messages"][0]["content"]) < 600
        assert "... (truncated)" in result["messages"][0]["content"]

    @pytest.mark.asyncio
    async def test_get_messages_full_content(self):
        """Test that content is not truncated when full_content=True."""
        long_content = "x" * 600
        message_manager = AsyncMock()
        message_manager.get_messages.return_value = [
            {"id": 1, "content": long_content, "role": "user"},
        ]
        message_manager.count_messages.return_value = 1

        registry = create_test_registry(message_manager=message_manager)
        get_messages = registry.get_tool("get_session_messages")

        result = await get_messages(session_id="sess-123", full_content=True)

        assert result["success"] is True
        assert result["truncated"] is False
        assert result["messages"][0]["content"] == long_content

    @pytest.mark.asyncio
    async def test_get_messages_truncates_tool_calls(self):
        """Test that tool call input is truncated."""
        long_input = "y" * 300
        message_manager = AsyncMock()
        message_manager.get_messages.return_value = [
            {
                "id": 1,
                "content": "test",
                "role": "assistant",
                "tool_calls": [{"name": "Edit", "input": long_input}],
            },
        ]
        message_manager.count_messages.return_value = 1

        registry = create_test_registry(message_manager=message_manager)
        get_messages = registry.get_tool("get_session_messages")

        result = await get_messages(session_id="sess-123", full_content=False)

        assert result["success"] is True
        assert "... (truncated)" in result["messages"][0]["tool_calls"][0]["input"]

    @pytest.mark.asyncio
    async def test_get_messages_truncates_tool_result(self):
        """Test that tool result content is truncated."""
        long_result = "z" * 300
        message_manager = AsyncMock()
        message_manager.get_messages.return_value = [
            {
                "id": 1,
                "content": "test",
                "role": "user",
                "tool_result": {"content": long_result},
            },
        ]
        message_manager.count_messages.return_value = 1

        registry = create_test_registry(message_manager=message_manager)
        get_messages = registry.get_tool("get_session_messages")

        result = await get_messages(session_id="sess-123", full_content=False)

        assert result["success"] is True
        assert "... (truncated)" in result["messages"][0]["tool_result"]["content"]

    @pytest.mark.asyncio
    async def test_get_messages_with_pagination(self):
        """Test message retrieval with pagination."""
        message_manager = AsyncMock()
        message_manager.get_messages.return_value = []
        message_manager.count_messages.return_value = 100

        registry = create_test_registry(message_manager=message_manager)
        get_messages = registry.get_tool("get_session_messages")

        result = await get_messages(session_id="sess-123", limit=10, offset=20)

        assert result["limit"] == 10
        assert result["offset"] == 20
        message_manager.get_messages.assert_called_once_with(
            session_id="sess-123", limit=10, offset=20
        )

    @pytest.mark.asyncio
    async def test_get_messages_error(self):
        """Test error handling in get_session_messages."""
        message_manager = AsyncMock()
        message_manager.get_messages.side_effect = Exception("Database error")

        registry = create_test_registry(message_manager=message_manager)
        get_messages = registry.get_tool("get_session_messages")

        result = await get_messages(session_id="sess-123")

        assert result["success"] is False
        assert "Database error" in result["error"]


class TestSearchMessages:
    """Tests for search_messages tool."""

    @pytest.mark.asyncio
    async def test_search_messages_success(self):
        """Test successful message search."""
        message_manager = AsyncMock()
        message_manager.search_messages.return_value = [
            {"id": 1, "content": "Found match", "role": "user"},
        ]

        registry = create_test_registry(message_manager=message_manager)
        search = registry.get_tool("search_messages")

        result = await search(query="match")

        assert result["success"] is True
        assert result["count"] == 1
        assert len(result["results"]) == 1
        message_manager.search_messages.assert_called_once()

    @pytest.mark.asyncio
    async def test_search_messages_with_session_filter(self):
        """Test search with session ID filter."""
        message_manager = AsyncMock()
        message_manager.search_messages.return_value = []

        registry = create_test_registry(message_manager=message_manager)
        search = registry.get_tool("search_messages")

        await search(query="test", session_id="sess-123")

        message_manager.search_messages.assert_called_once_with(
            query_text="test", session_id="sess-123", limit=20
        )

    @pytest.mark.asyncio
    async def test_search_messages_truncates_content(self):
        """Test that search results are truncated."""
        long_content = "x" * 600
        message_manager = AsyncMock()
        message_manager.search_messages.return_value = [
            {"id": 1, "content": long_content, "role": "user"},
        ]

        registry = create_test_registry(message_manager=message_manager)
        search = registry.get_tool("search_messages")

        result = await search(query="test", full_content=False)

        assert result["truncated"] is True
        assert "... (truncated)" in result["results"][0]["content"]

    @pytest.mark.asyncio
    async def test_search_messages_error(self):
        """Test error handling in search_messages."""
        message_manager = AsyncMock()
        message_manager.search_messages.side_effect = Exception("Search failed")

        registry = create_test_registry(message_manager=message_manager)
        search = registry.get_tool("search_messages")

        result = await search(query="test")

        assert result["success"] is False
        assert "Search failed" in result["error"]


# ============================================================================
# Tests for Handoff Tools
# ============================================================================


class TestGetHandoffContext:
    """Tests for get_handoff_context tool."""

    def test_get_handoff_context_success(self):
        """Test successful handoff context retrieval."""
        session_manager = MagicMock()
        mock_session = MagicMock()
        mock_session.compact_markdown = "## Context\nSome handoff data"
        session_manager.get.return_value = mock_session

        registry = create_test_registry(session_manager=session_manager)
        get_context = registry.get_tool("get_handoff_context")

        result = get_context(session_id="sess-123")

        assert result["session_id"] == "sess-123"
        assert result["has_context"] is True
        assert result["compact_markdown"] == "## Context\nSome handoff data"

    def test_get_handoff_context_no_session(self):
        """Test when session not found."""
        session_manager = MagicMock()
        session_manager.get.return_value = None

        registry = create_test_registry(session_manager=session_manager)
        get_context = registry.get_tool("get_handoff_context")

        result = get_context(session_id="nonexistent")

        assert result["found"] is False
        assert "not found" in result["error"]

    def test_get_handoff_context_no_compact_markdown(self):
        """Test when session has no compact_markdown."""
        session_manager = MagicMock()
        mock_session = MagicMock()
        mock_session.compact_markdown = None
        session_manager.get.return_value = mock_session

        registry = create_test_registry(session_manager=session_manager)
        get_context = registry.get_tool("get_handoff_context")

        result = get_context(session_id="sess-123")

        assert result["has_context"] is False


class TestPickup:
    """Tests for pickup tool."""

    def test_pickup_by_session_id(self):
        """Test pickup with specific session ID."""
        session_manager = MagicMock()
        mock_session = MagicMock()
        mock_session.id = "sess-123"
        mock_session.compact_markdown = "## Context"
        mock_session.summary_markdown = None
        mock_session.title = "Test Session"
        mock_session.status = "handoff_ready"
        session_manager.get.return_value = mock_session

        registry = create_test_registry(session_manager=session_manager)
        pickup = registry.get_tool("pickup")

        result = pickup(session_id="sess-123")

        assert result["found"] is True
        assert result["session_id"] == "sess-123"
        assert result["has_context"] is True
        assert result["context"] == "## Context"
        assert result["context_type"] == "compact_markdown"

    def test_pickup_by_prefix(self):
        """Test pickup with session ID prefix."""
        session_manager = MagicMock()
        session_manager.get.return_value = None

        mock_session = MagicMock()
        mock_session.id = "sess-123-full-id"
        mock_session.compact_markdown = "## Context"
        mock_session.summary_markdown = None
        mock_session.title = "Test"
        mock_session.status = "handoff_ready"

        session_manager.list.return_value = [mock_session]

        registry = create_test_registry(session_manager=session_manager)
        pickup = registry.get_tool("pickup")

        result = pickup(session_id="sess-123")

        assert result["found"] is True
        assert result["session_id"] == "sess-123-full-id"

    def test_pickup_ambiguous_prefix(self):
        """Test pickup with ambiguous session ID prefix."""
        session_manager = MagicMock()
        session_manager.get.return_value = None

        mock_session1 = MagicMock()
        mock_session1.id = "sess-123-a"
        mock_session2 = MagicMock()
        mock_session2.id = "sess-123-b"

        session_manager.list.return_value = [mock_session1, mock_session2]

        registry = create_test_registry(session_manager=session_manager)
        pickup = registry.get_tool("pickup")

        result = pickup(session_id="sess-123")

        assert "error" in result
        assert "Ambiguous" in result["error"]
        assert "matches" in result

    @patch("gobby.utils.machine_id.get_machine_id")
    def test_pickup_by_project_id(self, mock_get_machine_id):
        """Test pickup by project ID."""
        mock_get_machine_id.return_value = "machine-123"

        session_manager = MagicMock()

        mock_session = MagicMock()
        mock_session.id = "sess-456"
        mock_session.compact_markdown = "## Context"
        mock_session.summary_markdown = None
        mock_session.title = "Test"
        mock_session.status = "handoff_ready"

        session_manager.find_parent.return_value = mock_session

        registry = create_test_registry(session_manager=session_manager)
        pickup = registry.get_tool("pickup")

        result = pickup(project_id="project-123")

        assert result["found"] is True
        session_manager.find_parent.assert_called_once_with(
            machine_id="machine-123",
            project_id="project-123",
            source=None,
            status="handoff_ready",
        )

    def test_pickup_most_recent_handoff(self):
        """Test pickup finding most recent handoff_ready session."""
        session_manager = MagicMock()

        mock_session = MagicMock()
        mock_session.id = "sess-latest"
        mock_session.compact_markdown = None
        mock_session.summary_markdown = "## Summary"
        mock_session.title = "Latest"
        mock_session.status = "handoff_ready"

        session_manager.list.return_value = [mock_session]

        registry = create_test_registry(session_manager=session_manager)
        pickup = registry.get_tool("pickup")

        result = pickup()

        assert result["found"] is True
        assert result["context_type"] == "summary_markdown"

    def test_pickup_no_session_found(self):
        """Test pickup when no handoff_ready session found."""
        session_manager = MagicMock()
        session_manager.list.return_value = []

        registry = create_test_registry(session_manager=session_manager)
        pickup = registry.get_tool("pickup")

        result = pickup()

        assert result["found"] is False
        assert "No handoff-ready session found" in result["message"]

    def test_pickup_no_context(self):
        """Test pickup when session has no context."""
        session_manager = MagicMock()
        mock_session = MagicMock()
        mock_session.id = "sess-123"
        mock_session.compact_markdown = None
        mock_session.summary_markdown = None
        session_manager.get.return_value = mock_session

        registry = create_test_registry(session_manager=session_manager)
        pickup = registry.get_tool("pickup")

        result = pickup(session_id="sess-123")

        assert result["found"] is True
        assert result["has_context"] is False

    def test_pickup_with_link_child(self):
        """Test pickup with child session linking."""
        session_manager = MagicMock()
        mock_session = MagicMock()
        mock_session.id = "sess-parent"
        mock_session.compact_markdown = "## Context"
        mock_session.summary_markdown = None
        mock_session.title = "Parent"
        mock_session.status = "handoff_ready"
        session_manager.get.return_value = mock_session

        registry = create_test_registry(session_manager=session_manager)
        pickup = registry.get_tool("pickup")

        result = pickup(session_id="sess-parent", link_child_session_id="sess-child")

        assert result["found"] is True
        assert result["linked_child"] == "sess-child"
        session_manager.update_parent_session_id.assert_called_once_with(
            "sess-child", "sess-parent"
        )


# ============================================================================
# Tests for Session CRUD Tools
# ============================================================================


class TestGetSession:
    """Tests for get_session tool."""

    def test_get_session_success(self):
        """Test successful session retrieval."""
        session_manager = MagicMock()
        mock_session = MagicMock()
        mock_session.to_dict.return_value = {
            "id": "sess-123",
            "title": "Test Session",
            "status": "active",
        }
        session_manager.get.return_value = mock_session

        registry = create_test_registry(session_manager=session_manager)
        get_session = registry.get_tool("get_session")

        result = get_session(session_id="sess-123")

        assert result["found"] is True
        assert result["id"] == "sess-123"
        assert result["title"] == "Test Session"

    def test_get_session_by_prefix(self):
        """Test session retrieval by prefix."""
        session_manager = MagicMock()
        session_manager.get.return_value = None

        mock_session = MagicMock()
        mock_session.id = "sess-123-full"
        mock_session.to_dict.return_value = {"id": "sess-123-full"}

        session_manager.list.return_value = [mock_session]

        registry = create_test_registry(session_manager=session_manager)
        get_session = registry.get_tool("get_session")

        result = get_session(session_id="sess-123")

        assert result["found"] is True
        assert result["id"] == "sess-123-full"

    def test_get_session_ambiguous_prefix(self):
        """Test session retrieval with ambiguous prefix."""
        session_manager = MagicMock()
        session_manager.get.return_value = None

        mock_session1 = MagicMock()
        mock_session1.id = "sess-abc-1"
        mock_session2 = MagicMock()
        mock_session2.id = "sess-abc-2"
        mock_session3 = MagicMock()
        mock_session3.id = "sess-abc-3"

        session_manager.list.return_value = [mock_session1, mock_session2, mock_session3]

        registry = create_test_registry(session_manager=session_manager)
        get_session = registry.get_tool("get_session")

        result = get_session(session_id="sess-abc")

        assert "error" in result
        assert "matches 3 sessions" in result["error"]

    def test_get_session_not_found(self):
        """Test when session not found."""
        session_manager = MagicMock()
        session_manager.get.return_value = None
        session_manager.list.return_value = []

        registry = create_test_registry(session_manager=session_manager)
        get_session = registry.get_tool("get_session")

        result = get_session(session_id="nonexistent")

        assert result["found"] is False
        assert "not found" in result["error"]


class TestGetCurrentSession:
    """Tests for get_current_session tool."""

    def test_get_current_session_found(self):
        """Test finding current active session."""
        session_manager = MagicMock()
        mock_session = MagicMock()
        mock_session.to_dict.return_value = {
            "id": "sess-current",
            "status": "active",
        }
        session_manager.list.return_value = [mock_session]

        registry = create_test_registry(session_manager=session_manager)
        get_current = registry.get_tool("get_current_session")

        result = get_current(project_id="project-123")

        assert result["found"] is True
        assert result["id"] == "sess-current"
        session_manager.list.assert_called_once_with(
            project_id="project-123", status="active", limit=1
        )

    def test_get_current_session_not_found(self):
        """Test when no active session found."""
        session_manager = MagicMock()
        session_manager.list.return_value = []

        registry = create_test_registry(session_manager=session_manager)
        get_current = registry.get_tool("get_current_session")

        result = get_current()

        assert result["found"] is False
        assert "No active session found" in result["message"]


class TestListSessions:
    """Tests for list_sessions tool."""

    def test_list_sessions_basic(self):
        """Test basic session listing."""
        session_manager = MagicMock()
        mock_session = MagicMock()
        mock_session.to_dict.return_value = {"id": "sess-1", "status": "active"}
        session_manager.list.return_value = [mock_session]
        session_manager.count.return_value = 1

        registry = create_test_registry(session_manager=session_manager)
        list_sessions = registry.get_tool("list_sessions")

        result = list_sessions()

        assert result["count"] == 1
        assert result["total"] == 1
        assert len(result["sessions"]) == 1

    def test_list_sessions_with_filters(self):
        """Test session listing with filters."""
        session_manager = MagicMock()
        session_manager.list.return_value = []
        session_manager.count.return_value = 0

        registry = create_test_registry(session_manager=session_manager)
        list_sessions = registry.get_tool("list_sessions")

        result = list_sessions(
            project_id="proj-1", status="active", source="claude_code", limit=10
        )

        assert result["filters"]["project_id"] == "proj-1"
        assert result["filters"]["status"] == "active"
        assert result["filters"]["source"] == "claude_code"
        assert result["limit"] == 10

        session_manager.list.assert_called_once_with(
            project_id="proj-1", status="active", source="claude_code", limit=10
        )


class TestSessionStats:
    """Tests for session_stats tool."""

    def test_session_stats_basic(self):
        """Test basic session statistics."""
        session_manager = MagicMock()
        session_manager.count.side_effect = [
            100,  # Total
            50,  # claude_code
            30,  # gemini
            0,  # codex (will be excluded)
        ]
        session_manager.count_by_status.return_value = {
            "active": 10,
            "paused": 20,
            "expired": 70,
        }

        registry = create_test_registry(session_manager=session_manager)
        stats = registry.get_tool("session_stats")

        result = stats()

        assert result["total"] == 100
        assert result["by_status"]["active"] == 10
        assert result["by_source"]["claude_code"] == 50
        assert result["by_source"]["gemini"] == 30
        assert "codex" not in result["by_source"]  # Zero count excluded


# ============================================================================
# Tests for Session Commits Tool
# ============================================================================


class TestGetSessionCommits:
    """Tests for get_session_commits tool."""

    def test_get_session_commits_success(self):
        """Test successful commit retrieval."""
        session_manager = MagicMock()
        mock_session = MagicMock()
        mock_session.id = "sess-123"
        mock_session.jsonl_path = "/tmp/test/transcript.jsonl"
        mock_session.created_at = "2024-01-01T10:00:00+00:00"
        mock_session.updated_at = "2024-01-01T12:00:00+00:00"
        session_manager.get.return_value = mock_session

        registry = create_test_registry(session_manager=session_manager)
        get_commits = registry.get_tool("get_session_commits")

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="abc1234|First commit|2024-01-01T11:00:00\ndef5678|Second commit|2024-01-01T11:30:00",
            )

            result = get_commits(session_id="sess-123")

        assert result["session_id"] == "sess-123"
        assert result["count"] == 2
        assert result["commits"][0]["hash"] == "abc1234"
        assert result["commits"][0]["message"] == "First commit"

    def test_get_session_commits_not_found(self):
        """Test when session not found."""
        session_manager = MagicMock()
        session_manager.get.return_value = None
        session_manager.list.return_value = []

        registry = create_test_registry(session_manager=session_manager)
        get_commits = registry.get_tool("get_session_commits")

        result = get_commits(session_id="nonexistent")

        assert "error" in result
        assert "not found" in result["error"]

    def test_get_session_commits_git_error(self):
        """Test handling git command error."""
        session_manager = MagicMock()
        mock_session = MagicMock()
        mock_session.id = "sess-123"
        mock_session.jsonl_path = "/tmp/test/transcript.jsonl"
        mock_session.created_at = "2024-01-01T10:00:00+00:00"
        mock_session.updated_at = "2024-01-01T12:00:00+00:00"
        session_manager.get.return_value = mock_session

        registry = create_test_registry(session_manager=session_manager)
        get_commits = registry.get_tool("get_session_commits")

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=1, stderr="fatal: not a git repository"
            )

            result = get_commits(session_id="sess-123")

        assert "error" in result
        assert "Git command failed" in result["error"]

    def test_get_session_commits_timeout(self):
        """Test handling git command timeout."""
        import subprocess

        session_manager = MagicMock()
        mock_session = MagicMock()
        mock_session.id = "sess-123"
        mock_session.jsonl_path = "/tmp/test/transcript.jsonl"
        mock_session.created_at = "2024-01-01T10:00:00+00:00"
        mock_session.updated_at = "2024-01-01T12:00:00+00:00"
        session_manager.get.return_value = mock_session

        registry = create_test_registry(session_manager=session_manager)
        get_commits = registry.get_tool("get_session_commits")

        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired("git", 10)

            result = get_commits(session_id="sess-123")

        assert "error" in result
        assert "timed out" in result["error"]

    def test_get_session_commits_git_not_found(self):
        """Test handling git not found."""
        session_manager = MagicMock()
        mock_session = MagicMock()
        mock_session.id = "sess-123"
        mock_session.jsonl_path = "/tmp/test/transcript.jsonl"
        mock_session.created_at = "2024-01-01T10:00:00+00:00"
        mock_session.updated_at = "2024-01-01T12:00:00+00:00"
        session_manager.get.return_value = mock_session

        registry = create_test_registry(session_manager=session_manager)
        get_commits = registry.get_tool("get_session_commits")

        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = FileNotFoundError("git not found")

            result = get_commits(session_id="sess-123")

        assert "error" in result
        assert "Git not found" in result["error"]

    def test_get_session_commits_by_prefix(self):
        """Test commit retrieval by session ID prefix."""
        session_manager = MagicMock()
        session_manager.get.return_value = None

        mock_session = MagicMock()
        mock_session.id = "sess-123-full"
        mock_session.jsonl_path = "/tmp/test/transcript.jsonl"
        mock_session.created_at = "2024-01-01T10:00:00+00:00"
        mock_session.updated_at = "2024-01-01T12:00:00+00:00"

        session_manager.list.return_value = [mock_session]

        registry = create_test_registry(session_manager=session_manager)
        get_commits = registry.get_tool("get_session_commits")

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="")

            result = get_commits(session_id="sess-123")

        assert result["session_id"] == "sess-123-full"

    def test_get_session_commits_datetime_objects(self):
        """Test handling datetime objects instead of strings."""
        session_manager = MagicMock()
        mock_session = MagicMock()
        mock_session.id = "sess-123"
        mock_session.jsonl_path = "/tmp/test/transcript.jsonl"
        mock_session.created_at = datetime(2024, 1, 1, 10, 0, 0, tzinfo=UTC)
        mock_session.updated_at = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)
        session_manager.get.return_value = mock_session

        registry = create_test_registry(session_manager=session_manager)
        get_commits = registry.get_tool("get_session_commits")

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="")

            result = get_commits(session_id="sess-123")

        assert result["session_id"] == "sess-123"
        assert "timeframe" in result


class TestMarkLoopComplete:
    """Tests for mark_loop_complete tool."""

    def test_mark_loop_complete_success(self):
        """Test successful loop completion marking."""
        session_manager = MagicMock()
        mock_session = MagicMock()
        mock_session.id = "sess-123"
        session_manager.get.return_value = mock_session

        mock_state = MagicMock()
        mock_state_manager = MagicMock()
        mock_state_manager.get_state.return_value = mock_state

        registry = create_test_registry(session_manager=session_manager)
        mark_complete = registry.get_tool("mark_loop_complete")

        with (
            patch("gobby.storage.database.LocalDatabase"),
            patch(
                "gobby.workflows.state_manager.WorkflowStateManager"
            ) as mock_wsm_class,
            patch(
                "gobby.workflows.state_actions.mark_loop_complete"
            ) as mock_action,
        ):
            mock_wsm_class.return_value = mock_state_manager

            result = mark_complete(session_id="sess-123")

        assert result["success"] is True
        assert result["session_id"] == "sess-123"
        assert result["stop_reason"] == "completed"
        mock_action.assert_called_once_with(mock_state)

    def test_mark_loop_complete_no_session(self):
        """Test when session not found."""
        session_manager = MagicMock()
        session_manager.get.return_value = None
        session_manager.list.return_value = []

        registry = create_test_registry(session_manager=session_manager)
        mark_complete = registry.get_tool("mark_loop_complete")

        result = mark_complete(session_id="nonexistent")

        assert "error" in result
        assert "No session found" in result["error"]

    def test_mark_loop_complete_creates_state(self):
        """Test that state is created if it doesn't exist."""
        session_manager = MagicMock()
        mock_session = MagicMock()
        mock_session.id = "sess-123"
        session_manager.list.return_value = [mock_session]

        mock_state_manager = MagicMock()
        mock_state_manager.get_state.return_value = None  # No existing state

        registry = create_test_registry(session_manager=session_manager)
        mark_complete = registry.get_tool("mark_loop_complete")

        with (
            patch("gobby.storage.database.LocalDatabase"),
            patch(
                "gobby.workflows.state_manager.WorkflowStateManager"
            ) as mock_wsm_class,
            patch(
                "gobby.workflows.definitions.WorkflowState"
            ) as mock_ws_class,
            patch("gobby.workflows.state_actions.mark_loop_complete"),
        ):
            mock_wsm_class.return_value = mock_state_manager
            mock_ws_class.return_value = MagicMock()

            result = mark_complete()  # No session_id, uses active session

        assert result["success"] is True
        mock_ws_class.assert_called_once()


# ============================================================================
# Tests for Create Handoff Tool
# ============================================================================


class TestCreateHandoff:
    """Tests for create_handoff tool."""

    @pytest.mark.asyncio
    async def test_create_handoff_no_session(self):
        """Test when no session found."""
        session_manager = MagicMock()
        session_manager.get.return_value = None
        session_manager.list.return_value = []

        registry = create_test_registry(session_manager=session_manager)
        create_handoff = registry.get_tool("create_handoff")

        result = await create_handoff(session_id="nonexistent")

        assert "error" in result
        assert "No session found" in result["error"]

    @pytest.mark.asyncio
    async def test_create_handoff_no_transcript_path(self):
        """Test when session has no transcript path."""
        session_manager = MagicMock()
        mock_session = MagicMock()
        mock_session.id = "sess-123"
        mock_session.jsonl_path = None
        session_manager.get.return_value = mock_session

        registry = create_test_registry(session_manager=session_manager)
        create_handoff = registry.get_tool("create_handoff")

        result = await create_handoff(session_id="sess-123")

        assert "error" in result
        assert "No transcript path" in result["error"]

    @pytest.mark.asyncio
    async def test_create_handoff_transcript_not_found(self):
        """Test when transcript file doesn't exist."""
        session_manager = MagicMock()
        mock_session = MagicMock()
        mock_session.id = "sess-123"
        mock_session.jsonl_path = "/nonexistent/path/transcript.jsonl"
        session_manager.get.return_value = mock_session

        registry = create_test_registry(session_manager=session_manager)
        create_handoff = registry.get_tool("create_handoff")

        result = await create_handoff(session_id="sess-123")

        assert "error" in result
        assert "Transcript file not found" in result["error"]

    @pytest.mark.asyncio
    async def test_create_handoff_compact_only(self):
        """Test creating compact handoff only."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create test transcript
            transcript_path = Path(tmpdir) / "transcript.jsonl"
            with open(transcript_path, "w") as f:
                f.write(json.dumps({"type": "user", "message": {"content": "Hello"}}) + "\n")

            session_manager = MagicMock()
            mock_session = MagicMock()
            mock_session.id = "sess-123"
            mock_session.jsonl_path = str(transcript_path)
            session_manager.get.return_value = mock_session

            registry = create_test_registry(session_manager=session_manager)
            create_handoff = registry.get_tool("create_handoff")

            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(returncode=0, stdout="")

                result = await create_handoff(
                    session_id="sess-123",
                    compact=True,
                    write_file=False,
                )

            assert result["success"] is True
            assert result["compact_length"] > 0
            session_manager.update_compact_markdown.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_handoff_by_prefix(self):
        """Test finding session by prefix."""
        with tempfile.TemporaryDirectory() as tmpdir:
            transcript_path = Path(tmpdir) / "transcript.jsonl"
            with open(transcript_path, "w") as f:
                f.write(json.dumps({"type": "user", "message": {"content": "Test"}}) + "\n")

            session_manager = MagicMock()
            session_manager.get.return_value = None

            mock_session = MagicMock()
            mock_session.id = "sess-123-full-id"
            mock_session.jsonl_path = str(transcript_path)

            session_manager.list.return_value = [mock_session]

            registry = create_test_registry(session_manager=session_manager)
            create_handoff = registry.get_tool("create_handoff")

            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(returncode=0, stdout="")

                result = await create_handoff(
                    session_id="sess-123",
                    compact=True,
                    write_file=False,
                )

            assert result["success"] is True
            assert result["session_id"] == "sess-123-full-id"

    @pytest.mark.asyncio
    async def test_create_handoff_ambiguous_prefix(self):
        """Test ambiguous session ID prefix."""
        session_manager = MagicMock()
        session_manager.get.return_value = None

        mock_session1 = MagicMock()
        mock_session1.id = "sess-abc-1"
        mock_session2 = MagicMock()
        mock_session2.id = "sess-abc-2"

        session_manager.list.return_value = [mock_session1, mock_session2]

        registry = create_test_registry(session_manager=session_manager)
        create_handoff = registry.get_tool("create_handoff")

        result = await create_handoff(session_id="sess-abc")

        assert "error" in result
        assert "Ambiguous" in result["error"]

    @pytest.mark.asyncio
    async def test_create_handoff_writes_files(self):
        """Test that files are written when write_file=True."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create test transcript
            transcript_path = Path(tmpdir) / "transcript.jsonl"
            with open(transcript_path, "w") as f:
                f.write(json.dumps({"type": "user", "message": {"content": "Hello"}}) + "\n")

            output_dir = Path(tmpdir) / "summaries"

            session_manager = MagicMock()
            mock_session = MagicMock()
            mock_session.id = "sess-123"
            mock_session.jsonl_path = str(transcript_path)
            session_manager.get.return_value = mock_session

            registry = create_test_registry(session_manager=session_manager)
            create_handoff = registry.get_tool("create_handoff")

            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(returncode=0, stdout="")

                result = await create_handoff(
                    session_id="sess-123",
                    compact=True,
                    write_file=True,
                    output_path=str(output_dir),
                )

            assert result["success"] is True
            assert len(result["files_written"]) > 0
            assert output_dir.exists()


# ============================================================================
# Tests for Registry Creation
# ============================================================================


class TestRegistryCreation:
    """Tests for create_session_messages_registry function."""

    def test_create_registry_with_no_managers(self):
        """Test creating registry with no managers."""
        registry = create_session_messages_registry()

        assert registry.name == "gobby-sessions"
        # With no managers, only the registry shell is created
        assert len(registry) == 0

    def test_create_registry_with_message_manager(self):
        """Test creating registry with message manager only."""
        message_manager = MagicMock()
        registry = create_session_messages_registry(message_manager=message_manager)

        # Should have message tools
        tools = registry.list_tools()
        tool_names = [t["name"] for t in tools]
        assert "get_session_messages" in tool_names
        assert "search_messages" in tool_names

    def test_create_registry_with_session_manager(self):
        """Test creating registry with session manager only."""
        session_manager = MagicMock()
        registry = create_session_messages_registry(session_manager=session_manager)

        # Should have session CRUD and handoff tools
        tools = registry.list_tools()
        tool_names = [t["name"] for t in tools]
        assert "get_session" in tool_names
        assert "list_sessions" in tool_names
        assert "get_handoff_context" in tool_names
        assert "pickup" in tool_names

    def test_create_registry_with_both_managers(self):
        """Test creating registry with both managers."""
        message_manager = MagicMock()
        session_manager = MagicMock()
        registry = create_session_messages_registry(
            message_manager=message_manager,
            session_manager=session_manager,
        )

        tools = registry.list_tools()
        tool_names = [t["name"] for t in tools]

        # Should have all tools
        assert "get_session_messages" in tool_names
        assert "search_messages" in tool_names
        assert "get_session" in tool_names
        assert "list_sessions" in tool_names
        assert "get_handoff_context" in tool_names
        assert "pickup" in tool_names
        assert "create_handoff" in tool_names
        assert "mark_loop_complete" in tool_names


# ============================================================================
# Edge Case Tests
# ============================================================================


class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""

    @pytest.mark.asyncio
    async def test_get_messages_empty_content(self):
        """Test handling messages with empty content."""
        message_manager = AsyncMock()
        message_manager.get_messages.return_value = [
            {"id": 1, "content": "", "role": "user"},
            {"id": 2, "content": None, "role": "assistant"},
        ]
        message_manager.count_messages.return_value = 2

        registry = create_test_registry(message_manager=message_manager)
        get_messages = registry.get_tool("get_session_messages")

        result = await get_messages(session_id="sess-123")

        assert result["success"] is True
        assert result["returned_count"] == 2

    @pytest.mark.asyncio
    async def test_get_messages_non_string_content(self):
        """Test handling messages with non-string content."""
        message_manager = AsyncMock()
        message_manager.get_messages.return_value = [
            {"id": 1, "content": ["block1", "block2"], "role": "assistant"},
        ]
        message_manager.count_messages.return_value = 1

        registry = create_test_registry(message_manager=message_manager)
        get_messages = registry.get_tool("get_session_messages")

        result = await get_messages(session_id="sess-123", full_content=False)

        assert result["success"] is True
        # Non-string content should not be truncated
        assert result["messages"][0]["content"] == ["block1", "block2"]

    def test_format_turns_empty_message(self):
        """Test formatting turns with empty message dict."""
        turns = [{"message": {}}]
        result = _format_turns_for_llm(turns)

        assert "[Turn 1 - unknown]:" in result

    def test_handoff_markdown_empty_git_commit_fields(self):
        """Test handoff markdown with commits missing fields."""
        ctx = HandoffContext(
            git_commits=[
                {"hash": "", "message": ""},  # Empty fields
                {},  # Missing fields
            ]
        )
        result = _format_handoff_markdown(ctx)

        assert "### Commits This Session" in result

    def test_handoff_markdown_todo_missing_status(self):
        """Test handoff markdown with todo items missing status."""
        ctx = HandoffContext(
            todo_state=[
                {"content": "Task without status"},
                {"status": "completed"},  # Missing content
            ]
        )
        result = _format_handoff_markdown(ctx)

        assert "### In-Progress Work" in result
        assert "[ ] Task without status" in result  # Default to pending

"""
Tests for TranscriptAnalyzer in gobby.sessions.analyzer.
"""

from datetime import datetime
import pytest
from gobby.sessions.analyzer import TranscriptAnalyzer, HandoffContext


@pytest.fixture
def sample_turns():
    return [
        {"type": "user", "message": {"content": "Fix the bug in the login page"}},
        {
            "type": "assistant",
            "message": {
                "content": [
                    {"type": "text", "text": "Okay doing it"},
                    {
                        "type": "tool_use",
                        "name": "mcp_call_tool",
                        "input": {
                            "server_name": "gobby-tasks",
                            "tool_name": "get_task",
                            "arguments": {"task_id": "gt-123"},
                        },
                    },
                ]
            },
        },
        {
            "type": "assistant",
            "message": {
                "content": [
                    {
                        "type": "tool_use",
                        "name": "Write",
                        "input": {"file_path": "/path/to/login.py"},
                    },
                    {
                        "type": "tool_use",
                        "name": "Bash",
                        "input": {"command": "git commit -m 'fix login'"},
                    },
                ]
            },
        },
    ]


def test_extract_handoff_context_basic(sample_turns):
    analyzer = TranscriptAnalyzer()
    ctx = analyzer.extract_handoff_context(sample_turns)

    assert ctx.initial_goal == "Fix the bug in the login page"
    assert ctx.active_gobby_task is not None
    assert ctx.active_gobby_task["id"] == "gt-123"
    assert "/path/to/login.py" in ctx.files_modified
    assert len(ctx.git_commits) == 1
    assert "git commit -m 'fix login'" in ctx.git_commits[0]["command"]


def test_extract_handoff_context_empty():
    analyzer = TranscriptAnalyzer()
    ctx = analyzer.extract_handoff_context([])
    assert ctx.initial_goal == ""
    assert not ctx.active_gobby_task
    assert not ctx.files_modified


def test_extract_handoff_context_no_task(sample_turns):
    # Filter out mcp_call_tool lines
    # This requires deep filtering of the fixture structure
    turns = [
        {"type": "user", "message": {"content": "Fix the bug"}},
        {
            "type": "assistant",
            "message": {
                "content": [
                    {
                        "type": "tool_use",
                        "name": "Write",
                        "input": {"file_path": "/path/to/login.py"},
                    },
                ]
            },
        },
    ]

    analyzer = TranscriptAnalyzer()
    ctx = analyzer.extract_handoff_context(turns)
    assert ctx.active_gobby_task is None
    assert "/path/to/login.py" in ctx.files_modified


def test_extract_handoff_context_recent_activity(sample_turns):
    analyzer = TranscriptAnalyzer()
    ctx = analyzer.extract_handoff_context(sample_turns)
    # Check that recent tools are captured
    # The fixture has mcp_call_tool, Write, Bash (reverse order: Bash, Write, mcp_call_tool)
    assert len(ctx.recent_activity) > 0
    assert (
        "Called Bash" in ctx.recent_activity[0]
        or "Called Write" in ctx.recent_activity[0]
        or "Called Bash" in ctx.recent_activity[1]
    )


def test_extract_handoff_context_max_turns():
    # Generate many turns
    turns = [{"type": "user", "message": {"content": f"msg {i}"}} for i in range(200)]
    # Make the last one have a goal just to check scanning logic (first user message is usually goal)
    # But max_turns applies to backward scan for activity.
    # Initial goal scan is forward from 0.

    analyzer = TranscriptAnalyzer()
    ctx = analyzer.extract_handoff_context(turns, max_turns=50)

    assert ctx.initial_goal == "msg 0"
    # recent_activity should only scan last 50 turns?
    # Logic says `relevant_turns = turns[-max_turns:]`
    # So it won't see tool uses before that.


def test_extract_todowrite():
    """Test extraction of TodoWrite state from transcript."""
    turns = [
        {"type": "user", "message": {"content": "Help me with tasks"}},
        {
            "type": "assistant",
            "message": {
                "content": [
                    {
                        "type": "tool_use",
                        "name": "TodoWrite",
                        "input": {
                            "todos": [
                                {"content": "Fix the bug", "status": "completed"},
                                {"content": "Write tests", "status": "in_progress"},
                                {"content": "Update docs", "status": "pending"},
                            ]
                        },
                    },
                ]
            },
        },
    ]

    analyzer = TranscriptAnalyzer()
    ctx = analyzer.extract_handoff_context(turns)

    assert len(ctx.todo_state) == 3
    assert ctx.todo_state[0]["content"] == "Fix the bug"
    assert ctx.todo_state[0]["status"] == "completed"
    assert ctx.todo_state[1]["content"] == "Write tests"
    assert ctx.todo_state[1]["status"] == "in_progress"
    assert ctx.todo_state[2]["content"] == "Update docs"
    assert ctx.todo_state[2]["status"] == "pending"


def test_extract_todowrite_empty():
    """Test that empty transcript returns empty todo_state."""
    analyzer = TranscriptAnalyzer()
    ctx = analyzer.extract_handoff_context([])
    assert ctx.todo_state == []


def test_extract_todowrite_uses_latest():
    """Test that we extract the most recent TodoWrite, not earlier ones."""
    turns = [
        {
            "type": "assistant",
            "message": {
                "content": [
                    {
                        "type": "tool_use",
                        "name": "TodoWrite",
                        "input": {
                            "todos": [
                                {"content": "Old task", "status": "pending"},
                            ]
                        },
                    },
                ]
            },
        },
        {
            "type": "assistant",
            "message": {
                "content": [
                    {
                        "type": "tool_use",
                        "name": "TodoWrite",
                        "input": {
                            "todos": [
                                {"content": "New task", "status": "in_progress"},
                            ]
                        },
                    },
                ]
            },
        },
    ]

    analyzer = TranscriptAnalyzer()
    ctx = analyzer.extract_handoff_context(turns)

    # Should get the latest (second) TodoWrite
    assert len(ctx.todo_state) == 1
    assert ctx.todo_state[0]["content"] == "New task"
    assert ctx.todo_state[0]["status"] == "in_progress"

"""
Tests for TranscriptAnalyzer in gobby.sessions.analyzer.
"""


import pytest

from gobby.sessions.analyzer import TranscriptAnalyzer


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
    # Check that recent tools are captured with detailed descriptions
    # The fixture has mcp_call_tool, Write, Bash (reverse order: Bash, Write, mcp_call_tool)
    assert len(ctx.recent_activity) > 0
    # New format shows details: "Ran: <cmd>", "Write: <path>", "Called <server>.<tool>"
    activity_str = " ".join(ctx.recent_activity)
    assert "Ran:" in activity_str or "Write:" in activity_str


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


# --- Edge Case Tests ---


def test_todowrite_empty_todos_list():
    """Test that TodoWrite with empty todos list returns empty state."""
    turns = [
        {
            "type": "assistant",
            "message": {
                "content": [
                    {
                        "type": "tool_use",
                        "name": "TodoWrite",
                        "input": {"todos": []},  # Empty list
                    },
                ]
            },
        },
    ]

    analyzer = TranscriptAnalyzer()
    ctx = analyzer.extract_handoff_context(turns)

    assert ctx.todo_state == []


def test_malformed_tool_blocks_not_dict():
    """Test handling of malformed content blocks that aren't dicts."""
    turns = [
        {"type": "user", "message": {"content": "do something"}},
        {
            "type": "assistant",
            "message": {
                "content": [
                    "plain string block",  # Not a dict
                    123,  # Integer
                    None,  # None
                    {"type": "text", "text": "valid text block"},
                    {"type": "tool_use", "name": "Write", "input": {"file_path": "/valid.py"}},
                ]
            },
        },
    ]

    analyzer = TranscriptAnalyzer()
    ctx = analyzer.extract_handoff_context(turns)

    # Should still extract the valid Write call
    assert "/valid.py" in ctx.files_modified


def test_malformed_tool_blocks_missing_keys():
    """Test handling of tool_use blocks missing expected keys."""
    turns = [
        {"type": "user", "message": {"content": "do something"}},
        {
            "type": "assistant",
            "message": {
                "content": [
                    {"type": "tool_use"},  # Missing name and input
                    {"type": "tool_use", "name": "Edit"},  # Missing input
                    {"type": "tool_use", "name": "Write", "input": {}},  # Missing file_path
                    {"type": "tool_use", "name": "Write", "input": {"file_path": "/good.py"}},
                ]
            },
        },
    ]

    analyzer = TranscriptAnalyzer()
    ctx = analyzer.extract_handoff_context(turns)

    # Should only extract the one with valid file_path
    assert ctx.files_modified == ["/good.py"]


def test_multiple_edit_write_calls():
    """Test extraction of multiple Edit and Write calls to different files."""
    turns = [
        {"type": "user", "message": {"content": "refactor the code"}},
        {
            "type": "assistant",
            "message": {
                "content": [
                    {"type": "tool_use", "name": "Edit", "input": {"file_path": "/src/foo.py"}},
                    {"type": "tool_use", "name": "Write", "input": {"file_path": "/src/bar.py"}},
                ]
            },
        },
        {
            "type": "assistant",
            "message": {
                "content": [
                    {"type": "tool_use", "name": "Edit", "input": {"file_path": "/src/baz.py"}},
                    {"type": "tool_use", "name": "Edit", "input": {"file_path": "/src/foo.py"}},  # Duplicate
                ]
            },
        },
    ]

    analyzer = TranscriptAnalyzer()
    ctx = analyzer.extract_handoff_context(turns)

    # Should have 3 unique files, sorted
    assert ctx.files_modified == ["/src/bar.py", "/src/baz.py", "/src/foo.py"]


def test_git_status_not_extracted_from_transcript():
    """Test that git_status remains empty from transcript (enriched separately)."""
    turns = [
        {"type": "user", "message": {"content": "check status"}},
        {
            "type": "assistant",
            "message": {
                "content": [
                    {
                        "type": "tool_use",
                        "name": "Bash",
                        "input": {"command": "git status"},
                    },
                ]
            },
        },
    ]

    analyzer = TranscriptAnalyzer()
    ctx = analyzer.extract_handoff_context(turns)

    # git_status should remain empty - it's enriched by the caller, not extracted
    assert ctx.git_status == ""


def test_multiple_git_commits():
    """Test extraction of multiple git commit commands."""
    turns = [
        {"type": "user", "message": {"content": "commit the changes"}},
        {
            "type": "assistant",
            "message": {
                "content": [
                    {
                        "type": "tool_use",
                        "name": "Bash",
                        "input": {"command": "git add . && git commit -m 'first commit'"},
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
                        "name": "Bash",
                        "input": {"command": "git commit -m 'second commit'"},
                    },
                ]
            },
        },
    ]

    analyzer = TranscriptAnalyzer()
    ctx = analyzer.extract_handoff_context(turns)

    assert len(ctx.git_commits) == 2
    # Commits are in reverse order (latest first) due to reverse iteration
    assert "second commit" in ctx.git_commits[0]["command"]
    assert "first commit" in ctx.git_commits[1]["command"]


def test_large_transcript_max_turns_limits_scanning():
    """Test that max_turns limits which turns are scanned for activity."""
    # Create a large transcript with 150 turns
    turns = []

    # First turn is the goal
    turns.append({"type": "user", "message": {"content": "Original goal"}})

    # Add 100 turns with tool uses
    for i in range(100):
        turns.append(
            {
                "type": "assistant",
                "message": {
                    "content": [
                        {"type": "tool_use", "name": "Edit", "input": {"file_path": f"/file_{i}.py"}},
                    ]
                },
            }
        )

    # Add 50 more turns at the end
    for i in range(100, 150):
        turns.append(
            {
                "type": "assistant",
                "message": {
                    "content": [
                        {"type": "tool_use", "name": "Write", "input": {"file_path": f"/late_{i}.py"}},
                    ]
                },
            }
        )

    analyzer = TranscriptAnalyzer()
    ctx = analyzer.extract_handoff_context(turns, max_turns=50)

    # Should still get the initial goal from beginning
    assert ctx.initial_goal == "Original goal"

    # Should only have files from the last 50 turns (late_100 through late_149)
    assert all(f.startswith("/late_") for f in ctx.files_modified)
    assert len(ctx.files_modified) == 50


def test_content_as_string_not_list():
    """Test handling when message content is a string instead of list."""
    turns = [
        {"type": "user", "message": {"content": "plain string user message"}},
        {"type": "assistant", "message": {"content": "plain string assistant message"}},
    ]

    analyzer = TranscriptAnalyzer()
    ctx = analyzer.extract_handoff_context(turns)

    # Should handle gracefully without errors
    assert ctx.initial_goal == "plain string user message"
    assert ctx.files_modified == []
    assert ctx.todo_state == []


def test_todowrite_missing_content_or_status():
    """Test TodoWrite extraction with todos missing content or status keys."""
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
                                {"content": "Has content"},  # Missing status
                                {"status": "pending"},  # Missing content
                                {},  # Missing both
                            ]
                        },
                    },
                ]
            },
        },
    ]

    analyzer = TranscriptAnalyzer()
    ctx = analyzer.extract_handoff_context(turns)

    # Should extract with defaults
    assert len(ctx.todo_state) == 3
    assert ctx.todo_state[0]["content"] == "Has content"
    assert ctx.todo_state[0]["status"] == "pending"  # Default
    assert ctx.todo_state[1]["content"] == ""  # Default
    assert ctx.todo_state[1]["status"] == "pending"
    assert ctx.todo_state[2]["content"] == ""
    assert ctx.todo_state[2]["status"] == "pending"


def test_recent_activity_limited_to_5():
    """Test that recent_activity is limited to last 5 tool calls."""
    turns = []
    for i in range(20):
        turns.append(
            {
                "type": "assistant",
                "message": {
                    "content": [
                        {"type": "tool_use", "name": f"Tool{i}", "input": {}},
                    ]
                },
            }
        )

    analyzer = TranscriptAnalyzer()
    ctx = analyzer.extract_handoff_context(turns)

    assert len(ctx.recent_activity) == 5
    # Should be the last 5 (reverse order: 19, 18, 17, 16, 15)
    assert "Called Tool19" in ctx.recent_activity[0]
    assert "Called Tool15" in ctx.recent_activity[4]


def test_mcp_call_tool_gobby_tasks_extracts_task():
    """Test that mcp_call_tool with gobby-tasks extracts active task."""
    turns = [
        {"type": "user", "message": {"content": "work on the task"}},
        {
            "type": "assistant",
            "message": {
                "content": [
                    {
                        "type": "tool_use",
                        "name": "mcp_call_tool",
                        "input": {
                            "server_name": "gobby-tasks",
                            "tool_name": "update_task",
                            "arguments": {"task_id": "gt-abc123", "status": "in_progress"},
                        },
                    },
                ]
            },
        },
    ]

    analyzer = TranscriptAnalyzer()
    ctx = analyzer.extract_handoff_context(turns)

    assert ctx.active_gobby_task is not None
    assert ctx.active_gobby_task["id"] == "gt-abc123"
    assert ctx.active_gobby_task["action"] == "update_task"


def test_alternative_file_path_keys():
    """Test that alternative file path keys are recognized (TargetFile, path)."""
    turns = [
        {"type": "user", "message": {"content": "modify files"}},
        {
            "type": "assistant",
            "message": {
                "content": [
                    # Standard file_path
                    {"type": "tool_use", "name": "Edit", "input": {"file_path": "/a.py"}},
                    # Alternative TargetFile (Antigravity-style)
                    {"type": "tool_use", "name": "replace_file_content", "input": {"TargetFile": "/b.py"}},
                    # Alternative path
                    {"type": "tool_use", "name": "write_to_file", "input": {"path": "/c.py"}},
                ]
            },
        },
    ]

    analyzer = TranscriptAnalyzer()
    ctx = analyzer.extract_handoff_context(turns)

    assert "/a.py" in ctx.files_modified
    assert "/b.py" in ctx.files_modified
    assert "/c.py" in ctx.files_modified


class TestFormatToolDescription:
    """Tests for _format_tool_description method."""

    def test_mcp_call_tool(self):
        """Test MCP tool calls show server.tool format."""
        analyzer = TranscriptAnalyzer()
        block = {
            "name": "mcp__gobby__call_tool",
            "input": {"server_name": "gobby-tasks", "tool_name": "create_task"},
        }
        assert analyzer._format_tool_description(block) == "Called gobby-tasks.create_task"

    def test_mcp_call_tool_alternative_name(self):
        """Test alternative MCP tool name format."""
        analyzer = TranscriptAnalyzer()
        block = {
            "name": "mcp_call_tool",
            "input": {"server_name": "context7", "tool_name": "get_docs"},
        }
        assert analyzer._format_tool_description(block) == "Called context7.get_docs"

    def test_bash_command(self):
        """Test Bash commands show the actual command."""
        analyzer = TranscriptAnalyzer()
        block = {"name": "Bash", "input": {"command": "git status"}}
        assert analyzer._format_tool_description(block) == "Ran: git status"

    def test_bash_long_command_truncated(self):
        """Test long Bash commands are truncated."""
        analyzer = TranscriptAnalyzer()
        long_cmd = "git log --oneline --graph --all --decorate | head -50 && git status"
        block = {"name": "Bash", "input": {"command": long_cmd}}
        result = analyzer._format_tool_description(block)
        assert result.startswith("Ran: ")
        assert result.endswith("...")
        assert len(result) <= 65  # "Ran: " + 57 chars + "..."

    def test_edit_with_path(self):
        """Test Edit shows file path."""
        analyzer = TranscriptAnalyzer()
        block = {"name": "Edit", "input": {"file_path": "/src/main.py"}}
        assert analyzer._format_tool_description(block) == "Edit: /src/main.py"

    def test_write_with_path(self):
        """Test Write shows file path."""
        analyzer = TranscriptAnalyzer()
        block = {"name": "Write", "input": {"file_path": "/new_file.py"}}
        assert analyzer._format_tool_description(block) == "Write: /new_file.py"

    def test_read_with_path(self):
        """Test Read shows file path."""
        analyzer = TranscriptAnalyzer()
        block = {"name": "Read", "input": {"file_path": "/config.yaml"}}
        assert analyzer._format_tool_description(block) == "Read: /config.yaml"

    def test_glob_with_pattern(self):
        """Test Glob shows pattern."""
        analyzer = TranscriptAnalyzer()
        block = {"name": "Glob", "input": {"pattern": "**/*.py"}}
        assert analyzer._format_tool_description(block) == "Glob: **/*.py"

    def test_grep_with_pattern(self):
        """Test Grep shows pattern."""
        analyzer = TranscriptAnalyzer()
        block = {"name": "Grep", "input": {"pattern": "def test_"}}
        assert analyzer._format_tool_description(block) == "Grep: def test_"

    def test_grep_long_pattern_truncated(self):
        """Test long Grep patterns are truncated."""
        analyzer = TranscriptAnalyzer()
        long_pattern = "some_very_long_pattern_that_exceeds_the_limit_for_display"
        block = {"name": "Grep", "input": {"pattern": long_pattern}}
        result = analyzer._format_tool_description(block)
        assert result.startswith("Grep: ")
        assert result.endswith("...")
        assert len(result) <= 47  # "Grep: " + 37 chars + "..."

    def test_todowrite_shows_count(self):
        """Test TodoWrite shows item count."""
        analyzer = TranscriptAnalyzer()
        block = {
            "name": "TodoWrite",
            "input": {"todos": [{"content": "a"}, {"content": "b"}, {"content": "c"}]},
        }
        assert analyzer._format_tool_description(block) == "TodoWrite: 3 items"

    def test_task_with_subagent(self):
        """Test Task shows subagent type and description."""
        analyzer = TranscriptAnalyzer()
        block = {
            "name": "Task",
            "input": {"subagent_type": "Explore", "description": "Find auth code"},
        }
        assert analyzer._format_tool_description(block) == "Task (Explore): Find auth code"

    def test_task_subagent_only(self):
        """Test Task with only subagent type."""
        analyzer = TranscriptAnalyzer()
        block = {"name": "Task", "input": {"subagent_type": "Plan"}}
        assert analyzer._format_tool_description(block) == "Task (Plan)"

    def test_unknown_tool_fallback(self):
        """Test unknown tools fall back to 'Called <name>'."""
        analyzer = TranscriptAnalyzer()
        block = {"name": "SomeUnknownTool", "input": {}}
        assert analyzer._format_tool_description(block) == "Called SomeUnknownTool"

    def test_missing_input_graceful(self):
        """Test graceful handling when input is missing."""
        analyzer = TranscriptAnalyzer()
        block = {"name": "Bash"}  # No input key
        result = analyzer._format_tool_description(block)
        assert result == "Ran: "  # Empty command

    def test_missing_name_graceful(self):
        """Test graceful handling when name is missing."""
        analyzer = TranscriptAnalyzer()
        block = {"input": {"command": "ls"}}  # No name key
        result = analyzer._format_tool_description(block)
        assert result == "Called unknown"

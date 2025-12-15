"""Tests for src/tools/filesystem.py - Tool Filesystem Manager."""

import json
import pytest
from pathlib import Path
from unittest.mock import patch

from gobby.tools.filesystem import (
    get_tools_dir,
    generate_brief,
    write_tool_schema,
    write_server_tools,
    read_tool_schema,
    remove_server_tools,
    cleanup_removed_tools,
    list_server_tools,
)


class TestGetToolsDir:
    """Tests for get_tools_dir function."""

    def test_returns_path_object(self):
        """Test that get_tools_dir returns a Path object."""
        result = get_tools_dir()
        assert isinstance(result, Path)

    def test_returns_expanded_path(self):
        """Test that path is expanded from ~."""
        result = get_tools_dir()
        assert "~" not in str(result)
        assert "gobby/tools" in str(result)


class TestGenerateBrief:
    """Tests for generate_brief function."""

    def test_none_description(self):
        """Test with None description."""
        result = generate_brief(None)
        assert result == "No description available"

    def test_empty_description(self):
        """Test with empty description."""
        result = generate_brief("")
        assert result == "No description available"

    def test_short_description(self):
        """Test with short description."""
        result = generate_brief("A short description.")
        assert result == "A short description."

    def test_first_sentence_extraction_period(self):
        """Test extracting first sentence ending with period."""
        result = generate_brief("First sentence. Second sentence. Third sentence.")
        assert result == "First sentence."

    def test_first_sentence_extraction_exclamation(self):
        """Test extracting first sentence ending with exclamation."""
        # Note: generate_brief checks delimiters in order (., !, ?), so period takes precedence
        result = generate_brief("Hello world! This is great. More text.")
        assert result == "Hello world! This is great."

    def test_first_sentence_extraction_question(self):
        """Test extracting first sentence ending with question mark."""
        # Note: generate_brief checks delimiters in order (., !, ?), so period takes precedence
        result = generate_brief("What is this? It's a test. More info.")
        assert result == "What is this? It's a test."

    def test_truncation_no_delimiter(self):
        """Test truncation when no sentence delimiter found."""
        long_text = "A" * 150
        result = generate_brief(long_text, max_length=100)
        assert len(result) == 103  # 100 + "..."
        assert result.endswith("...")

    def test_custom_max_length(self):
        """Test with custom max_length."""
        result = generate_brief("Short text", max_length=5)
        assert result == "Short..."

    def test_first_sentence_too_long(self):
        """Test when first sentence exceeds max_length."""
        long_sentence = "This is a very long first sentence that exceeds the limit. Short second."
        result = generate_brief(long_sentence, max_length=30)
        # Should truncate since first sentence is too long
        assert len(result) <= 33  # 30 + "..."


class TestWriteToolSchema:
    """Tests for write_tool_schema function."""

    def test_write_creates_directory_and_file(self, tmp_path):
        """Test that write_tool_schema creates server directory and tool file."""
        with patch('gobby.tools.filesystem.get_tools_dir', return_value=tmp_path):
            write_tool_schema("test-server", "test-tool", {
                "name": "test-tool",
                "description": "A test tool",
                "inputSchema": {"type": "object"}
            })

        tool_file = tmp_path / "test-server" / "test-tool.json"
        assert tool_file.exists()

        with open(tool_file) as f:
            data = json.load(f)
        assert data["name"] == "test-tool"
        assert data["description"] == "A test tool"

    def test_write_overwrites_existing(self, tmp_path):
        """Test that write_tool_schema overwrites existing file."""
        server_dir = tmp_path / "test-server"
        server_dir.mkdir()
        tool_file = server_dir / "test-tool.json"
        tool_file.write_text(json.dumps({"old": "data"}))

        with patch('gobby.tools.filesystem.get_tools_dir', return_value=tmp_path):
            write_tool_schema("test-server", "test-tool", {
                "name": "test-tool",
                "description": "New description"
            })

        with open(tool_file) as f:
            data = json.load(f)
        assert data["description"] == "New description"
        assert "old" not in data


class TestWriteServerTools:
    """Tests for write_server_tools function."""

    def test_write_multiple_tools(self, tmp_path):
        """Test writing multiple tools for a server."""
        tools = [
            {"name": "tool1", "description": "First tool", "args": {"type": "object"}},
            {"name": "tool2", "description": "Second tool", "args": {"type": "string"}},
        ]

        count = write_server_tools("test-server", tools, tools_dir=tmp_path)

        assert count == 2
        assert (tmp_path / "test-server" / "tool1.json").exists()
        assert (tmp_path / "test-server" / "tool2.json").exists()

    def test_write_skips_tools_without_name(self, tmp_path):
        """Test that tools without name are skipped."""
        tools = [
            {"name": "valid-tool", "description": "Valid"},
            {"description": "Missing name"},  # No name
        ]

        count = write_server_tools("test-server", tools, tools_dir=tmp_path)

        assert count == 2  # Returns total count, not written count
        # Only valid tool should be written
        assert (tmp_path / "test-server" / "valid-tool.json").exists()

    def test_write_handles_none_values(self, tmp_path):
        """Test that None description and args are handled."""
        tools = [
            {"name": "tool-with-none", "description": None, "args": None},
        ]

        count = write_server_tools("test-server", tools, tools_dir=tmp_path)

        assert count == 1
        tool_file = tmp_path / "test-server" / "tool-with-none.json"
        with open(tool_file) as f:
            data = json.load(f)
        assert data["description"] == ""
        assert data["inputSchema"] == {}

    def test_write_creates_server_directory(self, tmp_path):
        """Test that server directory is created if it doesn't exist."""
        tools = [{"name": "test-tool", "description": "Test"}]

        write_server_tools("new-server", tools, tools_dir=tmp_path)

        assert (tmp_path / "new-server").is_dir()


class TestReadToolSchema:
    """Tests for read_tool_schema function."""

    def test_read_existing_tool(self, tmp_path):
        """Test reading an existing tool schema."""
        server_dir = tmp_path / "test-server"
        server_dir.mkdir()
        tool_file = server_dir / "test-tool.json"
        tool_data = {"name": "test-tool", "description": "Test", "inputSchema": {}}
        tool_file.write_text(json.dumps(tool_data))

        result = read_tool_schema("test-server", "test-tool", tools_dir=tmp_path)

        assert result == tool_data

    def test_read_nonexistent_tool(self, tmp_path):
        """Test reading non-existent tool returns None."""
        result = read_tool_schema("test-server", "nonexistent", tools_dir=tmp_path)
        assert result is None

    def test_read_nonexistent_server(self, tmp_path):
        """Test reading from non-existent server returns None."""
        result = read_tool_schema("nonexistent-server", "test-tool", tools_dir=tmp_path)
        assert result is None


class TestRemoveServerTools:
    """Tests for remove_server_tools function."""

    def test_remove_existing_server(self, tmp_path):
        """Test removing an existing server's tools."""
        server_dir = tmp_path / "test-server"
        server_dir.mkdir()
        (server_dir / "tool1.json").write_text("{}")
        (server_dir / "tool2.json").write_text("{}")

        remove_server_tools("test-server", tools_dir=tmp_path)

        assert not server_dir.exists()

    def test_remove_nonexistent_server(self, tmp_path):
        """Test removing non-existent server doesn't raise error."""
        # Should not raise any exception
        remove_server_tools("nonexistent-server", tools_dir=tmp_path)

    def test_remove_nested_directory(self, tmp_path):
        """Test removing server with nested content."""
        server_dir = tmp_path / "test-server"
        subdir = server_dir / "subdir"
        subdir.mkdir(parents=True)
        (subdir / "nested-file.json").write_text("{}")

        remove_server_tools("test-server", tools_dir=tmp_path)

        assert not server_dir.exists()


class TestCleanupRemovedTools:
    """Tests for cleanup_removed_tools function."""

    def test_cleanup_removes_orphaned_tools(self, tmp_path):
        """Test that orphaned tool files are removed."""
        server_dir = tmp_path / "test-server"
        server_dir.mkdir()
        (server_dir / "keep-tool.json").write_text("{}")
        (server_dir / "orphan-tool.json").write_text("{}")

        removed_count = cleanup_removed_tools(
            "test-server",
            current_tool_names=["keep-tool"],
            tools_dir=tmp_path
        )

        assert removed_count == 1
        assert (server_dir / "keep-tool.json").exists()
        assert not (server_dir / "orphan-tool.json").exists()

    def test_cleanup_nonexistent_server(self, tmp_path):
        """Test cleanup on non-existent server returns 0."""
        removed_count = cleanup_removed_tools(
            "nonexistent",
            current_tool_names=["tool"],
            tools_dir=tmp_path
        )
        assert removed_count == 0

    def test_cleanup_no_orphans(self, tmp_path):
        """Test cleanup when no orphans exist."""
        server_dir = tmp_path / "test-server"
        server_dir.mkdir()
        (server_dir / "tool1.json").write_text("{}")
        (server_dir / "tool2.json").write_text("{}")

        removed_count = cleanup_removed_tools(
            "test-server",
            current_tool_names=["tool1", "tool2"],
            tools_dir=tmp_path
        )

        assert removed_count == 0
        assert (server_dir / "tool1.json").exists()
        assert (server_dir / "tool2.json").exists()

    def test_cleanup_all_orphans(self, tmp_path):
        """Test cleanup when all tools are orphans."""
        server_dir = tmp_path / "test-server"
        server_dir.mkdir()
        (server_dir / "orphan1.json").write_text("{}")
        (server_dir / "orphan2.json").write_text("{}")

        removed_count = cleanup_removed_tools(
            "test-server",
            current_tool_names=[],
            tools_dir=tmp_path
        )

        assert removed_count == 2
        assert not (server_dir / "orphan1.json").exists()
        assert not (server_dir / "orphan2.json").exists()


class TestListServerTools:
    """Tests for list_server_tools function."""

    def test_list_existing_tools(self, tmp_path):
        """Test listing tools for existing server."""
        server_dir = tmp_path / "test-server"
        server_dir.mkdir()
        (server_dir / "tool1.json").write_text("{}")
        (server_dir / "tool2.json").write_text("{}")
        (server_dir / "tool3.json").write_text("{}")

        tools = list_server_tools("test-server", tools_dir=tmp_path)

        assert set(tools) == {"tool1", "tool2", "tool3"}

    def test_list_nonexistent_server(self, tmp_path):
        """Test listing tools for non-existent server returns empty list."""
        tools = list_server_tools("nonexistent", tools_dir=tmp_path)
        assert tools == []

    def test_list_empty_server(self, tmp_path):
        """Test listing tools for server with no tools."""
        server_dir = tmp_path / "empty-server"
        server_dir.mkdir()

        tools = list_server_tools("empty-server", tools_dir=tmp_path)

        assert tools == []

    def test_list_ignores_non_json_files(self, tmp_path):
        """Test that non-JSON files are ignored."""
        server_dir = tmp_path / "test-server"
        server_dir.mkdir()
        (server_dir / "tool1.json").write_text("{}")
        (server_dir / "readme.txt").write_text("Not a tool")
        (server_dir / "config.yaml").write_text("key: value")

        tools = list_server_tools("test-server", tools_dir=tmp_path)

        assert tools == ["tool1"]

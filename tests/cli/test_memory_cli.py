"""Tests for the memory CLI module."""

from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from gobby.cli import cli


class TestMemoryShowCommand:
    """Tests for gobby memory show command."""

    @pytest.fixture
    def runner(self) -> CliRunner:
        """Create a CLI test runner."""
        return CliRunner()

    @patch("gobby.cli.memory.resolve_memory_id")
    @patch("gobby.cli.memory.get_memory_manager")
    def test_show_success(
        self,
        mock_get_manager: MagicMock,
        mock_resolve: MagicMock,
        runner: CliRunner,
    ):
        """Test showing a memory item successfully (mocked)."""
        mock_manager = MagicMock()
        mock_item = MagicMock()
        mock_item.id = "mem-123"
        mock_item.content = "Remember this"
        mock_item.memory_type = "fact"
        mock_item.importance = 0.5
        mock_item.created_at = "2024-01-01"
        mock_item.updated_at = "2024-01-01"
        mock_item.source_type = "cli"
        mock_item.access_count = 0
        mock_item.tags = []

        mock_manager.get_memory.return_value = mock_item
        mock_get_manager.return_value = mock_manager

        mock_resolve.return_value = "mem-123"

        result = runner.invoke(cli, ["memory", "show", "mem-123"])

        assert result.exit_code == 0
        assert "ID: mem-123" in result.output
        assert "Remember this" in result.output

    def test_show_help(self, runner: CliRunner):
        """Test show --help."""
        result = runner.invoke(cli, ["memory", "show", "--help"])
        assert result.exit_code == 0
        assert "Show details of a specific memory" in result.output


class TestMemoryDeleteCommand:
    """Tests for gobby memory delete command."""

    @pytest.fixture
    def runner(self) -> CliRunner:
        """Create a CLI test runner."""
        return CliRunner()

    @patch("gobby.cli.memory.resolve_memory_id")
    @patch("gobby.cli.memory.get_memory_manager")
    def test_delete_success(
        self,
        mock_get_manager: MagicMock,
        mock_resolve: MagicMock,
        runner: CliRunner,
    ):
        """Test deleting a memory item."""
        mock_manager = MagicMock()
        mock_manager.forget.return_value = True
        mock_get_manager.return_value = mock_manager
        mock_resolve.return_value = "mem-del123"

        result = runner.invoke(cli, ["memory", "delete", "mem-del123"])

        assert result.exit_code == 0
        assert "Deleted memory: mem-del123" in result.output
        mock_manager.forget.assert_called_once_with("mem-del123")


class TestMemoryUpdateCommand:
    """Tests for gobby memory update command."""

    @pytest.fixture
    def runner(self) -> CliRunner:
        """Create a CLI test runner."""
        return CliRunner()

    @patch("gobby.cli.memory.resolve_memory_id")
    @patch("gobby.cli.memory.get_memory_manager")
    def test_update_success(
        self,
        mock_get_manager: MagicMock,
        mock_resolve: MagicMock,
        runner: CliRunner,
    ):
        """Test updating a memory item."""
        mock_manager = MagicMock()
        mock_mem = MagicMock()
        mock_mem.id = "mem-up123"
        mock_mem.content = "New content"
        mock_mem.importance = 0.5
        mock_manager.update_memory.return_value = mock_mem

        mock_get_manager.return_value = mock_manager
        mock_resolve.return_value = "mem-up123"

        result = runner.invoke(cli, ["memory", "update", "mem-up123", "--content", "New content"])

        assert result.exit_code == 0
        assert "Updated memory: mem-up123" in result.output
        mock_manager.update_memory.assert_called_once_with(
            memory_id="mem-up123", content="New content", importance=None, tags=None
        )

    @patch("gobby.cli.memory.resolve_memory_id")
    @patch("gobby.cli.memory.get_memory_manager")
    def test_update_with_tags(
        self,
        mock_get_manager: MagicMock,
        mock_resolve: MagicMock,
        runner: CliRunner,
    ):
        """Test updating a memory with tags."""
        mock_manager = MagicMock()
        mock_mem = MagicMock()
        mock_mem.id = "mem-up123"
        mock_mem.content = "Content"
        mock_mem.importance = 0.8
        mock_manager.update_memory.return_value = mock_mem

        mock_get_manager.return_value = mock_manager
        mock_resolve.return_value = "mem-up123"

        result = runner.invoke(
            cli, ["memory", "update", "mem-up123", "--tags", "tag1, tag2, tag3"]
        )

        assert result.exit_code == 0
        mock_manager.update_memory.assert_called_once_with(
            memory_id="mem-up123",
            content=None,
            importance=None,
            tags=["tag1", "tag2", "tag3"],
        )

    @patch("gobby.cli.memory.resolve_memory_id")
    @patch("gobby.cli.memory.get_memory_manager")
    def test_update_with_empty_tags(
        self,
        mock_get_manager: MagicMock,
        mock_resolve: MagicMock,
        runner: CliRunner,
    ):
        """Test updating with empty tags string."""
        mock_manager = MagicMock()
        mock_mem = MagicMock()
        mock_mem.id = "mem-up123"
        mock_mem.content = "Content"
        mock_mem.importance = 0.5
        mock_manager.update_memory.return_value = mock_mem

        mock_get_manager.return_value = mock_manager
        mock_resolve.return_value = "mem-up123"

        # Empty tags string should become None
        result = runner.invoke(cli, ["memory", "update", "mem-up123", "--tags", ""])

        assert result.exit_code == 0
        mock_manager.update_memory.assert_called_once_with(
            memory_id="mem-up123", content=None, importance=None, tags=None
        )

    @patch("gobby.cli.memory.resolve_memory_id")
    @patch("gobby.cli.memory.get_memory_manager")
    def test_update_error_handling(
        self,
        mock_get_manager: MagicMock,
        mock_resolve: MagicMock,
        runner: CliRunner,
    ):
        """Test update error handling."""
        mock_manager = MagicMock()
        mock_manager.update_memory.side_effect = ValueError("Invalid importance")
        mock_get_manager.return_value = mock_manager
        mock_resolve.return_value = "mem-up123"

        result = runner.invoke(
            cli, ["memory", "update", "mem-up123", "--importance", "0.5"]
        )

        assert result.exit_code == 0  # Click doesn't exit on echo
        assert "Error: Invalid importance" in result.output


class TestMemoryRecallCommand:
    """Tests for gobby memory recall command."""

    @pytest.fixture
    def runner(self) -> CliRunner:
        """Create a CLI test runner."""
        return CliRunner()

    @patch("gobby.cli.memory.get_memory_manager")
    def test_recall_no_results(
        self, mock_get_manager: MagicMock, runner: CliRunner
    ):
        """Test recall with no results."""
        mock_manager = MagicMock()
        mock_manager.recall.return_value = []
        mock_get_manager.return_value = mock_manager

        result = runner.invoke(cli, ["memory", "recall", "test query"])

        assert result.exit_code == 0
        assert "No memories found" in result.output

    @patch("gobby.cli.memory.get_memory_manager")
    def test_recall_with_results(
        self, mock_get_manager: MagicMock, runner: CliRunner
    ):
        """Test recall with results."""
        mock_manager = MagicMock()
        mock_mem = MagicMock()
        mock_mem.id = "mem-123456"
        mock_mem.memory_type = "fact"
        mock_mem.importance = 0.8
        mock_mem.content = "Test content"
        mock_mem.tags = ["tag1", "tag2"]
        mock_manager.recall.return_value = [mock_mem]
        mock_get_manager.return_value = mock_manager

        result = runner.invoke(cli, ["memory", "recall", "test"])

        assert result.exit_code == 0
        assert "mem-1234" in result.output
        assert "fact" in result.output
        assert "[tag1, tag2]" in result.output

    @patch("gobby.cli.memory.get_memory_manager")
    def test_recall_with_tag_filters(
        self, mock_get_manager: MagicMock, runner: CliRunner
    ):
        """Test recall with tag filters."""
        mock_manager = MagicMock()
        mock_manager.recall.return_value = []
        mock_get_manager.return_value = mock_manager

        result = runner.invoke(
            cli,
            [
                "memory",
                "recall",
                "query",
                "--tags-all",
                "tag1, tag2",
                "--tags-any",
                "tag3, tag4",
                "--tags-none",
                "excluded",
            ],
        )

        assert result.exit_code == 0
        mock_manager.recall.assert_called_once()
        call_kwargs = mock_manager.recall.call_args[1]
        assert call_kwargs["tags_all"] == ["tag1", "tag2"]
        assert call_kwargs["tags_any"] == ["tag3", "tag4"]
        assert call_kwargs["tags_none"] == ["excluded"]


class TestMemoryListCommand:
    """Tests for gobby memory list command."""

    @pytest.fixture
    def runner(self) -> CliRunner:
        """Create a CLI test runner."""
        return CliRunner()

    @patch("gobby.cli.memory.get_memory_manager")
    def test_list_no_results(
        self, mock_get_manager: MagicMock, runner: CliRunner
    ):
        """Test list with no results."""
        mock_manager = MagicMock()
        mock_manager.list_memories.return_value = []
        mock_get_manager.return_value = mock_manager

        result = runner.invoke(cli, ["memory", "list"])

        assert result.exit_code == 0
        assert "No memories found" in result.output

    @patch("gobby.cli.memory.get_memory_manager")
    def test_list_with_results(
        self, mock_get_manager: MagicMock, runner: CliRunner
    ):
        """Test list with results."""
        mock_manager = MagicMock()
        mock_mem = MagicMock()
        mock_mem.id = "mem-123456789"
        mock_mem.memory_type = "preference"
        mock_mem.importance = 0.75
        mock_mem.content = "x" * 150  # Long content
        mock_mem.tags = []
        mock_manager.list_memories.return_value = [mock_mem]
        mock_get_manager.return_value = mock_manager

        result = runner.invoke(cli, ["memory", "list"])

        assert result.exit_code == 0
        assert "mem-1234" in result.output
        assert "preference" in result.output
        assert "..." in result.output  # Truncated content

    @patch("gobby.cli.memory.get_memory_manager")
    def test_list_with_tags(
        self, mock_get_manager: MagicMock, runner: CliRunner
    ):
        """Test list with tag display."""
        mock_manager = MagicMock()
        mock_mem = MagicMock()
        mock_mem.id = "mem-123456789"
        mock_mem.memory_type = "fact"
        mock_mem.importance = 0.5
        mock_mem.content = "short"
        mock_mem.tags = ["important", "code"]
        mock_manager.list_memories.return_value = [mock_mem]
        mock_get_manager.return_value = mock_manager

        result = runner.invoke(cli, ["memory", "list"])

        assert result.exit_code == 0
        assert "[important, code]" in result.output

    @patch("gobby.cli.memory.get_memory_manager")
    def test_list_with_filters(
        self, mock_get_manager: MagicMock, runner: CliRunner
    ):
        """Test list with all filters."""
        mock_manager = MagicMock()
        mock_manager.list_memories.return_value = []
        mock_get_manager.return_value = mock_manager

        result = runner.invoke(
            cli,
            [
                "memory",
                "list",
                "--type",
                "fact",
                "--min-importance",
                "0.7",
                "--limit",
                "20",
                "--tags-all",
                "tag1",
            ],
        )

        assert result.exit_code == 0
        call_kwargs = mock_manager.list_memories.call_args[1]
        assert call_kwargs["memory_type"] == "fact"
        assert call_kwargs["min_importance"] == 0.7
        assert call_kwargs["limit"] == 20


class TestMemoryStatsCommand:
    """Tests for gobby memory stats command."""

    @pytest.fixture
    def runner(self) -> CliRunner:
        """Create a CLI test runner."""
        return CliRunner()

    @patch("gobby.cli.memory.get_memory_manager")
    def test_stats_output(
        self, mock_get_manager: MagicMock, runner: CliRunner
    ):
        """Test stats command output formatting."""
        mock_manager = MagicMock()
        mock_manager.get_stats.return_value = {
            "total_count": 42,
            "avg_importance": 0.654,
            "by_type": {"fact": 20, "preference": 15, "context": 7},
        }
        mock_get_manager.return_value = mock_manager

        result = runner.invoke(cli, ["memory", "stats"])

        assert result.exit_code == 0
        assert "Total Memories: 42" in result.output
        assert "Average Importance: 0.654" in result.output
        assert "fact: 20" in result.output
        assert "preference: 15" in result.output

    @patch("gobby.cli.memory.get_memory_manager")
    def test_stats_empty_by_type(
        self, mock_get_manager: MagicMock, runner: CliRunner
    ):
        """Test stats with no type breakdown."""
        mock_manager = MagicMock()
        mock_manager.get_stats.return_value = {
            "total_count": 0,
            "avg_importance": 0.0,
            "by_type": {},
        }
        mock_get_manager.return_value = mock_manager

        result = runner.invoke(cli, ["memory", "stats"])

        assert result.exit_code == 0
        assert "Total Memories: 0" in result.output


class TestResolveMemoryId:
    """Tests for resolve_memory_id function."""

    @patch("gobby.cli.memory.get_memory_manager")
    def test_resolve_exact_match(self, mock_get_manager: MagicMock):
        """Test resolving exact UUID match."""
        from gobby.cli.memory import resolve_memory_id

        mock_manager = MagicMock()
        mock_mem = MagicMock()
        mock_mem.id = "12345678-1234-1234-1234-123456789012"
        mock_manager.get_memory.return_value = mock_mem
        mock_get_manager.return_value = mock_manager

        result = resolve_memory_id(mock_manager, "12345678-1234-1234-1234-123456789012")
        assert result == "12345678-1234-1234-1234-123456789012"

    @patch("gobby.cli.memory.get_memory_manager")
    def test_resolve_prefix_match(self, mock_get_manager: MagicMock):
        """Test resolving prefix match."""
        from gobby.cli.memory import resolve_memory_id

        mock_manager = MagicMock()
        mock_manager.get_memory.return_value = None  # Not exact match
        mock_mem = MagicMock()
        mock_mem.id = "mem-123456789"
        mock_manager.find_by_prefix.return_value = [mock_mem]
        mock_get_manager.return_value = mock_manager

        result = resolve_memory_id(mock_manager, "mem-12")
        assert result == "mem-123456789"

    def test_resolve_not_found(self):
        """Test resolving non-existent memory."""
        import click

        from gobby.cli.memory import resolve_memory_id

        mock_manager = MagicMock()
        mock_manager.get_memory.return_value = None
        mock_manager.find_by_prefix.return_value = []

        with pytest.raises(click.ClickException) as exc_info:
            resolve_memory_id(mock_manager, "nonexistent")
        assert "Memory not found" in str(exc_info.value)

    def test_resolve_ambiguous(self):
        """Test resolving ambiguous prefix."""
        import click

        from gobby.cli.memory import resolve_memory_id

        mock_manager = MagicMock()
        mock_manager.get_memory.return_value = None
        mock_mem1 = MagicMock()
        mock_mem1.id = "mem-123a"
        mock_mem2 = MagicMock()
        mock_mem2.id = "mem-123b"
        mock_manager.find_by_prefix.return_value = [mock_mem1, mock_mem2]

        with pytest.raises(click.ClickException) as exc_info:
            resolve_memory_id(mock_manager, "mem-123")
        assert "Ambiguous memory reference" in str(exc_info.value)


class TestMemoryDeleteNotFound:
    """Additional delete tests."""

    @pytest.fixture
    def runner(self) -> CliRunner:
        """Create a CLI test runner."""
        return CliRunner()

    @patch("gobby.cli.memory.resolve_memory_id")
    @patch("gobby.cli.memory.get_memory_manager")
    def test_delete_not_found(
        self,
        mock_get_manager: MagicMock,
        mock_resolve: MagicMock,
        runner: CliRunner,
    ):
        """Test deleting a non-existent memory."""
        mock_manager = MagicMock()
        mock_manager.forget.return_value = False
        mock_get_manager.return_value = mock_manager
        mock_resolve.return_value = "nonexistent"

        result = runner.invoke(cli, ["memory", "delete", "nonexistent"])

        assert result.exit_code == 0
        assert "Memory not found" in result.output


class TestMemoryShowNotFound:
    """Additional show tests."""

    @pytest.fixture
    def runner(self) -> CliRunner:
        """Create a CLI test runner."""
        return CliRunner()

    @patch("gobby.cli.memory.resolve_memory_id")
    @patch("gobby.cli.memory.get_memory_manager")
    def test_show_not_found(
        self,
        mock_get_manager: MagicMock,
        mock_resolve: MagicMock,
        runner: CliRunner,
    ):
        """Test showing a non-existent memory."""
        mock_manager = MagicMock()
        mock_manager.get_memory.return_value = None
        mock_get_manager.return_value = mock_manager
        mock_resolve.return_value = "nonexistent"

        result = runner.invoke(cli, ["memory", "show", "nonexistent"])

        assert result.exit_code == 0
        assert "Memory not found" in result.output

    @patch("gobby.cli.memory.resolve_memory_id")
    @patch("gobby.cli.memory.get_memory_manager")
    def test_show_with_tags(
        self,
        mock_get_manager: MagicMock,
        mock_resolve: MagicMock,
        runner: CliRunner,
    ):
        """Test showing a memory with tags."""
        mock_manager = MagicMock()
        mock_item = MagicMock()
        mock_item.id = "mem-123"
        mock_item.content = "Content"
        mock_item.memory_type = "fact"
        mock_item.importance = 0.5
        mock_item.created_at = "2024-01-01"
        mock_item.updated_at = "2024-01-01"
        mock_item.source_type = "cli"
        mock_item.access_count = 5
        mock_item.tags = ["tag1", "tag2"]

        mock_manager.get_memory.return_value = mock_item
        mock_get_manager.return_value = mock_manager
        mock_resolve.return_value = "mem-123"

        result = runner.invoke(cli, ["memory", "show", "mem-123"])

        assert result.exit_code == 0
        assert "Tags: tag1, tag2" in result.output
        assert "Access Count: 5" in result.output

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

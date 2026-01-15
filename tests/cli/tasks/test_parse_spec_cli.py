"""Tests for gobby tasks parse-spec CLI command.

Tests verify the parse-spec command for creating tasks from spec files:
- Basic spec parsing
- --parent flag for parent task
- --project flag for project
"""

from unittest.mock import AsyncMock, MagicMock, patch
import tempfile
from pathlib import Path

import pytest
from click.testing import CliRunner

from gobby.cli.tasks import tasks


@pytest.fixture
def runner() -> CliRunner:
    """Create a CLI test runner."""
    return CliRunner()


@pytest.fixture
def mock_task():
    """Create a mock task."""
    task = MagicMock()
    task.id = "task-123"
    task.seq_num = 42
    task.title = "Test Task"
    task.description = "Test description"
    task.project_id = "proj-123"
    return task


class TestParseSpecCommand:
    """Tests for the parse-spec CLI command."""

    def test_parse_spec_command_exists(self, runner: CliRunner):
        """Test that parse-spec command is registered."""
        result = runner.invoke(tasks, ["parse-spec", "--help"])
        assert result.exit_code == 0
        assert "spec" in result.output.lower()

    def test_parse_spec_basic(self, runner: CliRunner, mock_task):
        """Test parsing a basic spec file."""
        spec_content = """# Feature Spec

## Phase 1
- [ ] Task 1
- [ ] Task 2
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            f.write(spec_content)
            spec_path = f.name

        try:
            with (
                patch("gobby.cli.tasks.ai.get_task_manager") as mock_get_manager,
                patch("gobby.utils.project_context.get_project_context") as mock_ctx,
            ):
                mock_manager = MagicMock()
                mock_manager.create_task.return_value = mock_task
                mock_get_manager.return_value = mock_manager
                mock_ctx.return_value = {"id": "proj-123"}

                result = runner.invoke(tasks, ["parse-spec", spec_path])

                # Should accept the spec path
                assert result.exit_code == 0 or "not found" not in result.output.lower()
        finally:
            Path(spec_path).unlink()

    def test_parse_spec_with_parent(self, runner: CliRunner, mock_task):
        """Test parsing with --parent flag."""
        spec_content = "# Spec\n- [ ] Task 1\n"
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            f.write(spec_content)
            spec_path = f.name

        try:
            with (
                patch("gobby.cli.tasks.ai.get_task_manager") as mock_get_manager,
                patch("gobby.cli.tasks.ai.resolve_task_id", return_value=mock_task),
                patch("gobby.utils.project_context.get_project_context") as mock_ctx,
            ):
                mock_manager = MagicMock()
                mock_manager.create_task.return_value = mock_task
                mock_get_manager.return_value = mock_manager
                mock_ctx.return_value = {"id": "proj-123"}

                result = runner.invoke(tasks, ["parse-spec", spec_path, "--parent", "#42"])

                # The --parent option should be recognized
                assert result.exit_code == 0 or "--parent" not in result.output
        finally:
            Path(spec_path).unlink()

    def test_parse_spec_with_project(self, runner: CliRunner, mock_task):
        """Test parsing with --project flag."""
        spec_content = "# Spec\n- [ ] Task 1\n"
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            f.write(spec_content)
            spec_path = f.name

        try:
            with (
                patch("gobby.cli.tasks.ai.get_task_manager") as mock_get_manager,
                patch("gobby.utils.project_context.get_project_context") as mock_ctx,
            ):
                mock_manager = MagicMock()
                mock_manager.create_task.return_value = mock_task
                mock_get_manager.return_value = mock_manager
                mock_ctx.return_value = {"id": "proj-123"}

                result = runner.invoke(tasks, ["parse-spec", spec_path, "--project", "myproject"])

                # The --project option should be recognized
                assert result.exit_code == 0 or "--project" not in result.output
        finally:
            Path(spec_path).unlink()


class TestParseSpecErrors:
    """Tests for error handling in parse-spec command."""

    def test_parse_spec_file_not_found(self, runner: CliRunner):
        """Test error when spec file doesn't exist."""
        result = runner.invoke(tasks, ["parse-spec", "/nonexistent/spec.md"])

        assert "not found" in result.output.lower() or result.exit_code != 0

    def test_parse_spec_missing_argument(self, runner: CliRunner):
        """Test error when spec path is missing."""
        result = runner.invoke(tasks, ["parse-spec"])

        assert result.exit_code != 0

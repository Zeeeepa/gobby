"""Tests for gobby tasks expand CLI command (now deprecated).

The expand command has been deprecated in favor of the /gobby-expand skill.
These tests verify that the command shows the deprecation message.
"""

import pytest
from click.testing import CliRunner

from gobby.cli.tasks import tasks


@pytest.fixture
def runner() -> CliRunner:
    """Create a CLI test runner."""
    return CliRunner()


class TestExpandMultipleTaskRefs:
    """Tests for expand command with multiple task refs."""

    def test_expand_multiple_tasks(self, runner: CliRunner):
        """Test that expand with multiple tasks shows deprecation message."""
        # Test with comma-separated task refs
        result = runner.invoke(tasks, ["expand", "#42,#43,#44"])

        # Verify CLI exits with code 1 (deprecated)
        assert result.exit_code == 1
        assert "DEPRECATED" in result.output
        assert "/gobby-expand" in result.output


class TestExpandCascade:
    """Tests for expand command with --cascade flag."""

    def test_expand_with_cascade(self, runner: CliRunner):
        """Test that expand with --cascade shows deprecation message."""
        result = runner.invoke(tasks, ["expand", "#42", "--cascade"])

        # Verify CLI exits with code 1 (deprecated)
        assert result.exit_code == 1
        assert "DEPRECATED" in result.output
        assert "/gobby-expand" in result.output


class TestExpandForce:
    """Tests for expand command with --force flag."""

    def test_expand_with_force(self, runner: CliRunner):
        """Test that expand with --force shows deprecation message."""
        result = runner.invoke(tasks, ["expand", "#42", "--force"])

        # Verify CLI exits with code 1 (deprecated)
        assert result.exit_code == 1
        assert "DEPRECATED" in result.output
        assert "/gobby-expand" in result.output

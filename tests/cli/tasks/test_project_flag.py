"""Tests for --project/-p flag on task CLI commands.

Tests verify the --project flag for specifying project context.
Note: The expand command is deprecated but the --project option is still accepted.
"""

import pytest
from click.testing import CliRunner

from gobby.cli.tasks import tasks


@pytest.fixture
def runner() -> CliRunner:
    """Create a CLI test runner."""
    return CliRunner()


class TestExpandProjectFlag:
    """Tests for expand command --project flag (deprecated)."""

    def test_expand_has_project_option(self, runner: CliRunner):
        """Test that expand command has --project option."""
        result = runner.invoke(tasks, ["expand", "--help"])
        assert result.exit_code == 0
        assert "--project" in result.output or "-p" in result.output

    def test_expand_with_project_flag(self, runner: CliRunner):
        """Test expand with --project flag shows deprecation message."""
        result = runner.invoke(tasks, ["expand", "#42", "--project", "myproject"])

        # Command should show deprecation message and exit with code 1
        assert result.exit_code == 1
        assert "DEPRECATED" in result.output
        assert "/gobby-expand" in result.output

"""Tests for expand command (now deprecated)."""

from click.testing import CliRunner

from gobby.cli.tasks import tasks


def test_expand_command_with_flags():
    """Test expand command shows deprecation message."""
    runner = CliRunner()

    # Test with explicit flags
    result = runner.invoke(tasks, ["expand", "t1", "--web-research", "--no-code-context"])

    assert result.exit_code == 1
    assert "DEPRECATED" in result.output
    assert "/gobby-expand" in result.output

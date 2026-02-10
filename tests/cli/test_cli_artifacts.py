"""Tests for CLI artifact commands.

These tests define the expected behavior for the artifacts CLI.
Tests should fail/skip initially (TDD red phase) until the implementation is complete.

The artifacts CLI should expose:
- gobby artifacts search <query>: Full-text search across artifact content
- gobby artifacts list: List artifacts with session and type filters
- gobby artifacts show <id>: Display full artifact content
- gobby artifacts timeline <session_id>: Chronological view of session artifacts
"""

from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from gobby.cli import cli

pytestmark = pytest.mark.unit


def get_artifacts_module():
    """Import the artifacts CLI module when it exists."""
    try:
        from gobby.cli import artifacts

        return artifacts
    except ImportError:
        pytest.skip("artifacts CLI module not yet implemented")


def artifacts_available() -> bool:
    """Check if artifacts command is registered in CLI."""
    try:
        # Check if 'artifacts' is a registered command
        return "artifacts" in cli.commands
    except Exception:
        return False


@pytest.fixture
def runner() -> CliRunner:
    """Create a CLI test runner."""
    return CliRunner()


@pytest.fixture
def mock_artifact():
    """Create a mock artifact for testing."""
    artifact = MagicMock()
    artifact.id = "art-abc123"
    artifact.session_id = "sess-xyz789"
    artifact.artifact_type = "code"
    artifact.content = (
        "function calculateTotal(items) {\n  return items.reduce((sum, i) => sum + i.price, 0);\n}"
    )
    artifact.source_file = "utils.js"
    artifact.line_start = 10
    artifact.line_end = 12
    artifact.created_at = "2024-01-01T00:00:00Z"
    artifact.title = "Test artifact"
    artifact.task_id = None
    artifact.metadata = {"language": "javascript"}
    artifact.to_dict = MagicMock(
        return_value={
            "id": "art-abc123",
            "session_id": "sess-xyz789",
            "artifact_type": "code",
            "content": artifact.content,
            "source_file": "utils.js",
            "line_start": 10,
            "line_end": 12,
            "created_at": "2024-01-01T00:00:00Z",
            "metadata": {"language": "javascript"},
        }
    )
    return artifact


@pytest.fixture
def mock_artifact_manager(mock_artifact):
    """Create a mock artifact manager."""
    manager = MagicMock()
    manager.search_artifacts.return_value = [mock_artifact]
    manager.list_artifacts.return_value = [mock_artifact]
    manager.get_artifact.return_value = mock_artifact
    return manager


# ==============================================================================
# Tests for 'gobby artifacts search <query>'
# ==============================================================================


class TestArtifactsSearch:
    """Tests for the gobby artifacts search command."""

    @pytest.mark.skipif(not artifacts_available(), reason="artifacts CLI not yet implemented")
    def test_search_returns_matching_artifacts(self, runner, mock_artifact_manager) -> None:
        """Verify 'gobby artifacts search <query>' returns matching artifacts."""
        with patch("gobby.cli.artifacts.get_artifact_manager", return_value=mock_artifact_manager):
            result = runner.invoke(cli, ["artifacts", "search", "calculateTotal"])

            assert result.exit_code == 0
            assert "art-abc123" in result.output
            mock_artifact_manager.search_artifacts.assert_called_once()

    @pytest.mark.skipif(not artifacts_available(), reason="artifacts CLI not yet implemented")
    def test_search_with_session_filter(self, runner, mock_artifact_manager) -> None:
        """Verify search can filter by session_id."""
        with patch("gobby.cli.artifacts.get_artifact_manager", return_value=mock_artifact_manager):
            result = runner.invoke(cli, ["artifacts", "search", "test", "--session", "sess-123"])

            assert result.exit_code == 0
            mock_artifact_manager.search_artifacts.assert_called_once()
            call_kwargs = mock_artifact_manager.search_artifacts.call_args
            assert "sess-123" in str(call_kwargs)

    @pytest.mark.skipif(not artifacts_available(), reason="artifacts CLI not yet implemented")
    def test_search_with_type_filter(self, runner, mock_artifact_manager) -> None:
        """Verify search can filter by artifact type."""
        with patch("gobby.cli.artifacts.get_artifact_manager", return_value=mock_artifact_manager):
            result = runner.invoke(cli, ["artifacts", "search", "error", "--type", "error"])

            assert result.exit_code == 0
            call_kwargs = mock_artifact_manager.search_artifacts.call_args
            assert "error" in str(call_kwargs)

    @pytest.mark.skipif(not artifacts_available(), reason="artifacts CLI not yet implemented")
    def test_search_with_limit(self, runner, mock_artifact_manager) -> None:
        """Verify search respects limit parameter."""
        with patch("gobby.cli.artifacts.get_artifact_manager", return_value=mock_artifact_manager):
            result = runner.invoke(cli, ["artifacts", "search", "test", "--limit", "10"])

            assert result.exit_code == 0
            call_kwargs = mock_artifact_manager.search_artifacts.call_args
            assert "10" in str(call_kwargs) or call_kwargs[1].get("limit") == 10

    @pytest.mark.skipif(not artifacts_available(), reason="artifacts CLI not yet implemented")
    def test_search_empty_results(self, runner, mock_artifact_manager) -> None:
        """Verify search handles empty results gracefully."""
        mock_artifact_manager.search_artifacts.return_value = []

        with patch("gobby.cli.artifacts.get_artifact_manager", return_value=mock_artifact_manager):
            result = runner.invoke(cli, ["artifacts", "search", "nonexistent"])

            assert result.exit_code == 0
            assert "No artifacts found" in result.output or result.output.strip() == ""


# ==============================================================================
# Tests for 'gobby artifacts list'
# ==============================================================================


class TestArtifactsList:
    """Tests for the gobby artifacts list command."""

    @pytest.mark.skipif(not artifacts_available(), reason="artifacts CLI not yet implemented")
    def test_list_all_artifacts(self, runner, mock_artifact_manager) -> None:
        """Verify 'gobby artifacts list' returns all artifacts."""
        with patch("gobby.cli.artifacts.get_artifact_manager", return_value=mock_artifact_manager):
            result = runner.invoke(cli, ["artifacts", "list"])

            assert result.exit_code == 0
            assert "art-abc123" in result.output

    @pytest.mark.skipif(not artifacts_available(), reason="artifacts CLI not yet implemented")
    def test_list_by_session(self, runner, mock_artifact_manager) -> None:
        """Verify list can filter by session_id."""
        with patch("gobby.cli.artifacts.get_artifact_manager", return_value=mock_artifact_manager):
            result = runner.invoke(cli, ["artifacts", "list", "--session", "sess-xyz789"])

            assert result.exit_code == 0
            mock_artifact_manager.list_artifacts.assert_called_once()
            call_kwargs = mock_artifact_manager.list_artifacts.call_args
            assert "sess-xyz789" in str(call_kwargs)

    @pytest.mark.skipif(not artifacts_available(), reason="artifacts CLI not yet implemented")
    def test_list_by_type(self, runner, mock_artifact_manager) -> None:
        """Verify list can filter by artifact type."""
        with patch("gobby.cli.artifacts.get_artifact_manager", return_value=mock_artifact_manager):
            result = runner.invoke(cli, ["artifacts", "list", "--type", "code"])

            assert result.exit_code == 0
            call_kwargs = mock_artifact_manager.list_artifacts.call_args
            assert "code" in str(call_kwargs)

    @pytest.mark.skipif(not artifacts_available(), reason="artifacts CLI not yet implemented")
    def test_list_with_pagination(self, runner, mock_artifact_manager) -> None:
        """Verify list supports pagination."""
        with patch("gobby.cli.artifacts.get_artifact_manager", return_value=mock_artifact_manager):
            result = runner.invoke(cli, ["artifacts", "list", "--limit", "10", "--offset", "20"])

            assert result.exit_code == 0
            call_kwargs = mock_artifact_manager.list_artifacts.call_args
            # Check limit and offset were passed
            assert "10" in str(call_kwargs) or call_kwargs[1].get("limit") == 10
            assert "20" in str(call_kwargs) or call_kwargs[1].get("offset") == 20

    @pytest.mark.skipif(not artifacts_available(), reason="artifacts CLI not yet implemented")
    def test_list_empty_results(self, runner, mock_artifact_manager) -> None:
        """Verify list handles empty results gracefully."""
        mock_artifact_manager.list_artifacts.return_value = []

        with patch("gobby.cli.artifacts.get_artifact_manager", return_value=mock_artifact_manager):
            result = runner.invoke(cli, ["artifacts", "list"])

            assert result.exit_code == 0


# ==============================================================================
# Tests for 'gobby artifacts show <id>'
# ==============================================================================


class TestArtifactsShow:
    """Tests for the gobby artifacts show command."""

    @pytest.mark.skipif(not artifacts_available(), reason="artifacts CLI not yet implemented")
    def test_show_artifact_by_id(self, runner, mock_artifact_manager, mock_artifact) -> None:
        """Verify 'gobby artifacts show <id>' displays artifact content."""
        with patch("gobby.cli.artifacts.get_artifact_manager", return_value=mock_artifact_manager):
            result = runner.invoke(cli, ["artifacts", "show", "art-abc123"])

            assert result.exit_code == 0
            # Should show the artifact content
            assert "calculateTotal" in result.output or mock_artifact.content in result.output
            mock_artifact_manager.get_artifact.assert_called_once_with("art-abc123")

    @pytest.mark.skipif(not artifacts_available(), reason="artifacts CLI not yet implemented")
    def test_show_nonexistent_artifact(self, runner, mock_artifact_manager) -> None:
        """Verify show returns error for nonexistent artifact."""
        mock_artifact_manager.get_artifact.return_value = None

        with patch("gobby.cli.artifacts.get_artifact_manager", return_value=mock_artifact_manager):
            result = runner.invoke(cli, ["artifacts", "show", "art-nonexistent"])

            assert result.exit_code != 0 or "not found" in result.output.lower()

    @pytest.mark.skipif(not artifacts_available(), reason="artifacts CLI not yet implemented")
    def test_show_includes_metadata(self, runner, mock_artifact_manager, mock_artifact) -> None:
        """Verify show displays artifact metadata."""
        with patch("gobby.cli.artifacts.get_artifact_manager", return_value=mock_artifact_manager):
            result = runner.invoke(cli, ["artifacts", "show", "art-abc123", "--verbose"])

            assert result.exit_code == 0
            # Should show source file in verbose mode
            assert "utils.js" in result.output or "source" in result.output.lower()


# ==============================================================================
# Tests for 'gobby artifacts timeline <session_id>'
# ==============================================================================


class TestArtifactsTimeline:
    """Tests for the gobby artifacts timeline command."""

    @pytest.mark.skipif(not artifacts_available(), reason="artifacts CLI not yet implemented")
    def test_timeline_for_session(self, runner, mock_artifact_manager) -> None:
        """Verify 'gobby artifacts timeline <session_id>' shows chronological view."""
        # Setup multiple artifacts with different timestamps
        art1 = MagicMock()
        art1.id = "art-1"
        art1.created_at = "2024-01-01T00:00:00Z"
        art1.artifact_type = "code"
        art1.to_dict = MagicMock(return_value={"id": "art-1", "created_at": "2024-01-01T00:00:00Z"})

        art2 = MagicMock()
        art2.id = "art-2"
        art2.created_at = "2024-01-01T01:00:00Z"
        art2.artifact_type = "error"
        art2.to_dict = MagicMock(return_value={"id": "art-2", "created_at": "2024-01-01T01:00:00Z"})

        mock_artifact_manager.list_artifacts.return_value = [art2, art1]  # Newest first

        with patch("gobby.cli.artifacts.get_artifact_manager", return_value=mock_artifact_manager):
            result = runner.invoke(cli, ["artifacts", "timeline", "sess-123"])

            assert result.exit_code == 0
            # Should show artifacts in chronological order (oldest first)
            output_lines = result.output.split("\n")
            # art-1 should appear before art-2 in chronological view
            art1_idx = next((i for i, line in enumerate(output_lines) if "art-1" in line), -1)
            art2_idx = next((i for i, line in enumerate(output_lines) if "art-2" in line), -1)
            if art1_idx != -1 and art2_idx != -1:
                assert art1_idx < art2_idx, "Timeline should show oldest first"

    @pytest.mark.skipif(not artifacts_available(), reason="artifacts CLI not yet implemented")
    def test_timeline_requires_session_id(self, runner) -> None:
        """Verify timeline requires session_id argument."""
        result = runner.invoke(cli, ["artifacts", "timeline"])

        # Should fail without session_id
        assert result.exit_code != 0 or "session" in result.output.lower()

    @pytest.mark.skipif(not artifacts_available(), reason="artifacts CLI not yet implemented")
    def test_timeline_with_type_filter(self, runner, mock_artifact_manager) -> None:
        """Verify timeline can filter by artifact type."""
        with patch("gobby.cli.artifacts.get_artifact_manager", return_value=mock_artifact_manager):
            result = runner.invoke(cli, ["artifacts", "timeline", "sess-123", "--type", "code"])

            assert result.exit_code == 0
            mock_artifact_manager.list_artifacts.assert_called_once()
            call_kwargs = mock_artifact_manager.list_artifacts.call_args
            assert "code" in str(call_kwargs)


# ==============================================================================
# Tests for output formatting
# ==============================================================================


class TestArtifactOutputFormatting:
    """Tests for artifact output formatting and syntax highlighting."""

    @pytest.mark.skipif(not artifacts_available(), reason="artifacts CLI not yet implemented")
    def test_code_artifact_has_syntax_highlighting(
        self, runner, mock_artifact_manager, mock_artifact
    ) -> None:
        """Verify code artifacts have syntax highlighting in output."""
        with patch("gobby.cli.artifacts.get_artifact_manager", return_value=mock_artifact_manager):
            result = runner.invoke(cli, ["artifacts", "show", "art-abc123"])

            assert result.exit_code == 0
            # Output should contain the code content
            # Syntax highlighting might add ANSI codes or rich formatting
            assert "calculateTotal" in result.output or "function" in result.output

    @pytest.mark.skipif(not artifacts_available(), reason="artifacts CLI not yet implemented")
    def test_json_output_format(self, runner, mock_artifact_manager, mock_artifact) -> None:
        """Verify --json flag outputs JSON format."""
        with patch("gobby.cli.artifacts.get_artifact_manager", return_value=mock_artifact_manager):
            result = runner.invoke(cli, ["artifacts", "show", "art-abc123", "--json"])

            assert result.exit_code == 0
            # Should be valid JSON
            import json

            try:
                data = json.loads(result.output)
                assert "id" in data or "artifact" in data
            except json.JSONDecodeError:
                pytest.fail("Output is not valid JSON")

    @pytest.mark.skipif(not artifacts_available(), reason="artifacts CLI not yet implemented")
    def test_list_table_format(self, runner, mock_artifact_manager) -> None:
        """Verify list command outputs in table format by default."""
        with patch("gobby.cli.artifacts.get_artifact_manager", return_value=mock_artifact_manager):
            result = runner.invoke(cli, ["artifacts", "list"])

            assert result.exit_code == 0
            # Should have some table-like formatting (headers, columns)
            # At minimum should show artifact IDs
            assert "art-abc123" in result.output

    @pytest.mark.skipif(not artifacts_available(), reason="artifacts CLI not yet implemented")
    def test_error_artifact_formatting(self, runner, mock_artifact_manager) -> None:
        """Verify error artifacts are formatted appropriately."""
        error_artifact = MagicMock()
        error_artifact.id = "art-error-1"
        error_artifact.artifact_type = "error"
        error_artifact.content = "TypeError: Cannot read property 'foo' of undefined"
        error_artifact.to_dict = MagicMock(
            return_value={
                "id": "art-error-1",
                "artifact_type": "error",
                "content": error_artifact.content,
            }
        )
        mock_artifact_manager.get_artifact.return_value = error_artifact

        with patch("gobby.cli.artifacts.get_artifact_manager", return_value=mock_artifact_manager):
            result = runner.invoke(cli, ["artifacts", "show", "art-error-1"])

            assert result.exit_code == 0
            assert "TypeError" in result.output


# ==============================================================================
# Tests for edge cases and error handling
# ==============================================================================


class TestArtifactsCLIErrorHandling:
    """Tests for error handling in artifacts CLI."""

    @pytest.mark.skipif(not artifacts_available(), reason="artifacts CLI not yet implemented")
    def test_search_with_invalid_type(self, runner, mock_artifact_manager) -> None:
        """Verify search handles invalid artifact type gracefully."""
        with patch("gobby.cli.artifacts.get_artifact_manager", return_value=mock_artifact_manager):
            result = runner.invoke(cli, ["artifacts", "search", "test", "--type", "invalid_type"])

            # Should either succeed with empty results or show helpful error
            # Implementation can choose which behavior
            assert result.exit_code == 0 or "invalid" in result.output.lower()

    @pytest.mark.skipif(not artifacts_available(), reason="artifacts CLI not yet implemented")
    def test_database_error_handling(self, runner, mock_artifact_manager) -> None:
        """Verify CLI handles database errors gracefully."""
        mock_artifact_manager.search_artifacts.side_effect = Exception("Database connection failed")

        with patch("gobby.cli.artifacts.get_artifact_manager", return_value=mock_artifact_manager):
            result = runner.invoke(cli, ["artifacts", "search", "test"])

            # Should show error message, not crash
            assert result.exit_code != 0 or "error" in result.output.lower()


# ==============================================================================
# Tests for CLI command registration
# ==============================================================================


class TestArtifactsCLIRegistration:
    """Tests for artifacts CLI command registration."""

    def test_artifacts_command_exists(self, runner) -> None:
        """Verify artifacts command is registered (will fail in TDD red phase)."""
        result = runner.invoke(cli, ["artifacts", "--help"])

        if result.exit_code == 2 and "No such command 'artifacts'" in result.output:
            pytest.skip("artifacts CLI command not yet registered")

        assert result.exit_code == 0
        assert "artifacts" in result.output.lower()

    def test_artifacts_subcommands_exist(self, runner) -> None:
        """Verify all expected subcommands are registered."""
        result = runner.invoke(cli, ["artifacts", "--help"])

        if result.exit_code == 2 and "No such command 'artifacts'" in result.output:
            pytest.skip("artifacts CLI command not yet registered")

        assert result.exit_code == 0
        expected_commands = ["search", "list", "show", "timeline"]
        for cmd in expected_commands:
            assert cmd in result.output, f"Subcommand '{cmd}' should be registered"

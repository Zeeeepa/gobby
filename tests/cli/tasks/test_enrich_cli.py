"""Tests for gobby tasks enrich CLI command.

Tests verify the enrich command for enriching tasks with additional context:
- Single task enrichment
- Multiple task refs (comma-separated, space-separated)
- --cascade flag for enriching subtasks
- --web-research flag
- --mcp-tools flag
- --force flag to re-enrich
- Integration with cascade_progress
"""

from unittest.mock import AsyncMock, MagicMock, patch

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
    task.is_enriched = False
    return task


@pytest.fixture
def mock_enricher():
    """Create a mock TaskEnricher."""
    enricher = MagicMock()
    enricher.enrich = AsyncMock()
    return enricher


class TestEnrichCommand:
    """Tests for the enrich CLI command."""

    def test_enrich_command_exists(self, runner: CliRunner):
        """Test that enrich command is registered."""
        result = runner.invoke(tasks, ["enrich", "--help"])
        assert result.exit_code == 0
        assert "Enrich" in result.output or "enrich" in result.output

    def test_enrich_single_task(self, runner: CliRunner, mock_task, mock_enricher):
        """Test enriching a single task."""
        with (
            patch("gobby.cli.tasks.ai.get_task_manager") as mock_get_manager,
            patch("gobby.cli.tasks.ai.resolve_task_id", return_value=mock_task),
            patch("gobby.config.app.load_config") as mock_config,
            patch("gobby.llm.LLMService"),
            patch("gobby.tasks.enrich.TaskEnricher", return_value=mock_enricher),
        ):
            mock_manager = MagicMock()
            mock_get_manager.return_value = mock_manager
            mock_config.return_value.gobby_tasks.enrichment.enabled = True

            mock_enricher.enrich.return_value = MagicMock(
                category="code",
                complexity_score=2,
                validation_criteria="Tests pass",
            )

            result = runner.invoke(tasks, ["enrich", "#42"])

            assert result.exit_code == 0

    def test_enrich_multiple_tasks(self, runner: CliRunner, mock_task, mock_enricher):
        """Test enriching multiple tasks with comma separation."""
        with (
            patch("gobby.cli.tasks.ai.get_task_manager") as mock_get_manager,
            patch("gobby.cli.tasks.ai.resolve_task_id", return_value=mock_task),
            patch("gobby.config.app.load_config") as mock_config,
            patch("gobby.llm.LLMService"),
            patch("gobby.tasks.enrich.TaskEnricher", return_value=mock_enricher),
        ):
            mock_manager = MagicMock()
            mock_get_manager.return_value = mock_manager
            mock_config.return_value.gobby_tasks.enrichment.enabled = True

            mock_enricher.enrich.return_value = MagicMock(
                category="code",
                complexity_score=2,
                validation_criteria="Tests pass",
            )

            result = runner.invoke(tasks, ["enrich", "#42,#43,#44"])

            assert result.exit_code == 0

    def test_enrich_with_web_research(self, runner: CliRunner, mock_task, mock_enricher):
        """Test enriching with web research enabled."""
        with (
            patch("gobby.cli.tasks.ai.get_task_manager") as mock_get_manager,
            patch("gobby.cli.tasks.ai.resolve_task_id", return_value=mock_task),
            patch("gobby.config.app.load_config") as mock_config,
            patch("gobby.llm.LLMService"),
            patch("gobby.tasks.enrich.TaskEnricher", return_value=mock_enricher),
        ):
            mock_manager = MagicMock()
            mock_get_manager.return_value = mock_manager
            mock_config.return_value.gobby_tasks.enrichment.enabled = True

            mock_enricher.enrich.return_value = MagicMock(
                category="code",
                complexity_score=2,
            )

            result = runner.invoke(tasks, ["enrich", "#42", "--web-research"])

            assert result.exit_code == 0
            # Verify web research was enabled
            mock_enricher.enrich.assert_called()
            call_kwargs = mock_enricher.enrich.call_args.kwargs
            assert call_kwargs.get("enable_web_research") is True

    def test_enrich_with_mcp_tools(self, runner: CliRunner, mock_task, mock_enricher):
        """Test enriching with MCP tools enabled."""
        with (
            patch("gobby.cli.tasks.ai.get_task_manager") as mock_get_manager,
            patch("gobby.cli.tasks.ai.resolve_task_id", return_value=mock_task),
            patch("gobby.config.app.load_config") as mock_config,
            patch("gobby.llm.LLMService"),
            patch("gobby.tasks.enrich.TaskEnricher", return_value=mock_enricher),
        ):
            mock_manager = MagicMock()
            mock_get_manager.return_value = mock_manager
            mock_config.return_value.gobby_tasks.enrichment.enabled = True

            mock_enricher.enrich.return_value = MagicMock(
                category="code",
                complexity_score=2,
            )

            result = runner.invoke(tasks, ["enrich", "#42", "--mcp-tools"])

            assert result.exit_code == 0
            mock_enricher.enrich.assert_called()
            call_kwargs = mock_enricher.enrich.call_args.kwargs
            assert call_kwargs.get("enable_mcp_tools") is True

    def test_enrich_with_cascade(self, runner: CliRunner, mock_task, mock_enricher):
        """Test enriching with cascade flag to include subtasks."""
        child_task = MagicMock()
        child_task.id = "child-123"
        child_task.seq_num = 43
        child_task.title = "Child Task"
        child_task.is_enriched = False

        with (
            patch("gobby.cli.tasks.ai.get_task_manager") as mock_get_manager,
            patch("gobby.cli.tasks.ai.resolve_task_id", return_value=mock_task),
            patch("gobby.config.app.load_config") as mock_config,
            patch("gobby.llm.LLMService"),
            patch("gobby.tasks.enrich.TaskEnricher", return_value=mock_enricher),
        ):
            mock_manager = MagicMock()
            mock_manager.list_tasks.return_value = [child_task]
            mock_get_manager.return_value = mock_manager
            mock_config.return_value.gobby_tasks.enrichment.enabled = True

            mock_enricher.enrich.return_value = MagicMock(
                category="code",
                complexity_score=2,
            )

            result = runner.invoke(tasks, ["enrich", "#42", "--cascade"])

            assert result.exit_code == 0

    def test_enrich_with_force(self, runner: CliRunner, mock_enricher):
        """Test re-enriching with force flag."""
        already_enriched_task = MagicMock()
        already_enriched_task.id = "task-123"
        already_enriched_task.seq_num = 42
        already_enriched_task.title = "Already Enriched Task"
        already_enriched_task.is_enriched = True

        with (
            patch("gobby.cli.tasks.ai.get_task_manager") as mock_get_manager,
            patch("gobby.cli.tasks.ai.resolve_task_id", return_value=already_enriched_task),
            patch("gobby.config.app.load_config") as mock_config,
            patch("gobby.llm.LLMService"),
            patch("gobby.tasks.enrich.TaskEnricher", return_value=mock_enricher),
        ):
            mock_manager = MagicMock()
            mock_get_manager.return_value = mock_manager
            mock_config.return_value.gobby_tasks.enrichment.enabled = True

            mock_enricher.enrich.return_value = MagicMock(
                category="code",
                complexity_score=2,
            )

            result = runner.invoke(tasks, ["enrich", "#42", "--force"])

            assert result.exit_code == 0
            mock_enricher.enrich.assert_called()


class TestEnrichCommandErrors:
    """Tests for error handling in enrich command."""

    def test_enrich_task_not_found(self, runner: CliRunner):
        """Test error when task is not found."""
        with (
            patch("gobby.cli.tasks.ai.get_task_manager") as mock_get_manager,
            patch("gobby.cli.tasks.ai.resolve_task_id", return_value=None),
        ):
            mock_manager = MagicMock()
            mock_get_manager.return_value = mock_manager

            result = runner.invoke(tasks, ["enrich", "#999"])

            assert result.exit_code != 0 or "not found" in result.output.lower()

    def test_enrich_disabled_in_config(self, runner: CliRunner, mock_task):
        """Test error when enrichment is disabled in config."""
        with (
            patch("gobby.cli.tasks.ai.get_task_manager") as mock_get_manager,
            patch("gobby.cli.tasks.ai.resolve_task_id", return_value=mock_task),
            patch("gobby.config.app.load_config") as mock_config,
        ):
            mock_manager = MagicMock()
            mock_get_manager.return_value = mock_manager
            mock_config.return_value.gobby_tasks.enrichment.enabled = False

            result = runner.invoke(tasks, ["enrich", "#42"])

            assert "disabled" in result.output.lower() or result.exit_code != 0

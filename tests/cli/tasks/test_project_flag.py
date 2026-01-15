"""Tests for --project/-p flag on task CLI commands.

Tests verify the --project flag for specifying project context:
- enrich command with --project
- expand command with --project
- apply-tdd command with --project
"""

from unittest.mock import MagicMock, patch

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
    task.status = "open"
    task.is_enriched = False
    task.is_tdd_applied = False
    task.priority = 2
    return task


class TestEnrichProjectFlag:
    """Tests for enrich command --project flag."""

    def test_enrich_has_project_option(self, runner: CliRunner):
        """Test that enrich command has --project option."""
        result = runner.invoke(tasks, ["enrich", "--help"])
        assert result.exit_code == 0
        assert "--project" in result.output or "-p" in result.output

    def test_enrich_with_project_flag(self, runner: CliRunner, mock_task):
        """Test enrich with --project flag."""
        with (
            patch("gobby.cli.tasks.ai.get_task_manager") as mock_get_manager,
            patch("gobby.cli.tasks.ai.resolve_task_id", return_value=mock_task),
            patch("gobby.config.app.load_config") as mock_config,
            patch("gobby.llm.LLMService"),
            patch("gobby.tasks.enrich.TaskEnricher") as mock_enricher_cls,
        ):
            mock_manager = MagicMock()
            mock_get_manager.return_value = mock_manager
            mock_config.return_value.gobby_tasks.enrichment.enabled = True

            mock_enricher = MagicMock()
            mock_enricher.enrich = MagicMock()
            mock_enricher_cls.return_value = mock_enricher

            from gobby.tasks.enrich import EnrichmentResult

            async def mock_enrich(*args, **kwargs):
                return EnrichmentResult(
                    category="feature",
                    complexity_score=5,
                    validation_criteria="Test criteria",
                )

            mock_enricher.enrich = mock_enrich

            result = runner.invoke(tasks, ["enrich", "#42", "--project", "myproject"])

            # Command should succeed with --project flag
            assert result.exit_code == 0, f"--project flag failed: {result.output}"
            # Verify the enricher was invoked
            assert mock_enricher_cls.called, "TaskEnricher should be instantiated"


class TestExpandProjectFlag:
    """Tests for expand command --project flag."""

    def test_expand_has_project_option(self, runner: CliRunner):
        """Test that expand command has --project option."""
        result = runner.invoke(tasks, ["expand", "--help"])
        assert result.exit_code == 0
        assert "--project" in result.output or "-p" in result.output

    def test_expand_with_project_flag(self, runner: CliRunner, mock_task):
        """Test expand with --project flag."""
        with (
            patch("gobby.cli.tasks.ai.get_task_manager") as mock_get_manager,
            patch("gobby.cli.tasks.ai.resolve_task_id", return_value=mock_task),
            patch("gobby.config.app.load_config") as mock_config,
            patch("gobby.llm.LLMService"),
            patch("gobby.tasks.expansion.TaskExpander") as mock_expander_cls,
        ):
            mock_manager = MagicMock()
            mock_get_manager.return_value = mock_manager
            mock_config.return_value.gobby_tasks.expansion.enabled = True

            mock_expander = MagicMock()
            mock_expander_cls.return_value = mock_expander

            async def mock_expand(*args, **kwargs):
                return {"phases": []}

            mock_expander.expand_task = mock_expand

            result = runner.invoke(tasks, ["expand", "#42", "--project", "myproject"])

            # Command should succeed with --project flag
            assert result.exit_code == 0, f"--project flag failed: {result.output}"
            # Verify the expander was invoked
            assert mock_expander_cls.called, "TaskExpander should be instantiated"


class TestApplyTddProjectFlag:
    """Tests for apply-tdd command --project flag."""

    def test_apply_tdd_has_project_option(self, runner: CliRunner):
        """Test that apply-tdd command has --project option."""
        result = runner.invoke(tasks, ["apply-tdd", "--help"])
        assert result.exit_code == 0
        assert "--project" in result.output or "-p" in result.output

    def test_apply_tdd_with_project_flag(self, runner: CliRunner, mock_task):
        """Test apply-tdd with --project flag."""
        with (
            patch("gobby.cli.tasks.ai.get_task_manager") as mock_get_manager,
            patch("gobby.cli.tasks.ai.resolve_task_id", return_value=mock_task),
        ):
            mock_manager = MagicMock()
            mock_get_manager.return_value = mock_manager
            mock_manager.create_task.return_value = mock_task

            result = runner.invoke(tasks, ["apply-tdd", "#42", "--project", "myproject"])

            # The --project option should be recognized
            assert result.exit_code == 0 or "--project" not in result.output

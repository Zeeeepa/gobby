"""Tests for CLI pipeline commands.

TDD tests for the pipelines CLI group.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from gobby.cli import cli
from gobby.workflows.definitions import PipelineDefinition, PipelineStep
from gobby.workflows.loader import DiscoveredWorkflow

pytestmark = pytest.mark.unit


def pipelines_available() -> bool:
    """Check if pipelines command is registered in CLI."""
    try:
        return "pipelines" in cli.commands
    except Exception:
        return False


@pytest.fixture
def runner() -> CliRunner:
    """Create a CLI test runner."""
    return CliRunner()


@pytest.fixture
def mock_pipeline():
    """Create a mock pipeline definition."""
    return PipelineDefinition(
        name="deploy",
        description="Deploy to production",
        steps=[
            PipelineStep(id="build", exec="npm run build"),
            PipelineStep(id="test", exec="npm test"),
            PipelineStep(id="deploy", exec="npm run deploy"),
        ],
    )


@pytest.fixture
def mock_discovered_pipelines(mock_pipeline):
    """Create mock discovered pipelines."""
    pipeline2 = PipelineDefinition(
        name="test",
        description="Run test suite",
        steps=[PipelineStep(id="test", exec="pytest")],
    )
    return [
        DiscoveredWorkflow(
            name="deploy",
            definition=mock_pipeline,
            priority=100,
            is_project=True,
            path=Path("/project/.gobby/workflows/deploy.yaml"),
        ),
        DiscoveredWorkflow(
            name="test",
            definition=pipeline2,
            priority=50,
            is_project=False,
            path=Path("/home/user/.gobby/workflows/test.yaml"),
        ),
    ]


class TestPipelinesCLIRegistration:
    """Tests for pipelines CLI command registration."""

    def test_pipelines_command_exists(self, runner) -> None:
        """Verify pipelines command is registered."""
        result = runner.invoke(cli, ["pipelines", "--help"])

        if result.exit_code == 2 and "No such command 'pipelines'" in result.output:
            pytest.skip("pipelines CLI command not yet registered")

        assert result.exit_code == 0
        assert "pipelines" in result.output.lower()

    def test_pipelines_subcommands_exist(self, runner) -> None:
        """Verify expected subcommands are registered."""
        result = runner.invoke(cli, ["pipelines", "--help"])

        if result.exit_code == 2 and "No such command 'pipelines'" in result.output:
            pytest.skip("pipelines CLI command not yet registered")

        assert result.exit_code == 0
        assert "list" in result.output
        assert "show" in result.output


class TestPipelinesList:
    """Tests for gobby pipelines list command."""

    @pytest.mark.skipif(not pipelines_available(), reason="pipelines CLI not yet implemented")
    def test_list_discovers_pipelines(self, runner, mock_discovered_pipelines) -> None:
        """Verify 'gobby pipelines list' calls discover_pipeline_workflows."""
        mock_loader = MagicMock()
        mock_loader.discover_pipeline_workflows.return_value = mock_discovered_pipelines

        with patch("gobby.cli.pipelines.get_workflow_loader", return_value=mock_loader):
            result = runner.invoke(cli, ["pipelines", "list"])

            assert result.exit_code == 0
            mock_loader.discover_pipeline_workflows.assert_called_once()

    @pytest.mark.skipif(not pipelines_available(), reason="pipelines CLI not yet implemented")
    def test_list_outputs_pipeline_names(self, runner, mock_discovered_pipelines) -> None:
        """Verify list command outputs pipeline names."""
        mock_loader = MagicMock()
        mock_loader.discover_pipeline_workflows.return_value = mock_discovered_pipelines

        with patch("gobby.cli.pipelines.get_workflow_loader", return_value=mock_loader):
            result = runner.invoke(cli, ["pipelines", "list"])

            assert result.exit_code == 0
            assert "deploy" in result.output
            assert "test" in result.output

    @pytest.mark.skipif(not pipelines_available(), reason="pipelines CLI not yet implemented")
    def test_list_shows_descriptions(self, runner, mock_discovered_pipelines) -> None:
        """Verify list command shows pipeline descriptions."""
        mock_loader = MagicMock()
        mock_loader.discover_pipeline_workflows.return_value = mock_discovered_pipelines

        with patch("gobby.cli.pipelines.get_workflow_loader", return_value=mock_loader):
            result = runner.invoke(cli, ["pipelines", "list"])

            assert result.exit_code == 0
            assert "Deploy to production" in result.output

    @pytest.mark.skipif(not pipelines_available(), reason="pipelines CLI not yet implemented")
    def test_list_shows_source(self, runner, mock_discovered_pipelines) -> None:
        """Verify list command indicates project vs global source."""
        mock_loader = MagicMock()
        mock_loader.discover_pipeline_workflows.return_value = mock_discovered_pipelines

        with patch("gobby.cli.pipelines.get_workflow_loader", return_value=mock_loader):
            result = runner.invoke(cli, ["pipelines", "list"])

            assert result.exit_code == 0
            assert "project" in result.output.lower()

    @pytest.mark.skipif(not pipelines_available(), reason="pipelines CLI not yet implemented")
    def test_list_empty_result(self, runner) -> None:
        """Verify list handles no pipelines found."""
        mock_loader = MagicMock()
        mock_loader.discover_pipeline_workflows.return_value = []

        with patch("gobby.cli.pipelines.get_workflow_loader", return_value=mock_loader):
            result = runner.invoke(cli, ["pipelines", "list"])

            assert result.exit_code == 0
            assert "no pipeline" in result.output.lower() or result.output.strip() == ""

    @pytest.mark.skipif(not pipelines_available(), reason="pipelines CLI not yet implemented")
    def test_list_json_format(self, runner, mock_discovered_pipelines) -> None:
        """Verify list command supports --json output."""
        import json

        mock_loader = MagicMock()
        mock_loader.discover_pipeline_workflows.return_value = mock_discovered_pipelines

        with patch("gobby.cli.pipelines.get_workflow_loader", return_value=mock_loader):
            result = runner.invoke(cli, ["pipelines", "list", "--json"])

            assert result.exit_code == 0
            data = json.loads(result.output)
            assert "pipelines" in data
            assert len(data["pipelines"]) == 2


class TestPipelinesShow:
    """Tests for gobby pipelines show command."""

    @pytest.mark.skipif(not pipelines_available(), reason="pipelines CLI not yet implemented")
    def test_show_loads_pipeline(self, runner, mock_pipeline) -> None:
        """Verify 'gobby pipelines show <name>' loads the pipeline."""
        mock_loader = MagicMock()
        mock_loader.load_pipeline.return_value = mock_pipeline

        with patch("gobby.cli.pipelines.get_workflow_loader", return_value=mock_loader):
            result = runner.invoke(cli, ["pipelines", "show", "deploy"])

            assert result.exit_code == 0
            mock_loader.load_pipeline.assert_called_once_with("deploy")

    @pytest.mark.skipif(not pipelines_available(), reason="pipelines CLI not yet implemented")
    def test_show_outputs_pipeline_details(self, runner, mock_pipeline) -> None:
        """Verify show command outputs pipeline definition details."""
        mock_loader = MagicMock()
        mock_loader.load_pipeline.return_value = mock_pipeline

        with patch("gobby.cli.pipelines.get_workflow_loader", return_value=mock_loader):
            result = runner.invoke(cli, ["pipelines", "show", "deploy"])

            assert result.exit_code == 0
            assert "deploy" in result.output
            assert "Deploy to production" in result.output

    @pytest.mark.skipif(not pipelines_available(), reason="pipelines CLI not yet implemented")
    def test_show_outputs_steps(self, runner, mock_pipeline) -> None:
        """Verify show command outputs step information."""
        mock_loader = MagicMock()
        mock_loader.load_pipeline.return_value = mock_pipeline

        with patch("gobby.cli.pipelines.get_workflow_loader", return_value=mock_loader):
            result = runner.invoke(cli, ["pipelines", "show", "deploy"])

            assert result.exit_code == 0
            assert "build" in result.output
            assert "test" in result.output

    @pytest.mark.skipif(not pipelines_available(), reason="pipelines CLI not yet implemented")
    def test_show_not_found(self, runner) -> None:
        """Verify show returns error for nonexistent pipeline."""
        mock_loader = MagicMock()
        mock_loader.load_pipeline.return_value = None

        with patch("gobby.cli.pipelines.get_workflow_loader", return_value=mock_loader):
            result = runner.invoke(cli, ["pipelines", "show", "nonexistent"])

            assert result.exit_code != 0 or "not found" in result.output.lower()

    @pytest.mark.skipif(not pipelines_available(), reason="pipelines CLI not yet implemented")
    def test_show_json_format(self, runner, mock_pipeline) -> None:
        """Verify show command supports --json output."""
        import json

        mock_loader = MagicMock()
        mock_loader.load_pipeline.return_value = mock_pipeline

        with patch("gobby.cli.pipelines.get_workflow_loader", return_value=mock_loader):
            result = runner.invoke(cli, ["pipelines", "show", "deploy", "--json"])

            assert result.exit_code == 0
            data = json.loads(result.output)
            assert data["name"] == "deploy"
            assert "steps" in data

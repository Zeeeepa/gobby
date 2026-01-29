"""Tests for project CLI commands.

Tests cover:
- Listing projects (empty, with data, JSON format)
- Showing project details (by ID, by name, not found, JSON format)
"""

import json
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from gobby.cli import cli

pytestmark = pytest.mark.unit

@pytest.fixture
def runner() -> CliRunner:
    """Create a CLI test runner."""
    return CliRunner()


@pytest.fixture
def mock_project():
    """Create a mock project with common attributes."""
    project = MagicMock()
    project.id = "proj-abc123"
    project.name = "test-project"
    project.repo_path = "/home/user/projects/test-project"
    project.github_url = "https://github.com/user/test-project"
    project.github_repo = "user/test-project"
    project.created_at = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)
    project.updated_at = datetime(2024, 1, 15, 14, 30, 0, tzinfo=UTC)
    project.to_dict.return_value = {
        "id": "proj-abc123",
        "name": "test-project",
        "repo_path": "/home/user/projects/test-project",
        "github_url": "https://github.com/user/test-project",
        "github_repo": "user/test-project",
        "created_at": "2024-01-01T12:00:00+00:00",
        "updated_at": "2024-01-15T14:30:00+00:00",
    }
    return project


class TestListProjects:
    """Tests for gobby projects list command."""

    @patch("gobby.cli.projects.get_project_manager")
    def test_list_projects_empty(
        self,
        mock_get_manager: MagicMock,
        runner: CliRunner,
    ) -> None:
        """Test list with no projects found."""
        mock_manager = MagicMock()
        mock_manager.list.return_value = []
        mock_get_manager.return_value = mock_manager

        result = runner.invoke(cli, ["projects", "list"])

        assert result.exit_code == 0
        assert "No projects found" in result.output
        assert "gobby init" in result.output

    @patch("gobby.cli.projects.get_project_manager")
    def test_list_projects_with_data(
        self,
        mock_get_manager: MagicMock,
        runner: CliRunner,
        mock_project: MagicMock,
    ) -> None:
        """Test list with multiple projects."""
        project2 = MagicMock()
        project2.id = "proj-def456"
        project2.name = "another-project"
        project2.repo_path = "/home/user/projects/another"

        mock_manager = MagicMock()
        mock_manager.list.return_value = [mock_project, project2]
        mock_get_manager.return_value = mock_manager

        result = runner.invoke(cli, ["projects", "list"])

        assert result.exit_code == 0
        assert "Found 2 project(s)" in result.output
        assert "test-project" in result.output
        assert "another-project" in result.output

    @patch("gobby.cli.projects.get_project_manager")
    def test_list_projects_json(
        self,
        mock_get_manager: MagicMock,
        runner: CliRunner,
        mock_project: MagicMock,
    ) -> None:
        """Test list with JSON output format."""
        mock_manager = MagicMock()
        mock_manager.list.return_value = [mock_project]
        mock_get_manager.return_value = mock_manager

        result = runner.invoke(cli, ["projects", "list", "--json"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert len(output) == 1
        assert output[0]["name"] == "test-project"

    @patch("gobby.cli.projects.get_project_manager")
    def test_list_projects_without_repo_path(
        self,
        mock_get_manager: MagicMock,
        runner: CliRunner,
    ) -> None:
        """Test list with project that has no repo_path."""
        project = MagicMock()
        project.id = "proj-no-path"
        project.name = "no-path-project"
        project.repo_path = None

        mock_manager = MagicMock()
        mock_manager.list.return_value = [project]
        mock_get_manager.return_value = mock_manager

        result = runner.invoke(cli, ["projects", "list"])

        assert result.exit_code == 0
        assert "no-path-project" in result.output


class TestShowProject:
    """Tests for gobby projects show command."""

    @patch("gobby.cli.projects.get_project_manager")
    def test_show_project_by_id(
        self,
        mock_get_manager: MagicMock,
        runner: CliRunner,
        mock_project: MagicMock,
    ) -> None:
        """Test showing project by UUID."""
        mock_manager = MagicMock()
        mock_manager.get.return_value = mock_project
        mock_get_manager.return_value = mock_manager

        result = runner.invoke(cli, ["projects", "show", "proj-abc123"])

        assert result.exit_code == 0
        assert "Project: test-project" in result.output
        assert "ID: proj-abc123" in result.output
        assert "Path:" in result.output
        assert "GitHub:" in result.output
        assert "Repo:" in result.output

    @patch("gobby.cli.projects.get_project_manager")
    def test_show_project_by_name(
        self,
        mock_get_manager: MagicMock,
        runner: CliRunner,
        mock_project: MagicMock,
    ) -> None:
        """Test showing project by name when ID lookup fails."""
        mock_manager = MagicMock()
        mock_manager.get.return_value = None  # ID lookup fails
        mock_manager.get_by_name.return_value = mock_project  # Name lookup succeeds
        mock_get_manager.return_value = mock_manager

        result = runner.invoke(cli, ["projects", "show", "test-project"])

        assert result.exit_code == 0
        assert "Project: test-project" in result.output
        mock_manager.get_by_name.assert_called_once_with("test-project")

    @patch("gobby.cli.projects.get_project_manager")
    def test_show_project_not_found(
        self,
        mock_get_manager: MagicMock,
        runner: CliRunner,
    ) -> None:
        """Test showing project when not found."""
        mock_manager = MagicMock()
        mock_manager.get.return_value = None
        mock_manager.get_by_name.return_value = None
        mock_get_manager.return_value = mock_manager

        result = runner.invoke(cli, ["projects", "show", "nonexistent"])

        assert result.exit_code == 1
        assert "Project not found: nonexistent" in result.output

    @patch("gobby.cli.projects.get_project_manager")
    def test_show_project_json(
        self,
        mock_get_manager: MagicMock,
        runner: CliRunner,
        mock_project: MagicMock,
    ) -> None:
        """Test showing project with JSON output format."""
        mock_manager = MagicMock()
        mock_manager.get.return_value = mock_project
        mock_get_manager.return_value = mock_manager

        result = runner.invoke(cli, ["projects", "show", "proj-abc123", "--json"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["name"] == "test-project"
        assert output["id"] == "proj-abc123"

    @patch("gobby.cli.projects.get_project_manager")
    def test_show_project_minimal_info(
        self,
        mock_get_manager: MagicMock,
        runner: CliRunner,
    ) -> None:
        """Test showing project with minimal information (no github)."""
        project = MagicMock()
        project.id = "proj-minimal"
        project.name = "minimal-project"
        project.repo_path = "/home/user/minimal"
        project.github_url = None
        project.github_repo = None
        project.created_at = datetime(2024, 1, 1, tzinfo=UTC)
        project.updated_at = datetime(2024, 1, 1, tzinfo=UTC)

        mock_manager = MagicMock()
        mock_manager.get.return_value = project
        mock_get_manager.return_value = mock_manager

        result = runner.invoke(cli, ["projects", "show", "proj-minimal"])

        assert result.exit_code == 0
        assert "Project: minimal-project" in result.output
        # Should not show GitHub fields
        assert "GitHub:" not in result.output
        assert "Repo:" not in result.output

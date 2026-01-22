"""Tests for the skills CLI module (TDD - written before implementation)."""

from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from gobby.cli import cli


class TestSkillsCommandGroup:
    """Tests for gobby skills command group."""

    @pytest.fixture
    def runner(self) -> CliRunner:
        """Create a CLI test runner."""
        return CliRunner()

    def test_skills_group_exists(self, runner: CliRunner):
        """Test that skills command group is registered."""
        result = runner.invoke(cli, ["skills", "--help"])
        assert result.exit_code == 0
        assert "skills" in result.output.lower() or "skill" in result.output.lower()

    def test_skills_help_shows_commands(self, runner: CliRunner):
        """Test that --help shows available subcommands."""
        result = runner.invoke(cli, ["skills", "--help"])
        assert result.exit_code == 0
        # Should show at least these commands
        assert "list" in result.output
        assert "show" in result.output


class TestSkillsListCommand:
    """Tests for gobby skills list command."""

    @pytest.fixture
    def runner(self) -> CliRunner:
        """Create a CLI test runner."""
        return CliRunner()

    def test_list_help(self, runner: CliRunner):
        """Test skills list --help."""
        result = runner.invoke(cli, ["skills", "list", "--help"])
        assert result.exit_code == 0
        assert "List" in result.output or "list" in result.output

    def test_list_help_shows_json_flag(self, runner: CliRunner):
        """Test skills list --help shows --json flag."""
        result = runner.invoke(cli, ["skills", "list", "--help"])
        assert result.exit_code == 0
        assert "--json" in result.output

    def test_list_help_shows_tags_flag(self, runner: CliRunner):
        """Test skills list --help shows --tags flag."""
        result = runner.invoke(cli, ["skills", "list", "--help"])
        assert result.exit_code == 0
        assert "--tags" in result.output

    @patch("gobby.cli.skills.get_skill_storage")
    def test_list_no_skills(self, mock_get_storage: MagicMock, runner: CliRunner):
        """Test listing skills when none exist."""
        mock_storage = MagicMock()
        mock_storage.list_skills.return_value = []
        mock_get_storage.return_value = mock_storage

        result = runner.invoke(cli, ["skills", "list"])

        assert result.exit_code == 0
        assert "No skills found" in result.output

    @patch("gobby.cli.skills.get_skill_storage")
    def test_list_with_skills(self, mock_get_storage: MagicMock, runner: CliRunner):
        """Test listing skills with results."""
        mock_storage = MagicMock()
        mock_skill = MagicMock()
        mock_skill.name = "test-skill"
        mock_skill.description = "A test skill"
        mock_skill.enabled = True
        mock_skill.metadata = None
        mock_storage.list_skills.return_value = [mock_skill]
        mock_get_storage.return_value = mock_storage

        result = runner.invoke(cli, ["skills", "list"])

        assert result.exit_code == 0
        assert "test-skill" in result.output

    @patch("gobby.cli.skills.get_skill_storage")
    def test_list_json_output(self, mock_get_storage: MagicMock, runner: CliRunner):
        """Test listing skills with JSON output."""
        import json

        mock_storage = MagicMock()
        mock_skill = MagicMock()
        mock_skill.name = "test-skill"
        mock_skill.description = "A test skill"
        mock_skill.enabled = True
        mock_skill.version = "1.0.0"
        mock_skill.metadata = {"skillport": {"category": "test", "tags": ["tag1"]}}
        mock_storage.list_skills.return_value = [mock_skill]
        mock_get_storage.return_value = mock_storage

        result = runner.invoke(cli, ["skills", "list", "--json"])

        assert result.exit_code == 0
        # Parse JSON output
        data = json.loads(result.output)
        assert len(data) == 1
        assert data[0]["name"] == "test-skill"
        assert data[0]["category"] == "test"
        assert data[0]["tags"] == ["tag1"]

    @patch("gobby.cli.skills.get_skill_storage")
    def test_list_empty_json_output(self, mock_get_storage: MagicMock, runner: CliRunner):
        """Test listing no skills with JSON output."""
        import json

        mock_storage = MagicMock()
        mock_storage.list_skills.return_value = []
        mock_get_storage.return_value = mock_storage

        result = runner.invoke(cli, ["skills", "list", "--json"])

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data == []

    @patch("gobby.cli.skills.get_skill_storage")
    def test_list_with_tags_filter(self, mock_get_storage: MagicMock, runner: CliRunner):
        """Test listing skills with tags filter."""
        mock_storage = MagicMock()
        mock_skill1 = MagicMock()
        mock_skill1.name = "skill-with-tag"
        mock_skill1.description = "Has matching tag"
        mock_skill1.enabled = True
        mock_skill1.metadata = {"skillport": {"tags": ["git", "workflow"]}}

        mock_skill2 = MagicMock()
        mock_skill2.name = "skill-no-tag"
        mock_skill2.description = "No matching tag"
        mock_skill2.enabled = True
        mock_skill2.metadata = {"skillport": {"tags": ["other"]}}

        mock_storage.list_skills.return_value = [mock_skill1, mock_skill2]
        mock_get_storage.return_value = mock_storage

        result = runner.invoke(cli, ["skills", "list", "--tags", "git"])

        assert result.exit_code == 0
        assert "skill-with-tag" in result.output
        assert "skill-no-tag" not in result.output

    @patch("gobby.cli.skills.get_skill_storage")
    def test_list_with_category_display(self, mock_get_storage: MagicMock, runner: CliRunner):
        """Test that category is displayed in list output."""
        mock_storage = MagicMock()
        mock_skill = MagicMock()
        mock_skill.name = "test-skill"
        mock_skill.description = "A test skill"
        mock_skill.enabled = True
        mock_skill.metadata = {"skillport": {"category": "git"}}
        mock_storage.list_skills.return_value = [mock_skill]
        mock_get_storage.return_value = mock_storage

        result = runner.invoke(cli, ["skills", "list"])

        assert result.exit_code == 0
        assert "[git]" in result.output


class TestSkillsShowCommand:
    """Tests for gobby skills show command."""

    @pytest.fixture
    def runner(self) -> CliRunner:
        """Create a CLI test runner."""
        return CliRunner()

    def test_show_help(self, runner: CliRunner):
        """Test skills show --help."""
        result = runner.invoke(cli, ["skills", "show", "--help"])
        assert result.exit_code == 0
        assert "Show" in result.output or "show" in result.output

    @patch("gobby.cli.skills.get_skill_storage")
    def test_show_not_found(self, mock_get_storage: MagicMock, runner: CliRunner):
        """Test showing non-existent skill."""
        mock_storage = MagicMock()
        mock_storage.get_by_name.return_value = None
        mock_get_storage.return_value = mock_storage

        result = runner.invoke(cli, ["skills", "show", "nonexistent"])

        assert result.exit_code == 0
        assert "not found" in result.output.lower()

    @patch("gobby.cli.skills.get_skill_storage")
    def test_show_success(self, mock_get_storage: MagicMock, runner: CliRunner):
        """Test showing an existing skill."""
        mock_storage = MagicMock()
        mock_skill = MagicMock()
        mock_skill.id = "skl-123"
        mock_skill.name = "test-skill"
        mock_skill.description = "A test skill for demonstration"
        mock_skill.version = "1.0.0"
        mock_skill.license = "MIT"
        mock_skill.enabled = True
        mock_skill.source_path = "/path/to/skill"
        mock_skill.source_type = "local"
        mock_skill.content = "# Test Skill\n\nInstructions here."
        mock_storage.get_by_name.return_value = mock_skill
        mock_get_storage.return_value = mock_storage

        result = runner.invoke(cli, ["skills", "show", "test-skill"])

        assert result.exit_code == 0
        assert "test-skill" in result.output
        assert "A test skill for demonstration" in result.output

    def test_show_help_shows_json_flag(self, runner: CliRunner):
        """Test skills show --help shows --json flag."""
        result = runner.invoke(cli, ["skills", "show", "--help"])
        assert result.exit_code == 0
        assert "--json" in result.output

    @patch("gobby.cli.skills.get_skill_storage")
    def test_show_json_output(self, mock_get_storage: MagicMock, runner: CliRunner):
        """Test showing skill with JSON output."""
        import json

        mock_storage = MagicMock()
        mock_skill = MagicMock()
        mock_skill.id = "skl-123"
        mock_skill.name = "test-skill"
        mock_skill.description = "A test skill for demonstration"
        mock_skill.version = "1.0.0"
        mock_skill.license = "MIT"
        mock_skill.enabled = True
        mock_skill.source_path = "/path/to/skill"
        mock_skill.source_type = "local"
        mock_skill.compatibility = "Requires Python 3.11+"
        mock_skill.content = "# Test Skill\n\nInstructions here."
        mock_skill.metadata = {"skillport": {"category": "test", "tags": ["demo"]}}
        mock_storage.get_by_name.return_value = mock_skill
        mock_get_storage.return_value = mock_storage

        result = runner.invoke(cli, ["skills", "show", "test-skill", "--json"])

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["name"] == "test-skill"
        assert data["description"] == "A test skill for demonstration"
        assert data["version"] == "1.0.0"
        assert data["license"] == "MIT"
        assert data["enabled"] is True
        assert data["content"] == "# Test Skill\n\nInstructions here."
        assert data["category"] == "test"
        assert data["tags"] == ["demo"]

    @patch("gobby.cli.skills.get_skill_storage")
    def test_show_json_not_found(self, mock_get_storage: MagicMock, runner: CliRunner):
        """Test showing non-existent skill with JSON output."""
        import json

        mock_storage = MagicMock()
        mock_storage.get_by_name.return_value = None
        mock_get_storage.return_value = mock_storage

        result = runner.invoke(cli, ["skills", "show", "nonexistent", "--json"])

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["error"] == "Skill not found"
        assert data["name"] == "nonexistent"


class TestSkillsInstallCommand:
    """Tests for gobby skills install command."""

    @pytest.fixture
    def runner(self) -> CliRunner:
        """Create a CLI test runner."""
        return CliRunner()

    def test_install_help(self, runner: CliRunner):
        """Test skills install --help."""
        result = runner.invoke(cli, ["skills", "install", "--help"])
        assert result.exit_code == 0
        assert "Install" in result.output or "install" in result.output

    def test_install_help_shows_project_flag(self, runner: CliRunner):
        """Test skills install --help shows --project flag."""
        result = runner.invoke(cli, ["skills", "install", "--help"])
        assert result.exit_code == 0
        assert "--project" in result.output

    def test_install_requires_source(self, runner: CliRunner):
        """Test that install requires source argument."""
        result = runner.invoke(cli, ["skills", "install"])
        # Should show missing argument error
        assert result.exit_code != 0

    @patch("gobby.cli.skills.get_skill_storage")
    @patch("gobby.skills.loader.SkillLoader")
    def test_install_from_local_path(
        self, mock_loader_class: MagicMock, mock_get_storage: MagicMock, runner: CliRunner
    ):
        """Test installing from a local directory path."""
        mock_storage = MagicMock()
        mock_skill = MagicMock()
        mock_skill.name = "test-skill"
        mock_storage.create_skill.return_value = mock_skill
        mock_get_storage.return_value = mock_storage

        mock_loader = MagicMock()
        mock_parsed = MagicMock()
        mock_parsed.name = "test-skill"
        mock_parsed.description = "A test skill"
        mock_parsed.content = "# Test"
        mock_parsed.version = "1.0.0"
        mock_parsed.license = "MIT"
        mock_parsed.compatibility = None
        mock_parsed.allowed_tools = None
        mock_parsed.metadata = None
        mock_parsed.source_path = "/path/to/skill"
        mock_loader.load_skill.return_value = mock_parsed
        mock_loader_class.return_value = mock_loader

        with runner.isolated_filesystem():
            import os

            os.makedirs("my-skill")
            with open("my-skill/SKILL.md", "w") as f:
                f.write("---\nname: test-skill\ndescription: A test skill\n---\n# Test")

            result = runner.invoke(cli, ["skills", "install", "my-skill"])

        assert result.exit_code == 0
        assert "Installed skill: test-skill" in result.output
        mock_storage.create_skill.assert_called_once()

    @patch("gobby.cli.skills.get_skill_storage")
    @patch("gobby.skills.loader.SkillLoader")
    def test_install_from_github(
        self, mock_loader_class: MagicMock, mock_get_storage: MagicMock, runner: CliRunner
    ):
        """Test installing from a GitHub URL."""
        mock_storage = MagicMock()
        mock_skill = MagicMock()
        mock_skill.name = "github-skill"
        mock_storage.create_skill.return_value = mock_skill
        mock_get_storage.return_value = mock_storage

        mock_loader = MagicMock()
        mock_parsed = MagicMock()
        mock_parsed.name = "github-skill"
        mock_parsed.description = "A GitHub skill"
        mock_parsed.content = "# GitHub"
        mock_parsed.version = "2.0.0"
        mock_parsed.license = "Apache-2.0"
        mock_parsed.compatibility = None
        mock_parsed.allowed_tools = None
        mock_parsed.metadata = None
        mock_parsed.source_path = "github:owner/repo"
        mock_loader.load_from_github.return_value = mock_parsed
        mock_loader_class.return_value = mock_loader

        result = runner.invoke(cli, ["skills", "install", "github:owner/repo"])

        assert result.exit_code == 0
        assert "Installed skill: github-skill" in result.output
        assert "github" in result.output.lower()
        mock_loader.load_from_github.assert_called_once_with("github:owner/repo")

    @patch("gobby.cli.skills.get_skill_storage")
    @patch("gobby.skills.loader.SkillLoader")
    def test_install_with_project_flag(
        self, mock_loader_class: MagicMock, mock_get_storage: MagicMock, runner: CliRunner
    ):
        """Test installing with --project flag scopes to project."""
        mock_storage = MagicMock()
        mock_skill = MagicMock()
        mock_skill.name = "project-skill"
        mock_storage.create_skill.return_value = mock_skill
        mock_get_storage.return_value = mock_storage

        mock_loader = MagicMock()
        mock_parsed = MagicMock()
        mock_parsed.name = "project-skill"
        mock_parsed.description = "A project skill"
        mock_parsed.content = "# Project"
        mock_parsed.version = "1.0.0"
        mock_parsed.license = None
        mock_parsed.compatibility = None
        mock_parsed.allowed_tools = None
        mock_parsed.metadata = None
        mock_parsed.source_path = "/path/to/skill"
        mock_loader.load_from_github.return_value = mock_parsed
        mock_loader_class.return_value = mock_loader

        result = runner.invoke(
            cli, ["skills", "install", "github:owner/repo", "--project", "my-project"]
        )

        assert result.exit_code == 0
        # Verify create_skill was called with project_id
        call_kwargs = mock_storage.create_skill.call_args[1]
        assert call_kwargs["project_id"] == "my-project"

    def test_install_source_not_found(self, runner: CliRunner):
        """Test installing from non-existent source."""
        result = runner.invoke(cli, ["skills", "install", "/nonexistent/path/to/skill"])

        assert result.exit_code == 0
        assert "not found" in result.output.lower() or "error" in result.output.lower()


class TestSkillsUpdateCommand:
    """Tests for gobby skills update command."""

    @pytest.fixture
    def runner(self) -> CliRunner:
        """Create a CLI test runner."""
        return CliRunner()

    def test_update_help(self, runner: CliRunner):
        """Test skills update --help."""
        result = runner.invoke(cli, ["skills", "update", "--help"])
        assert result.exit_code == 0
        assert "Update" in result.output or "update" in result.output

    def test_update_help_shows_all_flag(self, runner: CliRunner):
        """Test skills update --help shows --all flag."""
        result = runner.invoke(cli, ["skills", "update", "--help"])
        assert result.exit_code == 0
        assert "--all" in result.output

    @patch("gobby.cli.skills.get_skill_storage")
    @patch("gobby.skills.loader.SkillLoader")
    def test_update_single_skill(
        self, mock_loader_class: MagicMock, mock_get_storage: MagicMock, runner: CliRunner
    ):
        """Test updating a single skill by name."""
        mock_storage = MagicMock()
        mock_skill = MagicMock()
        mock_skill.id = "skl-123"
        mock_skill.name = "test-skill"
        mock_skill.source_type = "github"
        mock_skill.source_path = "github:owner/repo"
        mock_storage.get_by_name.return_value = mock_skill
        mock_get_storage.return_value = mock_storage

        mock_loader = MagicMock()
        mock_parsed = MagicMock()
        mock_parsed.content = "# Updated content"
        mock_parsed.description = "Updated description"
        mock_parsed.version = "2.0.0"
        mock_parsed.metadata = {"updated": True}
        mock_loader.load_from_github.return_value = mock_parsed
        mock_loader_class.return_value = mock_loader

        result = runner.invoke(cli, ["skills", "update", "test-skill"])

        assert result.exit_code == 0
        assert "Updated" in result.output or "updated" in result.output
        mock_storage.get_by_name.assert_called_once_with("test-skill")
        mock_storage.update_skill.assert_called_once()

    @patch("gobby.cli.skills.get_skill_storage")
    def test_update_skill_not_found(self, mock_get_storage: MagicMock, runner: CliRunner):
        """Test updating a non-existent skill."""
        mock_storage = MagicMock()
        mock_storage.get_by_name.return_value = None
        mock_get_storage.return_value = mock_storage

        result = runner.invoke(cli, ["skills", "update", "nonexistent"])

        assert result.exit_code == 0
        assert "not found" in result.output.lower()

    @patch("gobby.cli.skills.get_skill_storage")
    @patch("gobby.skills.loader.SkillLoader")
    def test_update_all_skills(
        self, mock_loader_class: MagicMock, mock_get_storage: MagicMock, runner: CliRunner
    ):
        """Test updating all skills with --all flag."""
        mock_storage = MagicMock()
        mock_skill1 = MagicMock()
        mock_skill1.id = "skl-1"
        mock_skill1.name = "skill-1"
        mock_skill1.source_type = "github"
        mock_skill1.source_path = "github:owner/repo1"
        mock_skill2 = MagicMock()
        mock_skill2.id = "skl-2"
        mock_skill2.name = "skill-2"
        mock_skill2.source_type = "local"
        mock_skill2.source_path = "/path/to/skill"
        mock_storage.list_skills.return_value = [mock_skill1, mock_skill2]
        mock_get_storage.return_value = mock_storage

        mock_loader = MagicMock()
        mock_parsed = MagicMock()
        mock_parsed.content = "# Updated"
        mock_parsed.description = "Updated"
        mock_parsed.version = "2.0.0"
        mock_parsed.metadata = {}
        mock_loader.load_from_github.return_value = mock_parsed
        mock_loader_class.return_value = mock_loader

        result = runner.invoke(cli, ["skills", "update", "--all"])

        assert result.exit_code == 0
        mock_storage.list_skills.assert_called_once()
        # One GitHub skill updated, one local skipped
        assert "Updated" in result.output or "updated" in result.output
        assert "Skipped" in result.output or "skipped" in result.output

    @patch("gobby.cli.skills.get_skill_storage")
    def test_update_local_skill_skipped(self, mock_get_storage: MagicMock, runner: CliRunner):
        """Test that local skills without remote source are skipped."""
        mock_storage = MagicMock()
        mock_skill = MagicMock()
        mock_skill.name = "local-skill"
        mock_skill.source_type = "local"
        mock_skill.source_path = "/some/local/path"
        mock_storage.get_by_name.return_value = mock_skill
        mock_get_storage.return_value = mock_storage

        result = runner.invoke(cli, ["skills", "update", "local-skill"])

        assert result.exit_code == 0
        # Local skills can't be updated from remote
        assert (
            "skip" in result.output.lower()
            or "cannot" in result.output.lower()
            or "local" in result.output.lower()
        )


class TestSkillsRemoveCommand:
    """Tests for gobby skills remove command."""

    @pytest.fixture
    def runner(self) -> CliRunner:
        """Create a CLI test runner."""
        return CliRunner()

    def test_remove_help(self, runner: CliRunner):
        """Test skills remove --help."""
        result = runner.invoke(cli, ["skills", "remove", "--help"])
        assert result.exit_code == 0
        assert "Remove" in result.output or "remove" in result.output

    @patch("gobby.cli.skills.get_skill_storage")
    def test_remove_not_found(self, mock_get_storage: MagicMock, runner: CliRunner):
        """Test removing non-existent skill."""
        mock_storage = MagicMock()
        mock_storage.get_by_name.return_value = None
        mock_get_storage.return_value = mock_storage

        result = runner.invoke(cli, ["skills", "remove", "nonexistent"])

        assert result.exit_code == 0
        assert "not found" in result.output.lower()

    @patch("gobby.cli.skills.get_skill_storage")
    def test_remove_success(self, mock_get_storage: MagicMock, runner: CliRunner):
        """Test removing an existing skill."""
        mock_storage = MagicMock()
        mock_skill = MagicMock()
        mock_skill.id = "skl-123"
        mock_skill.name = "test-skill"
        mock_storage.get_by_name.return_value = mock_skill
        mock_get_storage.return_value = mock_storage

        result = runner.invoke(cli, ["skills", "remove", "test-skill"])

        assert result.exit_code == 0
        assert "Removed" in result.output or "removed" in result.output
        mock_storage.delete_skill.assert_called_once_with("skl-123")

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

    def test_install_requires_source(self, runner: CliRunner):
        """Test that install requires source argument."""
        result = runner.invoke(cli, ["skills", "install"])
        # Should show missing argument error
        assert result.exit_code != 0


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

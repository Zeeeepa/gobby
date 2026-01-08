"""Comprehensive tests for the CLI init command module."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from gobby.cli import cli
from gobby.cli.init import init
from gobby.utils.project_init import InitResult, VerificationCommands


@pytest.fixture
def runner() -> CliRunner:
    """Create a CLI test runner."""
    return CliRunner()


@pytest.fixture
def mock_config() -> MagicMock:
    """Create a mock configuration."""
    config = MagicMock()
    config.logging.client = "/tmp/logs/client.log"
    return config


@pytest.fixture
def mock_init_result_new() -> InitResult:
    """Create a mock InitResult for a new project."""
    return InitResult(
        project_id="proj-abc123",
        project_name="my-test-project",
        project_path="/tmp/my-test-project",
        created_at="2024-01-15T10:00:00Z",
        already_existed=False,
        verification=None,
    )


@pytest.fixture
def mock_init_result_existing() -> InitResult:
    """Create a mock InitResult for an existing project."""
    return InitResult(
        project_id="proj-existing-456",
        project_name="existing-project",
        project_path="/tmp/existing-project",
        created_at="2024-01-01T00:00:00Z",
        already_existed=True,
        verification=None,
    )


@pytest.fixture
def mock_init_result_with_verification() -> InitResult:
    """Create a mock InitResult with verification commands."""
    verification = VerificationCommands(
        unit_tests="uv run pytest tests/ -v",
        type_check="uv run mypy src/",
        lint="uv run ruff check src/",
        integration=None,
        custom={"e2e": "uv run pytest tests/e2e/"},
    )
    return InitResult(
        project_id="proj-verified-789",
        project_name="verified-project",
        project_path="/tmp/verified-project",
        created_at="2024-01-15T10:00:00Z",
        already_existed=False,
        verification=verification,
    )


class TestInitCommandBasic:
    """Basic tests for the init command."""

    def test_init_help(self, runner: CliRunner):
        """Test init --help displays help text."""
        result = runner.invoke(cli, ["init", "--help"])
        assert result.exit_code == 0
        assert "Initialize a new Gobby project" in result.output
        assert "--name" in result.output
        assert "--github-url" in result.output

    def test_init_command_directly(self, runner: CliRunner):
        """Test invoking init command directly."""
        result = runner.invoke(init, ["--help"])
        assert result.exit_code == 0
        assert "Initialize a new Gobby project" in result.output


class TestInitNewProject:
    """Tests for initializing a new project."""

    @patch("gobby.cli.init.initialize_project")
    @patch("gobby.cli.load_config")
    def test_init_new_project_success(
        self,
        mock_load_config: MagicMock,
        mock_initialize: MagicMock,
        runner: CliRunner,
        mock_config: MagicMock,
        mock_init_result_new: InitResult,
        temp_dir: Path,
    ):
        """Test successful initialization of a new project."""
        mock_load_config.return_value = mock_config
        mock_initialize.return_value = mock_init_result_new

        with runner.isolated_filesystem(temp_dir=str(temp_dir)):
            result = runner.invoke(cli, ["init"])

        assert result.exit_code == 0
        assert "Initialized project" in result.output
        assert mock_init_result_new.project_name in result.output
        assert mock_init_result_new.project_id in result.output
        assert "Config:" in result.output
        mock_initialize.assert_called_once()

    @patch("gobby.cli.init.initialize_project")
    @patch("gobby.cli.load_config")
    def test_init_with_custom_name(
        self,
        mock_load_config: MagicMock,
        mock_initialize: MagicMock,
        runner: CliRunner,
        mock_config: MagicMock,
        mock_init_result_new: InitResult,
        temp_dir: Path,
    ):
        """Test initialization with a custom project name."""
        mock_load_config.return_value = mock_config
        mock_initialize.return_value = mock_init_result_new

        with runner.isolated_filesystem(temp_dir=str(temp_dir)):
            result = runner.invoke(cli, ["init", "--name", "custom-name"])

        assert result.exit_code == 0
        # Verify the name was passed to initialize_project
        call_kwargs = mock_initialize.call_args
        assert call_kwargs.kwargs.get("name") == "custom-name" or call_kwargs[1].get("name") == "custom-name"

    @patch("gobby.cli.init.initialize_project")
    @patch("gobby.cli.load_config")
    def test_init_with_github_url(
        self,
        mock_load_config: MagicMock,
        mock_initialize: MagicMock,
        runner: CliRunner,
        mock_config: MagicMock,
        mock_init_result_new: InitResult,
        temp_dir: Path,
    ):
        """Test initialization with a GitHub URL."""
        mock_load_config.return_value = mock_config
        mock_initialize.return_value = mock_init_result_new

        github_url = "https://github.com/myorg/myrepo"

        with runner.isolated_filesystem(temp_dir=str(temp_dir)):
            result = runner.invoke(cli, ["init", "--github-url", github_url])

        assert result.exit_code == 0
        # Verify the github_url was passed to initialize_project
        call_kwargs = mock_initialize.call_args
        assert (
            call_kwargs.kwargs.get("github_url") == github_url
            or call_kwargs[1].get("github_url") == github_url
        )

    @patch("gobby.cli.init.initialize_project")
    @patch("gobby.cli.load_config")
    def test_init_with_both_options(
        self,
        mock_load_config: MagicMock,
        mock_initialize: MagicMock,
        runner: CliRunner,
        mock_config: MagicMock,
        mock_init_result_new: InitResult,
        temp_dir: Path,
    ):
        """Test initialization with both name and github-url options."""
        mock_load_config.return_value = mock_config
        mock_initialize.return_value = mock_init_result_new

        with runner.isolated_filesystem(temp_dir=str(temp_dir)):
            result = runner.invoke(
                cli,
                [
                    "init",
                    "--name",
                    "my-custom-project",
                    "--github-url",
                    "https://github.com/test/repo",
                ],
            )

        assert result.exit_code == 0
        call_kwargs = mock_initialize.call_args
        # Check both positional and keyword arg forms
        assert (
            call_kwargs.kwargs.get("name") == "my-custom-project"
            or call_kwargs[1].get("name") == "my-custom-project"
        )


class TestInitExistingProject:
    """Tests for initializing when a project already exists."""

    @patch("gobby.cli.init.initialize_project")
    @patch("gobby.cli.load_config")
    def test_init_existing_project(
        self,
        mock_load_config: MagicMock,
        mock_initialize: MagicMock,
        runner: CliRunner,
        mock_config: MagicMock,
        mock_init_result_existing: InitResult,
        temp_dir: Path,
    ):
        """Test initializing when project already exists."""
        mock_load_config.return_value = mock_config
        mock_initialize.return_value = mock_init_result_existing

        with runner.isolated_filesystem(temp_dir=str(temp_dir)):
            result = runner.invoke(cli, ["init"])

        assert result.exit_code == 0
        assert "already initialized" in result.output.lower()
        assert mock_init_result_existing.project_name in result.output
        assert mock_init_result_existing.project_id in result.output
        # Should NOT show "Config:" for already existing projects
        assert "Config:" not in result.output


class TestInitWithVerification:
    """Tests for initialization with verification commands."""

    @patch("gobby.cli.init.initialize_project")
    @patch("gobby.cli.load_config")
    def test_init_shows_verification_commands(
        self,
        mock_load_config: MagicMock,
        mock_initialize: MagicMock,
        runner: CliRunner,
        mock_config: MagicMock,
        mock_init_result_with_verification: InitResult,
        temp_dir: Path,
    ):
        """Test that verification commands are displayed."""
        mock_load_config.return_value = mock_config
        mock_initialize.return_value = mock_init_result_with_verification

        with runner.isolated_filesystem(temp_dir=str(temp_dir)):
            result = runner.invoke(cli, ["init"])

        assert result.exit_code == 0
        assert "Detected verification commands:" in result.output
        assert "unit_tests:" in result.output
        assert "uv run pytest tests/ -v" in result.output
        assert "type_check:" in result.output
        assert "uv run mypy src/" in result.output
        assert "lint:" in result.output
        assert "uv run ruff check src/" in result.output

    @patch("gobby.cli.init.initialize_project")
    @patch("gobby.cli.load_config")
    def test_init_shows_custom_verification_commands(
        self,
        mock_load_config: MagicMock,
        mock_initialize: MagicMock,
        runner: CliRunner,
        mock_config: MagicMock,
        mock_init_result_with_verification: InitResult,
        temp_dir: Path,
    ):
        """Test that custom verification commands are displayed."""
        mock_load_config.return_value = mock_config
        mock_initialize.return_value = mock_init_result_with_verification

        with runner.isolated_filesystem(temp_dir=str(temp_dir)):
            result = runner.invoke(cli, ["init"])

        assert result.exit_code == 0
        # Custom commands should be shown
        assert "e2e:" in result.output
        assert "uv run pytest tests/e2e/" in result.output

    @patch("gobby.cli.init.initialize_project")
    @patch("gobby.cli.load_config")
    def test_init_verification_skips_none_values(
        self,
        mock_load_config: MagicMock,
        mock_initialize: MagicMock,
        runner: CliRunner,
        mock_config: MagicMock,
        temp_dir: Path,
    ):
        """Test that None verification values are not displayed."""
        mock_load_config.return_value = mock_config

        # Create result with only some verification commands
        verification = VerificationCommands(
            unit_tests="pytest",
            type_check=None,  # Should be skipped
            lint=None,  # Should be skipped
            integration=None,  # Should be skipped
            custom={},
        )
        result_with_partial = InitResult(
            project_id="proj-partial",
            project_name="partial-project",
            project_path="/tmp/partial",
            created_at="2024-01-15T10:00:00Z",
            already_existed=False,
            verification=verification,
        )
        mock_initialize.return_value = result_with_partial

        with runner.isolated_filesystem(temp_dir=str(temp_dir)):
            result = runner.invoke(cli, ["init"])

        assert result.exit_code == 0
        assert "unit_tests:" in result.output
        # None values should not appear (they're skipped with continue)
        assert "type_check: None" not in result.output
        assert "lint: None" not in result.output
        assert "integration: None" not in result.output

    @patch("gobby.cli.init.initialize_project")
    @patch("gobby.cli.load_config")
    def test_init_no_verification_commands(
        self,
        mock_load_config: MagicMock,
        mock_initialize: MagicMock,
        runner: CliRunner,
        mock_config: MagicMock,
        mock_init_result_new: InitResult,
        temp_dir: Path,
    ):
        """Test initialization without any verification commands."""
        mock_load_config.return_value = mock_config
        mock_initialize.return_value = mock_init_result_new  # Has verification=None

        with runner.isolated_filesystem(temp_dir=str(temp_dir)):
            result = runner.invoke(cli, ["init"])

        assert result.exit_code == 0
        assert "Detected verification commands:" not in result.output

    @patch("gobby.cli.init.initialize_project")
    @patch("gobby.cli.load_config")
    def test_init_verification_empty_dict(
        self,
        mock_load_config: MagicMock,
        mock_initialize: MagicMock,
        runner: CliRunner,
        mock_config: MagicMock,
        temp_dir: Path,
    ):
        """Test that empty verification dict doesn't show section."""
        mock_load_config.return_value = mock_config

        # Create result with verification that has empty to_dict()
        verification = VerificationCommands()  # All None/empty
        result_with_empty = InitResult(
            project_id="proj-empty",
            project_name="empty-project",
            project_path="/tmp/empty",
            created_at="2024-01-15T10:00:00Z",
            already_existed=False,
            verification=verification,
        )
        mock_initialize.return_value = result_with_empty

        with runner.isolated_filesystem(temp_dir=str(temp_dir)):
            result = runner.invoke(cli, ["init"])

        assert result.exit_code == 0
        # Empty verification dict should not show section
        assert "Detected verification commands:" not in result.output

    @patch("gobby.cli.init.initialize_project")
    @patch("gobby.cli.load_config")
    def test_init_verification_custom_non_dict(
        self,
        mock_load_config: MagicMock,
        mock_initialize: MagicMock,
        runner: CliRunner,
        mock_config: MagicMock,
        temp_dir: Path,
    ):
        """Test handling of non-dict custom verification value."""
        mock_load_config.return_value = mock_config

        # Create mock result with non-dict custom value
        mock_verification = MagicMock()
        mock_verification.to_dict.return_value = {
            "unit_tests": "pytest",
            "custom": "some-string-value",  # Non-dict custom
        }

        result_with_custom = InitResult(
            project_id="proj-custom",
            project_name="custom-project",
            project_path="/tmp/custom",
            created_at="2024-01-15T10:00:00Z",
            already_existed=False,
            verification=mock_verification,
        )
        mock_initialize.return_value = result_with_custom

        with runner.isolated_filesystem(temp_dir=str(temp_dir)):
            result = runner.invoke(cli, ["init"])

        assert result.exit_code == 0
        assert "custom: some-string-value" in result.output


class TestInitErrorHandling:
    """Tests for error handling in the init command."""

    @patch("gobby.cli.init.initialize_project")
    @patch("gobby.cli.load_config")
    def test_init_generic_exception(
        self,
        mock_load_config: MagicMock,
        mock_initialize: MagicMock,
        runner: CliRunner,
        mock_config: MagicMock,
        temp_dir: Path,
    ):
        """Test handling of generic exception during initialization."""
        mock_load_config.return_value = mock_config
        mock_initialize.side_effect = Exception("Database connection failed")

        with runner.isolated_filesystem(temp_dir=str(temp_dir)):
            result = runner.invoke(cli, ["init"])

        assert result.exit_code == 1
        assert "Failed to initialize project" in result.output
        assert "Database connection failed" in result.output

    @patch("gobby.cli.init.initialize_project")
    @patch("gobby.cli.load_config")
    def test_init_permission_error(
        self,
        mock_load_config: MagicMock,
        mock_initialize: MagicMock,
        runner: CliRunner,
        mock_config: MagicMock,
        temp_dir: Path,
    ):
        """Test handling of permission error during initialization."""
        mock_load_config.return_value = mock_config
        mock_initialize.side_effect = PermissionError("Cannot write to directory")

        with runner.isolated_filesystem(temp_dir=str(temp_dir)):
            result = runner.invoke(cli, ["init"])

        assert result.exit_code == 1
        assert "Failed to initialize project" in result.output
        assert "Cannot write to directory" in result.output

    @patch("gobby.cli.init.initialize_project")
    @patch("gobby.cli.load_config")
    def test_init_file_not_found_error(
        self,
        mock_load_config: MagicMock,
        mock_initialize: MagicMock,
        runner: CliRunner,
        mock_config: MagicMock,
        temp_dir: Path,
    ):
        """Test handling of file not found error."""
        mock_load_config.return_value = mock_config
        mock_initialize.side_effect = FileNotFoundError("Config file not found")

        with runner.isolated_filesystem(temp_dir=str(temp_dir)):
            result = runner.invoke(cli, ["init"])

        assert result.exit_code == 1
        assert "Failed to initialize project" in result.output
        assert "Config file not found" in result.output

    @patch("gobby.cli.init.initialize_project")
    @patch("gobby.cli.load_config")
    def test_init_os_error(
        self,
        mock_load_config: MagicMock,
        mock_initialize: MagicMock,
        runner: CliRunner,
        mock_config: MagicMock,
        temp_dir: Path,
    ):
        """Test handling of OS error during initialization."""
        mock_load_config.return_value = mock_config
        mock_initialize.side_effect = OSError("Disk full")

        with runner.isolated_filesystem(temp_dir=str(temp_dir)):
            result = runner.invoke(cli, ["init"])

        assert result.exit_code == 1
        assert "Failed to initialize project" in result.output
        assert "Disk full" in result.output

    @patch("gobby.cli.init.initialize_project")
    @patch("gobby.cli.load_config")
    def test_init_value_error(
        self,
        mock_load_config: MagicMock,
        mock_initialize: MagicMock,
        runner: CliRunner,
        mock_config: MagicMock,
        temp_dir: Path,
    ):
        """Test handling of value error during initialization."""
        mock_load_config.return_value = mock_config
        mock_initialize.side_effect = ValueError("Invalid project name")

        with runner.isolated_filesystem(temp_dir=str(temp_dir)):
            result = runner.invoke(cli, ["init"])

        assert result.exit_code == 1
        assert "Failed to initialize project" in result.output
        assert "Invalid project name" in result.output


class TestInitOutputFormat:
    """Tests for the output format of the init command."""

    @patch("gobby.cli.init.initialize_project")
    @patch("gobby.cli.load_config")
    def test_init_output_format_new_project(
        self,
        mock_load_config: MagicMock,
        mock_initialize: MagicMock,
        runner: CliRunner,
        mock_config: MagicMock,
        temp_dir: Path,
    ):
        """Test the output format for a new project initialization."""
        mock_load_config.return_value = mock_config

        result_obj = InitResult(
            project_id="proj-format-test",
            project_name="format-test-project",
            project_path="/tmp/format-test",
            created_at="2024-01-15T10:00:00Z",
            already_existed=False,
            verification=None,
        )
        mock_initialize.return_value = result_obj

        with runner.isolated_filesystem(temp_dir=str(temp_dir)):
            result = runner.invoke(cli, ["init"])

        assert result.exit_code == 0
        # Check output structure
        output_lines = result.output.strip().split("\n")
        assert len(output_lines) >= 2
        # First line should have project name
        assert "format-test-project" in output_lines[0]
        # Second line should have project ID
        assert "Project ID:" in output_lines[1]
        assert "proj-format-test" in output_lines[1]
        # Third line should have config path
        assert "Config:" in output_lines[2]

    @patch("gobby.cli.init.initialize_project")
    @patch("gobby.cli.load_config")
    def test_init_output_format_existing_project(
        self,
        mock_load_config: MagicMock,
        mock_initialize: MagicMock,
        runner: CliRunner,
        mock_config: MagicMock,
        temp_dir: Path,
    ):
        """Test the output format for an existing project."""
        mock_load_config.return_value = mock_config

        result_obj = InitResult(
            project_id="proj-existing-format",
            project_name="existing-format-project",
            project_path="/tmp/existing-format",
            created_at="2024-01-01T00:00:00Z",
            already_existed=True,
            verification=None,
        )
        mock_initialize.return_value = result_obj

        with runner.isolated_filesystem(temp_dir=str(temp_dir)):
            result = runner.invoke(cli, ["init"])

        assert result.exit_code == 0
        output_lines = result.output.strip().split("\n")
        # First line should mention "already initialized"
        assert "already initialized" in output_lines[0].lower()
        # Should have project ID on second line
        assert "Project ID:" in output_lines[1]


class TestInitCwdHandling:
    """Tests for current working directory handling."""

    @patch("gobby.cli.init.initialize_project")
    @patch("gobby.cli.load_config")
    def test_init_uses_cwd(
        self,
        mock_load_config: MagicMock,
        mock_initialize: MagicMock,
        runner: CliRunner,
        mock_config: MagicMock,
        mock_init_result_new: InitResult,
        temp_dir: Path,
    ):
        """Test that init uses current working directory."""
        mock_load_config.return_value = mock_config
        mock_initialize.return_value = mock_init_result_new

        with runner.isolated_filesystem(temp_dir=str(temp_dir)):
            result = runner.invoke(cli, ["init"])

        assert result.exit_code == 0
        # Verify cwd was passed to initialize_project
        call_args = mock_initialize.call_args
        cwd_arg = call_args.kwargs.get("cwd") or call_args[1].get("cwd")
        assert cwd_arg is not None
        assert isinstance(cwd_arg, Path)


class TestVerificationCommandsDataclass:
    """Tests for VerificationCommands dataclass behavior in CLI context."""

    @patch("gobby.cli.init.initialize_project")
    @patch("gobby.cli.load_config")
    def test_verification_with_all_fields(
        self,
        mock_load_config: MagicMock,
        mock_initialize: MagicMock,
        runner: CliRunner,
        mock_config: MagicMock,
        temp_dir: Path,
    ):
        """Test verification with all fields populated."""
        mock_load_config.return_value = mock_config

        verification = VerificationCommands(
            unit_tests="pytest tests/",
            type_check="mypy src/",
            lint="ruff check .",
            integration="pytest tests/integration/",
            custom={"security": "bandit -r src/"},
        )
        result_obj = InitResult(
            project_id="proj-full",
            project_name="full-project",
            project_path="/tmp/full",
            created_at="2024-01-15T10:00:00Z",
            already_existed=False,
            verification=verification,
        )
        mock_initialize.return_value = result_obj

        with runner.isolated_filesystem(temp_dir=str(temp_dir)):
            result = runner.invoke(cli, ["init"])

        assert result.exit_code == 0
        assert "unit_tests:" in result.output
        assert "type_check:" in result.output
        assert "lint:" in result.output
        assert "integration:" in result.output
        assert "security:" in result.output

    @patch("gobby.cli.init.initialize_project")
    @patch("gobby.cli.load_config")
    def test_verification_with_multiple_custom_commands(
        self,
        mock_load_config: MagicMock,
        mock_initialize: MagicMock,
        runner: CliRunner,
        mock_config: MagicMock,
        temp_dir: Path,
    ):
        """Test verification with multiple custom commands."""
        mock_load_config.return_value = mock_config

        verification = VerificationCommands(
            unit_tests="pytest",
            custom={
                "security": "bandit -r src/",
                "coverage": "pytest --cov",
                "docs": "mkdocs build",
            },
        )
        result_obj = InitResult(
            project_id="proj-multi",
            project_name="multi-project",
            project_path="/tmp/multi",
            created_at="2024-01-15T10:00:00Z",
            already_existed=False,
            verification=verification,
        )
        mock_initialize.return_value = result_obj

        with runner.isolated_filesystem(temp_dir=str(temp_dir)):
            result = runner.invoke(cli, ["init"])

        assert result.exit_code == 0
        assert "security:" in result.output
        assert "bandit -r src/" in result.output
        assert "coverage:" in result.output
        assert "pytest --cov" in result.output
        assert "docs:" in result.output
        assert "mkdocs build" in result.output


class TestInitInvalidOptions:
    """Tests for invalid command options."""

    def test_init_unknown_option(self, runner: CliRunner):
        """Test that unknown options are rejected."""
        result = runner.invoke(cli, ["init", "--unknown-option", "value"])
        assert result.exit_code != 0
        assert "No such option" in result.output or "no such option" in result.output.lower()

    def test_init_name_without_value(self, runner: CliRunner):
        """Test that --name without value shows error."""
        result = runner.invoke(cli, ["init", "--name"])
        assert result.exit_code != 0

    def test_init_github_url_without_value(self, runner: CliRunner):
        """Test that --github-url without value shows error."""
        result = runner.invoke(cli, ["init", "--github-url"])
        assert result.exit_code != 0


class TestInitContext:
    """Tests for Click context handling."""

    @patch("gobby.cli.init.initialize_project")
    @patch("gobby.cli.load_config")
    def test_init_receives_context(
        self,
        mock_load_config: MagicMock,
        mock_initialize: MagicMock,
        runner: CliRunner,
        mock_config: MagicMock,
        mock_init_result_new: InitResult,
        temp_dir: Path,
    ):
        """Test that init command receives Click context."""
        mock_load_config.return_value = mock_config
        mock_initialize.return_value = mock_init_result_new

        with runner.isolated_filesystem(temp_dir=str(temp_dir)):
            # The @click.pass_context decorator ensures ctx is passed
            result = runner.invoke(cli, ["init"])

        assert result.exit_code == 0

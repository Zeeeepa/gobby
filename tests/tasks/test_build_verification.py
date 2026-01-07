"""Tests for build verification functionality.

Tests for:
1. run_build_check() executes configured command
2. detect_build_command() finds npm/pytest/cargo/go test
3. Build timeout is enforced (5 min default)
4. Build failures converted to structured Issue objects
5. Build check skipped when disabled
"""

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

from gobby.tasks.build_verification import (
    BuildResult,
    BuildVerifier,
    detect_build_command,
    run_build_check,
)
from gobby.tasks.validation_models import Issue, IssueSeverity, IssueType


class TestDetectBuildCommand:
    """Tests for detect_build_command() auto-detection."""

    def test_detects_npm_from_package_json(self, tmp_path):
        """Test detecting npm test from package.json."""
        (tmp_path / "package.json").write_text('{"name": "test"}')

        result = detect_build_command(tmp_path)

        assert result == "npm test"

    def test_detects_pytest_from_pyproject_toml(self, tmp_path):
        """Test detecting pytest from pyproject.toml."""
        (tmp_path / "pyproject.toml").write_text("[project]\nname = 'test'")

        result = detect_build_command(tmp_path)

        assert result == "uv run pytest"

    def test_detects_cargo_test_from_cargo_toml(self, tmp_path):
        """Test detecting cargo test from Cargo.toml."""
        (tmp_path / "Cargo.toml").write_text('[package]\nname = "test"')

        result = detect_build_command(tmp_path)

        assert result == "cargo test"

    def test_detects_go_test_from_go_mod(self, tmp_path):
        """Test detecting go test from go.mod."""
        (tmp_path / "go.mod").write_text("module test")

        result = detect_build_command(tmp_path)

        assert result == "go test ./..."

    def test_returns_none_when_no_project_files(self, tmp_path):
        """Test returning None when no recognized project files exist."""
        result = detect_build_command(tmp_path)

        assert result is None

    def test_prefers_package_json_over_others(self, tmp_path):
        """Test that package.json takes priority when multiple exist."""
        (tmp_path / "package.json").write_text('{"name": "test"}')
        (tmp_path / "pyproject.toml").write_text("[project]")

        result = detect_build_command(tmp_path)

        # package.json should be detected first
        assert result == "npm test"


class TestRunBuildCheck:
    """Tests for run_build_check() execution."""

    def test_runs_configured_command(self, tmp_path):
        """Test that run_build_check executes the configured command."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="All tests passed",
                stderr="",
            )

            result = run_build_check(
                command="npm test",
                cwd=tmp_path,
            )

            assert result.success is True
            mock_run.assert_called_once()
            call_kwargs = mock_run.call_args.kwargs
            assert call_kwargs["cwd"] == tmp_path
            assert "npm test" in mock_run.call_args.args[0]

    def test_returns_failure_on_nonzero_exit(self, tmp_path):
        """Test that non-zero exit code results in failure."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=1,
                stdout="",
                stderr="Test failed: assertion error",
            )

            result = run_build_check(
                command="npm test",
                cwd=tmp_path,
            )

            assert result.success is False
            assert "assertion error" in result.stderr

    def test_captures_stdout_and_stderr(self, tmp_path):
        """Test that stdout and stderr are captured."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="Test output here",
                stderr="Warning: deprecated function",
            )

            result = run_build_check(
                command="pytest",
                cwd=tmp_path,
            )

            assert result.stdout == "Test output here"
            assert result.stderr == "Warning: deprecated function"


class TestBuildTimeout:
    """Tests for build timeout enforcement."""

    def test_default_timeout_is_5_minutes(self, tmp_path):
        """Test that default timeout is 300 seconds (5 minutes)."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="",
                stderr="",
            )

            run_build_check(command="npm test", cwd=tmp_path)

            call_kwargs = mock_run.call_args.kwargs
            assert call_kwargs["timeout"] == 300

    def test_timeout_exceeded_returns_failure(self, tmp_path):
        """Test that timeout exceeded results in failure with error message."""
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired(
                cmd="npm test",
                timeout=300,
            )

            result = run_build_check(
                command="npm test",
                cwd=tmp_path,
            )

            assert result.success is False
            assert "timeout" in result.error.lower()

    def test_custom_timeout_is_respected(self, tmp_path):
        """Test that custom timeout value is passed to subprocess."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="",
                stderr="",
            )

            run_build_check(
                command="npm test",
                cwd=tmp_path,
                timeout=60,
            )

            call_kwargs = mock_run.call_args.kwargs
            assert call_kwargs["timeout"] == 60


class TestBuildResultToIssue:
    """Tests for converting build failures to Issue objects."""

    def test_failed_build_converts_to_issue(self):
        """Test that a failed build can be converted to an Issue."""
        result = BuildResult(
            success=False,
            command="npm test",
            stdout="",
            stderr="Error: test failed at src/index.ts:42",
            returncode=1,
        )

        issue = result.to_issue()

        assert isinstance(issue, Issue)
        assert issue.issue_type == IssueType.TEST_FAILURE
        assert issue.severity == IssueSeverity.BLOCKER
        assert "npm test" in issue.title or "build" in issue.title.lower()
        assert "test failed" in issue.details.lower()

    def test_timeout_converts_to_issue(self):
        """Test that a timeout failure converts to an Issue."""
        result = BuildResult(
            success=False,
            command="npm test",
            error="Build timeout after 300 seconds",
        )

        issue = result.to_issue()

        assert isinstance(issue, Issue)
        assert issue.severity == IssueSeverity.BLOCKER
        assert "timeout" in issue.title.lower() or "timeout" in issue.details.lower()

    def test_successful_build_to_issue_returns_none(self):
        """Test that successful build to_issue returns None."""
        result = BuildResult(
            success=True,
            command="npm test",
            stdout="All tests passed",
            returncode=0,
        )

        issue = result.to_issue()

        assert issue is None


class TestBuildVerifierSkipped:
    """Tests for build check skipping when disabled."""

    def test_skipped_when_disabled_in_config(self):
        """Test that build check is skipped when disabled in config."""
        verifier = BuildVerifier(
            enabled=False,
            build_command="npm test",
        )

        result = verifier.check(cwd=Path("/tmp"))

        assert result.skipped is True
        assert result.success is True

    def test_skipped_when_no_command_detected(self, tmp_path):
        """Test that build check is skipped when no command can be detected."""
        verifier = BuildVerifier(
            enabled=True,
            build_command=None,  # Auto-detect
        )

        # tmp_path has no project files
        result = verifier.check(cwd=tmp_path)

        assert result.skipped is True
        assert result.success is True

    def test_not_skipped_when_enabled_with_command(self, tmp_path):
        """Test that build check runs when enabled with explicit command."""
        verifier = BuildVerifier(
            enabled=True,
            build_command="echo test",
        )

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="test",
                stderr="",
            )

            result = verifier.check(cwd=tmp_path)

            assert result.skipped is False
            mock_run.assert_called_once()


class TestBuildVerifierIntegration:
    """Integration tests for BuildVerifier class."""

    def test_verifier_uses_auto_detected_command(self, tmp_path):
        """Test that verifier auto-detects command when not configured."""
        (tmp_path / "pyproject.toml").write_text("[project]")

        verifier = BuildVerifier(
            enabled=True,
            build_command=None,
        )

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="",
                stderr="",
            )

            result = verifier.check(cwd=tmp_path)

            # Should use auto-detected pytest command
            assert result.skipped is False
            call_args = mock_run.call_args.args[0]
            assert "pytest" in call_args

    def test_verifier_uses_configured_command_over_auto_detect(self, tmp_path):
        """Test that configured command takes priority over auto-detect."""
        (tmp_path / "package.json").write_text('{"name": "test"}')

        verifier = BuildVerifier(
            enabled=True,
            build_command="make test",  # Override
        )

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="",
                stderr="",
            )

            verifier.check(cwd=tmp_path)

            call_args = mock_run.call_args.args[0]
            assert "make test" in call_args

    def test_verifier_result_includes_command_used(self, tmp_path):
        """Test that result includes the command that was executed."""
        verifier = BuildVerifier(
            enabled=True,
            build_command="npm run test:ci",
        )

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="OK",
                stderr="",
            )

            result = verifier.check(cwd=tmp_path)

            assert result.command == "npm run test:ci"


class TestBuildResult:
    """Tests for BuildResult dataclass."""

    def test_build_result_success(self):
        """Test creating a successful BuildResult."""
        result = BuildResult(
            success=True,
            command="npm test",
            stdout="All 42 tests passed",
            stderr="",
            returncode=0,
        )

        assert result.success is True
        assert result.skipped is False
        assert result.error is None

    def test_build_result_failure(self):
        """Test creating a failed BuildResult."""
        result = BuildResult(
            success=False,
            command="npm test",
            stdout="",
            stderr="FAIL src/index.test.ts",
            returncode=1,
        )

        assert result.success is False
        assert result.returncode == 1

    def test_build_result_skipped(self):
        """Test creating a skipped BuildResult."""
        result = BuildResult(
            success=True,
            skipped=True,
        )

        assert result.success is True
        assert result.skipped is True

    def test_build_result_with_error(self):
        """Test creating a BuildResult with error message."""
        result = BuildResult(
            success=False,
            error="Command not found: npm",
        )

        assert result.success is False
        assert "Command not found" in result.error
